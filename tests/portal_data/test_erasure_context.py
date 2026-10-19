"""Fictional receipt-bound context lookup; no real provider or database by default."""

import hashlib
import unittest
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_mock_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data import erasure_context
from shared_lib.shared_module.portal_data.erasure_context import (
    ErasureContextRejected,
    ErasureContextUnavailable,
    ErasureVerificationContext,
    load_erasure_verification_context,
)
from shared_lib.shared_module.portal_data.erasure_models import AccountErasureJobRecord
from shared_lib.shared_module.portal_data.models import AuthIdentityRecord, PersonRecord
from shared_lib.shared_module.portal_data.runtime import (
    ADMIN_LOCK_KEY,
    EVENT_SNAPSHOT_LOCK_KEY,
)
from tests.portal_data import test_erasure_ledger as ledger_fixture

NOW = datetime(2035, 1, 1, 0, 1, tzinfo=timezone.utc)
JOB = "11111111-1111-4111-8111-111111111111"
PERSON_GENERATION = "22222222-2222-4222-8222-222222222222"
IDENTITY_GENERATION = "33333333-3333-4333-8333-333333333333"
SECRET = "fictional-only-receipt-secret-" + "a" * 20
SECRET_HASH = hashlib.sha256(SECRET.encode("ascii")).hexdigest()


class ErasureContextTests(unittest.TestCase):
    def test_pending_receipt_selects_only_its_server_bound_identity(self):
        self.job.update(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=11,
            expected_generation=IDENTITY_GENERATION,
        )
        self.identity.update(person_id=None, status="pending")
        result = self.load(identity_id=None)
        self.assertEqual(result.identity_id, 11)
        self.assertIsNone(result.person_id)
        self.assertEqual(result.target_generation, IDENTITY_GENERATION)

    def test_receipt_only_selector_rejects_person_job_before_identity_lookup(self):
        with self.assertRaisesRegex(
            ErasureContextRejected, "context_scope_unavailable"
        ):
            self.load(identity_id=None)
        self.assertFalse(
            any(
                "FROM ntubtob.auth_identities" in str(call.args[0])
                for call in self.connection.execute.call_args_list
            )
        )

    def setUp(self):
        self.session = MagicMock()
        self.session.in_transaction.return_value = True
        self.session.new = self.session.dirty = self.session.deleted = set()
        self.connection = self.session.connection.return_value
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.scalars.return_value.all.return_value = [
            "0015_account_generations"
        ]
        self.connection.scalar.return_value = False
        self.connection.execute.side_effect = self.execute
        self.job = dict(
            id=JOB,
            status="requested",
            target_kind="person",
            person_id=7,
            auth_identity_id=None,
            expected_generation=PERSON_GENERATION,
            receipt_secret_hash=SECRET_HASH,
            receipt_expires_at=NOW + timedelta(minutes=1),
            requested_at=NOW - timedelta(minutes=1),
        )
        self.identity = dict(
            id=11,
            provider="line",
            provider_subject="fictional-private-subject",
            person_id=7,
            status="linked",
            account_generation=IDENTITY_GENERATION,
        )
        self.person = dict(id=7, account_generation=PERSON_GENERATION)

    def execute(self, statement, parameters=None):
        for table, row in (
            ("account_erasure_jobs", self.job),
            ("auth_identities", self.identity),
            ("people", self.person),
        ):
            if f"FROM ntubtob.{table}" in str(statement):
                return SimpleNamespace(
                    mappings=lambda row=row: SimpleNamespace(first=lambda: row)
                )
        return SimpleNamespace()

    def load(self, **changes):
        values = dict(
            job_id=JOB, receipt_secret=SECRET, identity_id=11, clock=lambda: NOW
        )
        values.update(changes)
        return load_erasure_verification_context(self.session, **values)

    def test_person_context_uses_constant_time_hash_and_current_database_fields(self):
        with patch.object(
            erasure_context, "compare_digest", wraps=erasure_context.compare_digest
        ) as compare:
            result = self.load()
        compare.assert_called_once_with(SECRET_HASH, SECRET_HASH)
        self.assertIs(type(result), ErasureVerificationContext)
        self.assertEqual(result.job_id, JOB)
        self.assertEqual(result.identity_generation, IDENTITY_GENERATION)
        self.assertEqual(result.target_generation, PERSON_GENERATION)
        self.assertEqual(result.provider_subject, self.identity["provider_subject"])
        self.assertEqual(result.requested_at, self.job["requested_at"])
        self.assertEqual(
            {field.name for field in fields(result)},
            {
                "job_id",
                "identity_id",
                "provider",
                "provider_subject",
                "identity_generation",
                "target_kind",
                "person_id",
                "target_generation",
                "requested_at",
            },
        )
        self.assertNotIn("fictional-private-subject", repr(result))
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn(SECRET_HASH, repr(result))
        with self.assertRaises(FrozenInstanceError):
            result.job_id = str(uuid4())

    def test_pending_context_requires_exact_identity_and_null_person(self):
        self.job.update(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=11,
            expected_generation=IDENTITY_GENERATION,
        )
        self.identity.update(person_id=None, status="pending")
        result = self.load()
        self.assertIsNone(result.person_id)
        self.assertEqual(result.target_generation, IDENTITY_GENERATION)
        self.job["auth_identity_id"] = 12
        with self.assertRaises(ErasureContextRejected):
            self.load()

    def test_wrong_secret_never_reads_identity_and_is_not_exposed_to_sql(self):
        wrong = "fictional-wrong-secret-" + "b" * 20
        with self.assertRaisesRegex(
            ErasureContextRejected, "receipt_unavailable"
        ) as error:
            self.load(receipt_secret=wrong)
        self.assertNotIn(wrong, str(error.exception))
        self.assertEqual(self.connection.execute.call_count, 3)
        for call in self.connection.execute.call_args_list:
            self.assertNotIn(wrong, repr(call))
            self.assertNotIn(SECRET, repr(call))

    def test_expiry_is_checked_after_all_target_locks(self):
        def expired_clock():
            calls = self.connection.execute.call_args_list
            self.assertEqual(len(calls), 5)
            self.assertIn("FROM ntubtob.people", str(calls[-1].args[0]))
            return self.job["receipt_expires_at"]

        with self.assertRaisesRegex(ErasureContextRejected, "receipt_unavailable"):
            self.load(clock=expired_clock)

    def test_unknown_status_or_receipt_reject_without_details(self):
        for status in ("verified", "processing", "completed", "unknown"):
            self.job["status"] = status
            with self.assertRaisesRegex(ErasureContextRejected, "receipt_unavailable"):
                self.load()
        self.job = None
        with self.assertRaisesRegex(ErasureContextRejected, "receipt_unavailable"):
            self.load()

    def test_invalid_stored_digest_fails_closed_without_subject_read(self):
        for stored_hash in (None, "not-a-digest", "A" * 64):
            self.setUp()
            self.job["receipt_secret_hash"] = stored_hash
            with self.assertRaisesRegex(ErasureContextRejected, "receipt_unavailable"):
                self.load()
            self.assertEqual(self.connection.execute.call_count, 3)

    def test_invalid_clock_does_not_expose_callback_error(self):
        def broken_clock():
            raise ValueError("fictional-private-clock-detail")

        for clock in (broken_clock, lambda: NOW.replace(tzinfo=None)):
            with self.assertRaises(ErasureContextUnavailable) as error:
                self.load(clock=clock)
            self.assertNotIn("fictional-private", str(error.exception))

    def test_cross_identity_mapping_and_stale_generation_rejected(self):
        for attribute, change in (
            ("job", {"id": str(uuid4())}),
            ("identity", {"id": 12}),
            ("identity", {"person_id": 8}),
            ("identity", {"account_generation": "not-a-uuid"}),
            ("identity", {"status": "pending"}),
            ("person", {"account_generation": str(uuid4())}),
            ("job", {"expected_generation": str(uuid4())}),
        ):
            with self.subTest(attribute=attribute, change=change):
                self.setUp()
                getattr(self, attribute).update(change)
                with self.assertRaises(ErasureContextRejected):
                    self.load()

    def test_unbound_or_missing_identity_person_rejected(self):
        for attribute in ("identity", "person"):
            self.setUp()
            setattr(self, attribute, None)
            with self.assertRaises(ErasureContextRejected):
                self.load()

    def test_disabled_or_blocked_bound_identity_still_proves_data_mapping(self):
        for status in ("disabled", "blocked"):
            self.identity["status"] = status
            self.assertEqual(self.load().person_id, 7)

    def test_strict_input_bounds_reject_before_connection(self):
        for values in (
            {"job_id": "not-a-uuid"},
            {"job_id": JOB.upper() + "x"},
            {"identity_id": True},
            {"identity_id": 0},
            {"identity_id": 2**63},
            {"receipt_secret": True},
            {"receipt_secret": "a" * 31},
            {"receipt_secret": "a" * 257},
            {"receipt_secret": "a" * 31 + " "},
            {"receipt_secret": "a" * 31 + "非"},
        ):
            with (
                self.subTest(field=next(iter(values))),
                self.assertRaises(ErasureContextRejected),
            ):
                self.load(**values)
        self.session.connection.assert_not_called()

    def test_rejects_missing_transaction_pending_changes_bad_driver_and_isolation(self):
        for attribute in ("new", "dirty", "deleted"):
            self.setUp()
            setattr(self.session, attribute, {object()})
            with self.assertRaises(ErasureContextUnavailable):
                self.load()
            self.session.connection.assert_not_called()
        self.setUp()
        self.session.in_transaction.return_value = False
        with self.assertRaises(ErasureContextUnavailable):
            self.load()
        self.session.connection.assert_not_called()
        for autocommit in (True, None, "false"):
            self.setUp()
            self.connection.connection.dbapi_connection.autocommit = autocommit
            with self.assertRaises(ErasureContextUnavailable):
                self.load()
            self.connection.execute.assert_not_called()
        self.setUp()
        self.connection.get_isolation_level.return_value = "REPEATABLE READ"
        with self.assertRaises(ErasureContextUnavailable):
            self.load()
        self.connection.execute.assert_not_called()

    def test_exact_schema_and_unfiltered_visibility_are_required(self):
        for revisions in (
            [],
            ["0014_account_erasure_ledger"],
            ["0015_account_generations", "branch"],
        ):
            self.connection.scalars.return_value.all.return_value = revisions
            with self.assertRaises(ErasureContextUnavailable):
                self.load()
        for index in range(3):
            for filtered in (True, None):
                self.setUp()
                self.connection.scalar.side_effect = [False] * index + [filtered]
                with self.assertRaises(ErasureContextUnavailable):
                    self.load()
                self.assertEqual(self.connection.execute.call_count, 2)

    def test_canonical_fixed_connection_only_reads_without_session_flush_or_commit(
        self,
    ):
        self.load()
        calls = self.connection.execute.call_args_list
        self.assertEqual(calls[0].args[1], {"key": ADMIN_LOCK_KEY})
        self.assertEqual(calls[1].args[1], {"key": EVENT_SNAPSHOT_LOCK_KEY})
        self.assertTrue(all("FOR UPDATE" in str(c.args[0]) for c in calls[2:]))
        self.assertTrue(
            all(str(c.args[0]).lstrip().startswith("SELECT") for c in calls)
        )
        self.session.execute.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()
        self.session.add.assert_not_called()

    def test_storage_failure_is_sanitized_without_retry(self):
        self.connection.execute.side_effect = SQLAlchemyError(
            "fictional-private-db-secret"
        )
        with self.assertRaises(ErasureContextUnavailable) as error:
            self.load()
        self.assertNotIn("fictional-private", str(error.exception))
        self.assertEqual(self.connection.execute.call_count, 1)


@unittest.skipUnless(ledger_fixture.DATABASE_URL, "isolated ledger URL not configured")
class ErasureContextPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ledger_fixture.ErasureLedgerPostgresTests.setUpClass.__func__(cls)
        with cls.engine.begin() as connection:
            config = Config(str(ledger_fixture.ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "0015_account_generations")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = ledger_fixture.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.setUp()
        self.connection = self.fixture.connection

    def tearDown(self):
        if self.fixture.transaction.is_active:
            self.fixture.transaction.rollback()
        self.connection.close()

    def prepare(self, *, pending=False, **changes):
        if not pending:
            self.connection.execute(
                text(
                    "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
                ),
                {"person": self.fixture.person, "id": self.fixture.identity},
            )
        table, row = (
            ("auth_identities", self.fixture.identity)
            if pending
            else ("people", self.fixture.person)
        )
        self.generation = str(
            self.connection.scalar(
                text(f"SELECT account_generation FROM ntubtob.{table} WHERE id=:id"),
                {"id": row},
            )
        )
        values = dict(
            expected_generation=self.generation,
            receipt_secret_hash=SECRET_HASH,
            target_kind="pending_identity" if pending else "person",
            person_id=None if pending else self.fixture.person,
            auth_identity_id=self.fixture.identity if pending else None,
        )
        values.update(changes)
        self.job_id = self.fixture.job(**values)

    def load(self, *, identity_id=None, receipt_secret=SECRET, binds=None):
        with (
            Session(
                bind=self.connection,
                binds=binds,
                join_transaction_mode="create_savepoint",
            ) as session,
            session.begin(),
        ):
            return load_erasure_verification_context(
                session,
                job_id=self.job_id,
                identity_id=identity_id or self.fixture.identity,
                receipt_secret=receipt_secret,
                clock=lambda: NOW,
            )

    def test_person_context_is_actual_and_read_only(self):
        self.prepare()
        result = self.load()
        self.assertEqual(result.target_generation, self.generation)
        self.assertEqual(result.person_id, self.fixture.person)
        self.assertEqual(
            self.connection.scalar(
                text("SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"),
                {"id": self.job_id},
            ),
            "requested",
        )
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_steps WHERE job_id=:id"
                ),
                {"id": self.job_id},
            ),
            0,
        )

    def test_pending_context_then_linked_mapping_rejects(self):
        self.prepare(pending=True)
        self.assertIsNone(self.load().person_id)
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.fixture.person, "id": self.fixture.identity},
        )
        with self.assertRaises(ErasureContextRejected):
            self.load()

    def test_wrong_secret_and_cross_identity_reject_otherwise_valid_context(self):
        self.prepare()
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.fixture.other_person, "id": self.fixture.other_identity},
        )
        for values in (
            {"identity_id": self.fixture.other_identity},
            {"receipt_secret": "b" * 43},
        ):
            with (
                self.subTest(fields=tuple(values)),
                self.assertRaises(ErasureContextRejected),
            ):
                self.load(**values)
        self.assertEqual(self.load().person_id, self.fixture.person)

    def test_stale_job_generation_is_not_replaced_by_current_generation(self):
        self.prepare(expected_generation=str(uuid4()))
        with self.assertRaises(ErasureContextRejected):
            self.load()

    def test_expired_receipt_rejects_at_exact_boundary(self):
        self.prepare(receipt_expires_at=NOW)
        with self.assertRaisesRegex(ErasureContextRejected, "receipt_unavailable"):
            self.load()

    def test_other_mapper_bind_does_not_replace_checked_connection(self):
        self.prepare()
        other_engine = create_mock_engine(
            "postgresql://", lambda *args, **kwargs: self.fail("wrong bind")
        )
        result = self.load(
            binds={
                model: other_engine
                for model in (PersonRecord, AuthIdentityRecord, AccountErasureJobRecord)
            }
        )
        self.assertEqual(result.person_id, self.fixture.person)
