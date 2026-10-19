"""Actual candidate gate through repository calls, with rollback-only fixtures."""

import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from shared_module.mobile_api import AccountUnavailable
from sqlalchemy import text
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data import (
    identity_lifecycle,
    mobile_repository,
    repository,
)
from shared_lib.shared_module.portal_data.domain import AuthorizationError
from tests.portal_data import test_erasure_admin_recovery_schema as fixture


@unittest.skipUnless(fixture.ledger.DATABASE_URL, "isolated ledger URL not configured")
class ManagementSuspensionIntegrationTests(unittest.TestCase):
    setUpClass = classmethod(fixture.AdminRecoveryPostgresTests.setUpClass.__func__)
    tearDownClass = classmethod(
        fixture.AdminRecoveryPostgresTests.tearDownClass.__func__
    )
    apply = fixture.AdminRecoveryPostgresTests.apply

    def setUp(self):
        fixture.AdminRecoveryPostgresTests.setUp(self)
        # Earlier suites retain fictional people. Establish this scenario's sole
        # administrator within the outer rollback, without deleting any history.
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_access_level='basic' "
                "WHERE id<>:person AND portal_access_level='admin'"
            ),
            {"person": self.fixture.person},
        )

    def sessions(self, module):
        # Use real Sessions and the same checked database transaction, not a fake
        # gate. Each repository transaction is a savepoint under fixture rollback.
        return patch.object(
            module,
            "Session",
            side_effect=lambda *args, **kwargs: Session(
                bind=self.connection, join_transaction_mode="create_savepoint"
            ),
        )

    def suspend(self):
        self.apply()
        self.connection.execute(text("RESET ROLE"))

    def test_low_level_creation_works_before_and_rejects_after_suspension(self):
        repo = repository.PostgresTeamPortalRepository(self.engine)
        with self.sessions(repository):
            created = repo.create_person("Fictional pre-suspension person")
            self.assertGreater(created.id, 0)
            before = self.connection.scalar(text("SELECT count(*) FROM ntubtob.people"))
            self.suspend()
            with self.assertRaisesRegex(
                AuthorizationError, "management writes unavailable"
            ):
                repo.create_person("Fictional forbidden person")
            self.assertEqual(
                self.connection.scalar(text("SELECT count(*) FROM ntubtob.people")),
                before,
            )
            self.assertEqual(
                repo.get_person(created.id).display_name,
                "Fictional pre-suspension person",
            )

    def test_bootstrap_cannot_resume_but_other_person_self_profile_is_not_global_blocked(
        self,
    ):
        repo = identity_lifecycle.IdentityLifecycleRepository(self.engine)
        self.suspend()
        with self.sessions(identity_lifecycle):
            with self.assertRaisesRegex(
                AuthorizationError, "management writes unavailable"
            ):
                repo.bootstrap_zero_admin_member(
                    self.fixture.identity,
                    7101,
                    "Fictional bootstrap test",
                    str(uuid4()),
                )
            result = repo.update_profile(
                self.fixture.other_person,
                self.fixture.other_person,
                "Fictional self profile",
                str(uuid4()),
            )
            self.assertEqual(result.display_name, "Fictional self profile")
        self.assertEqual(
            self.connection.scalar(
                text("SELECT epoch FROM ntubtob.portal_authority_state")
            ),
            11,
        )

    def test_mobile_delivery_stops_before_adapter_even_with_default_flags(self):
        repo = mobile_repository.MobileRepository(self.engine)
        adapter = Mock()
        self.suspend()
        with self.sessions(mobile_repository):
            with self.assertRaisesRegex(
                AccountUnavailable, "management writes unavailable"
            ):
                repo.attempt_rejecting_delivery(
                    delivery_id=1, adapter=adapter, now=fixture.ledger.NOW
                )
        adapter.deliver.assert_not_called()
