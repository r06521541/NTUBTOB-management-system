from __future__ import annotations

import os
import threading
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from shared_lib.shared_module.portal_data.domain import (
    AuthorizationError,
    ConflictError,
    Person,
)
from shared_lib.shared_module.portal_data.local_database import (
    require_local_database_url,
)
from shared_lib.shared_module.portal_data.repository import (
    InMemoryTeamPortalRepository,
    PostgresTeamPortalRepository,
)


class RepositoryContractMixin:
    repository = None

    def make_admin(self, name="虛構管理員"):
        return self.repository.create_person(name, access_level="admin")

    def test_same_person_can_link_multiple_accounts_from_same_provider(self):
        admin = self.make_admin()
        person = self.repository.create_person("虛構親友")
        first = self.repository.create_pending_identity("line", "fake-line-subject-a")
        second = self.repository.create_pending_identity("line", "fake-line-subject-b")

        self.repository.approve_identity(
            admin.id, first.id, "核可虛構帳號", "approve-a", person_id=person.id
        )
        self.repository.approve_identity(
            admin.id, second.id, "核可虛構帳號", "approve-b", person_id=person.id
        )

        identities = self.repository.identities_for_person(person.id)
        self.assertEqual(
            {item.provider_subject for item in identities},
            {
                "fake-line-subject-a",
                "fake-line-subject-b",
            },
        )
        with self.assertRaises(ConflictError):
            self.repository.create_pending_identity("line", "fake-line-subject-a")

    def test_non_member_affiliate_admin_does_not_become_team_player(self):
        person = self.repository.create_person(
            "虛構親友管理員",
            access_level="admin",
            qualifications=("affiliate", "guest_player"),
        )
        self.assertTrue(person.is_admin)
        self.assertEqual(
            self.repository.qualifications_for_person(person.id),
            {"affiliate", "guest_player"},
        )
        self.assertNotIn(
            "team_player", self.repository.qualifications_for_person(person.id)
        )

    def test_qualification_validity_and_revocation_fail_closed(self):
        person = self.repository.create_person("虛構期間資格者")
        now = datetime.now(timezone.utc)
        self.repository.grant_qualification(
            person.id,
            "staff",
            valid_from=now - timedelta(days=2),
            valid_until=now - timedelta(days=1),
        )
        self.assertNotIn("staff", self.repository.qualifications_for_person(person.id))
        self.repository.grant_qualification(person.id, "staff")
        self.assertIn("staff", self.repository.qualifications_for_person(person.id))
        self.repository.revoke_qualification(person.id, "staff")
        self.assertNotIn("staff", self.repository.qualifications_for_person(person.id))

    def test_disabled_person_cannot_manage_events(self):
        admin = self.make_admin()
        officer = self.repository.create_person(
            "虛構待停權幹部", access_level="officer"
        )
        self.repository.change_status(
            admin.id, officer.id, "disabled", "暫停虛構幹部", "disable-officer"
        )
        with self.assertRaises(AuthorizationError):
            self.repository.create_event(
                officer.id,
                "不可建立的虛構活動",
                "other",
                datetime.now(timezone.utc) + timedelta(days=1),
                ("affiliate",),
            )

    def test_unknown_status_and_access_fail_closed(self):
        self.assertFalse(Person(1, "虛構人物", "unknown", "active").can_use_portal)
        self.assertFalse(Person(1, "虛構人物", "admin", "unknown").is_admin)

    def test_identity_can_be_approved_as_new_non_member_or_blocked(self):
        admin = self.make_admin()
        approved = self.repository.create_pending_identity(
            "google", "fake-google-subject"
        )
        person = self.repository.approve_identity(
            admin.id,
            approved.id,
            "核可虛構親友",
            "approve-new-affiliate",
            display_name="虛構新親友",
            qualifications=("affiliate",),
        )
        self.assertEqual(
            self.repository.qualifications_for_person(person.id), {"affiliate"}
        )

        rejected = self.repository.create_pending_identity(
            "apple", "fake-apple-subject"
        )
        blocked = self.repository.block_identity(
            admin.id, rejected.id, "拒絕虛構申請", "block-fake-identity"
        )
        self.assertEqual(blocked.status, "blocked")
        self.assertIsNone(blocked.person_id)

    def test_identity_can_match_a_known_member_but_cannot_invent_one(self):
        admin = self.make_admin()
        if hasattr(self.repository, "add_legacy_member"):
            self.repository.add_legacy_member(7001, "虛構校友甲")
        identity = self.repository.create_pending_identity(
            "line", "fake-member-subject"
        )
        person = self.repository.approve_identity(
            admin.id,
            identity.id,
            "匹配虛構校友",
            "match-fake-member",
            member_id=7001,
            qualifications=("team_player",),
        )
        self.assertEqual(
            self.repository.qualifications_for_person(person.id), {"team_player"}
        )

        unknown = self.repository.create_pending_identity("line", "fake-unknown-member")
        with self.assertRaises(ConflictError):
            self.repository.approve_identity(
                admin.id,
                unknown.id,
                "不得虛構校友列",
                "reject-unknown-member",
                member_id=7999,
            )

    def test_duplicate_audit_request_rolls_back_access_change(self):
        admin = self.make_admin()
        target = self.repository.create_person("虛構隊務")
        self.repository.change_access(
            admin.id, target.id, "officer", "第一次權限調整", "same-request-id"
        )
        with self.assertRaises(ConflictError):
            self.repository.change_access(
                admin.id, target.id, "admin", "重複請求應回滾", "same-request-id"
            )
        self.assertEqual(self.repository.get_person(target.id).access_level, "officer")

    def test_last_admin_concurrent_demotion_keeps_an_active_admin(self):
        first = self.repository.create_person("虛構管理員甲", access_level="admin")
        second = self.repository.create_person("虛構管理員乙", access_level="admin")
        barrier = threading.Barrier(2)
        outcomes = []

        def demote(actor_id, target_id, request_id):
            barrier.wait()
            try:
                self.repository.change_access(
                    actor_id, target_id, "basic", "交叉降權競爭測試", request_id
                )
                outcomes.append("changed")
            except (AuthorizationError, ConflictError):
                outcomes.append("rejected")

        threads = [
            threading.Thread(
                target=demote, args=(first.id, second.id, "demote-second")
            ),
            threading.Thread(target=demote, args=(second.id, first.id, "demote-first")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(outcomes.count("changed"), 1)
        self.assertEqual(
            sum(
                self.repository.get_person(person_id).is_admin
                for person_id in (first.id, second.id)
            ),
            1,
        )

    def test_publish_snapshot_is_stable_and_roster_separates_guests(self):
        officer = self.repository.create_person("虛構幹部", access_level="officer")
        team_player = self.repository.create_person(
            "虛構正式球員", qualifications=("team_player",)
        )
        guest = self.repository.create_person(
            "虛構客座球員", qualifications=("guest_player",)
        )
        late_player = self.repository.create_person("虛構稍後加入者")
        event_id = self.repository.create_event(
            officer.id,
            "虛構友誼賽",
            "game",
            datetime.now(timezone.utc) + timedelta(days=7),
            ("team_player", "guest_player"),
        )

        first = self.repository.publish_event(
            officer.id, event_id, "publish-fake-event"
        )
        self.repository.grant_qualification(late_player.id, "team_player")
        second = self.repository.publish_event(officer.id, event_id, "retry-publish")

        self.assertEqual(first, second)
        self.assertEqual({row.person_id for row in first}, {team_player.id, guest.id})
        self.assertEqual(
            self.repository.roster_summary(event_id),
            {
                "team_player:unanswered": 1,
                "guest_player:unanswered": 1,
            },
        )
        self.repository.reply_to_event(event_id, team_player.id, "attending")
        self.repository.reply_to_event(event_id, guest.id, "attending")
        self.assertEqual(
            self.repository.roster_summary(event_id),
            {
                "team_player:attending": 1,
                "guest_player:attending": 1,
            },
        )
        with self.assertRaises(AuthorizationError):
            self.repository.reply_to_event(event_id, late_player.id, "attending")

    def test_manual_include_and_exclude_are_snapshotted(self):
        officer = self.repository.create_person("虛構幹部", access_level="officer")
        team_player = self.repository.create_person(
            "虛構被排除球員", qualifications=("team_player",)
        )
        individual = self.repository.create_person("虛構個別受邀者")
        event_id = self.repository.create_event(
            officer.id,
            "虛構聚餐",
            "meal",
            datetime.now(timezone.utc) + timedelta(days=3),
            ("team_player",),
        )
        self.repository.set_invitee_override(
            officer.id,
            event_id,
            team_player.id,
            "exclude",
            "team_player",
            "本次虛構活動排除",
        )
        self.repository.set_invitee_override(
            officer.id,
            event_id,
            individual.id,
            "include",
            "other",
            "本次虛構活動邀請",
        )
        rows = self.repository.publish_event(officer.id, event_id, "publish-overrides")
        by_person = {row.person_id: row for row in rows}
        self.assertFalse(by_person[team_player.id].included)
        self.assertEqual(by_person[team_player.id].source, "manual_exclude")
        self.assertTrue(by_person[individual.id].included)
        self.assertEqual(by_person[individual.id].source, "manual_include")

    def test_member_backfill_is_idempotent(self):
        self.repository.add_legacy_member(7001, "虛構校友甲")
        self.repository.add_legacy_member(7002, "虛構校友乙")
        first = self.repository.backfill_members(fake_admin_member_ids=(7001,))
        first_people = (
            dict(self.repository.members)
            if hasattr(self.repository, "members")
            else None
        )
        second = self.repository.backfill_members(fake_admin_member_ids=(7001,))
        self.assertEqual(first.created_people, 2)
        self.assertEqual(first.granted_team_players, 2)
        self.assertEqual(second.created_people, 0)
        self.assertEqual(second.granted_team_players, 0)
        self.assertEqual(second.promoted_fake_admins, 0)
        if first_people is not None:
            self.assertEqual(first_people, self.repository.members)


class InMemoryRepositoryContractTests(RepositoryContractMixin, unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryTeamPortalRepository()


@unittest.skipUnless(
    os.environ.get("PORTAL_DATA_TEST_DATABASE_URL"),
    "isolated local PostgreSQL URL not configured",
)
class PostgresRepositoryContractTests(RepositoryContractMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = require_local_database_url(os.environ["PORTAL_DATA_TEST_DATABASE_URL"])
        cls.engine = create_engine(url, pool_pre_ping=True)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    TRUNCATE TABLE
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
                      ntubtob.members,
                      ntubtob.people
                    RESTART IDENTITY;
                    INSERT INTO ntubtob.members (id, name) VALUES
                      (7001, '虛構校友甲'),
                      (7002, '虛構校友乙')
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, person_id = NULL;
                    """
                )
            )
        self.repository = PostgresTeamPortalRepository(self.engine)

    def test_member_backfill_is_idempotent(self):
        first = self.repository.backfill_members(fake_admin_member_ids=(7001,))
        first_links = self._member_links()
        second = self.repository.backfill_members(fake_admin_member_ids=(7001,))
        self.assertEqual(first.created_people, 2)
        self.assertEqual(first.granted_team_players, 2)
        self.assertEqual(second.created_people, 0)
        self.assertEqual(second.granted_team_players, 0)
        self.assertEqual(second.promoted_fake_admins, 0)
        self.assertEqual(first_links, self._member_links())

    def _member_links(self):
        with self.engine.connect() as connection:
            return connection.execute(
                text("SELECT id, person_id FROM ntubtob.members ORDER BY id")
            ).all()


if __name__ == "__main__":
    unittest.main()
