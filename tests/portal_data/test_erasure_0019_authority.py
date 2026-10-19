"""Candidate0019 preserves persistent roles and erasure-aware admin counts."""

import unittest
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data import repository as portal
from shared_lib.shared_module.portal_data.domain import AuthorizationError
from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from tests.portal_data import test_erasure_admin_recovery_schema as fixture


@unittest.skipUnless(fixture.ledger.DATABASE_URL, "isolated ledger URL required")
class CandidateAuthorityTests(unittest.TestCase):
    setUpClass = classmethod(fixture.AdminRecoveryPostgresTests.setUpClass.__func__)
    tearDownClass = classmethod(
        fixture.AdminRecoveryPostgresTests.tearDownClass.__func__
    )
    setUp = fixture.AdminRecoveryPostgresTests.setUp
    apply = fixture.AdminRecoveryPostgresTests.apply

    def session(self):
        return Session(bind=self.connection, join_transaction_mode="create_savepoint")

    def test_persistent_mode_and_existing_admin_role_work_without_promotion(self):
        repo = IdentityLifecycleRepository(self.engine, authority_mode="persistent")
        with self.session() as session, session.begin():
            self.assertTrue(repo.authority_mode_is_ready(session=session))
            self.assertEqual(
                repo._require_admin(session, self.fixture.person).id,
                self.fixture.person,
            )
            self.assertFalse(
                IdentityLifecycleRepository(
                    self.engine, authority_mode="legacy_allowlist"
                ).authority_mode_is_ready(session=session)
            )

    def test_basic_and_officer_never_become_admin(self):
        repo = IdentityLifecycleRepository(self.engine, authority_mode="persistent")
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.fixture.other_person, "id": self.fixture.other_identity},
        )
        for access in ("basic", "officer"):
            with self.subTest(access=access):
                self.connection.execute(
                    text(
                        "UPDATE ntubtob.people SET portal_access_level=:access WHERE id=:id"
                    ),
                    {"access": access, "id": self.fixture.other_person},
                )
                with self.session() as session, session.begin():
                    with self.assertRaisesRegex(
                        AuthorizationError, "persistent administrator required"
                    ):
                        repo._require_admin(session, self.fixture.other_person)

    def test_verified_erasure_target_never_counts_as_surviving_admin(self):
        repo = IdentityLifecycleRepository(
            self.engine, authority_mode="persistent", erasure_checks_enabled=True
        )
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_access_level='basic' WHERE id<>:id"),
            {"id": self.fixture.person},
        )
        with self.session() as session, session.begin():
            self.assertEqual(repo._reachable_persistent_admin_count(session), 0)
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_access_level='admin' WHERE id=:id"),
            {"id": self.fixture.other_person},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:id"
            ),
            {"person": self.fixture.other_person, "id": self.fixture.other_identity},
        )
        with self.session() as session, session.begin():
            self.assertEqual(repo._reachable_persistent_admin_count(session), 1)

    def test_guest_reads_remain_available_but_suspension_blocks_writes(self):
        self.connection.execute(
            text("UPDATE ntubtob.people SET portal_access_level='basic' WHERE id<>:id"),
            {"id": self.fixture.person},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_access_level='officer' WHERE id=:id"
            ),
            {"id": self.fixture.other_person},
        )
        repo = portal.PostgresTeamPortalRepository(self.engine)
        with patch.object(
            portal, "Session", side_effect=lambda *a, **kw: self.session()
        ):
            before = repo.managed_guests(self.fixture.other_person)
            self.apply()
            self.connection.execute(text("RESET ROLE"))
            self.assertEqual(repo.managed_guests(self.fixture.other_person), before)
            with self.assertRaisesRegex(
                AuthorizationError, "management writes unavailable"
            ):
                repo.create_person("Fictional suspended runtime attempt")
