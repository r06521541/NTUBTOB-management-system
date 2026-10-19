"""Fictional receipt tests; no provider or production data access."""

import hashlib
import unittest
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from shared_lib.shared_module.mobile_api import MobilePrincipal
from shared_lib.shared_module.portal_data import erasure_request as requests
from tests.portal_data import test_erasure_verification as verification_fixture

NOW = datetime(2035, 1, 1, tzinfo=timezone.utc)
KEY = b"fictional-erasure-receipt-key-only-12345"
GENERATION = "11111111-1111-4111-8111-111111111111"
JOB = "22222222-2222-4222-8222-222222222222"
SESSION = "33333333-3333-4333-8333-333333333333"


def plan(**kwargs):
    return requests.ErasureRequestPlan(
        1,
        "a" * 64,
        1,
        NOW + timedelta(hours=1),
        NOW + timedelta(hours=2),
        NOW + timedelta(hours=3),
    )


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.principal = MobilePrincipal(SESSION, 1, 2, "basic", "Fictional", 1)
        self.repo = requests.AccountErasureRequestRepository(
            None, KEY, plan, lambda: NOW
        )
        self.session = MagicMock()
        self.session.new = self.session.dirty = self.session.deleted = ()
        self.session.in_transaction.return_value = True
        self.connection = self.session.connection.return_value
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.scalars.return_value.all.return_value = [
            "0015_account_generations"
        ]
        self.connection.scalar.return_value = False
        self.rows = {
            "auth_identities": dict(id=2, person_id=1, status="linked"),
            "people": dict(id=1, portal_status="active", account_generation=GENERATION),
            "mobile_sessions": dict(
                id=SESSION,
                person_id=1,
                auth_identity_id=2,
                access_epoch=1,
                status="active",
                refresh_family_expires_at=NOW + timedelta(days=1),
            ),
            "account_erasure_jobs": None,
            "account_deletion_requests": None,
        }
        self.inserts = []
        self.adopted_legacy_job = None

        def execute(statement, values):
            sql = str(statement)
            if sql.startswith("INSERT"):
                self.inserts.append(dict(values))
                return MagicMock(rowcount=1)
            table = sql.split("FROM ntubtob.")[1].split()[0]
            result = MagicMock()
            result.mappings.return_value.first.return_value = (
                self.adopted_legacy_job
                if table == "account_erasure_jobs" and "WHERE id=:id" in sql
                else self.rows[table]
            )
            return result

        self.connection.execute.side_effect = execute
        stack = ExitStack()
        self.addCleanup(stack.close)
        factory = stack.enter_context(patch.object(requests, "Session"))
        factory.return_value.__enter__.return_value = self.session
        self.locks = stack.enter_context(
            patch.object(requests, "acquire_admin_event_locks")
        )

    def test_configuration_rejects_short_key(self):
        with self.assertRaises(ValueError):
            requests.AccountErasureRequestRepository(None, b"short", lambda **kw: None)

    def test_custody_builder_uses_original_connection_and_store_after_job_insert(self):
        store = MagicMock()
        snapshot = object()

        def builder(**values):
            self.assertIs(values["connection"], self.connection)
            self.assertFalse(self.inserts)
            self.assertEqual(values["target_generation"], GENERATION)
            return requests.CapturedErasureRequestPlan(plan(), snapshot)

        self.repo = requests.AccountErasureRequestRepository(
            MagicMock(spec=Engine),
            KEY,
            builder,
            lambda: NOW,
            sealed_plan_store=store,
        )
        store.store_requested.side_effect = lambda connection, job, value: (
            self.assertEqual(len(self.inserts), 1),
            self.assertIs(value, snapshot),
        )
        result = self.repo.request(self.principal)
        store.store_requested.assert_called_once_with(
            self.connection, result.job_id, snapshot
        )
        store.load.assert_not_called()

    def test_custody_duplicate_loads_only_and_final_check_follows_storage(self):
        store = MagicMock()
        self.repo = requests.AccountErasureRequestRepository(
            MagicMock(spec=Engine),
            KEY,
            MagicMock(),
            lambda: NOW,
            sealed_plan_store=store,
        )
        self.existing()
        self.repo.request(self.principal)
        store.load.assert_called_once_with(self.connection, JOB)
        self.repo.plan_builder.assert_not_called()
        self.assertFalse(self.inserts)
        store.load.side_effect = lambda *args: setattr(
            self.repo, "clock", lambda: NOW + timedelta(days=2)
        )
        with self.assertRaisesRegex(requests.ErasureRequestRejected, "request_expired"):
            self.repo.request(self.principal)

    def existing(self):
        self.rows["account_erasure_jobs"] = dict(
            id=JOB,
            status="requested",
            target_kind="person",
            person_id=1,
            auth_identity_id=None,
            expected_generation=GENERATION,
            receipt_secret_hash=hashlib.sha256(
                self.repo._secret(JOB).encode()
            ).hexdigest(),
            requested_at=NOW - timedelta(hours=1),
            receipt_expires_at=NOW + timedelta(hours=1),
        )

    def test_create_uses_actual_generation_hash_only_and_minimal_receipt(self):
        receipt = self.repo.request(self.principal)
        self.assertEqual(len(self.inserts), 1)
        self.assertEqual(self.inserts[0]["generation"], GENERATION)
        self.assertEqual(
            self.inserts[0]["receipt_hash"],
            hashlib.sha256(receipt.receipt_secret.encode()).hexdigest(),
        )
        self.assertNotIn(receipt.receipt_secret, repr(self.inserts))
        self.assertNotIn(receipt.receipt_secret, repr(receipt))
        self.assertEqual(receipt.requested_at, NOW)
        self.locks.assert_called_once_with(self.connection)

    def test_duplicate_returns_stable_secret_without_plan_or_mutation(self):
        self.existing()
        self.repo.plan_builder = lambda **kw: self.fail("duplicate recomputed plan")
        first = self.repo.request(self.principal)
        second = self.repo.request(self.principal)
        self.assertEqual(first, second)
        self.assertEqual(first.requested_at, NOW - timedelta(hours=1))
        self.assertEqual(self.inserts, [])

    def test_legacy_uuid_reused_but_timestamp_is_fresh(self):
        self.rows["account_deletion_requests"] = dict(id=JOB, status="requested")
        receipt = self.repo.request(self.principal)
        self.assertEqual(receipt.job_id, JOB)
        self.assertEqual(receipt.requested_at, NOW)
        self.assertEqual(self.inserts[0]["now"], NOW)
        self.assertFalse(
            any(
                str(c.args[0]).startswith("UPDATE")
                for c in self.connection.execute.call_args_list
            )
        )

    def test_cancelled_legacy_intent_is_not_reused(self):
        self.connection.scalars.return_value.all.return_value = [
            "0016_erasure_cancellation"
        ]
        self.rows["account_deletion_requests"] = dict(id=JOB, status="requested")
        self.adopted_legacy_job = dict(
            id=JOB,
            status="cancelled",
            target_kind="person",
            person_id=None,
            auth_identity_id=None,
            expected_generation=GENERATION,
        )
        receipt = self.repo.request(self.principal)
        self.assertNotEqual(receipt.job_id, JOB)
        self.assertNotEqual(receipt.receipt_secret, self.repo._secret(JOB))
        self.assertEqual(len(self.inserts), 1)

    def test_legacy_collision_requires_same_generation_cancelled_detached_intent(self):
        self.connection.scalars.return_value.all.return_value = [
            "0016_erasure_cancellation"
        ]
        self.rows["account_deletion_requests"] = dict(id=JOB, status="requested")
        valid = dict(
            id=JOB,
            status="cancelled",
            target_kind="person",
            person_id=None,
            auth_identity_id=None,
            expected_generation=GENERATION,
        )
        for field, value in (
            ("status", "completed"),
            ("status", "requested"),
            ("expected_generation", str(uuid4())),
            ("person_id", 1),
            ("auth_identity_id", 2),
            ("target_kind", "pending_identity"),
        ):
            with self.subTest(field=field, value=value):
                self.adopted_legacy_job = dict(valid, **{field: value})
                with self.assertRaises(requests.ErasureRequestRejected):
                    self.repo.request(self.principal)
        self.assertEqual(self.inserts, [])

    def test_retained_cancelled_job_on_old_revision_cannot_renew(self):
        self.rows["account_deletion_requests"] = dict(id=JOB, status="requested")
        self.adopted_legacy_job = dict(
            id=JOB,
            status="cancelled",
            target_kind="person",
            person_id=None,
            auth_identity_id=None,
            expected_generation=GENERATION,
        )
        with self.assertRaises(requests.ErasureRequestRejected):
            self.repo.request(self.principal)
        self.assertEqual(self.inserts, [])

    def test_stale_tuple_rejects_without_insert(self):
        for table, field, value in (
            ("auth_identities", "person_id", 9),
            ("auth_identities", "status", "disabled"),
            ("people", "portal_status", "inactive"),
            ("mobile_sessions", "access_epoch", 3),
            ("mobile_sessions", "auth_identity_id", 9),
            ("mobile_sessions", "refresh_family_expires_at", NOW),
        ):
            original = self.rows[table][field]
            self.rows[table][field] = value
            with self.assertRaises(requests.ErasureRequestRejected):
                self.repo.request(self.principal)
            self.rows[table][field] = original
        self.assertEqual(self.inserts, [])

    def test_duplicate_key_generation_expiry_state_mismatch_rejected(self):
        for field, value in (
            ("receipt_secret_hash", "b" * 64),
            ("expected_generation", str(uuid4())),
            ("receipt_expires_at", NOW),
            ("status", "verified"),
        ):
            self.existing()
            self.rows["account_erasure_jobs"][field] = value
            with self.assertRaises(requests.ErasureRequestRejected):
                self.repo.request(self.principal)
        self.assertEqual(self.inserts, [])

    def test_plan_invalid_and_exceptions_rollback_without_disclosure(self):
        for value in (
            None,
            replace(plan(), scope_version=True),
            replace(plan(), scope_hash="secret-sentinel"),
            replace(plan(), fulfillment_due_at=NOW),
            replace(plan(), evidence_expires_at=NOW),
            replace(plan(), receipt_expires_at=NOW.replace(tzinfo=None)),
        ):
            self.repo.plan_builder = lambda **kw: value
            with self.assertRaises(requests.ErasureRequestRejected):
                self.repo.request(self.principal)
        self.repo.plan_builder = MagicMock(side_effect=RuntimeError("secret-sentinel"))
        with self.assertRaises(requests.ErasureRequestUnavailable) as caught:
            self.repo.request(self.principal)
        self.assertNotIn("secret-sentinel", str(caught.exception))
        self.assertEqual(self.inserts, [])
        self.assertIsNotNone(self.session.begin.return_value.__exit__.call_args.args[0])

    def test_schema_rls_transaction_fail_closed(self):
        for change in ("schema", "rls", "isolation", "autocommit", "dirty"):
            with self.subTest(change=change):
                if change == "schema":
                    self.connection.scalars.return_value.all.return_value = [
                        "0014_account_erasure_ledger"
                    ]
                if change == "rls":
                    self.connection.scalar.return_value = True
                if change == "isolation":
                    self.connection.get_isolation_level.return_value = "REPEATABLE READ"
                if change == "autocommit":
                    self.connection.connection.dbapi_connection.autocommit = True
                if change == "dirty":
                    self.session.dirty = [object()]
                with self.assertRaises(requests.ErasureRequestUnavailable):
                    self.repo.request(self.principal)
                self.connection.scalars.return_value.all.return_value = [
                    "0015_account_generations"
                ]
                self.connection.scalar.return_value = False
                self.connection.get_isolation_level.return_value = "READ COMMITTED"
                self.connection.connection.dbapi_connection.autocommit = False
                self.session.dirty = ()
        self.assertEqual(self.inserts, [])

    def test_planning_cannot_outlive_session_or_deadline(self):
        self.repo.clock = MagicMock(side_effect=[NOW, NOW + timedelta(days=2)])
        with self.assertRaisesRegex(
            requests.ErasureRequestRejected, "expired_during_planning"
        ):
            self.repo.request(self.principal)
        self.assertEqual(self.inserts, [])

    def test_commit_uncertainty_does_not_return_receipt_or_retry(self):
        self.session.begin.return_value.__exit__.side_effect = RuntimeError(
            "private-sentinel"
        )
        with self.assertRaises(requests.ErasureRequestUnavailable) as caught:
            self.repo.request(self.principal)
        self.assertNotIn("private-sentinel", str(caught.exception))
        self.assertEqual(len(self.inserts), 1)


@unittest.skipUnless(
    verification_fixture.ledger_fixture.DATABASE_URL,
    "isolated ledger URL not configured",
)
class RequestPostgresTests(unittest.TestCase):
    def test_approved_receipt_keeps_180_days_independent_of_30_day_due(self):
        from shared_lib.shared_module.portal_data.erasure_composition import (
            ErasurePlanPolicy,
        )
        from shared_lib.shared_module.portal_data.erasure_receipt import (
            ErasureReceiptRejected,
            load_erasure_receipt,
        )

        policy = ErasurePlanPolicy.initial_request(NOW)
        self.repo.plan_builder = lambda **kw: replace(plan(), **vars(policy))
        receipt = self.repo.request(self.principal)
        due, expires = self.connection.execute(
            text(
                "SELECT fulfillment_due_at,receipt_expires_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
            ),
            {"id": receipt.job_id},
        ).one()
        self.assertEqual(due, NOW + timedelta(days=30))
        self.assertEqual(expires, NOW + timedelta(days=180))
        for elapsed in (
            timedelta(days=31),
            timedelta(days=180) - timedelta(microseconds=1),
        ):
            with (
                Session(
                    bind=self.connection, join_transaction_mode="create_savepoint"
                ) as session,
                session.begin(),
            ):
                status = load_erasure_receipt(
                    session,
                    job_id=receipt.job_id,
                    receipt_secret=receipt.receipt_secret,
                    clock=lambda: NOW + elapsed,
                )
                self.assertEqual(status.status, "requested")
        with (
            Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            with self.assertRaises(ErasureReceiptRejected):
                load_erasure_receipt(
                    session,
                    job_id=receipt.job_id,
                    receipt_secret=receipt.receipt_secret,
                    clock=lambda: expires,
                )

    @classmethod
    def setUpClass(cls):
        verification_fixture.ErasureVerificationPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = verification_fixture.ledger_fixture.ErasureLedgerPostgresTests(
            "runTest"
        )
        self.fixture.engine = self.engine
        self.fixture.setUp()
        self.connection = self.fixture.connection
        self.addCleanup(self.connection.close)
        self.addCleanup(
            lambda: (
                self.fixture.transaction.rollback()
                if self.fixture.transaction.is_active
                else None
            )
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            dict(person=self.fixture.person, id=self.fixture.identity),
        )
        self.session_id = str(uuid4())
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.mobile_sessions (id,auth_identity_id,person_id,installation_id_hash,platform,status,access_epoch,refresh_family_expires_at,created_at,updated_at) VALUES (:id,:identity,:person,:hash,'ios','active',1,:expiry,:now,:now)"
            ),
            dict(
                id=self.session_id,
                identity=self.fixture.identity,
                person=self.fixture.person,
                hash="a" * 64,
                expiry=NOW + timedelta(days=1),
                now=NOW,
            ),
        )
        self.principal = MobilePrincipal(
            self.session_id,
            self.fixture.person,
            self.fixture.identity,
            "basic",
            "Fictional",
            1,
        )
        self.repo = requests.AccountErasureRequestRepository(
            self.engine, KEY, plan, lambda: NOW
        )
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(
            patch.object(
                requests,
                "Session",
                side_effect=lambda engine: Session(
                    bind=self.connection, join_transaction_mode="create_savepoint"
                ),
            )
        )

    def test_real_insert_duplicate_generation_and_hash_only(self):
        first = self.repo.request(self.principal)
        self.assertEqual(first, self.repo.request(self.principal))
        row = self.connection.execute(
            text(
                "SELECT expected_generation,receipt_secret_hash,requested_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
            ),
            dict(id=first.job_id),
        ).one()
        generation = self.connection.scalar(
            text("SELECT account_generation FROM ntubtob.people WHERE id=:id"),
            dict(id=self.fixture.person),
        )
        self.assertEqual(row.expected_generation, generation)
        self.assertEqual(
            row.receipt_secret_hash,
            hashlib.sha256(first.receipt_secret.encode()).hexdigest(),
        )
        self.assertEqual(row.requested_at, NOW)

    def test_stale_session_and_invalid_plan_leave_no_job(self):
        self.connection.execute(
            text("UPDATE ntubtob.mobile_sessions SET status='revoked' WHERE id=:id"),
            dict(id=self.session_id),
        )
        with self.assertRaises(requests.ErasureRequestRejected):
            self.repo.request(self.principal)
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_jobs WHERE person_id=:id"
                ),
                dict(id=self.fixture.person),
            ),
            0,
        )

    def test_legacy_reuse_and_wrong_receipt_key_preserve_row(self):
        legacy_id = str(uuid4())
        old_time = NOW - timedelta(days=1)
        self.connection.execute(
            text(
                "INSERT INTO ntubtob.account_deletion_requests (id,person_id,status,requested_at) VALUES (:id,:person,'requested',:now)"
            ),
            dict(id=legacy_id, person=self.fixture.person, now=old_time),
        )
        first = self.repo.request(self.principal)
        self.assertEqual(first.job_id, legacy_id)
        self.assertEqual(first.requested_at, NOW)
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT requested_at FROM ntubtob.account_deletion_requests WHERE id=:id"
                ),
                dict(id=legacy_id),
            ),
            old_time,
        )
        self.repo._key = b"different-fictional-key" * 2
        with self.assertRaisesRegex(
            requests.ErasureRequestRejected, "receipt_key_mismatch"
        ):
            self.repo.request(self.principal)
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT count(*) FROM ntubtob.account_erasure_jobs WHERE person_id=:id"
                ),
                dict(id=self.fixture.person),
            ),
            1,
        )

    def test_invalid_plan_rolls_back_and_does_not_create_legacy_receipt(self):
        self.repo.plan_builder = lambda **kw: replace(plan(), receipt_expires_at=NOW)
        with self.assertRaises(requests.ErasureRequestRejected):
            self.repo.request(self.principal)
        for table in ("account_erasure_jobs", "account_deletion_requests"):
            self.assertEqual(
                self.connection.scalar(
                    text(f"SELECT count(*) FROM ntubtob.{table} WHERE person_id=:id"),
                    dict(id=self.fixture.person),
                ),
                0,
            )


@unittest.skipUnless(
    verification_fixture.ledger_fixture.DATABASE_URL,
    "isolated ledger URL not configured",
)
class RequestCustodyPostgresTests(unittest.TestCase):
    setUpClass = RequestPostgresTests.__dict__["setUpClass"]
    tearDownClass = RequestPostgresTests.__dict__["tearDownClass"]

    def setUp(self):
        from alembic import command
        from alembic.config import Config

        from tests.portal_data.test_erasure_plan_store import fictional_store

        RequestPostgresTests.setUp(self)
        config = Config(str(verification_fixture.ledger_fixture.ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.upgrade(config, "0018_erasure_privacy_mutation")
        self.captures = []
        self.store = fictional_store()
        self.repo = requests.AccountErasureRequestRepository(
            self.engine,
            KEY,
            self.capture,
            lambda: NOW,
            sealed_plan_store=self.store,
        )

    def capture(self, *, connection, job_id, person_id, **values):
        from shared_lib.shared_module.erasure_restore_binding import RestoreBindingCodec
        from shared_lib.shared_module.portal_data.erasure_person_fulfillment import (
            capture_person_snapshot,
        )

        self.assertIs(connection, self.connection)
        self.assertIsNone(
            connection.scalar(
                text("SELECT id FROM ntubtob.account_erasure_jobs WHERE id=:job"),
                {"job": job_id},
            )
        )
        with (
            Session(
                bind=connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            self.assertIs(session.connection(), connection)
            snapshot = capture_person_snapshot(
                session,
                person_id,
                reviewed_dispositions=(),
                restore_codec=RestoreBindingCodec(
                    namespace="00000000-0000-4000-8000-000000000003",
                    active_key="fictional",
                    keys={"fictional": b"F" * 32},
                ),
                provider_audiences={"apple": "fictional-apple"},
            )
        self.captures.append(snapshot)
        return requests.CapturedErasureRequestPlan(
            replace(plan(), scope_hash=snapshot.scope_hash), snapshot
        )

    def count(self, table):
        return self.connection.scalar(text(f"SELECT count(*) FROM ntubtob.{table}"))

    def test_capture_job_and_plan_share_connection_and_duplicate_never_recaptures(self):
        from tests.portal_data.test_erasure_plan_store import fictional_store

        receipt = self.repo.request(self.principal)
        self.assertEqual(
            fictional_store().load(self.connection, receipt.job_id), self.captures[0]
        )
        self.assertEqual(self.repo.request(self.principal), receipt)
        self.assertEqual(len(self.captures), 1)
        self.assertEqual(self.count("account_erasure_jobs"), 1)
        self.assertEqual(self.count("account_erasure_sealed_plans"), 1)

    def test_after_storage_failure_or_session_expiry_rolls_back_job_and_plan(self):
        original = self.store.store_requested
        for failure in ("storage", "session_expiry"):
            self.repo.clock = lambda: NOW

            def after_storage(connection, job_id, snapshot):
                original(connection, job_id, snapshot)
                if failure == "storage":
                    raise RuntimeError("private-sentinel")
                self.repo.clock = lambda: NOW + timedelta(days=1)

            with patch.object(self.store, "store_requested", side_effect=after_storage):
                with self.assertRaises(
                    (
                        requests.ErasureRequestRejected,
                        requests.ErasureRequestUnavailable,
                    )
                ) as raised:
                    self.repo.request(self.principal)
                self.assertNotIn("private-sentinel", str(raised.exception))
            self.assertEqual(self.count("account_erasure_jobs"), 0)
            self.assertEqual(self.count("account_erasure_sealed_plans"), 0)

    def test_preexisting_uncustodied_job_is_not_backfilled(self):
        self.repo.sealed_plan_store = None
        self.repo.plan_builder = plan
        receipt = self.repo.request(self.principal)
        self.repo.sealed_plan_store = self.store
        self.repo.plan_builder = MagicMock(
            side_effect=AssertionError("must not recapture")
        )
        with self.assertRaises(requests.ErasureRequestUnavailable):
            self.repo.request(self.principal)
        self.repo.plan_builder.assert_not_called()
        self.assertEqual(self.count("account_erasure_jobs"), 1)
        self.assertEqual(self.count("account_erasure_sealed_plans"), 0)
