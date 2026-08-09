import os
import unittest

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools import portal_data_production_bootstrap_candidate_diagnostic as diagnostic
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class CandidateDiagnosticPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        setup_legacy_fixture()
        command.upgrade(Config("alembic.ini"), "head")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    TRUNCATE TABLE
                      ntubtob.identity_review_messages,
                      ntubtob.identity_review_threads,
                      ntubtob.access_audit,
                      ntubtob.person_qualifications,
                      ntubtob.auth_identities,
                      ntubtob.line_users,
                      ntubtob.members,
                      ntubtob.people
                    RESTART IDENTITY CASCADE;
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status, version,
                       created_at, updated_at)
                    VALUES ('Fake Candidate', 'basic', 'inactive', 1, now(), now());
                    INSERT INTO ntubtob.members (id, name, person_id)
                    SELECT 7001, 'Fake Member', id FROM ntubtob.people;
                    """
                )
            )

    def _state(self, allowlist=None):
        with Session(self.engine) as session, session.begin():
            session.execute(text("SET TRANSACTION READ ONLY"))
            return diagnostic._candidate_state(session, allowlist or {7001})

    def test_inactive_unlinked_candidate_is_redacted(self):
        self.assertEqual(
            self._state(),
            {
                "allowlisted_member": "one",
                "person_state": "inactive",
                "reliable_line_identity": "none",
                "pending_review_thread": "zero",
                "legacy_line_link": "zero",
                "active_team_player": "zero",
                "bootstrap_audit": "zero",
            },
        )

    def test_pending_review_thread_is_counted_without_linking_to_member(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.line_users
                      (nickname, line_user_id, member_id, has_replied, ignored)
                    VALUES ('Fake Pending', 'fake-pending-subject', NULL, false, false);
                    WITH identity AS (
                      INSERT INTO ntubtob.auth_identities
                        (provider, provider_subject, person_id, status, created_at, updated_at)
                      VALUES ('line', 'fake-pending-subject', NULL, 'pending', now(), now())
                      RETURNING id
                    )
                    INSERT INTO ntubtob.identity_review_threads
                      (auth_identity_id, status, last_activity_at, created_at, updated_at)
                    SELECT id, 'open', now(), now(), now() FROM identity;
                    """
                )
            )
        state = self._state()
        self.assertEqual(state["pending_review_thread"], "one")
        self.assertEqual(state["legacy_line_link"], "zero")
        self.assertEqual(state["reliable_line_identity"], "pending_unlinked")

    def test_linked_relationship_qualification_and_audit_are_classified(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE ntubtob.people SET portal_status='active';
                    INSERT INTO ntubtob.line_users
                      (nickname, line_user_id, member_id, has_replied, ignored)
                    VALUES ('Fake Linked', 'fake-linked-subject', 7001, false, false);
                    WITH person AS (SELECT id FROM ntubtob.people), identity AS (
                      INSERT INTO ntubtob.auth_identities
                        (provider, provider_subject, person_id, status, created_at, updated_at)
                      SELECT 'line', 'fake-linked-subject', id, 'linked', now(), now()
                      FROM person RETURNING id, person_id
                    )
                    INSERT INTO ntubtob.access_audit
                      (action, actor_person_id, target_person_id, auth_identity_id,
                       reason, request_id, created_at)
                    SELECT 'identity_linked', NULL, person_id, id,
                           :reason, 'task086-fake-audit', now() FROM identity;
                    INSERT INTO ntubtob.person_qualifications
                      (person_id, qualification, status, reason, created_at, updated_at)
                    SELECT id, 'team_player', 'active', 'fake qualification', now(), now()
                    FROM ntubtob.people;
                    """
                ),
                {"reason": diagnostic.BOOTSTRAP_REASON},
            )
        state = self._state()
        self.assertEqual(state["person_state"], "active")
        self.assertEqual(state["reliable_line_identity"], "linked_same_person")
        self.assertEqual(state["legacy_line_link"], "one")
        self.assertEqual(state["active_team_player"], "one")
        self.assertEqual(state["bootstrap_audit"], "one")

    def test_allowlist_ambiguity_is_fail_closed(self):
        with self.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO ntubtob.members (id, name) VALUES (7002, 'Other')")
            )
        state = self._state({7001, 7002})
        self.assertEqual(state["allowlisted_member"], "other")
        self.assertEqual(state["person_state"], "other")

    def test_absent_blocked_and_linked_other_person_states(self):
        with self.engine.begin() as connection:
            connection.execute(text("UPDATE ntubtob.members SET person_id=NULL"))
        self.assertEqual(self._state()["person_state"], "absent")
        with self.engine.begin() as connection:
            person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status, version,
                       created_at, updated_at)
                    VALUES ('Blocked Candidate', 'basic', 'blocked', 1, now(), now())
                    RETURNING id
                    """
                )
            )
            other_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status, version,
                       created_at, updated_at)
                    VALUES ('Other Person', 'basic', 'active', 1, now(), now())
                    RETURNING id
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE ntubtob.members SET person_id=:person_id;
                    INSERT INTO ntubtob.line_users
                      (nickname, line_user_id, member_id, has_replied, ignored)
                    VALUES ('Other Link', 'fake-other-subject', 7001, false, false);
                    INSERT INTO ntubtob.auth_identities
                      (provider, provider_subject, person_id, status, created_at, updated_at)
                    VALUES ('line', 'fake-other-subject', :other_id, 'linked', now(), now());
                    """
                ),
                {"person_id": person_id, "other_id": other_id},
            )
        state = self._state()
        self.assertEqual(state["person_state"], "blocked")
        self.assertEqual(state["reliable_line_identity"], "linked_other_person")


if __name__ == "__main__":
    unittest.main()
