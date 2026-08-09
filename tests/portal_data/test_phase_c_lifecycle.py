from __future__ import annotations

import os
import threading
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from shared_lib.shared_module.portal_data.domain import (
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tools.portal_data_phase_c_evidence import ARTIFACTS as EVIDENCE_ARTIFACTS
from tools.portal_data_phase_c_evidence import PhaseCEvidenceError
from tools.portal_data_phase_c_evidence import (
    verify_artifacts as verify_evidence_artifacts,
)
from tools.portal_data_phase_c_evidence import verify_sql as verify_evidence_sql
from tools.portal_data_phase_c_migration import (
    ARTIFACT,
    CHECKSUM,
    verify_artifact,
    verify_sql,
)
from tools.setup_portal_data_legacy import main as setup_legacy_fixture

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


class PhaseCArtifactTests(unittest.TestCase):
    def test_phase_c_artifact_is_deterministic_and_checksummed(self):
        verify_artifact()

    def test_phase_c_artifact_rejects_mutation(self):
        sql = ARTIFACT.read_text(encoding="utf-8")
        checksum = CHECKSUM.read_text(encoding="ascii").split()[0]
        with self.assertRaises(Exception):
            verify_sql(
                sql.replace("ADD COLUMN formal_name", "ADD COLUMN other"), checksum
            )

    def test_phase_c_evidence_is_checksummed_and_read_only(self):
        verify_evidence_artifacts()
        sql = EVIDENCE_ARTIFACTS[0].read_text(encoding="utf-8")
        with self.assertRaises(PhaseCEvidenceError):
            verify_evidence_sql(sql.replace("ROLLBACK;", "DELETE FROM ntubtob.people;"))


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class PhaseCLifecyclePostgresTests(unittest.TestCase):
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
                      ntubtob.game_attendance_replies,
                      ntubtob.line_users,
                      ntubtob.cancellations,
                      ntubtob.games,
                      ntubtob.members,
                      ntubtob.people
                    RESTART IDENTITY CASCADE;
                    INSERT INTO ntubtob.attendance_reply_types (id, description)
                    VALUES (1, 'yes'), (2, 'no'), (3, 'maybe'), (4, 'late'), (5, 'none')
                    ON CONFLICT (id) DO NOTHING;
                    """
                )
            )
            admin_person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, formal_name, portal_access_level, portal_status,
                       version, created_at, updated_at)
                    VALUES ('Fake Admin', 'Admin Formal', 'basic', 'active', 1, now(), now())
                    RETURNING id
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.members (id, name, person_id)
                    VALUES (7001, 'Fake Admin Member', :person_id);
                    INSERT INTO ntubtob.auth_identities
                      (provider, provider_subject, person_id, status, created_at, updated_at)
                    VALUES ('line', 'fake-admin-subject', :person_id, 'linked', now(), now());
                    """
                ),
                {"person_id": admin_person_id},
            )
        self.admin_person_id = admin_person_id
        self.repository = IdentityLifecycleRepository(self.engine, {7001})

    def _pending(self, suffix: str = "one"):
        return self.repository.ensure_pending_line_identity(
            f"fake-pending-{suffix}", "Fake Applicant", f"pending-{suffix}"
        )

    def test_schema_has_next_head_rls_and_attendance_person_fk(self):
        inspector = inspect(self.engine)
        self.assertIn(
            "person_id",
            {
                column["name"]
                for column in inspector.get_columns(
                    "game_attendance_replies", schema="ntubtob"
                )
            },
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT version_num FROM ntubtob.alembic_version")
                ),
                "0004_phase_c_identity_lifecycle",
            )
            rls = dict(
                connection.execute(
                    text(
                        "SELECT relname, relrowsecurity FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='ntubtob' AND c.relkind='r' "
                        "AND relname LIKE 'identity_review_%'"
                    )
                ).all()
            )
            self.assertEqual(
                rls, {"identity_review_messages": True, "identity_review_threads": True}
            )

    def test_phase_c_postcheck_has_no_failed_gate(self):
        sql = EVIDENCE_ARTIFACTS[1].read_text(encoding="utf-8")
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                cursor.execute(sql.rsplit("ROLLBACK;", 1)[0])
                rows = cursor.fetchall()
                cursor.execute("ROLLBACK")
        finally:
            raw.close()
        self.assertTrue(rows)
        self.assertEqual(
            [
                (metric, actual, expected)
                for metric, actual, expected in rows
                if actual != expected
            ],
            [],
        )

    def test_unresolved_attendance_aborts_migration_atomically(self):
        config = Config("alembic.ini")
        command.downgrade(config, "0003_legacy_bigint_activity_game")
        try:
            with self.engine.begin() as connection:
                game_id = connection.scalar(
                    text(
                        "INSERT INTO ntubtob.games (start_datetime) "
                        "VALUES (now() + interval '1 day') RETURNING id"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO ntubtob.game_attendance_replies "
                        "(game_id, user_id, member_id, reply, updated_at) "
                        "VALUES (:game_id, NULL, NULL, 1, now())"
                    ),
                    {"game_id": game_id},
                )
            with self.assertRaises(Exception):
                command.upgrade(config, "head")
            with self.engine.connect() as connection:
                self.assertEqual(
                    connection.scalar(
                        text("SELECT version_num FROM ntubtob.alembic_version")
                    ),
                    "0003_legacy_bigint_activity_game",
                )
                self.assertFalse(
                    connection.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                            "WHERE table_schema='ntubtob' AND table_name='people' "
                            "AND column_name='formal_name')"
                        )
                    )
                )
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "DELETE FROM ntubtob.game_attendance_replies "
                        "WHERE member_id IS NULL"
                    )
                )
            command.upgrade(config, "head")

    def test_pending_conversation_throttle_ignore_and_unignore(self):
        pending = self._pending()
        now = datetime.now(timezone.utc)
        self.repository.post_review_message(
            pending.identity.id, "Please review", "review-one", now=now
        )
        with self.assertRaises(ConflictError):
            self.repository.post_review_message(
                pending.identity.id,
                "Too soon",
                "review-two",
                now=now + timedelta(hours=23, minutes=59),
            )
        self.repository.set_ignored(
            self.admin_person_id,
            pending.identity.id,
            True,
            "Applicant requested later review",
            "ignore-one",
        )
        self.repository.set_ignored(
            self.admin_person_id,
            pending.identity.id,
            True,
            "Applicant requested later review",
            "ignore-one",
        )
        with self.engine.begin() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.access_audit "
                        "WHERE request_id='ignore-one' AND action='identity_ignored'"
                    )
                ),
                1,
            )
        self.repository.set_ignored(
            self.admin_person_id,
            pending.identity.id,
            False,
            "Applicant returned for review",
            "unignore-one",
        )
        with self.engine.begin() as connection:
            self.assertFalse(
                connection.scalar(
                    text(
                        "SELECT ignored FROM ntubtob.line_users "
                        "WHERE line_user_id='fake-pending-one'"
                    )
                )
            )

    def test_non_member_guest_has_no_fake_member_and_is_excluded_after_expiry(self):
        pending = self._pending("guest")
        now = datetime.now(timezone.utc)
        principal = self.repository.approve_non_member(
            self.admin_person_id,
            pending.identity.id,
            "Guest Display",
            "Approve bounded guest",
            "approve-guest",
            formal_name="Guest Formal",
            qualifications={"guest_player"},
            guest_valid_from=now - timedelta(days=1),
            guest_valid_until=now + timedelta(days=7),
        )
        with self.engine.begin() as connection:
            self.assertIsNone(
                connection.scalar(
                    text(
                        "SELECT member_id FROM ntubtob.line_users WHERE line_user_id='fake-pending-guest'"
                    )
                )
            )
            game_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.games (start_datetime)
                    VALUES (:start_datetime) RETURNING id
                    """
                ),
                {"start_datetime": now + timedelta(days=1)},
            )
        self.assertTrue(self.repository.reply_to_game(principal.person.id, game_id, 1))
        self.assertFalse(self.repository.reply_to_game(principal.person.id, game_id, 1))
        summary = self.repository.attendance_summary(game_id)
        self.assertEqual(summary.team_player_total, 0)
        self.assertEqual(summary.participants[0]["name"], "Guest Formal")
        self.assertEqual(
            self.repository.attendance_summary(
                game_id, use_display_name=True
            ).participants[0]["name"],
            "Guest Display",
        )
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ntubtob.people SET formal_name=NULL WHERE id=:person_id"),
                {"person_id": principal.person.id},
            )
        self.assertEqual(
            self.repository.attendance_summary(game_id).participants[0]["name"],
            "Guest Display",
        )
        self.assertTrue(self.repository.reply_to_game(principal.person.id, game_id, 5))
        self.assertEqual(self.repository.attendance_summary(game_id).participants, ())

    def test_guest_period_over_five_years_fails_in_domain_and_database(self):
        start = datetime(2024, 2, 29, tzinfo=timezone.utc)
        with self.assertRaises(ValidationError):
            from shared_lib.shared_module.portal_data.domain import (
                validate_guest_period,
            )

            validate_guest_period(start, datetime(2029, 3, 1, tzinfo=timezone.utc))
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO ntubtob.person_qualifications
                          (person_id, qualification, status, valid_from, valid_until,
                           reason, created_at, updated_at)
                        VALUES (:person_id, 'guest_player', 'active', :start, :finish,
                                'Invalid oversized period', now(), now())
                        """
                    ),
                    {
                        "person_id": self.admin_person_id,
                        "start": start,
                        "finish": datetime(2029, 3, 1, tzinfo=timezone.utc),
                    },
                )

    def test_remap_audits_inactive_activation_without_restoring_qualification(self):
        with self.engine.begin() as connection:
            source_person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status,
                       version, created_at, updated_at)
                    VALUES ('Source Person', 'basic', 'active', 1, now(), now())
                    RETURNING id
                    """
                )
            )
            target_person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status,
                       version, created_at, updated_at)
                    VALUES ('Inactive Target', 'basic', 'inactive', 1, now(), now())
                    RETURNING id
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.members (id, name, person_id)
                    VALUES
                      (7002, 'Source Member', :source_person_id),
                      (7003, 'Target Member', :target_person_id);
                    INSERT INTO ntubtob.person_qualifications
                      (person_id, qualification, status, reason, created_at, updated_at)
                    VALUES
                      (:target_person_id, 'team_player', 'revoked',
                       'Previously revoked qualification', now(), now());
                    """
                ),
                {
                    "source_person_id": source_person_id,
                    "target_person_id": target_person_id,
                },
            )
        pending = self._pending("remap")
        self.repository.approve_member(
            self.admin_person_id,
            pending.identity.id,
            7002,
            "Approve source Member",
            "approve-remap-source",
        )

        with self.assertRaises(ConflictError):
            self.repository.remap_member_identity(
                self.admin_person_id,
                pending.identity.id,
                7003,
                "Current login identity must not move",
                "remap-current-login",
                current_identity_id=pending.identity.id,
            )

        principal = self.repository.remap_member_identity(
            self.admin_person_id,
            pending.identity.id,
            7003,
            "Correct verified Member mapping",
            "remap-inactive-target",
        )

        self.assertEqual(principal.person.id, target_person_id)
        self.assertEqual(principal.identity.status, "linked")
        with self.engine.connect() as connection:
            state = connection.execute(
                text(
                    """
                    SELECT p.portal_status, q.status, i.status, l.member_id,
                           a.before_state ->> 'target_person_status',
                           a.after_state ->> 'target_person_status'
                    FROM ntubtob.people p
                    JOIN ntubtob.person_qualifications q ON q.person_id = p.id
                    JOIN ntubtob.auth_identities i ON i.person_id = p.id
                    JOIN ntubtob.line_users l
                      ON l.line_user_id = i.provider_subject
                    JOIN ntubtob.access_audit a
                      ON a.auth_identity_id = i.id
                     AND a.request_id = 'remap-inactive-target'
                    WHERE p.id = :person_id
                      AND q.qualification = 'team_player'
                    """
                ),
                {"person_id": target_person_id},
            ).one()
        self.assertEqual(
            state,
            ("active", "revoked", "linked", 7003, "inactive", "active"),
        )

    def test_reject_unblock_and_audit_append_only(self):
        pending = self._pending("reject")
        self.repository.set_identity_status(
            self.admin_person_id,
            pending.identity.id,
            "blocked",
            "Reject unverifiable identity",
            "reject-one",
        )
        self.repository.set_identity_status(
            self.admin_person_id,
            pending.identity.id,
            "pending",
            "Applicant supplied new evidence",
            "unblock-one",
        )
        with self.engine.connect() as connection:
            self.assertFalse(
                connection.scalar(
                    text(
                        "SELECT ignored FROM ntubtob.line_users WHERE line_user_id='fake-pending-reject'"
                    )
                )
            )
        with self.assertRaises(Exception):
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE ntubtob.access_audit SET reason='tampered' WHERE request_id='reject-one'"
                    )
                )

    def test_closed_review_retention_supports_dry_run_and_audited_redaction(self):
        pending = self._pending("retention")
        self.repository.post_review_message(
            pending.identity.id, "Sensitive application note", "review-retention"
        )
        self.repository.approve_non_member(
            self.admin_person_id,
            pending.identity.id,
            "Retention Applicant",
            "Approve retention applicant",
            "approve-retention",
            qualifications={"affiliate"},
        )
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.identity_review_threads "
                    "SET closed_at=:closed_at WHERE auth_identity_id=:identity_id"
                ),
                {
                    "closed_at": now - timedelta(days=366),
                    "identity_id": pending.identity.id,
                },
            )
        self.assertEqual(self.repository.redact_closed_reviews(now, dry_run=True), 1)
        self.assertEqual(self.repository.redact_closed_reviews(now, dry_run=False), 1)
        messages = self.repository.review_messages(pending.identity.id)
        self.assertTrue(messages[0].redacted)
        self.assertIsNone(messages[0].body)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.access_audit "
                        "WHERE action='review_redacted'"
                    )
                ),
                1,
            )

    def _prepare_zero_admin_bootstrap(self):
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
                    """
                )
            )
            person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, portal_access_level, portal_status,
                       version, created_at, updated_at)
                    VALUES ('Fake Bootstrap', 'basic', 'inactive', 1, now(), now())
                    RETURNING id
                    """
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.members (id, name, person_id) "
                    "VALUES (7001, 'Fake Bootstrap Member', :person_id)"
                ),
                {"person_id": person_id},
            )
        self.repository = IdentityLifecycleRepository(self.engine, {7001})
        return self.repository.ensure_pending_line_identity(
            "fake-bootstrap-subject", "Fake Bootstrap", "fake-bootstrap-pending"
        )

    def test_zero_admin_bootstrap_links_only_allowlisted_pending_member(self):
        pending = self._prepare_zero_admin_bootstrap()
        principal = self.repository.bootstrap_zero_admin_member(
            pending.identity.id,
            7001,
            "One-time fictional bootstrap",
            "fake-bootstrap-link",
        )
        retry = self.repository.bootstrap_zero_admin_member(
            pending.identity.id,
            7001,
            "One-time fictional bootstrap",
            "fake-bootstrap-link",
        )
        self.assertEqual(retry.person.id, principal.person.id)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.execute(
                    text(
                        "SELECT actor_person_id, action, count(*) "
                        "FROM ntubtob.access_audit WHERE request_id='fake-bootstrap-link' "
                        "GROUP BY actor_person_id, action"
                    )
                ).one(),
                (None, "identity_linked", 1),
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.person_qualifications "
                        "WHERE person_id=:person_id AND qualification='team_player'"
                    ),
                    {"person_id": principal.person.id},
                ),
                1,
            )

    def test_zero_admin_bootstrap_rejects_non_allowlisted_target_and_existing_admin(
        self,
    ):
        pending = self._prepare_zero_admin_bootstrap()
        with self.assertRaises(AuthorizationError):
            self.repository.bootstrap_zero_admin_member(
                pending.identity.id, 7002, "One-time fictional bootstrap", "fake-wrong"
            )
        self.repository.bootstrap_zero_admin_member(
            pending.identity.id, 7001, "One-time fictional bootstrap", "fake-first"
        )
        with self.engine.begin() as connection:
            second_person = connection.scalar(
                text(
                    "INSERT INTO ntubtob.people "
                    "(display_name, portal_access_level, portal_status, version, created_at, updated_at) "
                    "VALUES ('Fake Second', 'basic', 'inactive', 1, now(), now()) RETURNING id"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.members (id, name, person_id) "
                    "VALUES (7003, 'Fake Second Member', :person_id)"
                ),
                {"person_id": second_person},
            )
        second = self.repository.ensure_pending_line_identity(
            "fake-second-subject", "Fake Second", "fake-second-pending"
        )
        with self.assertRaises(ConflictError):
            self.repository.bootstrap_zero_admin_member(
                second.identity.id, 7001, "One-time fictional bootstrap", "fake-second"
            )

    def test_concurrent_zero_admin_bootstraps_allow_exactly_one_initial_link(self):
        first = self._prepare_zero_admin_bootstrap()
        second = self.repository.ensure_pending_line_identity(
            "fake-concurrent-subject", "Fake Concurrent", "fake-concurrent-pending"
        )
        barrier = threading.Barrier(2)
        outcomes = []
        outcome_lock = threading.Lock()

        def attempt(pending, request_id):
            barrier.wait()
            try:
                self.repository.bootstrap_zero_admin_member(
                    pending.identity.id,
                    7001,
                    "One-time fictional bootstrap",
                    request_id,
                )
                result = "linked"
            except ConflictError:
                result = "rejected"
            with outcome_lock:
                outcomes.append(result)

        threads = (
            threading.Thread(target=attempt, args=(first, "fake-concurrent-one")),
            threading.Thread(target=attempt, args=(second, "fake-concurrent-two")),
        )
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes, ("linked", "rejected"))


from alembic import command
from alembic.config import Config
