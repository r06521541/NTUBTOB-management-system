from __future__ import annotations

import concurrent.futures
import contextlib
import io
import json
import os
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError

from shared_lib.shared_module.mobile_api import BasicApiService, MobilePrincipal
from shared_lib.shared_module.portal_data.domain import (
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from shared_lib.shared_module.portal_data.identity_lifecycle import (
    EVENT_SNAPSHOT_LOCK_KEY,
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from tests.portal_data._apple_lifecycle_test_harness import (
    remove_retained_apple_evidence_from_isolated_test_database,
)
from tests.portal_data._event_guest_lifecycle_test_harness import (
    prepare_event_guest_lifecycle_downgrade_for_isolated_test_database,
)
from tools import portal_data_production_zero_admin_bootstrap as production_bootstrap
from tools import portal_data_zero_admin_bootstrap as bootstrap_operator
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
        prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(self.engine)
        remove_retained_apple_evidence_from_isolated_test_database(self.engine)
        setup_legacy_fixture()
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        prepare_event_guest_lifecycle_downgrade_for_isolated_test_database(self.engine)
        command.downgrade(config, "0004_phase_c_identity_lifecycle")
        remove_retained_apple_evidence_from_isolated_test_database(self.engine)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    TRUNCATE TABLE
                      ntubtob.identity_review_messages,
                      ntubtob.identity_review_threads,
                      ntubtob.event_audit,
                      ntubtob.event_managers,
                      ntubtob.activity_attendance_replies,
                      ntubtob.event_attendance_replies,
                      ntubtob.event_invitees,
                      ntubtob.event_invitee_overrides,
                      ntubtob.event_eligibility_rules,
                      ntubtob.activities,
                      ntubtob.events,
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

    def _qualification_target(self, name="Fictional Qualification Target"):
        with self.engine.begin() as connection:
            return connection.scalar(
                text(
                    "INSERT INTO ntubtob.people "
                    "(display_name,portal_access_level,portal_status,version,created_at,updated_at) "
                    "VALUES (:name,'basic','active',1,now(),now()) RETURNING id"
                ),
                {"name": name},
            )

    def test_qualification_status_serializes_behind_event_snapshot_lock(self):
        target_id = self._qualification_target()
        attempted = threading.Event()

        def observe_lock(_connection, _cursor, statement, parameters, _context, _many):
            if "pg_advisory_xact_lock" in statement and (
                parameters == {"key": EVENT_SNAPSHOT_LOCK_KEY}
                or parameters == (EVENT_SNAPSHOT_LOCK_KEY,)
            ):
                attempted.set()

        event.listen(self.engine, "before_cursor_execute", observe_lock)
        blocker = self.engine.connect()
        transaction = blocker.begin()
        blocker.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": EVENT_SNAPSHOT_LOCK_KEY},
        )
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self.repository.grant_qualification,
                    self.admin_person_id,
                    target_id,
                    "affiliate",
                    "Fictional serialized change",
                    "qualification-lock-fictional",
                )
                self.assertTrue(attempted.wait(2))
                self.assertFalse(future.done())
                transaction.commit()
                future.result(timeout=5)
        finally:
            if transaction.is_active:
                transaction.rollback()
            blocker.close()
            event.remove(self.engine, "before_cursor_execute", observe_lock)

    def test_qualification_status_rolls_back_when_audit_insert_fails(self):
        target_id = self._qualification_target("Fictional Rollback Target")

        def reject_audit(_connection, _cursor, statement, _parameters, _context, _many):
            if "INSERT INTO ntubtob.access_audit" in statement:
                raise RuntimeError("fictional audit failure")

        event.listen(self.engine, "before_cursor_execute", reject_audit)
        try:
            with self.assertRaisesRegex(RuntimeError, "fictional audit failure"):
                self.repository.grant_qualification(
                    self.admin_person_id,
                    target_id,
                    "affiliate",
                    "Fictional rollback",
                    "qualification-rollback-fictional",
                )
        finally:
            event.remove(self.engine, "before_cursor_execute", reject_audit)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.person_qualifications "
                        "WHERE person_id=:person_id"
                    ),
                    {"person_id": target_id},
                ),
                0,
            )

    def test_event_reads_require_included_snapshot_and_filter_linked_games(self):
        now = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
        with self.engine.begin() as connection:
            visible_game_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.games (start_datetime, invitation_time) "
                    "VALUES (:start, :invited) RETURNING id"
                ),
                {"start": now + timedelta(days=2), "invited": now},
            )
            hidden_game_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.games (start_datetime) "
                    "VALUES (:start) RETURNING id"
                ),
                {"start": now + timedelta(days=2)},
            )
            published_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.events
                      (title, event_type, status, start_at, end_at,
                       created_by_person_id, published_at, version,
                       created_at, updated_at)
                    VALUES
                      ('Included Trip', 'trip', 'published', :start, :finish,
                       :person_id, :published, 2, :published, :published)
                    RETURNING id
                    """
                ),
                {
                    "start": now + timedelta(days=1),
                    "finish": now + timedelta(days=3),
                    "person_id": self.admin_person_id,
                    "published": now - timedelta(days=1),
                },
            )
            draft_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.events
                      (title, event_type, status, start_at, created_by_person_id,
                       version, created_at, updated_at)
                    VALUES ('Hidden Draft', 'meal', 'draft', :start, :person_id,
                            1, :created, :created)
                    RETURNING id
                    """
                ),
                {
                    "start": now + timedelta(days=1),
                    "person_id": self.admin_person_id,
                    "created": now,
                },
            )
            cancelled_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.events
                      (title, event_type, status, start_at, created_by_person_id,
                       published_at, version, created_at, updated_at)
                    VALUES ('Visible Cancellation', 'social', 'cancelled', :start,
                            :person_id, :published, 3, :published, :published)
                    RETURNING id
                    """
                ),
                {
                    "start": now + timedelta(days=4),
                    "person_id": self.admin_person_id,
                    "published": now - timedelta(days=1),
                },
            )
            ended_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.events
                      (title, event_type, status, start_at, end_at,
                       created_by_person_id, published_at, version,
                       created_at, updated_at)
                    VALUES ('Ended Event', 'meal', 'published', :start, :finish,
                            :person_id, :published, 2, :published, :published)
                    RETURNING id
                    """
                ),
                {
                    "start": now - timedelta(days=2),
                    "finish": now - timedelta(days=1),
                    "person_id": self.admin_person_id,
                    "published": now - timedelta(days=3),
                },
            )
            excluded_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.events
                      (title, event_type, status, start_at, created_by_person_id,
                       published_at, version, created_at, updated_at)
                    VALUES ('Excluded Event', 'practice', 'published', :start,
                            :person_id, :published, 2, :published, :published)
                    RETURNING id
                    """
                ),
                {
                    "start": now + timedelta(days=2),
                    "person_id": self.admin_person_id,
                    "published": now - timedelta(days=1),
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.event_invitees
                      (event_id, person_id, included, source,
                       source_qualification, participation_category,
                       actor_person_id, reason, snapshotted_at)
                    VALUES
                      (:published_id, :person_id, true, 'qualification',
                       'team_player', 'team_player', NULL, NULL, :now),
                      (:draft_id, :person_id, true, 'qualification',
                       'team_player', 'team_player', NULL, NULL, :now),
                      (:cancelled_id, :person_id, true, 'qualification',
                       'team_player', 'team_player', NULL, NULL, :now),
                      (:ended_id, :person_id, true, 'qualification',
                       'team_player', 'team_player', NULL, NULL, :now),
                      (:excluded_id, :person_id, false, 'manual_exclude',
                       NULL, 'team_player', :person_id, 'Excluded by snapshot', :now)
                    """
                ),
                {
                    "published_id": published_id,
                    "draft_id": draft_id,
                    "cancelled_id": cancelled_id,
                    "ended_id": ended_id,
                    "excluded_id": excluded_id,
                    "person_id": self.admin_person_id,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.activities
                      (event_id, title, activity_type, position, start_at,
                       end_at, game_id)
                    VALUES
                      (:event_id, 'Hidden linked game', 'game', 2, :start,
                       NULL, :hidden_game_id),
                      (:event_id, 'Visible linked game', 'game', 1, :start,
                       NULL, :visible_game_id)
                    """
                ),
                {
                    "event_id": published_id,
                    "start": now + timedelta(days=2),
                    "hidden_game_id": hidden_game_id,
                    "visible_game_id": visible_game_id,
                },
            )

        events = self.repository.scoped_events(self.admin_person_id, now)
        self.assertEqual(
            [event["id"] for event in events], [published_id, cancelled_id]
        )
        self.assertEqual(events[1]["status"], "cancelled")
        self.assertEqual(
            [activity["position"] for activity in events[0]["activities"]], [1, 2]
        )
        self.assertEqual(events[0]["activities"][0]["linked_game_id"], visible_game_id)
        self.assertIsNone(events[0]["activities"][1]["linked_game_id"])
        self.assertNotIn("source_qualification", str(events))
        self.assertEqual(
            self.repository.scoped_event(self.admin_person_id, published_id, now),
            events[0],
        )
        self.assertIsNone(
            self.repository.scoped_event(self.admin_person_id, draft_id, now)
        )

        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ntubtob.people SET portal_status='disabled' WHERE id=:id"),
                {"id": self.admin_person_id},
            )
        with self.assertRaises(AuthorizationError):
            self.repository.scoped_events(self.admin_person_id, now)

    def test_game_attendance_report_projects_member_number_in_fixed_queries(self):
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                    INSERT INTO ntubtob.people
                      (display_name, formal_name, portal_access_level, portal_status,
                       version, created_at, updated_at)
                    VALUES
                      ('Numbered', 'Numbered Formal', 'basic', 'active', 1, now(), now()),
                      ('Unnumbered', 'Unnumbered Formal', 'basic', 'active', 1, now(), now())
                    RETURNING id
                    """
                    )
                )
                .scalars()
                .all()
            )
            numbered_id, unnumbered_id = rows
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.members (id, name, number, person_id)
                    VALUES (7101, 'Numbered Member', 27, :numbered_id);
                    INSERT INTO ntubtob.person_qualifications
                      (person_id, qualification, status, created_at, updated_at)
                    VALUES
                      (:numbered_id, 'team_player', 'active', now(), now()),
                      (:unnumbered_id, 'team_player', 'active', now(), now());
                    """
                ),
                {"numbered_id": numbered_id, "unnumbered_id": unnumbered_id},
            )
            game_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.games (start_datetime) "
                    "VALUES (now() + interval '1 day') RETURNING id"
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.game_attendance_replies
                      (game_id, person_id, reply, updated_at)
                    VALUES
                      (:game_id, :numbered_id, 1, now()),
                      (:game_id, :unnumbered_id, 2, now())
                    """
                ),
                {
                    "game_id": game_id,
                    "numbered_id": numbered_id,
                    "unnumbered_id": unnumbered_id,
                },
            )

        statements = []

        def record_query(*args):
            statements.append(args[2])

        event.listen(self.engine, "before_cursor_execute", record_query)
        try:
            report = self.repository.game_attendance_report(game_id)
        finally:
            event.remove(self.engine, "before_cursor_execute", record_query)
        self.assertEqual(len(statements), 4)
        self.assertEqual(report["attending"][0]["member_number"], 27)
        self.assertIsNone(report["not_attending"][0]["member_number"])

        data = SimpleNamespace(
            scoped_game=Mock(return_value={"id": game_id}),
            game_attendance_report=Mock(return_value=report),
        )
        service = BasicApiService(
            data, Mock(), Mock(), clock=lambda: report["generated_at"]
        )
        public = service.attendance_report(
            MobilePrincipal(
                "session", self.admin_person_id, 1, "officer", "Officer", 1
            ),
            game_id,
        )
        self.assertEqual(public["attending"][0]["member_number"], 27)
        self.assertIsNone(public["not_attending"][0]["member_number"])
        self.assertNotIn("member_id", str(public))

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
        with self.engine.connect() as connection:
            initial_version = connection.scalar(
                text("SELECT updated_at FROM ntubtob.auth_identities WHERE id=:id"),
                {"id": pending.identity.id},
            )
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
        ignore_at = now + timedelta(minutes=1)
        self.repository.set_ignored(
            self.admin_person_id,
            pending.identity.id,
            True,
            "Applicant requested later review",
            "ignore-one",
            at=ignore_at,
        )
        self.repository.set_ignored(
            self.admin_person_id,
            pending.identity.id,
            True,
            "Applicant requested later review",
            "ignore-one",
            at=ignore_at + timedelta(minutes=1),
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
            ignored_version = connection.scalar(
                text("SELECT updated_at FROM ntubtob.auth_identities WHERE id=:id"),
                {"id": pending.identity.id},
            )
            self.assertGreater(ignored_version, initial_version)
            self.assertEqual(ignored_version, ignore_at)
        self.repository.set_ignored(
            self.admin_person_id,
            pending.identity.id,
            False,
            "Applicant returned for review",
            "unignore-one",
            at=ignore_at + timedelta(minutes=2),
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
            self.assertEqual(
                connection.scalar(
                    text("SELECT updated_at FROM ntubtob.auth_identities WHERE id=:id"),
                    {"id": pending.identity.id},
                ),
                ignore_at + timedelta(minutes=2),
            )

    def test_unchanged_ignore_request_does_not_advance_identity_version(self):
        pending = self._pending("ignore-noop")
        transition_at = datetime(2026, 8, 24, 1, 2, 3, 456789, timezone.utc)
        self.repository.set_ignored(
            self.admin_person_id,
            pending.identity.id,
            True,
            "Applicant requested later review",
            "ignore-noop-first",
            at=transition_at,
        )
        with self.assertRaises(ConflictError):
            self.repository.set_ignored(
                self.admin_person_id,
                pending.identity.id,
                True,
                "Applicant requested later review",
                "ignore-noop-second",
                at=transition_at + timedelta(minutes=1),
            )
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text("SELECT updated_at FROM ntubtob.auth_identities WHERE id=:id"),
                    {"id": pending.identity.id},
                ),
                transition_at,
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

    def _assert_bootstrap_failure_is_atomic(self, identity_id, request_id):
        query = text(
            "SELECT i.status,i.person_id,l.member_id,p.portal_status,"
            "(SELECT count(*) FROM ntubtob.access_audit WHERE request_id=:request_id),"
            "(SELECT count(*) FROM ntubtob.person_qualifications q WHERE q.person_id=p.id) "
            "FROM ntubtob.auth_identities i "
            "JOIN ntubtob.line_users l ON l.line_user_id=i.provider_subject "
            "JOIN ntubtob.members m ON m.id=7001 "
            "JOIN ntubtob.people p ON p.id=m.person_id WHERE i.id=:identity_id"
        )
        parameters = {"identity_id": identity_id, "request_id": request_id}
        with self.engine.connect() as connection:
            before = connection.execute(query, parameters).one()
        with self.assertRaises(ConflictError):
            self.repository.bootstrap_zero_admin_member(
                identity_id, 7001, "One-time fictional bootstrap", request_id
            )
        with self.engine.connect() as connection:
            after = connection.execute(query, parameters).one()
        self.assertEqual(after, before)

    def test_zero_admin_bootstrap_rejects_target_state_drift_atomically(self):
        cases = (
            ("blocked-person", "UPDATE ntubtob.people SET portal_status='blocked'"),
            ("disabled-person", "UPDATE ntubtob.people SET portal_status='disabled'"),
            ("ignored-legacy", "UPDATE ntubtob.line_users SET ignored=true"),
            (
                "closed-thread",
                "UPDATE ntubtob.identity_review_threads SET status='closed',closed_at=now()",
            ),
            (
                "redacted-thread",
                "UPDATE ntubtob.identity_review_threads SET redacted_at=now()",
            ),
        )
        for suffix, mutation in cases:
            with self.subTest(suffix=suffix):
                pending = self._prepare_zero_admin_bootstrap()
                with self.engine.begin() as connection:
                    connection.execute(text(mutation))
                self._assert_bootstrap_failure_is_atomic(
                    pending.identity.id, f"fake-{suffix}"
                )

        pending = self._prepare_zero_admin_bootstrap()
        with self.engine.begin() as connection:
            person_id = connection.scalar(
                text("SELECT person_id FROM ntubtob.members WHERE id=7001")
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.person_qualifications "
                    "(person_id,qualification,status,reason,created_at,updated_at) "
                    "VALUES (:person_id,'team_player','revoked','fictional drift',now(),now())"
                ),
                {"person_id": person_id},
            )
        self._assert_bootstrap_failure_is_atomic(
            pending.identity.id, "fake-revoked-qualification"
        )

    def test_zero_admin_bootstrap_rejects_ordinary_approval_audit_retry(self):
        pending = self._prepare_zero_admin_bootstrap()
        with self.engine.begin() as connection:
            person_id = connection.scalar(
                text("SELECT person_id FROM ntubtob.members WHERE id=7001")
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.access_audit "
                    "(action,actor_person_id,target_person_id,auth_identity_id,before_state,after_state,reason,request_id,created_at) "
                    "VALUES ('identity_linked',:person_id,:person_id,:identity_id,CAST(:before_state AS json),"
                    "CAST(:after_state AS json),'ordinary approval',"
                    "'fake-ordinary-retry',now())"
                ),
                {
                    "person_id": person_id,
                    "identity_id": pending.identity.id,
                    "before_state": '{"status":"pending"}',
                    "after_state": '{"status":"linked","member_id":7001}',
                },
            )
        self._assert_bootstrap_failure_is_atomic(
            pending.identity.id, "fake-ordinary-retry"
        )

    def test_zero_admin_bootstrap_rolls_back_on_audit_insert_failure(self):
        pending = self._prepare_zero_admin_bootstrap()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE FUNCTION ntubtob.fail_fake_bootstrap_audit() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fake audit failure'; END $$; "
                    "CREATE TRIGGER fail_fake_bootstrap_audit BEFORE INSERT ON ntubtob.access_audit "
                    "FOR EACH ROW WHEN (NEW.request_id='fake-injected-failure') "
                    "EXECUTE FUNCTION ntubtob.fail_fake_bootstrap_audit()"
                )
            )
        try:
            self._assert_bootstrap_failure_is_atomic(
                pending.identity.id, "fake-injected-failure"
            )
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "DROP TRIGGER fail_fake_bootstrap_audit ON ntubtob.access_audit; "
                        "DROP FUNCTION ntubtob.fail_fake_bootstrap_audit()"
                    )
                )

    def test_zero_admin_bootstrap_rejects_wrong_identity_and_member(self):
        pending = self._prepare_zero_admin_bootstrap()
        for identity_id, member_id, request_id in (
            (pending.identity.id + 9999, 7001, "fake-wrong-identity"),
            (pending.identity.id, 7999, "fake-wrong-member"),
        ):
            with (
                self.subTest(request_id=request_id),
                self.assertRaises((AuthorizationError, ConflictError)),
            ):
                self.repository.bootstrap_zero_admin_member(
                    identity_id,
                    member_id,
                    "One-time fictional bootstrap",
                    request_id,
                )

    def test_zero_admin_operator_dry_run_and_execute_use_redacted_schema(self):
        pending = self._prepare_zero_admin_bootstrap()

        def invoke(mode, values):
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"PORTAL_DATA_DATABASE_URL": DATABASE_URL}),
                patch.object(bootstrap_operator.getpass, "getpass", side_effect=values),
                contextlib.redirect_stdout(output),
            ):
                bootstrap_operator.run(mode)
            return json.loads(output.getvalue())

        dry_run = invoke(
            "dry-run",
            ("7001", str(pending.identity.id), "7001", "Fake reason", "fake-op-dry"),
        )
        self.assertEqual(tuple(dry_run), bootstrap_operator.OUTPUT_FIELDS)
        self.assertEqual(dry_run["status"], "ready")
        self.assertFalse(dry_run["applied"])
        execute = invoke(
            "execute",
            (
                "7001",
                str(pending.identity.id),
                "7001",
                "Fake reason",
                "fake-op-execute",
                "EXECUTE TASK-085",
            ),
        )
        self.assertEqual(tuple(execute), bootstrap_operator.OUTPUT_FIELDS)
        self.assertEqual(execute["status"], "applied")
        self.assertTrue(execute["applied"])

    def test_production_bootstrap_discovers_executes_and_retries_without_identifiers(
        self,
    ):
        self._prepare_zero_admin_bootstrap()
        environment = {
            production_bootstrap.DATABASE_ENV: DATABASE_URL,
            production_bootstrap.ALLOWLIST_ENV: "7001",
        }

        def invoke(mode, extra=None):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                production_bootstrap.run(mode, environ={**environment, **(extra or {})})
            return json.loads(output.getvalue())

        discovery = invoke("discovery")
        self.assertEqual(tuple(discovery), production_bootstrap.OUTPUT_FIELDS)
        self.assertEqual(discovery["eligible_member_count"], 1)
        self.assertEqual(discovery["eligible_identity_count"], 1)
        self.assertFalse(discovery["applied"])

        generated = uuid.UUID("00000000-0000-4000-8000-000000000086")
        with patch.object(production_bootstrap.uuid, "uuid4", return_value=generated):
            execute = invoke(
                "execute",
                {
                    production_bootstrap.EXECUTION_ENV: production_bootstrap.EXECUTION_ACKNOWLEDGEMENT
                },
            )
        self.assertEqual(tuple(execute), production_bootstrap.OUTPUT_FIELDS)
        self.assertEqual(execute["status"], "applied")
        self.assertEqual(execute["audit_delta"], 1)
        self.assertTrue(execute["applied"])
        self.assertTrue(execute["retry_verified"])
        self.assertNotIn("request_id", execute)
        post_check = invoke("post-check")
        self.assertEqual(post_check["status"], "verified")
        self.assertEqual(post_check["active_admin_count"], 1)
        self.assertTrue(post_check["retry_verified"])
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.access_audit "
                        "WHERE request_id='task086-00000000-0000-4000-8000-000000000086'"
                    )
                ),
                1,
            )

    def test_production_bootstrap_schema_and_logging_gates_stop_before_mutation(self):
        self._prepare_zero_admin_bootstrap()
        environment = {
            production_bootstrap.DATABASE_ENV: DATABASE_URL,
            production_bootstrap.ALLOWLIST_ENV: "7001",
        }
        for gate in ("_schema_ready", "_read_logging_safe"):
            with (
                self.subTest(gate=gate),
                patch.object(production_bootstrap, gate, return_value=False),
                self.assertRaises(production_bootstrap.ProductionBootstrapError),
            ):
                production_bootstrap.run("dry-run", environ=environment)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.access_audit")),
                1,
            )

    def test_production_bootstrap_mod_logging_stops_before_mutation(self):
        self._prepare_zero_admin_bootstrap()
        environment = {
            production_bootstrap.DATABASE_ENV: DATABASE_URL,
            production_bootstrap.ALLOWLIST_ENV: "7001",
            production_bootstrap.EXECUTION_ENV: production_bootstrap.EXECUTION_ACKNOWLEDGEMENT,
        }
        with self.engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.execute(
                text(
                    "ALTER DATABASE ntubtob_portal_local " "SET log_statement TO 'mod'"
                )
            )
        try:
            with self.engine.connect() as connection:
                before = connection.scalar(
                    text("SELECT count(*) FROM ntubtob.access_audit")
                )
            with self.assertRaises(production_bootstrap.ProductionBootstrapError):
                production_bootstrap.run("execute", environ=environment)
            with self.engine.connect() as connection:
                after = connection.scalar(
                    text("SELECT count(*) FROM ntubtob.access_audit")
                )
            self.assertEqual(after, before)
        finally:
            with self.engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                connection.execute(
                    text("ALTER DATABASE ntubtob_portal_local " "RESET log_statement")
                )

    def test_production_bootstrap_ambiguity_stops_before_mutation(self):
        self._prepare_zero_admin_bootstrap()
        self.repository.ensure_pending_line_identity(
            "fake-ambiguous-subject", "Fake Ambiguous", "fake-ambiguous-pending"
        )
        environment = {
            production_bootstrap.DATABASE_ENV: DATABASE_URL,
            production_bootstrap.ALLOWLIST_ENV: "7001",
        }
        with self.engine.connect() as connection:
            before = connection.scalar(
                text("SELECT count(*) FROM ntubtob.access_audit")
            )
        with self.assertRaises(production_bootstrap.ProductionBootstrapError):
            production_bootstrap.run("dry-run", environ=environment)
        with self.engine.connect() as connection:
            after = connection.scalar(text("SELECT count(*) FROM ntubtob.access_audit"))
        self.assertEqual(after, before)

    def test_production_bootstrap_member_ambiguity_stops_before_mutation(self):
        self._prepare_zero_admin_bootstrap()
        with self.engine.begin() as connection:
            second_person = connection.scalar(
                text(
                    "INSERT INTO ntubtob.people "
                    "(display_name,portal_access_level,portal_status,version,created_at,updated_at) "
                    "VALUES ('Fake Other','basic','inactive',1,now(),now()) RETURNING id"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO ntubtob.members (id,name,person_id) "
                    "VALUES (7002,'Fake Other Member',:person_id)"
                ),
                {"person_id": second_person},
            )
        environment = {
            production_bootstrap.DATABASE_ENV: DATABASE_URL,
            production_bootstrap.ALLOWLIST_ENV: "7001,7002",
        }
        with self.assertRaises(production_bootstrap.ProductionBootstrapError):
            production_bootstrap.run("preflight", environ=environment)
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(text("SELECT count(*) FROM ntubtob.access_audit")),
                1,
            )

    def test_concurrent_production_bootstrap_allows_one_execution(self):
        self._prepare_zero_admin_bootstrap()
        environment = {
            production_bootstrap.DATABASE_ENV: DATABASE_URL,
            production_bootstrap.ALLOWLIST_ENV: "7001",
            production_bootstrap.EXECUTION_ENV: production_bootstrap.EXECUTION_ACKNOWLEDGEMENT,
        }
        barrier = threading.Barrier(2)
        outcomes = []
        outcome_lock = threading.Lock()

        def attempt():
            barrier.wait()
            try:
                production_bootstrap.run("execute", environ=environment)
                result = "applied"
            except (ConflictError, production_bootstrap.ProductionBootstrapError):
                result = "stopped"
            with outcome_lock:
                outcomes.append(result)

        with patch.object(production_bootstrap, "_emit"):
            threads = (
                threading.Thread(target=attempt),
                threading.Thread(target=attempt),
            )
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
                self.assertFalse(thread.is_alive())
        self.assertCountEqual(outcomes, ("applied", "stopped"))
        with self.engine.connect() as connection:
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.access_audit "
                        "WHERE action='identity_linked' AND actor_person_id IS NULL"
                    )
                ),
                1,
            )

    def test_production_bootstrap_domain_failure_rolls_back(self):
        self._prepare_zero_admin_bootstrap()
        environment = {
            production_bootstrap.DATABASE_ENV: DATABASE_URL,
            production_bootstrap.ALLOWLIST_ENV: "7001",
            production_bootstrap.EXECUTION_ENV: production_bootstrap.EXECUTION_ACKNOWLEDGEMENT,
        }
        with self.engine.begin() as connection:
            before = connection.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM ntubtob.access_audit),"
                    "(SELECT count(*) FROM ntubtob.auth_identities WHERE status='linked'),"
                    "(SELECT count(*) FROM ntubtob.line_users WHERE member_id IS NOT NULL)"
                )
            ).one()
            connection.execute(
                text(
                    "CREATE FUNCTION ntubtob.fail_task086_audit() RETURNS trigger "
                    "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fake task086 failure'; END $$; "
                    "CREATE TRIGGER fail_task086_audit BEFORE INSERT ON ntubtob.access_audit "
                    "FOR EACH ROW WHEN (NEW.action='identity_linked' AND NEW.actor_person_id IS NULL) "
                    "EXECUTE FUNCTION ntubtob.fail_task086_audit()"
                )
            )
        try:
            with self.assertRaises(ConflictError):
                production_bootstrap.run("execute", environ=environment)
            with self.engine.connect() as connection:
                after = connection.execute(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM ntubtob.access_audit),"
                        "(SELECT count(*) FROM ntubtob.auth_identities WHERE status='linked'),"
                        "(SELECT count(*) FROM ntubtob.line_users WHERE member_id IS NOT NULL)"
                    )
                ).one()
            self.assertEqual(after, before)
        finally:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "DROP TRIGGER fail_task086_audit ON ntubtob.access_audit; "
                        "DROP FUNCTION ntubtob.fail_task086_audit()"
                    )
                )

    def test_preview_persisted_admin_does_not_change_production_allowlist(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ntubtob.people SET portal_access_level='admin' "
                    "WHERE id=:person_id"
                ),
                {"person_id": self.admin_person_id},
            )
        production_repository = IdentityLifecycleRepository(self.engine, ())
        with self.assertRaises(AuthorizationError):
            production_repository.admin_dashboard(self.admin_person_id)

        preview_repository = IdentityLifecycleRepository(
            self.engine, (), allow_persisted_admins=True
        )
        self.assertIn(
            "people", preview_repository.admin_dashboard(self.admin_person_id)
        )

    def test_admin_changes_only_basic_and_officer_with_audited_readback(self):
        with self.engine.begin() as connection:
            target_person_id = connection.scalar(
                text(
                    "INSERT INTO ntubtob.people "
                    "(display_name, formal_name, portal_access_level, portal_status, "
                    "version, created_at, updated_at) VALUES "
                    "('Fake Target', 'Fake Target', 'basic', 'active', 1, now(), now()) "
                    "RETURNING id"
                )
            )
        promoted = self.repository.change_access(
            self.admin_person_id,
            target_person_id,
            "officer",
            "Assign game operations",
            "person-access-promote",
        )
        self.assertEqual(promoted.access_level, "officer")
        with self.engine.connect() as connection:
            audit = connection.execute(
                text(
                    "SELECT action, before_state->>'access_level', "
                    "after_state->>'access_level', reason "
                    "FROM ntubtob.access_audit WHERE request_id=:request_id"
                ),
                {"request_id": "person-access-promote"},
            ).one()
        self.assertEqual(
            tuple(audit),
            ("access_changed", "basic", "officer", "Assign game operations"),
        )
        with self.assertRaises(ConflictError):
            self.repository.change_access(
                self.admin_person_id,
                target_person_id,
                "basic",
                "Replay must fail",
                "person-access-promote",
            )
        with self.assertRaises(AuthorizationError):
            self.repository.change_access(
                self.admin_person_id,
                self.admin_person_id,
                "officer",
                "Self change denied",
                "person-access-self",
            )


from alembic import command
from alembic.config import Config
