"""Cancellation schema evidence, not a cancellation authority or executor.

Real database cases require an explicit disposable local opt-in. Each case's
0016 DDL and fictional data roll back to the 0015 fixture; no live URL is used.
"""

import importlib.util
import os
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, create_engine, text

from shared_lib.shared_module.portal_data.erasure_models import (
    AccountErasureJobRecord,
    AccountErasureStepRecord,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tests.portal_data import test_erasure_ledger as ledger_fixture
from tests.portal_data._erasure_ledger_test_harness import (
    remove_retained_erasure_ledger_from_isolated_test_database,
)

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.environ.get("ACCOUNT_ERASURE_LEDGER_TEST_DATABASE_URL")
NOW = ledger_fixture.NOW
LATER = NOW + timedelta(minutes=1)
AFTER = NOW + timedelta(minutes=2)
REPLACED_CHECKS = {
    "ck_erasure_job_status",
    "ck_erasure_job_target",
    "ck_erasure_job_times",
    "ck_erasure_job_verified",
    "ck_erasure_job_cancelled",
    "ck_erasure_job_irreversible",
    "ck_erasure_step_stage",
}


def migration():
    spec = importlib.util.spec_from_file_location(
        "erasure_cancellation",
        ROOT / "migrations/versions/0016_erasure_cancellation.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ErasureCancellationSchemaTests(unittest.TestCase):
    def sql(self):
        module = migration()
        with patch.object(module.op, "execute") as execute:
            module.upgrade()
        return "\n".join(str(call.args[0]) for call in execute.call_args_list)

    def test_model_has_nullable_explicit_times_and_cancellation_stage(self):
        table = AccountErasureJobRecord.__table__
        for name in ("cancelled_at", "irreversible_started_at"):
            self.assertIn(name, table.c)
            column = table.c[name]
            self.assertTrue(column.nullable)
            self.assertTrue(column.type.timezone)
            self.assertIsNone(column.default)
            self.assertIsNone(column.server_default)
        checks = {
            constraint.name: str(constraint.sqltext)
            for model in (AccountErasureJobRecord, AccountErasureStepRecord)
            for constraint in model.__table__.constraints
            if isinstance(constraint, CheckConstraint)
        }
        self.assertTrue(REPLACED_CHECKS <= checks.keys())
        self.assertIn("'cancelled'", checks["ck_erasure_job_status"])
        self.assertIn("'cancellation'", checks["ck_erasure_step_stage"])

    def test_incremental_migration_and_exact_model_replacement_checks(self):
        self.assertEqual(migration().revision, "0016_erasure_cancellation")
        self.assertEqual(migration().down_revision, "0015_account_generations")
        sql = " ".join(self.sql().split())
        for model in (AccountErasureJobRecord, AccountErasureStepRecord):
            for constraint in model.__table__.constraints:
                if constraint.name in REPLACED_CHECKS:
                    self.assertIn(constraint.name, sql)
                    self.assertIn(" ".join(str(constraint.sqltext).split()), sql)
        for name in ("cancelled_at", "irreversible_started_at"):
            self.assertIn(f"ADD COLUMN {name} timestamptz", sql)

    def test_preflight_is_locked_unfiltered_and_rejects_legacy_dispatch(self):
        sql = self.sql()
        lock = sql.index("LOCK TABLE ntubtob.account_erasure_jobs")
        check = sql.index("status <> 'requested'")
        alter = sql.index("ADD COLUMN cancelled_at")
        self.assertLess(lock, check)
        self.assertLess(check, alter)
        self.assertIn("ntubtob.account_erasure_steps IN ACCESS EXCLUSIVE MODE", sql)
        for table in ("account_erasure_jobs", "account_erasure_steps"):
            self.assertIn(
                f"pg_catalog.row_security_active('ntubtob.{table}'::regclass)", sql
            )
        for stage in (
            "provider_revocation",
            "online_erasure",
            "online_verification",
            "restore_suppression",
            "completion",
        ):
            self.assertIn(f"'{stage}'", sql[:alter])
        self.assertIn("event_kind <> 'planned'", sql[:alter])
        self.assertIn(
            "pg_catalog.current_setting('transaction_isolation')", sql[:alter]
        )
        self.assertIn("'read committed'", sql[:alter])

    def test_mutation_fixture_does_not_overwrite_the_changed_id(self):
        fixture = ErasureCancellationPostgresTests()
        fixture.connection = Mock()
        fixture.update("old-id", id="new-id")
        statement, parameters = fixture.connection.execute.call_args.args
        self.assertIn("WHERE id=:_job_id", str(statement))
        self.assertEqual(parameters, {"id": "new-id", "_job_id": "old-id"})

    def test_guards_preserve_binding_metadata_and_all_terminal_times(self):
        sql = self.sql()
        for name in (
            "id",
            "target_kind",
            "expected_generation",
            "receipt_secret_hash",
            "requested_at",
            "scope_version",
            "scope_hash",
            "retention_policy_version",
            "fulfillment_due_at",
            "receipt_expires_at",
            "evidence_expires_at",
            "verified_at",
            "online_completed_at",
            "completed_at",
            "irreversible_started_at",
        ):
            self.assertIn(f"NEW.{name} IS DISTINCT FROM OLD.{name}", sql)
        self.assertIn("OLD.status = 'cancelled'", sql)
        self.assertIn("NEW IS DISTINCT FROM OLD", sql)
        self.assertIn("OLD.irreversible_started_at IS NOT NULL", sql)
        self.assertIn("NEW.status = 'cancelled'", sql)

    def test_no_authority_or_retention_defaults_and_downgrade_retains_guards(self):
        sql = self.sql()
        self.assertNotRegex(
            sql.upper().replace(
                "BEFORE UPDATE OR DELETE OR TRUNCATE ON", "BEFORE MUTATION ON"
            ),
            r"\b(GRANT|CREATE POLICY|DELETE FROM|TRUNCATE|DROP TABLE|DROP COLUMN|SECURITY DEFINER)\b",
        )
        self.assertNotIn("DISABLE ROW LEVEL SECURITY", sql.upper())
        self.assertNotRegex(sql, r"INTERVAL|interval|30 days|90 days")
        self.assertNotIn("ALTER TABLE ntubtob.account_deletion_requests", sql)
        self.assertIn("CREATE OR REPLACE FUNCTION ntubtob.guard_erasure_job()", sql)
        module = migration()
        with patch.object(module.op, "execute") as execute:
            module.downgrade()
        execute.assert_not_called()


@unittest.skipUnless(
    DATABASE_URL, "dedicated isolated erasure-ledger URL not configured"
)
class ErasureCancellationPostgresTests(unittest.TestCase):
    job = ledger_fixture.ErasureLedgerPostgresTests.job
    step = ledger_fixture.ErasureLedgerPostgresTests.step
    rejected = ledger_fixture.ErasureLedgerPostgresTests.rejected

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))
        try:
            remove_retained_erasure_ledger_from_isolated_test_database(cls.engine)
            with cls.engine.begin() as connection:
                config = Config(str(ROOT / "alembic.ini"))
                config.attributes["connection"] = connection
                command.upgrade(config, "0015_account_generations")
        except BaseException:
            cls.engine.dispose()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        ledger_fixture.ErasureLedgerPostgresTests.setUp(self)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.transaction.rollback)

    def upgrade(self):
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.upgrade(config, "0016_erasure_cancellation")

    def row(self, job):
        return dict(
            self.connection.execute(
                text("SELECT * FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": job},
            )
            .mappings()
            .one()
        )

    def update(self, job_id, **changes):
        assignments = ",".join(f"{key}=:{key}" for key in changes)
        self.connection.execute(
            text(
                f"UPDATE ntubtob.account_erasure_jobs SET {assignments} WHERE id=:_job_id"
            ),
            dict(changes, _job_id=job_id),
        )

    def verify(self, job):
        self.update(job, status="verified", verified_at=LATER, updated_at=LATER)

    def cancel(self, job, **changes):
        values = dict(
            status="cancelled",
            person_id=None,
            auth_identity_id=None,
            cancelled_at=AFTER,
            updated_at=AFTER,
        )
        values.update(changes)
        self.update(job, **values)

    def test_upgrade_preserves_clean_requested_jobs_and_evidence(self):
        job = self.job()
        self.step(job, event_kind="failed", result_code="verification_failed")
        before = self.row(job)
        self.upgrade()
        after = self.row(job)
        self.assertEqual(before, {key: after[key] for key in before})
        self.assertIsNone(after["cancelled_at"])
        self.assertIsNone(after["irreversible_started_at"])
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                ),
                {"id": job},
            ),
            1,
        )

    def test_upgrade_rejects_every_nonrequested_legacy_state_without_backfill(self):
        for status in (
            "verified",
            "processing",
            "needs_attention",
            "online_completed",
            "completed",
        ):
            with self.subTest(status=status), self.connection.begin_nested() as case:
                job = self.job()
                self.verify(job)
                if status != "verified":
                    self.update(job, status="processing")
                if status == "needs_attention":
                    self.update(job, status="needs_attention")
                elif status in {"online_completed", "completed"}:
                    self.update(
                        job,
                        status="online_completed",
                        online_completed_at=AFTER,
                        updated_at=AFTER,
                    )
                    if status == "completed":
                        self.update(job, status="completed", completed_at=AFTER)
                before = self.row(job)
                self.rejected(self.upgrade)
                self.assertEqual(before, self.row(job))
                self.assertIsNone(
                    self.connection.scalar(
                        text(
                            "SELECT attname FROM pg_catalog.pg_attribute "
                            "WHERE attrelid='ntubtob.account_erasure_jobs'::regclass "
                            "AND attname='cancelled_at' AND NOT attisdropped"
                        )
                    )
                )
                case.rollback()

    def test_upgrade_rejects_requested_with_possible_irreversible_evidence(self):
        for stage in (
            "provider_revocation",
            "online_erasure",
            "online_verification",
            "restore_suppression",
            "completion",
        ):
            for kind, result in (
                ("started", "in_progress"),
                ("unknown", "response_unknown"),
                ("confirmed", "succeeded"),
                ("failed", "dependency_unavailable"),
            ):
                with (
                    self.subTest(stage=stage, kind=kind),
                    self.connection.begin_nested() as case,
                ):
                    job = self.job()
                    self.step(job, stage=stage, event_kind=kind, result_code=result)
                    self.rejected(self.upgrade)
                    self.assertEqual(self.row(job)["status"], "requested")
                    case.rollback()

    def test_requested_cancellation_preserves_unverified_state_and_frees_target(self):
        self.upgrade()
        for target in ("person", "pending_identity"):
            with self.subTest(target=target):
                values = (
                    {}
                    if target == "person"
                    else dict(
                        target_kind=target,
                        person_id=None,
                        auth_identity_id=self.identity,
                    )
                )
                job = self.job(**values)
                before = self.row(job)
                self.cancel(job)
                after = self.row(job)
                self.assertIsNone(after["verified_at"])
                self.assertIsNone(after["person_id"])
                self.assertIsNone(after["auth_identity_id"])
                self.assertIsNone(after["irreversible_started_at"])
                for key in before.keys() - {
                    "status",
                    "person_id",
                    "auth_identity_id",
                    "cancelled_at",
                    "updated_at",
                }:
                    self.assertEqual(before[key], after[key], key)
                self.assertNotEqual(job, self.job(**values))

    def test_each_precursor_may_cancel_only_before_fence(self):
        self.upgrade()
        for status in ("verified", "processing", "needs_attention"):
            with self.subTest(status=status):
                job = self.job()
                self.verify(job)
                if status != "verified":
                    self.update(job, status=status)
                self.cancel(job)
                self.assertEqual(self.row(job)["verified_at"], LATER)

    def test_cancel_requires_detachment_and_preserves_verified_timestamp(self):
        self.upgrade()
        job = self.job()
        self.rejected(lambda: self.cancel(job, person_id=self.person))
        self.rejected(lambda: self.cancel(job, verified_at=LATER))
        self.verify(job)
        self.rejected(lambda: self.cancel(job, verified_at=None))
        self.rejected(lambda: self.cancel(job, verified_at=AFTER))
        self.cancel(job)

    def test_cancellation_cannot_rewrite_binding_scope_policy_or_deadlines(self):
        self.upgrade()
        job = self.job()
        changes = dict(
            id=str(uuid4()),
            target_kind="pending_identity",
            expected_generation=str(uuid4()),
            receipt_secret_hash="b" * 64,
            requested_at=NOW - timedelta(seconds=1),
            scope_version=2,
            scope_hash="b" * 64,
            retention_policy_version=2,
            fulfillment_due_at=NOW + timedelta(hours=3),
            receipt_expires_at=NOW + timedelta(hours=4),
            evidence_expires_at=NOW + timedelta(hours=5),
        )
        for field, value in changes.items():
            with self.subTest(field=field):
                self.rejected(lambda: self.cancel(job, **{field: value}))
        self.cancel(job)

    def test_cancelled_is_immutable_and_cannot_reattach_or_reopen(self):
        self.upgrade()
        job = self.job()
        self.cancel(job)
        for changes in (
            dict(status="requested", cancelled_at=None, person_id=self.person),
            dict(
                status="verified",
                cancelled_at=None,
                verified_at=LATER,
                person_id=self.person,
            ),
            dict(person_id=self.person),
            dict(auth_identity_id=self.identity),
            dict(cancelled_at=LATER),
            dict(updated_at=AFTER + timedelta(seconds=1)),
            dict(verified_at=LATER),
            dict(irreversible_started_at=LATER),
            dict(scope_hash="b" * 64),
            dict(receipt_expires_at=NOW + timedelta(hours=4)),
        ):
            with self.subTest(changes=tuple(changes)):
                self.rejected(lambda: self.update(job, **changes))
        self.update(job, status="cancelled")  # Identical writes do not reopen it.

    def test_fence_cannot_be_set_on_requested_or_rewritten_or_cleared(self):
        self.upgrade()
        job = self.job()
        self.rejected(
            lambda: self.update(job, irreversible_started_at=LATER, updated_at=LATER)
        )
        self.verify(job)
        self.update(job, irreversible_started_at=LATER)
        for value in (None, AFTER):
            self.rejected(
                lambda: self.update(
                    job, irreversible_started_at=value, updated_at=AFTER
                )
            )
        self.rejected(lambda: self.cancel(job))
        self.rejected(lambda: self.cancel(job, irreversible_started_at=None))
        self.update(job, status="processing", updated_at=AFTER)
        self.rejected(lambda: self.cancel(job))
        self.update(job, status="needs_attention")
        self.rejected(lambda: self.cancel(job))

    def test_completion_needs_fence_and_cannot_cancel_after_online_completion(self):
        self.upgrade()
        job = self.job()
        self.verify(job)
        self.update(job, status="processing")
        self.rejected(
            lambda: self.update(
                job,
                status="online_completed",
                online_completed_at=AFTER,
                updated_at=AFTER,
            )
        )
        self.update(job, irreversible_started_at=LATER)
        self.update(
            job,
            status="online_completed",
            online_completed_at=AFTER,
            updated_at=AFTER,
            person_id=None,
        )
        self.rejected(lambda: self.cancel(job))
        self.update(job, status="completed", completed_at=AFTER)
        self.rejected(lambda: self.cancel(job))

    def test_cancel_and_fence_times_must_be_finite_ordered_and_not_future_updates(self):
        self.upgrade()
        job = self.job()
        for value in (
            None,
            "infinity",
            "-infinity",
            NOW - timedelta(seconds=1),
            AFTER + timedelta(seconds=1),
        ):
            with self.subTest(cancelled_at=value):
                self.rejected(lambda: self.cancel(job, cancelled_at=value))
        self.rejected(lambda: self.update(job, cancelled_at=NOW))
        self.verify(job)
        self.rejected(lambda: self.cancel(job, cancelled_at=NOW))
        for value in ("infinity", "-infinity", NOW, AFTER):
            with self.subTest(irreversible_started_at=value):
                self.rejected(lambda: self.update(job, irreversible_started_at=value))
        self.cancel(job)

    def test_metadata_freezes_on_verification_and_illegal_transitions_reject(self):
        self.upgrade()
        job = self.job()
        self.update(job, scope_version=2)  # Requested metadata remains configurable.
        self.rejected(
            lambda: self.update(
                job,
                status="verified",
                verified_at=LATER,
                updated_at=LATER,
                scope_version=3,
            )
        )
        self.rejected(
            lambda: self.update(
                job, status="processing", verified_at=LATER, updated_at=LATER
            )
        )
        self.rejected(lambda: self.update(job, person_id=None))
        self.rejected(lambda: self.update(job, person_id=self.other_person))
        self.verify(job)
        self.rejected(lambda: self.update(job, status="requested", verified_at=None))
        self.rejected(lambda: self.update(job, status="completed", completed_at=AFTER))

    def test_cancellation_step_is_fixed_append_only_evidence_after_detachment(self):
        self.upgrade()
        job = self.job()
        self.cancel(job)
        self.step(
            job,
            stage="cancellation",
            event_kind="confirmed",
            result_code="succeeded",
            occurred_at=AFTER,
        )
        for sql in (
            "UPDATE ntubtob.account_erasure_steps SET result_code='not_applicable' WHERE job_id=:id",
            "DELETE FROM ntubtob.account_erasure_steps WHERE job_id=:id",
            "DELETE FROM ntubtob.account_erasure_jobs WHERE id=:id",
        ):
            self.rejected(lambda: self.connection.execute(text(sql), {"id": job}))
        self.rejected(
            lambda: self.step(
                job,
                stage="cancellation",
                event_kind="confirmed",
                result_code="arbitrary_message",
            )
        )

    def test_insert_cannot_skip_requested_or_start_with_fence(self):
        self.upgrade()
        self.rejected(
            lambda: self.job(status="cancelled", person_id=None, cancelled_at=NOW)
        )
        self.rejected(lambda: self.job(status="verified", verified_at=NOW))
        self.rejected(lambda: self.job(irreversible_started_at=NOW))

    def test_downgrade_retains_terminal_and_fence_guards_and_rls(self):
        self.upgrade()
        job = self.job()
        self.cancel(job)
        config = Config(str(ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.downgrade(config, "0015_account_generations")
        self.assertEqual(self.row(job)["status"], "cancelled")
        self.rejected(lambda: self.update(job, person_id=self.person))
        other = self.job()
        self.verify(other)
        self.update(other, irreversible_started_at=LATER)
        self.rejected(lambda: self.cancel(other))
        rows = (
            self.connection.execute(
                text(
                    "SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid IN ('ntubtob.account_erasure_jobs'::regclass,'ntubtob.account_erasure_steps'::regclass)"
                )
            )
            .scalars()
            .all()
        )
        self.assertEqual(rows, [True, True])
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM pg_catalog.pg_policy WHERE polrelid IN ('ntubtob.account_erasure_jobs'::regclass,'ntubtob.account_erasure_steps'::regclass)"
                )
            ),
            0,
        )
        # A retaining downgrade is not an old-runtime compatibility certificate.
        self.rejected(self.upgrade)


if __name__ == "__main__":
    unittest.main()
