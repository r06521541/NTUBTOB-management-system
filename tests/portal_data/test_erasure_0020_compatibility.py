"""Exact0020 recovery capability on fictional, rollback-only distinct roles.

Reuse the existing0019 authority assertions, not a new operator or schema reset.
The schema setup is privileged; only the unchanged approval function is exercised
as the separately granted operator. No real identities or external effects.
"""

import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.portal_data import test_erasure_admin_recovery_schema as recovery


@unittest.skipUnless(recovery.ledger.DATABASE_URL, "isolated ledger URL required")
class IntakeAuthorityPostgresTests(unittest.TestCase):
    setUpClass = classmethod(recovery.AdminRecoveryPostgresTests.setUpClass.__func__)
    tearDownClass = classmethod(
        recovery.AdminRecoveryPostgresTests.tearDownClass.__func__
    )
    apply = recovery.AdminRecoveryPostgresTests.apply
    rejected = recovery.AdminRecoveryPostgresTests.rejected
    state = recovery.AdminRecoveryPostgresTests.state

    def setUp(self):
        recovery.AdminRecoveryPostgresTests.setUp(self)
        config = Config(str(recovery.ROOT / "alembic.ini"))
        config.attributes["connection"] = self.connection
        command.upgrade(config, "0020_erasure_intake")
        # Match the trusted schema owner: SELECT alone cannot acquire SHARE.
        # Runtime/operator receive no extra rights from this fixture correction.
        self.connection.execute(
            text(f'ALTER TABLE ntubtob.account_erasure_intakes OWNER TO "{self.owner}"')
        )

    test_acl_and_runtime_rejection = (
        recovery.AdminRecoveryPostgresTests.test_acl_three_roles_and_named_default_grants_are_removed
    )
    test_atomic_operation_and_session_binding = (
        recovery.AdminRecoveryPostgresTests.test_exact_operation_pointer_epoch_and_session_user_are_atomic
    )
    test_wrong_scope_and_replay_reject = (
        recovery.AdminRecoveryPostgresTests.test_wrong_status_generation_epoch_target_and_replay_reject
    )
    test_runtime_cannot_clear_or_replace_suspension = (
        recovery.AdminRecoveryPostgresTests.test_runtime_table_update_cannot_set_clear_or_replace_pointer
    )
    test_recovery_rolls_back_atomically = (
        recovery.AdminRecoveryPostgresTests.test_rollback_after_success_removes_operation_and_pointer_together
    )
    test_management_guard_reads_exact_durable_approval = (
        recovery.AdminRecoveryPostgresTests.test_real_management_guard_and_exact_bound_reader
    )


if __name__ == "__main__":
    unittest.main()
