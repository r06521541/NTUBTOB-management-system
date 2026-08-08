from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from shared_lib.shared_module import attendance_analyzer
from shared_lib.shared_module.portal_data.domain import AuthorizationError
from shared_lib.shared_module.portal_data.identity_lifecycle import (
    IdentityLifecycleRepository,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
)


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class PhaseCCrossServiceRolloutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(require_local_database_url(DATABASE_URL))
        command.upgrade(Config("alembic.ini"), "head")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
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
            self.admin_person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, formal_name, portal_access_level, portal_status,
                       version, created_at, updated_at)
                    VALUES
                      ('Fake Admin Display', 'Fake Admin Formal', 'basic', 'active',
                       1, now(), now())
                    RETURNING id
                    """
                )
            )
            self.member_person_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.people
                      (display_name, formal_name, portal_access_level, portal_status,
                       version, created_at, updated_at)
                    VALUES
                      ('Fake Player Display', 'Ignored Member Formal', 'basic', 'inactive',
                       1, now(), now())
                    RETURNING id
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.members (id, name, person_id)
                    VALUES
                      (7601, 'Fake Admin Member', :admin_person_id),
                      (7602, 'Fake Player Member', :member_person_id);
                    INSERT INTO ntubtob.auth_identities
                      (provider, provider_subject, person_id, status, created_at, updated_at)
                    VALUES
                      ('line', 'fake-rollout-admin', :admin_person_id, 'linked', now(), now());
                    INSERT INTO ntubtob.line_users
                      (line_user_id, member_id, nickname, ignored, has_replied)
                    VALUES
                      ('fake-rollout-admin', 7601, 'Fake Admin', false, true);
                    """
                ),
                {
                    "admin_person_id": self.admin_person_id,
                    "member_person_id": self.member_person_id,
                },
            )
            self.game_id = connection.scalar(
                text(
                    """
                    INSERT INTO ntubtob.games (start_datetime)
                    VALUES (now() + interval '2 days')
                    RETURNING id
                    """
                )
            )
        self.repository = IdentityLifecycleRepository(self.engine, {7601})

    def _approve_member(self):
        pending = self.repository.ensure_pending_line_identity(
            "fake-rollout-player", "Fake Player Login", "pending-rollout-player"
        )
        return self.repository.approve_member(
            self.admin_person_id,
            pending.identity.id,
            7602,
            "Verified fictional roster membership",
            "approve-rollout-player",
        )

    def _approve_guest(self):
        pending = self.repository.ensure_pending_line_identity(
            "fake-rollout-guest", "Fake Guest Login", "pending-rollout-guest"
        )
        now = datetime.now(timezone.utc)
        return self.repository.approve_non_member(
            self.admin_person_id,
            pending.identity.id,
            "Fake Guest Display",
            "Approved fictional bounded guest",
            "approve-rollout-guest",
            formal_name="Fake Guest Formal",
            qualifications=("guest_player",),
            guest_valid_from=now - timedelta(days=1),
            guest_valid_until=now + timedelta(days=10),
        )

    def test_schema_0004_with_flags_off_keeps_legacy_write_shape_and_zero_identity_side_effects(
        self,
    ):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.game_attendance_replies
                      (game_id, user_id, member_id, person_id, reply, updated_at)
                    VALUES (:game_id, NULL, 7602, NULL, 1, now())
                    """
                ),
                {"game_id": self.game_id},
            )
            before = tuple(
                connection.execute(
                    text(
                        """
                        SELECT
                          (SELECT count(*) FROM ntubtob.auth_identities),
                          (SELECT count(*) FROM ntubtob.person_qualifications),
                          (SELECT count(*) FROM ntubtob.access_audit)
                        """
                    )
                ).one()
            )

        legacy_projection = {1: [SimpleNamespace(name="Fake Player Member")]}
        with patch.dict(os.environ, {}, clear=True), patch.object(
            attendance_analyzer,
            "get_identity_lifecycle_repository",
            side_effect=AssertionError(
                "flags-off must not construct Phase C repository"
            ),
        ), patch.object(
            attendance_analyzer, "_legacy_attendance", return_value=legacy_projection
        ):
            self.assertEqual(
                attendance_analyzer.get_attendance_of_game(self.game_id),
                legacy_projection,
            )

        with self.engine.connect() as connection:
            after = tuple(
                connection.execute(
                    text(
                        """
                        SELECT
                          (SELECT count(*) FROM ntubtob.auth_identities),
                          (SELECT count(*) FROM ntubtob.person_qualifications),
                          (SELECT count(*) FROM ntubtob.access_audit)
                        """
                    )
                ).one()
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT person_id FROM ntubtob.game_attendance_replies "
                        "WHERE game_id=:game_id"
                    ),
                    {"game_id": self.game_id},
                ),
                None,
            )
        self.assertEqual(after, before)

    def test_member_pairing_attendance_and_retry_are_one_cross_service_contract(self):
        principal = self._approve_member()
        retried = self.repository.approve_member(
            self.admin_person_id,
            principal.identity.id,
            7602,
            "Verified fictional roster membership",
            "approve-rollout-player",
        )
        self.assertEqual(retried.person.id, principal.person.id)
        self.assertEqual(
            self.repository.resolve_line_principal("fake-rollout-player").person.id,
            principal.person.id,
        )

        self.assertTrue(
            self.repository.reply_to_game(principal.person.id, self.game_id, 1)
        )
        self.assertFalse(
            self.repository.reply_to_game(principal.person.id, self.game_id, 1)
        )
        portal_summary = self.repository.attendance_summary(self.game_id)
        with patch.object(
            attendance_analyzer,
            "is_phase_c_enabled",
            return_value=True,
        ), patch.object(
            attendance_analyzer,
            "get_identity_lifecycle_repository",
            return_value=self.repository,
        ):
            webhook_projection = attendance_analyzer.get_attendance_of_game(
                self.game_id
            )
            notify_projection = attendance_analyzer.get_attendance_of_game(self.game_id)

        self.assertEqual(portal_summary.participants[0]["name"], "Fake Player Member")
        self.assertEqual(webhook_projection[1][0].name, "Fake Player Member")
        self.assertEqual(notify_projection, webhook_projection)
        with self.engine.connect() as connection:
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
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.game_attendance_replies "
                        "WHERE game_id=:game_id AND person_id=:person_id"
                    ),
                    {"game_id": self.game_id, "person_id": principal.person.id},
                ),
                1,
            )
            self.assertEqual(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM ntubtob.access_audit "
                        "WHERE request_id='approve-rollout-player'"
                    )
                ),
                1,
            )

    def test_phase_c_reader_projects_member_reply_written_by_feature_off_revision(self):
        principal = self._approve_member()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ntubtob.game_attendance_replies
                      (game_id, user_id, member_id, person_id, reply, updated_at)
                    VALUES (:game_id, NULL, 7602, NULL, 3, now())
                    """
                ),
                {"game_id": self.game_id},
            )

        summary = self.repository.attendance_summary(self.game_id)

        self.assertEqual(len(summary.participants), 1)
        self.assertEqual(summary.participants[0]["person_id"], principal.person.id)
        self.assertEqual(summary.participants[0]["member_id"], 7602)
        self.assertEqual(summary.participants[0]["reply"], 3)

    def test_guest_bounds_status_and_revocation_fail_closed_without_name_drift(self):
        guest = self._approve_guest()
        self.assertTrue(self.repository.reply_to_game(guest.person.id, self.game_id, 1))
        formal = self.repository.attendance_summary(self.game_id)
        display = self.repository.attendance_summary(
            self.game_id, use_display_name=True
        )
        self.assertEqual(formal.participants[0]["name"], "Fake Guest Formal")
        self.assertEqual(display.participants[0]["name"], "Fake Guest Display")
        self.assertEqual(formal.participants[0]["qualification"], "guest_player")

        self.repository.revoke_qualification(
            self.admin_person_id,
            guest.person.id,
            "guest_player",
            "Bounded guest access ended",
            "revoke-rollout-guest",
        )
        with self.assertRaises(AuthorizationError):
            self.repository.reply_to_game(guest.person.id, self.game_id, 2)
        self.assertEqual(
            self.repository.attendance_summary(self.game_id).participants, ()
        )

    def test_blocked_or_suspended_person_is_not_restored_by_login_or_retry(self):
        principal = self._approve_member()
        for status, request_id in (
            ("disabled", "disable-rollout-player"),
            ("active", "restore-rollout-player"),
            ("blocked", "block-rollout-player"),
        ):
            self.repository.change_person_status(
                self.admin_person_id,
                principal.person.id,
                status,
                "Fictional lifecycle exercise",
                request_id,
            )
            resolved = self.repository.resolve_line_principal("fake-rollout-player")
            if status == "active":
                self.assertIsNotNone(resolved)
            else:
                self.assertIsNone(resolved)
                with self.assertRaises(AuthorizationError):
                    self.repository.reply_to_game(principal.person.id, self.game_id, 1)

        pending_retry = self.repository.ensure_pending_line_identity(
            "fake-rollout-player", "Renamed Login", "pending-retry-blocked"
        )
        self.assertFalse(pending_retry.created)
        self.assertEqual(pending_retry.identity.status, "linked")
        self.assertIsNone(self.repository.resolve_line_principal("fake-rollout-player"))


if __name__ == "__main__":
    unittest.main()
