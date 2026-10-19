"""Offline fail-closed contracts for the candidate management suspension reader."""

import unittest
from unittest.mock import MagicMock, patch

from shared_module.portal_data import erasure_management_guard as guard
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError


class ManagementGuardTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock(spec=Connection)
        self.connection.closed = False
        self.connection.in_transaction.return_value = True
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.scalars.return_value = [guard.REVISION]
        self.connection.scalar.return_value = False
        self.operation = "00000000-0000-4000-8000-000000000001"
        self.job = "00000000-0000-4000-8000-000000000002"
        self.generation = "00000000-0000-4000-8000-000000000003"
        self.scope = "a" * 64
        self.rows = [(1, "persistent", 2, None)]
        self.evidence = [(self.operation, self.job, self.generation, self.scope, 1, 2)]
        self.connection.execute.return_value.all.side_effect = lambda: self.rows
        lock_patch = patch.object(guard, "acquire_admin_event_locks")
        self.locks = lock_patch.start()
        self.addCleanup(lock_patch.stop)

    def read(self):
        return guard.read_applied_admin_suspension(
            self.connection,
            job_id=self.job,
            generation=self.generation,
            scope_hash=self.scope,
        )

    def prepare_evidence(self):
        self.connection.execute.return_value.all.side_effect = [
            [(1, "persistent", 2, self.operation)],
            self.evidence,
        ]

    def test_available_requires_canonical_locks_and_locked_state(self):
        guard.require_management_writes_available(self.connection)
        self.locks.assert_called_once_with(self.connection)
        sql = str(self.connection.execute.call_args.args[0])
        self.assertIn("FOR UPDATE", sql)
        self.connection.commit.assert_not_called()

    def test_any_non_null_pointer_suspends_even_broken_evidence(self):
        for pointer in (self.operation, "invalid", ""):
            with self.subTest(pointer=pointer):
                self.rows = [(1, "persistent", 2, pointer)]
                with self.assertRaises(guard.ManagementWritesSuspended):
                    guard.require_management_writes_available(self.connection)

    def test_transaction_and_isolation_are_required(self):
        for attribute, invalid in (("closed", True),):
            setattr(self.connection, attribute, invalid)
            with self.assertRaisesRegex(
                guard.ManagementGuardUnavailable, "transaction_required"
            ):
                guard.require_management_writes_available(self.connection)
        self.connection.closed = False
        self.connection.get_isolation_level.return_value = "REPEATABLE READ"
        with self.assertRaises(guard.ManagementGuardUnavailable):
            self.read()
        self.locks.assert_not_called()

    def test_missing_transaction_autocommit_and_wrong_connection_fail_closed(self):
        with self.assertRaises(guard.ManagementGuardUnavailable):
            guard.require_management_writes_available(object())
        self.connection.in_transaction.return_value = False
        with self.assertRaises(guard.ManagementGuardUnavailable):
            self.read()
        self.connection.in_transaction.return_value = True
        for value in (True, None):
            self.connection.connection.dbapi_connection.autocommit = value
            with self.assertRaises(guard.ManagementGuardUnavailable):
                self.read()
        self.locks.assert_not_called()

    def test_unknown_revision_and_rls_are_not_permission(self):
        for revisions in ([], ["0018_erasure_privacy_mutation"], [guard.REVISION] * 2):
            self.connection.scalars.return_value = revisions
            with self.assertRaisesRegex(
                guard.ManagementGuardUnavailable, "schema_not_ready"
            ):
                self.read()

        self.connection.scalars.return_value = [guard.REVISION]
        for result in (True, None):
            self.connection.scalar.return_value = result
            with self.assertRaisesRegex(
                guard.ManagementGuardUnavailable, "unfiltered_authority_required"
            ):
                self.read()

    def test_second_table_rls_also_blocks_unfiltered_evidence(self):
        self.connection.scalar.side_effect = [False, True]
        with self.assertRaisesRegex(
            guard.ManagementGuardUnavailable, "unfiltered_authority_required"
        ):
            self.read()
        self.connection.execute.assert_not_called()

    def test_single_persistent_positive_epoch_is_required(self):
        for rows in (
            [],
            [(1, "legacy_allowlist", 1, None)],
            [(1, "persistent", 0, None)],
            [(1, "persistent", True, None)],
            [(1, "persistent", 1, None)] * 2,
        ):
            self.rows = rows
            with self.assertRaisesRegex(
                guard.ManagementGuardUnavailable, "authority_state_unavailable"
            ):
                guard.require_management_writes_available(self.connection)

    def test_exact_bound_evidence_is_read_without_mutation(self):
        self.prepare_evidence()
        result = self.read()
        self.assertEqual(result.job_id, self.job)
        self.assertEqual(result.authority_epoch, 2)
        self.assertNotIn(self.job, repr(result))
        for call in self.connection.execute.call_args_list:
            self.assertTrue(str(call.args[0]).startswith("SELECT "))

    def test_mismatched_or_missing_evidence_never_authorizes(self):
        original = self.evidence[0]
        for index, value in (
            (0, self.job),
            (1, self.operation),
            (2, self.operation),
            (3, "b" * 64),
            (4, 0),
            (4, True),
            (5, 3),
        ):
            row = list(original)
            row[index] = value
            self.evidence = [tuple(row)]
            self.prepare_evidence()
            with self.assertRaisesRegex(
                guard.ManagementGuardUnavailable, "suspension_binding_unavailable"
            ):
                self.read()
        self.evidence = []
        self.prepare_evidence()
        with self.assertRaises(guard.ManagementGuardUnavailable):
            self.read()

    def test_no_suspension_is_not_an_approval(self):
        with self.assertRaisesRegex(
            guard.ManagementGuardUnavailable, "invalid_binding"
        ):
            self.read()

    def test_duplicate_evidence_and_epoch_mismatch_are_not_approval(self):
        self.evidence *= 2
        self.prepare_evidence()
        with self.assertRaises(guard.ManagementGuardUnavailable):
            self.read()
        self.evidence = [(self.operation, self.job, self.generation, self.scope, 1, 2)]
        self.connection.execute.return_value.all.side_effect = [
            [(1, "persistent", 3, self.operation)],
            self.evidence,
        ]
        with self.assertRaises(guard.ManagementGuardUnavailable):
            self.read()

    def test_invalid_input_never_queries(self):
        self.job = "not-a-uuid"
        with self.assertRaises(guard.ManagementGuardUnavailable):
            self.read()
        self.connection.execute.assert_not_called()
        self.locks.assert_not_called()

    def test_database_failure_has_only_fixed_safe_message(self):
        self.connection.execute.side_effect = SQLAlchemyError("private-sentinel")
        for action in (
            self.read,
            lambda: guard.require_management_writes_available(self.connection),
        ):
            with self.assertRaisesRegex(
                guard.ManagementGuardUnavailable, "^authority_query_failed$"
            ):
                action()
