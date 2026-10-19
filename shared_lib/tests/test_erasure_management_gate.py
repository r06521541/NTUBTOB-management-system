"""Compatibility dispatch is not permission to bypass a candidate suspension."""

import unittest
from unittest.mock import MagicMock, patch

from shared_module.portal_data import erasure_management_gate as gate
from shared_module.portal_data.erasure_management_guard import (
    REVISION,
    ManagementGuardUnavailable,
    ManagementWritesSuspended,
)
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


class ManagementMutationGateTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock(spec=Session)
        self.session.in_transaction.return_value = True
        self.session.new = self.session.dirty = self.session.deleted = set()
        self.connection = MagicMock(spec=Connection)
        self.session.connection.return_value = self.connection
        self.connection.closed = False
        self.connection.in_transaction.return_value = True
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.connection.dbapi_connection.autocommit = False
        self.connection.scalars.return_value.all.return_value = [REVISION]
        for name in (
            "acquire_admin_event_locks",
            "require_management_writes_available",
        ):
            patcher = patch.object(gate, name)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def test_candidate_uses_same_connection_under_canonical_locks(self):
        order = []
        self.acquire_admin_event_locks.side_effect = lambda c: order.append("locks")
        self.connection.scalars.side_effect = lambda sql: (
            order.append("revision") or MagicMock(all=lambda: [REVISION])
        )
        self.require_management_writes_available.side_effect = lambda c: order.append(
            "state"
        )
        gate.require_management_mutation(self.session)
        self.assertEqual(order, ["locks", "revision", "state"])
        self.require_management_writes_available.assert_called_once_with(
            self.connection
        )
        self.session.flush.assert_not_called()
        self.session.commit.assert_not_called()

    def test_each_legacy_revision_never_queries_new_pointer(self):
        self.assertEqual(len(gate.LEGACY_REVISIONS), 18)
        for revision in gate.LEGACY_REVISIONS:
            self.connection.scalars.return_value.all.return_value = [revision]
            gate.require_management_mutation(self.session)
        self.require_management_writes_available.assert_not_called()
        self.connection.execute.assert_not_called()

    def test_unknown_empty_and_multiple_revisions_fail_closed(self):
        for values in (
            [],
            ["future"],
            [REVISION, REVISION],
            ["0018_erasure_privacy_mutation", REVISION],
        ):
            self.connection.scalars.return_value.all.return_value = values
            with self.assertRaisesRegex(ManagementGuardUnavailable, "schema_not_ready"):
                gate.require_management_mutation(self.session)
        self.require_management_writes_available.assert_not_called()

    def test_dirty_or_absent_transaction_rejected_before_connection(self):
        for attribute in ("new", "dirty", "deleted"):
            setattr(self.session, attribute, {object()})
            with self.assertRaises(ManagementGuardUnavailable):
                gate.require_management_mutation(self.session)
            setattr(self.session, attribute, set())
        self.session.in_transaction.return_value = False
        with self.assertRaises(ManagementGuardUnavailable):
            gate.require_management_mutation(self.session)
        self.session.connection.assert_not_called()

    def test_legacy_also_requires_checked_connection(self):
        self.connection.scalars.return_value.all.return_value = [
            "0004_phase_c_identity_lifecycle"
        ]
        self.connection.get_isolation_level.return_value = "REPEATABLE READ"
        with self.assertRaises(ManagementGuardUnavailable):
            gate.require_management_mutation(self.session)
        self.connection.get_isolation_level.return_value = "READ COMMITTED"
        self.connection.connection.dbapi_connection.autocommit = True
        with self.assertRaises(ManagementGuardUnavailable):
            gate.require_management_mutation(self.session)
        self.acquire_admin_event_locks.assert_not_called()

    def test_suspension_and_storage_errors_never_become_legacy_success(self):
        self.require_management_writes_available.side_effect = (
            ManagementWritesSuspended("management_writes_suspended")
        )
        with self.assertRaises(ManagementWritesSuspended):
            gate.require_management_mutation(self.session)
        self.connection.scalars.side_effect = SQLAlchemyError("private-sentinel")
        with self.assertRaisesRegex(
            ManagementGuardUnavailable, "^authority_query_failed$"
        ):
            gate.require_management_mutation(self.session)
