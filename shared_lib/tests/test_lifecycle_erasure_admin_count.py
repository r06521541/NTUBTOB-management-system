"""Fail-closed administrator count preconditions without a database."""

import unittest
from unittest.mock import MagicMock

from shared_module.portal_data.domain import AuthorizationError
from shared_module.portal_data.identity_lifecycle import IdentityLifecycleRepository
from sqlalchemy.exc import SQLAlchemyError


class ErasureAdminCountTests(unittest.TestCase):
    def setUp(self):
        self.repo = IdentityLifecycleRepository(None, erasure_checks_enabled=True)
        self.session = MagicMock()
        self.session.in_transaction.return_value = True
        self.connection = self.session.connection.return_value
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.scalars.return_value.all.return_value = [
            "0016_erasure_cancellation"
        ]
        self.connection.scalar.side_effect = [False, False, False, 1]

    def test_checked_core_count_does_not_flush_or_use_orm_queries(self):
        self.assertEqual(self.repo._reachable_persistent_admin_count(self.session), 1)
        self.session.flush.assert_not_called()
        self.session.scalar.assert_not_called()
        self.assertEqual(self.connection.execute.call_count, 2)  # canonical locks

    def test_filtered_or_unknown_rls_never_looks_like_zero_admins(self):
        for index in range(3):
            for filtered in (True, None):
                with self.subTest(index=index, filtered=filtered):
                    self.connection.scalar.side_effect = [False] * index + [filtered]
                    with self.assertRaisesRegex(
                        AuthorizationError, "^administrator availability unavailable$"
                    ):
                        self.repo._reachable_persistent_admin_count(self.session)

    def test_wrong_revision_or_isolation_and_storage_failure_are_not_zero(self):
        self.connection.scalars.return_value.all.return_value = [
            "0013_account_deletion_requests"
        ]
        with self.assertRaises(AuthorizationError):
            self.repo._reachable_persistent_admin_count(self.session)
        self.connection.get_isolation_level.return_value = "REPEATABLE READ"
        with self.assertRaises(AuthorizationError):
            self.repo._reachable_persistent_admin_count(self.session)
        self.connection.get_isolation_level.side_effect = SQLAlchemyError(
            "private-sentinel"
        )
        with self.assertRaisesRegex(
            AuthorizationError, "^administrator availability unavailable$"
        ):
            self.repo._reachable_persistent_admin_count(self.session)

    def test_default_off_uses_legacy_count_without_ledger_connection(self):
        self.session.scalar.return_value = 2
        self.assertEqual(
            IdentityLifecycleRepository(None)._reachable_persistent_admin_count(
                self.session
            ),
            2,
        )
        self.session.connection.assert_not_called()

    def test_intake_revision_excludes_verified_intakes_on_same_checked_connection(self):
        self.connection.scalars.return_value.all.return_value = ["0020_erasure_intake"]
        self.connection.scalar.side_effect = [False, False, False, False, 1]
        self.assertEqual(self.repo._reachable_persistent_admin_count(self.session), 1)
        sql = str(self.connection.scalar.call_args.args[0])
        self.assertIn("ntubtob.account_erasure_intakes", sql)
        self.assertIn("status='verified'", sql)
        self.assertIn("j.person_id=p.id", sql)
        self.assertIn("owned.person_id=p.id", sql)
        self.session.scalar.assert_not_called()

    def test_intake_rls_cannot_hide_erasing_admins(self):
        self.connection.scalars.return_value.all.return_value = ["0020_erasure_intake"]
        self.connection.scalar.side_effect = [False, False, False, True]
        with self.assertRaises(AuthorizationError):
            self.repo._reachable_persistent_admin_count(self.session)
