"""Default-unused erasure gate; fake-only tests, no provider authorization claims."""

import unittest
from unittest.mock import MagicMock

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.erasure_guard import (
    ErasureAccessBlocked,
    ErasureGuardUnavailable,
    require_account_not_erasing,
)
from shared_lib.shared_module.portal_data.runtime import (
    ADMIN_LOCK_KEY,
    EVENT_SNAPSHOT_LOCK_KEY,
)
from tests.portal_data import test_erasure_ledger as ledger_fixture


class ErasureGuardTests(unittest.TestCase):
    def fixture(self, *, identity=(11, 7), person=7, jobs=()):
        session = MagicMock()
        session.in_transaction.return_value = True
        session.new = session.dirty = session.deleted = set()
        connection = session.connection.return_value
        connection.connection.dbapi_connection.autocommit = False
        connection.get_isolation_level.return_value = "READ COMMITTED"
        # The first two execute calls are canonical advisory locks.
        connection.scalars.return_value.all.return_value = [
            "0014_account_erasure_ledger"
        ]
        connection.execute.return_value.first.return_value = identity
        connection.scalar.side_effect = [False, False, person]
        connection.execute.return_value.all.return_value = list(jobs)
        return session, connection

    def test_requested_is_not_authorization_and_does_not_block(self):
        session, connection = self.fixture(jobs=[("requested",)])
        self.assertIsNone(
            require_account_not_erasing(session, person_id=7, identity_id=11)
        )
        sql = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertIn("pg_advisory_xact_lock", sql[0])
        self.assertIn("pg_advisory_xact_lock", sql[1])
        self.assertEqual(
            connection.execute.call_args_list[0].args[1], {"key": ADMIN_LOCK_KEY}
        )
        self.assertEqual(
            connection.execute.call_args_list[1].args[1],
            {"key": EVENT_SNAPSHOT_LOCK_KEY},
        )
        self.assertIn("FOR UPDATE", sql[2])
        self.assertIn("auth_identities", sql[-1])
        session.execute.assert_not_called()
        session.commit.assert_not_called()
        session.flush.assert_not_called()

    def test_verified_and_all_later_states_block(self):
        for status in (
            "verified",
            "processing",
            "needs_attention",
            "online_completed",
            "completed",
        ):
            with self.subTest(status=status):
                session, _ = self.fixture(jobs=[(status,)])
                with self.assertRaises(ErasureAccessBlocked):
                    require_account_not_erasing(session, person_id=7, identity_id=11)

    def test_unknown_status_fails_closed(self):
        session, _ = self.fixture(jobs=[("unexpected",)])
        with self.assertRaises(ErasureGuardUnavailable):
            require_account_not_erasing(session, person_id=7)

    def test_rls_filtered_or_unknown_ledger_visibility_is_not_empty_success(self):
        for value in (True, None):
            session, connection = self.fixture()
            connection.scalar.side_effect = [value]
            with self.assertRaisesRegex(
                ErasureGuardUnavailable, "unfiltered_ledger_required"
            ):
                require_account_not_erasing(session, person_id=7)
            self.assertEqual(connection.execute.call_count, 2)

    def test_filtered_or_unknown_identity_visibility_cannot_hide_owned_jobs(self):
        for value in (True, None):
            session, connection = self.fixture()
            connection.scalar.side_effect = [False, value]
            with self.assertRaisesRegex(
                ErasureGuardUnavailable, "unfiltered_identities_required"
            ):
                require_account_not_erasing(session, person_id=7)
            self.assertEqual(connection.execute.call_count, 2)

    def test_pending_target_requires_still_unlinked_identity(self):
        session, _ = self.fixture(identity=(11, None))
        require_account_not_erasing(session, identity_id=11)
        for identity in ((11, 7), None):
            session, _ = self.fixture(identity=identity)
            with self.assertRaises(ErasureGuardUnavailable):
                require_account_not_erasing(session, identity_id=11)

    def test_mismatched_person_or_missing_person_is_rejected(self):
        for identity, person in (((11, 9), 7), ((11, 7), None)):
            session, _ = self.fixture(identity=identity, person=person)
            with self.assertRaises(ErasureGuardUnavailable):
                require_account_not_erasing(session, person_id=7, identity_id=11)

    def test_invalid_input_is_rejected_before_connection(self):
        for values in ({}, {"person_id": True}, {"identity_id": 0}, {"person_id": "7"}):
            session, _ = self.fixture()
            with self.assertRaises(ErasureGuardUnavailable):
                require_account_not_erasing(session, **values)
            session.connection.assert_not_called()

    def test_no_transaction_or_pending_changes_are_rejected(self):
        for transaction, pending in ((False, set()), (True, {object()})):
            session, _ = self.fixture()
            session.in_transaction.return_value = transaction
            session.dirty = pending
            with self.assertRaises(ErasureGuardUnavailable):
                require_account_not_erasing(session, person_id=7)
            session.connection.assert_not_called()

    def test_autocommit_or_unknown_driver_state_is_rejected(self):
        for value in (True, None):
            session, connection = self.fixture()
            connection.connection.dbapi_connection.autocommit = value
            with self.assertRaises(ErasureGuardUnavailable):
                require_account_not_erasing(session, person_id=7)
            connection.execute.assert_not_called()

    def test_unknown_or_multiple_revisions_rejected(self):
        for revisions in (
            [],
            ["0013_account_deletion_requests"],
            ["0014_account_erasure_ledger", "other"],
        ):
            session, connection = self.fixture()
            connection.scalars.return_value.all.return_value = revisions
            with self.assertRaises(ErasureGuardUnavailable):
                require_account_not_erasing(session, person_id=7)

    def test_generation_candidate_revision_keeps_blocking_semantics(self):
        session, connection = self.fixture(jobs=[("verified",)])
        connection.scalars.return_value.all.return_value = ["0015_account_generations"]
        with self.assertRaises(ErasureAccessBlocked):
            require_account_not_erasing(session, person_id=7)

    def test_stale_snapshot_isolation_rejected_before_locking(self):
        session, connection = self.fixture()
        connection.get_isolation_level.return_value = "REPEATABLE READ"
        with self.assertRaisesRegex(ErasureGuardUnavailable, "read_committed_required"):
            require_account_not_erasing(session, person_id=7)
        connection.execute.assert_not_called()

    def test_storage_error_is_sanitized_without_commit_or_retry(self):
        session, connection = self.fixture()
        connection.execute.side_effect = SQLAlchemyError("fictional-private-detail")
        with self.assertRaises(ErasureGuardUnavailable) as error:
            require_account_not_erasing(session, person_id=7)
        self.assertNotIn("fictional-private-detail", str(error.exception))
        self.assertEqual(connection.execute.call_count, 1)
        session.commit.assert_not_called()


@unittest.skipUnless(
    ledger_fixture.DATABASE_URL, "isolated ledger test URL not configured"
)
class ErasureGuardPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ledger_fixture.ErasureLedgerPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.fixture = ledger_fixture.ErasureLedgerPostgresTests("runTest")
        self.fixture.engine = self.engine
        self.fixture.setUp()

    def tearDown(self):
        if self.fixture.transaction.is_active:
            self.fixture.transaction.rollback()
        self.fixture.connection.close()

    def check(self, **target):
        with (
            Session(
                bind=self.fixture.connection, join_transaction_mode="create_savepoint"
            ) as session,
            session.begin(),
        ):
            require_account_not_erasing(session, **target)

    def test_person_job_blocks_only_its_target_after_verification(self):
        job = self.fixture.job()
        self.check(person_id=self.fixture.person)
        self.fixture.update(job, status="verified", verified_at=ledger_fixture.NOW)
        with self.assertRaises(ErasureAccessBlocked):
            self.check(person_id=self.fixture.person)
        self.check(person_id=self.fixture.other_person)

    def test_pending_scope_and_linked_person_cover_same_identity_job(self):
        job = self.fixture.job(
            target_kind="pending_identity",
            person_id=None,
            auth_identity_id=self.fixture.identity,
        )
        self.fixture.update(job, status="verified", verified_at=ledger_fixture.NOW)
        with self.assertRaises(ErasureAccessBlocked):
            self.check(identity_id=self.fixture.identity)
        self.check(identity_id=self.fixture.other_identity)
        self.fixture.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person, status='linked' WHERE id=:identity"
            ),
            {"person": self.fixture.person, "identity": self.fixture.identity},
        )
        with self.assertRaises(ErasureGuardUnavailable):
            self.check(identity_id=self.fixture.identity)
        with self.assertRaises(ErasureAccessBlocked):
            self.check(person_id=self.fixture.person)

    def test_advisory_lock_is_owned_by_caller_transaction(self):
        self.check(person_id=self.fixture.person)
        with self.engine.begin() as other:
            self.assertFalse(
                other.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": ADMIN_LOCK_KEY},
                )
            )
        self.fixture.transaction.rollback()
        with self.engine.begin() as other:
            self.assertTrue(
                other.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": ADMIN_LOCK_KEY},
                )
            )
