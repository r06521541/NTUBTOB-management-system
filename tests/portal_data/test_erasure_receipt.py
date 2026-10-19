"""Receipt-only status: fictional secrets and opt-in disposable database tests."""

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

from shared_lib.shared_module.portal_data import erasure_receipt
from shared_lib.shared_module.portal_data.erasure_models import AccountErasureJobRecord
from shared_lib.shared_module.portal_data.erasure_receipt import (
    ErasureReceiptRejected,
    ErasureReceiptStatus,
    ErasureReceiptUnavailable,
    load_erasure_receipt,
)
from shared_lib.shared_module.portal_data.runtime import (
    ADMIN_LOCK_KEY,
    EVENT_SNAPSHOT_LOCK_KEY,
)
from tests.portal_data import test_erasure_ledger as ledger_fixture

NOW = datetime(2035, 1, 1, 0, 1, tzinfo=timezone.utc)
JOB = "a1111111-1111-4111-8111-111111111111"
SECRET = "fictional-only-status-receipt-" + "a" * 20
SECRET_HASH = hashlib.sha256(SECRET.encode("ascii")).hexdigest()
STATUSES = (
    "requested",
    "verified",
    "processing",
    "needs_attention",
    "online_completed",
    "completed",
)


class ErasureReceiptTests(unittest.TestCase):
    def test_cancelled_receipt_requires_cancellation_revision(self):
        self.job["status"] = "cancelled"
        with self.assertRaises(ErasureReceiptUnavailable):
            self.load()
        self.connection.scalars.return_value.all.return_value = [
            "0016_erasure_cancellation"
        ]
        self.assertEqual(self.load().status, "cancelled")

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
            receipt_secret_hash=SECRET_HASH,
            receipt_expires_at=NOW + timedelta(minutes=1),
            requested_at=NOW - timedelta(minutes=1),
            updated_at=NOW,
        )

    def execute(self, statement, parameters=None):
        if "FROM ntubtob.account_erasure_jobs" in str(statement):
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(first=lambda: self.job)
            )
        return SimpleNamespace()

    def load(self, **changes):
        values = dict(job_id=JOB, receipt_secret=SECRET, clock=lambda: NOW)
        values.update(changes)
        return load_erasure_receipt(self.session, **values)

    def test_exact_minimal_immutable_dto_and_constant_time_hash_comparison(self):
        with patch.object(
            erasure_receipt, "compare_digest", wraps=erasure_receipt.compare_digest
        ) as compare:
            result = self.load()
        compare.assert_called_once_with(SECRET_HASH, SECRET_HASH)
        self.assertIs(type(result), ErasureReceiptStatus)
        self.assertEqual(
            {field.name for field in fields(result)},
            {"job_id", "status", "requested_at", "updated_at"},
        )
        self.assertEqual(result.job_id, JOB)
        self.assertEqual(result.status, "requested")
        self.assertEqual(result.requested_at, self.job["requested_at"])
        self.assertEqual(result.updated_at, NOW)
        self.assertNotIn(SECRET, repr(result))
        self.assertNotIn(SECRET_HASH, repr(result))
        with self.assertRaises(FrozenInstanceError):
            result.status = "completed"

    def test_every_known_status_works_without_any_target_or_session_fields(self):
        for status in STATUSES:
            with self.subTest(status=status):
                self.job["status"] = status
                self.assertEqual(self.load().status, status)

    def test_fixed_connection_reads_only_ledger_and_never_mutates(self):
        self.load()
        calls = self.connection.execute.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].args[1], {"key": ADMIN_LOCK_KEY})
        self.assertEqual(calls[1].args[1], {"key": EVENT_SNAPSHOT_LOCK_KEY})
        self.assertIn("FOR UPDATE", str(calls[2].args[0]))
        self.assertTrue(
            all(str(call.args[0]).lstrip().startswith("SELECT") for call in calls)
        )
        sql = str(calls[2].args[0])
        selected = sql.split("FROM", 1)[0].removeprefix("SELECT ")
        self.assertEqual(
            {column.strip() for column in selected.split(",")},
            {
                "id",
                "status",
                "requested_at",
                "updated_at",
                "receipt_secret_hash",
                "receipt_expires_at",
            },
        )
        self.assertNotIn("person", sql)
        self.assertNotIn("identit", sql)
        self.assertNotIn("mobile_sessions", sql)
        self.assertNotIn(SECRET, repr(calls))
        self.assertNotIn(SECRET_HASH, repr(calls))
        self.session.execute.assert_not_called()
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()
        self.session.add.assert_not_called()

    def test_unknown_job_wrong_secret_and_expiry_share_fixed_rejection(self):
        reasons = []
        for scenario in ("missing", "wrong_secret", "expired"):
            self.setUp()
            values = {}
            if scenario == "missing":
                self.job = None
            elif scenario == "wrong_secret":
                values["receipt_secret"] = "b" * 43
            else:
                self.job["receipt_expires_at"] = NOW
            with self.assertRaises(ErasureReceiptRejected) as error:
                self.load(**values)
            reasons.append(str(error.exception))
        self.assertEqual(reasons, ["receipt_unavailable"] * 3)

    def test_clock_and_expiry_checked_after_waiting_for_job_lock(self):
        def clock():
            calls = self.connection.execute.call_args_list
            self.assertEqual(len(calls), 3)
            self.assertIn("FOR UPDATE", str(calls[-1].args[0]))
            return self.job["receipt_expires_at"]

        with self.assertRaisesRegex(ErasureReceiptRejected, "receipt_unavailable"):
            self.load(clock=clock)

    def test_invalid_uuid_secret_bounds_and_types_reject_before_connection(self):
        for values in (
            {"job_id": True},
            {"job_id": "not-a-uuid"},
            {"job_id": JOB.upper()},
            {"receipt_secret": True},
            {"receipt_secret": None},
            {"receipt_secret": "a" * 31},
            {"receipt_secret": "a" * 257},
            {"receipt_secret": "a" * 31 + " "},
            {"receipt_secret": "a" * 31 + "非"},
        ):
            with (
                self.subTest(field=next(iter(values))),
                self.assertRaises(ErasureReceiptRejected),
            ):
                self.load(**values)
        self.session.connection.assert_not_called()

    def test_secret_bounds_are_inclusive_without_returning_secret(self):
        for length in (32, 256):
            secret = "a" * length
            self.job["receipt_secret_hash"] = hashlib.sha256(
                secret.encode("ascii")
            ).hexdigest()
            self.assertEqual(self.load(receipt_secret=secret).job_id, JOB)

    def test_response_timestamps_are_utc_and_invalid_stored_times_fail_closed(self):
        local_zone = timezone(timedelta(hours=8))
        self.job["requested_at"] = self.job["requested_at"].astimezone(local_zone)
        self.job["updated_at"] = NOW.astimezone(local_zone)
        result = self.load()
        self.assertEqual(result.requested_at.tzinfo, timezone.utc)
        self.assertEqual(result.updated_at, NOW)
        for updated_at in (
            NOW.replace(tzinfo=None),
            "fictional-private-time",
            NOW - timedelta(days=1),
        ):
            self.job["updated_at"] = updated_at
            with self.assertRaises(ErasureReceiptUnavailable) as error:
                self.load()
            self.assertNotIn("fictional-private", str(error.exception))

    def test_wrong_secret_stops_before_clock_or_any_additional_lookup(self):
        clock = MagicMock(return_value=NOW)
        with self.assertRaises(ErasureReceiptRejected):
            self.load(receipt_secret="b" * 43, clock=clock)
        clock.assert_not_called()
        self.assertEqual(self.connection.execute.call_count, 3)

    def test_malformed_stored_hash_and_wrong_row_are_not_authorized(self):
        for change in (
            {"receipt_secret_hash": None},
            {"receipt_secret_hash": "A" * 64},
            {"receipt_secret_hash": "short"},
            {"id": str(uuid4())},
        ):
            self.setUp()
            self.job.update(change)
            with self.assertRaises(ErasureReceiptRejected):
                self.load()

    def test_unknown_or_malformed_status_is_not_exposed(self):
        for status in ("unexpected", None, []):
            self.job["status"] = status
            with self.assertRaises(ErasureReceiptUnavailable):
                self.load()

    def test_clean_transaction_is_required_but_no_login_principal_is_needed(self):
        for attribute in ("new", "dirty", "deleted"):
            self.setUp()
            setattr(self.session, attribute, {object()})
            with self.assertRaises(ErasureReceiptUnavailable):
                self.load()
            self.session.connection.assert_not_called()
        self.setUp()
        self.session.in_transaction.return_value = False
        with self.assertRaises(ErasureReceiptUnavailable):
            self.load()
        self.session.connection.assert_not_called()

    def test_driver_isolation_and_exact_schema_fail_closed(self):
        for autocommit in (True, None, "false"):
            self.setUp()
            self.connection.connection.dbapi_connection.autocommit = autocommit
            with self.assertRaises(ErasureReceiptUnavailable):
                self.load()
            self.connection.execute.assert_not_called()
        for isolation in ("REPEATABLE READ", "SERIALIZABLE", "AUTOCOMMIT"):
            self.setUp()
            self.connection.get_isolation_level.return_value = isolation
            with self.assertRaises(ErasureReceiptUnavailable):
                self.load()
            self.connection.execute.assert_not_called()
        for revisions in (
            [],
            ["0014_account_erasure_ledger"],
            ["0015_account_generations", "branch"],
        ):
            self.setUp()
            self.connection.scalars.return_value.all.return_value = revisions
            with self.assertRaises(ErasureReceiptUnavailable):
                self.load()
            self.assertEqual(self.connection.execute.call_count, 2)

    def test_filtered_or_unknown_rls_is_not_an_empty_receipt(self):
        for filtered in (True, None):
            self.setUp()
            self.connection.scalar.return_value = filtered
            with self.assertRaises(ErasureReceiptUnavailable):
                self.load()
            self.assertEqual(self.connection.execute.call_count, 2)

    def test_invalid_clock_and_storage_errors_are_sanitized_without_retry(self):
        def broken_clock():
            raise ValueError("fictional-private-clock")

        with self.assertRaises(ErasureReceiptUnavailable) as error:
            self.load(clock=broken_clock)
        self.assertNotIn("fictional-private", str(error.exception))
        self.setUp()
        self.connection.execute.side_effect = SQLAlchemyError(
            "fictional-private-driver"
        )
        with self.assertRaises(ErasureReceiptUnavailable) as error:
            self.load()
        self.assertNotIn("fictional-private", str(error.exception))
        self.assertEqual(self.connection.execute.call_count, 1)


@unittest.skipUnless(ledger_fixture.DATABASE_URL, "isolated ledger URL not configured")
class ErasureReceiptPostgresTests(unittest.TestCase):
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
        self.job_id = self.fixture.job(receipt_secret_hash=SECRET_HASH)

    def tearDown(self):
        if self.fixture.transaction.is_active:
            self.fixture.transaction.rollback()
        self.connection.close()

    def load(
        self, *, job_id=None, receipt_secret=SECRET, clock=lambda: NOW, binds=None
    ):
        with (
            Session(
                bind=self.connection,
                binds=binds,
                join_transaction_mode="create_savepoint",
            ) as session,
            session.begin(),
        ):
            return load_erasure_receipt(
                session,
                job_id=job_id or self.job_id,
                receipt_secret=receipt_secret,
                clock=clock,
            )

    def test_all_known_states_are_readable_without_login_and_without_writes(self):
        for status, changes in (
            ("requested", {}),
            ("verified", {"verified_at": ledger_fixture.NOW}),
            ("processing", {}),
            ("needs_attention", {}),
            ("processing", {}),
            ("online_completed", {"online_completed_at": ledger_fixture.NOW}),
            ("completed", {"completed_at": ledger_fixture.NOW}),
        ):
            with self.subTest(status=status):
                if status != "requested":
                    self.fixture.update(self.job_id, status=status, **changes)
                self.assertEqual(self.load().status, status)
                self.assertEqual(
                    self.connection.scalar(
                        text(
                            "SELECT status FROM ntubtob.account_erasure_jobs WHERE id=:id"
                        ),
                        {"id": self.job_id},
                    ),
                    status,
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

    def test_completed_detached_job_remains_readable_after_target_removed(self):
        self.fixture.update(
            self.job_id, status="verified", verified_at=ledger_fixture.NOW
        )
        self.fixture.update(self.job_id, status="processing")
        self.fixture.update(
            self.job_id,
            status="online_completed",
            online_completed_at=ledger_fixture.NOW,
            person_id=None,
        )
        self.fixture.update(
            self.job_id, status="completed", completed_at=ledger_fixture.NOW
        )
        self.connection.execute(
            text("DELETE FROM ntubtob.people WHERE id=:id"), {"id": self.fixture.person}
        )
        self.assertEqual(self.load().status, "completed")

    def test_cross_job_unknown_job_and_wrong_secret_rejected(self):
        other = self.fixture.job(
            person_id=self.fixture.other_person,
            receipt_secret_hash=hashlib.sha256(b"b" * 43).hexdigest(),
        )
        for values in (
            {"job_id": other},
            {"job_id": str(uuid4())},
            {"receipt_secret": "b" * 43},
        ):
            with (
                self.subTest(fields=tuple(values)),
                self.assertRaisesRegex(ErasureReceiptRejected, "receipt_unavailable"),
            ):
                self.load(**values)
        self.assertEqual(self.load(job_id=other, receipt_secret="b" * 43).job_id, other)
        self.assertEqual(self.load().job_id, self.job_id)

    def test_expired_receipt_rejected_without_extending_expiry(self):
        self.fixture.update(self.job_id, receipt_expires_at=NOW)
        with self.assertRaisesRegex(ErasureReceiptRejected, "receipt_unavailable"):
            self.load()
        self.assertEqual(
            self.connection.scalar(
                text(
                    "SELECT receipt_expires_at FROM ntubtob.account_erasure_jobs WHERE id=:id"
                ),
                {"id": self.job_id},
            ),
            NOW,
        )

    def test_mapper_routing_cannot_escape_checked_connection(self):
        other = create_mock_engine(
            "postgresql://", lambda *args, **kwargs: self.fail("wrong bind")
        )
        self.assertEqual(
            self.load(binds={AccountErasureJobRecord: other}).job_id, self.job_id
        )
