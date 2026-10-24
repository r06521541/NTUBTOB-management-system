"""Unused ledger schema tests; no deletion executor or proof authorization.

PostgreSQL cases require a dedicated disposable local database opt-in. Every
case rolls back its fixture transaction, including append-only evidence.
"""

import hashlib
import importlib.util
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from shared_lib.shared_module.portal_data.erasure_models import (
    AccountErasureJobRecord,
    AccountErasureStepRecord,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.models import PortalDataBase
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations/versions/0014_account_erasure_ledger.py"
NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)
DATABASE_URL = os.environ.get("ACCOUNT_ERASURE_LEDGER_TEST_DATABASE_URL")


def migration_module():
    spec = importlib.util.spec_from_file_location("erasure_ledger_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ErasureLedgerSchemaTests(unittest.TestCase):
    def setUp(self):
        self.migration = migration_module()
        with patch.object(self.migration.op, "execute") as execute:
            self.migration.upgrade()
        self.sql = "\n".join(str(call.args[0]) for call in execute.call_args_list)

    def test_models_share_base_and_store_no_payload_or_entity_generation_claim(self):
        for model in (AccountErasureJobRecord, AccountErasureStepRecord):
            self.assertIs(model.metadata, PortalDataBase.metadata)
            for column in model.__table__.columns:
                self.assertNotIn(type(column.type).__name__, ("JSON", "JSONB", "Text"))
        job = AccountErasureJobRecord.__table__
        self.assertIn("expected_generation", job.c)
        self.assertNotIn("generation_verified", job.c)
        self.assertIn("receipt_secret_hash", job.c)
        self.assertNotIn("receipt_secret", job.c)
        for field in (
            "fulfillment_due_at",
            "receipt_expires_at",
            "evidence_expires_at",
        ):
            self.assertFalse(job.c[field].nullable)
            self.assertIsNone(job.c[field].default)
            self.assertIsNone(job.c[field].server_default)

    def test_migration_is_additive_restricted_and_downgrade_retains_evidence(self):
        self.assertEqual(self.migration.down_revision, "0013_account_deletion_requests")
        for table in ("account_erasure_jobs", "account_erasure_steps"):
            self.assertIn(f"CREATE TABLE ntubtob.{table}", self.sql)
            self.assertIn(
                f"ALTER TABLE ntubtob.{table} ENABLE ROW LEVEL SECURITY", self.sql
            )
        self.assertNotRegex(self.sql.upper(), r"\b(GRANT|CREATE POLICY|DELETE FROM)\b")
        self.assertNotIn("ALTER TABLE ntubtob.account_deletion_requests", self.sql)
        self.assertNotRegex(self.sql, r"INTERVAL|interval|30 days|90 days")
        with patch.object(self.migration.op, "execute") as execute:
            self.migration.downgrade()
        execute.assert_not_called()

    def test_model_checks_and_indexes_are_present_in_migration(self):
        normalized = " ".join(self.sql.split())
        # Freeze the complete historical DDL, not merely the subset of old checks
        # still represented by today's models. Whitespace is immaterial here.
        self.assertEqual(
            hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "79cff93168aa0f84816b0913efb49520cde843e4608fd26a7ded005b5d836091",
        )
        # These named checks were replaced/added by 0016. Current models cannot
        # be used as the oracle for their historical 0014 definitions.
        evolved = {
            "ck_erasure_job_status",
            "ck_erasure_job_target",
            "ck_erasure_job_times",
            "ck_erasure_job_verified",
            "ck_erasure_job_cancelled",
            "ck_erasure_job_irreversible",
            "ck_erasure_step_stage",
        }
        for model in (AccountErasureJobRecord, AccountErasureStepRecord):
            for constraint in model.__table__.constraints:
                if (
                    isinstance(constraint, CheckConstraint)
                    and constraint.name not in evolved
                ):
                    self.assertIn(constraint.name, normalized)
                    self.assertIn(" ".join(str(constraint.sqltext).split()), normalized)
            for index in model.__table__.indexes:
                self.assertIn(index.name, normalized)
        for model in (AccountErasureJobRecord, AccountErasureStepRecord):
            for foreign_key in model.__table__.foreign_keys:
                self.assertEqual(foreign_key.ondelete, "RESTRICT")
        for historical in (
            "status IN ('requested', 'verified', 'processing', 'needs_attention', 'online_completed', 'completed')",
            "(status = 'requested' AND verified_at IS NULL) OR (status <> 'requested' AND verified_at IS NOT NULL)",
            "(status IN ('online_completed', 'completed') AND person_id IS NULL AND auth_identity_id IS NULL)",
            "(online_completed_at IS NULL OR online_completed_at >= verified_at)",
            "stage IN ('verification', 'access_block', 'provider_revocation', 'online_erasure', 'online_verification', 'restore_suppression', 'completion')",
        ):
            self.assertIn(historical, normalized)
        self.assertNotIn("cancelled_at", normalized)
        self.assertNotIn("irreversible_started_at", normalized)

    def test_target_and_step_evidence_have_database_mutation_guards(self):
        self.assertIn("BEFORE UPDATE ON ntubtob.account_erasure_jobs", self.sql)
        self.assertIn(
            "BEFORE DELETE OR TRUNCATE ON ntubtob.account_erasure_jobs", self.sql
        )
        self.assertIn(
            "BEFORE UPDATE OR DELETE OR TRUNCATE ON ntubtob.account_erasure_steps",
            self.sql,
        )
        self.assertIn(
            "NEW.expected_generation IS DISTINCT FROM OLD.expected_generation", self.sql
        )
        self.assertIn("NEW.person_id IS DISTINCT FROM OLD.person_id", self.sql)
        self.assertIn(
            "NEW.auth_identity_id IS DISTINCT FROM OLD.auth_identity_id", self.sql
        )
        self.assertNotIn("SECURITY DEFINER", self.sql.upper())

    def test_explicit_deadlines_are_finite_and_verified_policy_is_not_rewritten(self):
        self.assertIn("isfinite(evidence_expires_at)", self.sql)
        self.assertIn("isfinite(receipt_expires_at)", self.sql)
        self.assertIn("isfinite(fulfillment_due_at)", self.sql)
        self.assertIn("isfinite(occurred_at)", self.sql)
        self.assertIn(
            "NEW.retention_policy_version IS DISTINCT FROM OLD.retention_policy_version",
            self.sql,
        )


@unittest.skipUnless(
    DATABASE_URL, "dedicated isolated erasure-ledger URL not configured"
)
class ErasureMetadataPostgresTests(unittest.TestCase):
    """Current metadata is checked at current schema, not a historical fixture."""

    def test_fresh_process_migration_metadata_matches_ledger(self):
        engine = create_engine(require_local_database_url(DATABASE_URL))
        try:
            remove_retained_erasure_ledger_from_isolated_test_database(engine)
            with engine.begin() as connection:
                config = Config(str(ROOT / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "0024_erasure_provider_phases")
        finally:
            engine.dispose()
        environment = os.environ.copy()
        environment["PORTAL_DATA_DATABASE_URL"] = require_local_database_url(
            DATABASE_URL
        )
        try:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "check"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                timeout=30,
                check=False,
            )
        finally:
            # The fresh-process check creates no intake/recovery operations. Use the
            # real downgrade guard, never discard any unexpected history.
            cleanup_engine = create_engine(require_local_database_url(DATABASE_URL))
            try:
                with cleanup_engine.begin() as connection:
                    config = Config(str(ROOT / "alembic.ini"))
                    config.attributes["connection"] = connection
                    command.downgrade(config, "0018_erasure_privacy_mutation")
            finally:
                cleanup_engine.dispose()
        self.assertEqual(result.returncode, 0, "fresh-process migration metadata drift")


@unittest.skipUnless(
    DATABASE_URL, "dedicated isolated erasure-ledger URL not configured"
)
class ErasureLedgerPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))
        remove_retained_erasure_ledger_from_isolated_test_database(cls.engine)
        with cls.engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0014_account_erasure_ledger")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.person = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.people (display_name,portal_access_level,portal_status,version,created_at,updated_at) VALUES ('Fictional ledger person','basic','active',1,:now,:now) RETURNING id"
            ),
            {"now": NOW},
        )
        self.identity = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.auth_identities (provider,provider_subject,status,created_at,updated_at) VALUES ('apple',:subject,'pending',:now,:now) RETURNING id"
            ),
            {"subject": "fictional-ledger-" + str(uuid4()), "now": NOW},
        )
        self.other_person = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.people (display_name,portal_access_level,portal_status,version,created_at,updated_at) VALUES ('Other fictional ledger person','basic','active',1,:now,:now) RETURNING id"
            ),
            {"now": NOW},
        )
        self.other_identity = self.connection.scalar(
            text(
                "INSERT INTO ntubtob.auth_identities (provider,provider_subject,status,created_at,updated_at) VALUES ('apple',:subject,'pending',:now,:now) RETURNING id"
            ),
            {"subject": "fictional-ledger-other-" + str(uuid4()), "now": NOW},
        )

    def tearDown(self):
        self.transaction.rollback()
        self.connection.close()

    def job(self, **changes):
        values = {
            "id": str(uuid4()),
            "target_kind": "person",
            "person_id": self.person,
            "auth_identity_id": None,
            "expected_generation": str(uuid4()),
            "status": "requested",
            "scope_version": 1,
            "scope_hash": "a" * 64,
            "receipt_secret_hash": uuid4().hex * 2,
            "retention_policy_version": 1,
            "requested_at": NOW,
            "updated_at": NOW,
            "fulfillment_due_at": NOW + timedelta(hours=2),
            "receipt_expires_at": NOW + timedelta(hours=3),
            "evidence_expires_at": NOW + timedelta(hours=4),
        }
        values.update(changes)
        columns = ",".join(values)
        params = ",".join(":" + key for key in values)
        self.connection.execute(
            text(
                f"INSERT INTO ntubtob.account_erasure_jobs ({columns}) VALUES ({params})"
            ),
            values,
        )
        return values["id"]

    def step(self, job_id, **changes):
        values = dict(
            job_id=job_id,
            stage="verification",
            attempt=1,
            event_sequence=1,
            event_kind="planned",
            result_code="scheduled",
            occurred_at=NOW,
        )
        values.update(changes)
        columns = ",".join(values)
        params = ",".join(":" + key for key in values)
        self.connection.execute(
            text(
                f"INSERT INTO ntubtob.account_erasure_steps ({columns}) VALUES ({params})"
            ),
            values,
        )

    def rejected(self, operation):
        with self.assertRaises(DBAPIError):
            with self.connection.begin_nested():
                operation()

    def update(self, job_id, **changes):
        assignments = ",".join(f"{key}=:{key}" for key in changes)
        self.connection.execute(
            text(f"UPDATE ntubtob.account_erasure_jobs SET {assignments} WHERE id=:id"),
            dict(changes, id=job_id),
        )

    def advance_online(self, job_id):
        self.update(job_id, status="verified", verified_at=NOW)
        self.update(job_id, status="processing")
        self.update(job_id, status="online_completed", online_completed_at=NOW)

    def test_person_and_pending_identity_receipts_are_separate_no_person_created(self):
        job = self.job()
        pending = self.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.identity,
        )
        self.assertNotEqual(job, pending)
        self.assertIsNone(
            self.connection.scalar(
                text("SELECT person_id FROM ntubtob.auth_identities WHERE id=:id"),
                {"id": self.identity},
            )
        )
        self.advance_online(job)
        self.update(job, person_id=None)
        self.advance_online(pending)
        self.update(pending, auth_identity_id=None)
        for changes in (
            {"auth_identity_id": self.identity},
            {"person_id": None},
            {"target_kind": "apple"},
            {"status": "completed"},
            {"receipt_secret_hash": "raw-secret"},
            {"scope_hash": "A" * 64},
            {"evidence_expires_at": NOW},
            {
                "fulfillment_due_at": "infinity",
                "receipt_expires_at": "infinity",
                "evidence_expires_at": "infinity",
            },
        ):
            with self.subTest(changes=tuple(changes)):
                self.rejected(lambda changes=changes: self.job(**changes))

    def test_duplicate_bound_target_rejected_until_completed_target_detaches(self):
        first = self.job()
        self.rejected(self.job)
        self.advance_online(first)
        self.rejected(self.job)
        self.update(first, person_id=None)
        self.job()
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": first},
            ),
            "online_completed",
        )
        pending = self.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.identity,
        )
        self.rejected(
            lambda: self.job(
                target_kind="pending_identity",
                person_id=None,
                auth_identity_id=self.identity,
            )
        )
        self.rejected(lambda: self.update(pending, auth_identity_id=None))

    def test_target_identity_generation_and_receipt_cannot_be_rewritten(self):
        job = self.job()
        for changes in (
            {"person_id": None},
            {"person_id": self.other_person},
            {"expected_generation": str(uuid4())},
            {"receipt_secret_hash": "b" * 64},
            {
                "target_kind": "pending_identity",
                "person_id": None,
                "auth_identity_id": self.identity,
            },
        ):
            self.rejected(lambda changes=changes: self.update(job, **changes))
        self.rejected(
            lambda: self.connection.execute(
                text("DELETE FROM ntubtob.people WHERE id=:id"), {"id": self.person}
            )
        )
        pending = self.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.identity,
        )
        self.rejected(
            lambda: self.connection.execute(
                text("DELETE FROM ntubtob.auth_identities WHERE id=:id"),
                {"id": self.identity},
            )
        )
        self.rejected(lambda: self.update(pending, expected_generation=str(uuid4())))
        self.rejected(
            lambda: self.update(pending, auth_identity_id=self.other_identity)
        )

    def test_detach_only_after_online_completion_and_never_reattach(self):
        job = self.job()
        self.advance_online(job)
        self.update(job, person_id=None)
        self.rejected(lambda: self.update(job, person_id=self.person))
        self.update(job, status="completed", completed_at=NOW)
        self.rejected(lambda: self.update(job, status="processing"))

    def test_invalid_state_progression_and_scope_changes_after_verification_rejected(
        self,
    ):
        job = self.job()
        self.rejected(lambda: self.update(job, status="processing"))
        self.rejected(lambda: self.update(job, status="verified"))
        self.update(job, status="verified", verified_at=NOW)
        for changes in (
            {"scope_hash": "b" * 64},
            {"scope_version": 2},
            {"retention_policy_version": 2},
            {"fulfillment_due_at": NOW + timedelta(hours=1)},
            {"receipt_expires_at": NOW + timedelta(hours=2)},
            {"evidence_expires_at": NOW + timedelta(hours=5)},
            {"verified_at": NOW + timedelta(seconds=1)},
        ):
            self.rejected(lambda changes=changes: self.update(job, **changes))
        self.update(job, status="processing")
        self.update(job, status="needs_attention")
        self.rejected(lambda: self.update(job, status="cancelled"))
        self.update(job, status="processing")

    def test_steps_are_append_only_bounded_and_have_unique_event_identity(self):
        job = self.job()
        self.step(job)
        self.rejected(lambda: self.step(job))
        for changes in (
            {"stage": "unknown_stage"},
            {"result_code": "private_error"},
            {"attempt": 0},
            {"event_sequence": 0},
            {"event_kind": "confirmed"},
            {"occurred_at": "infinity"},
        ):
            self.rejected(
                lambda changes=changes: (
                    self.step(job, event_sequence=2, **changes)
                    if "event_sequence" not in changes
                    else self.step(job, **changes)
                )
            )
        self.step(
            job, event_sequence=2, event_kind="started", result_code="in_progress"
        )
        self.step(
            job, event_sequence=3, event_kind="unknown", result_code="response_unknown"
        )
        for statement in (
            "UPDATE ntubtob.account_erasure_steps SET result_code='in_progress'",
            "DELETE FROM ntubtob.account_erasure_steps",
            "TRUNCATE ntubtob.account_erasure_steps",
            "DELETE FROM ntubtob.account_erasure_jobs",
            "TRUNCATE ntubtob.account_erasure_jobs CASCADE",
        ):
            self.rejected(
                lambda statement=statement: self.connection.execute(text(statement))
            )

    def test_foreign_job_step_rejected_and_rls_enabled_without_policies(self):
        self.rejected(lambda: self.step(str(uuid4())))
        for table in ("account_erasure_jobs", "account_erasure_steps"):
            self.assertTrue(
                self.connection.scalar(
                    text(
                        "SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:name AS regclass)"
                    ),
                    {"name": "ntubtob." + table},
                )
            )
            self.assertEqual(
                self.connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_policies WHERE schemaname='ntubtob' AND tablename=:name"
                    ),
                    {"name": table},
                ),
                0,
            )

    def test_downgrade_retains_jobs_steps_and_does_not_touch_original_intent(self):
        job = self.job()
        self.step(job)
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_deletion_requests (id,person_id,status,requested_at) VALUES (:id,:person,'requested',:now)"
            ),
            {"id": job, "person": self.person, "now": NOW},
        )
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.downgrade(config, "0013_account_deletion_requests")
        for table in (
            "account_erasure_jobs",
            "account_erasure_steps",
            "account_deletion_requests",
        ):
            self.assertTrue(inspect(self.connection).has_table(table, schema="ntubtob"))
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                ),
                {"id": job},
            ),
            1,
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_deletion_requests WHERE id=:id"
                ),
                {"id": job},
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
