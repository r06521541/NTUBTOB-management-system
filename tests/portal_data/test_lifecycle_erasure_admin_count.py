"""Fictional last-admin protection counts only currently usable accounts."""

import unittest
from unittest.mock import patch

from shared_module.portal_data.domain import ConflictError
from shared_module.portal_data.identity_lifecycle import IdentityLifecycleRepository
from shared_module.portal_data.models import PersonRecord
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.portal_data import test_erasure_ledger as ledger
from tests.portal_data import test_lifecycle_erasure_gate as fixture


@unittest.skipUnless(ledger.DATABASE_URL, "isolated ledger URL required")
class ErasureAdminCountPostgresTests(unittest.TestCase):
    setUpClass = classmethod(
        fixture.LifecycleErasureGatePostgresTests.setUpClass.__func__
    )
    tearDownClass = classmethod(
        fixture.LifecycleErasureGatePostgresTests.tearDownClass.__func__
    )
    tearDown = fixture.LifecycleErasureGatePostgresTests.tearDown

    def setUp(self):
        fixture.LifecycleErasureGatePostgresTests.setUp(self)
        self.connection.execute(
            text(
                "UPDATE ntubtob.people SET portal_access_level='admin' WHERE id IN (:first,:second)"
            ),
            {"first": self.fixture.person, "second": self.fixture.other_person},
        )
        self.connection.execute(
            text(
                "UPDATE ntubtob.auth_identities SET person_id=:person,status='linked' WHERE id=:identity"
            ),
            {
                "person": self.fixture.other_person,
                "identity": self.fixture.other_identity,
            },
        )

    def session(self):
        return Session(bind=self.connection, join_transaction_mode="create_savepoint")

    def test_requested_still_counts_verified_does_not_and_default_off_is_unchanged(
        self,
    ):
        job = self.fixture.job()
        with self.session() as session, session.begin():
            self.assertEqual(self.repo._reachable_persistent_admin_count(session), 2)
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        with self.session() as session, session.begin():
            self.assertEqual(self.repo._reachable_persistent_admin_count(session), 1)
            self.assertEqual(
                IdentityLifecycleRepository(None)._reachable_persistent_admin_count(
                    session
                ),
                2,
            )
            for exclusion in (
                {"excluding_person_id": self.fixture.other_person},
                {"excluding_identity_id": self.fixture.other_identity},
            ):
                self.assertEqual(
                    self.repo._reachable_persistent_admin_count(session, **exclusion), 0
                )
                with self.assertRaises(ConflictError):
                    self.repo._assert_reachable_admin_remains(session, **exclusion)

    def test_enabled_core_count_never_autoflushes_unrelated_pending_changes(self):
        with self.session() as session, session.begin():
            person = session.get(PersonRecord, self.fixture.person)
            person.display_name = None  # Would violate NOT NULL if autoflushed.
            self.assertEqual(self.repo._reachable_persistent_admin_count(session), 2)
            self.assertTrue(session.dirty)
            session.expire(person)

    def test_demotion_cannot_rely_on_verified_erasing_other_administrator(self):
        job = self.fixture.job()
        self.fixture.update(job, status="verified", verified_at=ledger.NOW)
        with (
            patch.object(self.repo, "_require_admin"),
            self.assertRaisesRegex(ConflictError, "last reachable administrator"),
        ):
            self.repo.change_admin_access(
                self.fixture.person,
                self.fixture.other_person,
                "basic",
                1,
                "Fictional demotion",
                "fictional-request",
            )
        self.assertEqual(
            self.connection.scalar(
                text("SELECT portal_access_level FROM ntubtob.people WHERE id=:id"),
                {"id": self.fixture.other_person},
            ),
            "admin",
        )
