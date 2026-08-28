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

DATABASE_URL = os.environ.get("PORTAL_DATA_TEST_DATABASE_URL") or os.environ.get(
    "PORTAL_DATA_DATABASE_URL"
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
        now = datetime.now(timezone.utc)
        person = self.repository.create_person(
            "虛構親友管理員",
            access_level="admin",
            qualifications=("affiliate", "guest_player"),
            guest_valid_from=now - timedelta(days=1),
            guest_valid_until=now + timedelta(days=365),
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
        game_start = datetime.now(timezone.utc) + timedelta(days=7)
        officer = self.repository.create_person("虛構幹部", access_level="officer")
        team_player = self.repository.create_person(
            "虛構正式球員", qualifications=("team_player",)
        )
        guest = self.repository.create_person(
            "虛構客座球員",
            qualifications=("guest_player",),
            guest_valid_from=datetime.now(timezone.utc) - timedelta(days=1),
            guest_valid_until=game_start + timedelta(days=365),
        )
        late_player = self.repository.create_person("虛構稍後加入者")
        event_id = self.repository.create_event(
            officer.id,
            "虛構友誼賽",
            "game",
            game_start,
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
            "override-exclude-player",
        )
        self.repository.set_invitee_override(
            officer.id,
            event_id,
            individual.id,
            "include",
            "other",
            "本次虛構活動邀請",
            "override-include-individual",
        )
        self.repository.set_invitee_override(
            officer.id,
            event_id,
            individual.id,
            "include",
            "other",
            "本次虛構活動邀請",
            "override-include-individual",
        )
        with self.assertRaises(ConflictError):
            self.repository.set_invitee_override(
                officer.id,
                event_id,
                team_player.id,
                "include",
                "other",
                "不同內容不得沿用請求",
                "override-include-individual",
            )
        rows = self.repository.publish_event(officer.id, event_id, "publish-overrides")
        by_person = {row.person_id: row for row in rows}
        self.assertFalse(by_person[team_player.id].included)
        self.assertEqual(by_person[team_player.id].source, "manual_exclude")
        self.assertTrue(by_person[individual.id].included)
        self.assertEqual(by_person[individual.id].source, "manual_include")
        audits = self.repository.event_audits(event_id)
        self.assertEqual(
            [row["action"] for row in audits],
            ["invitee_excluded", "invitee_included", "published"],
        )
        self.assertEqual(audits[1]["reason"], "本次虛構活動邀請")

    def test_event_management_validates_draft_and_keeps_activity_order_contiguous(self):
        officer = self.repository.create_person("虛構活動幹部", access_level="officer")
        basic = self.repository.create_person("虛構一般成員")
        start = datetime.now(timezone.utc) + timedelta(days=5)
        with self.assertRaises(AuthorizationError):
            self.repository.create_event(
                basic.id, "不得建立", "meal", start, ("team_player",)
            )
        event_id = self.repository.create_event(
            officer.id, "虛構兩日活動", "trip", start, ("team_player",)
        )
        first = self.repository.add_activity(
            officer.id,
            event_id,
            "集合",
            "gathering",
            start,
            start + timedelta(hours=1),
        )
        second = self.repository.add_activity(
            officer.id,
            event_id,
            "用餐",
            "meal",
            start + timedelta(hours=2),
            start + timedelta(hours=3),
        )
        third = self.repository.add_activity(
            officer.id,
            event_id,
            "住宿",
            "lodging",
            start + timedelta(hours=4),
            start + timedelta(hours=5),
        )

        self.repository.move_activity(officer.id, event_id, third, "up")
        self.repository.delete_activity(officer.id, event_id, first)
        managed = self.repository.managed_event(officer.id, event_id)

        self.assertEqual(
            [(row["id"], row["position"]) for row in managed["activities"]],
            [(third, 1), (second, 2)],
        )
        with self.assertRaises(ConflictError):
            self.repository.update_activity(
                officer.id,
                event_id + 1,
                second,
                "越界更新",
                "other",
                start,
                None,
                request_id="cross-event-update",
            )

    def test_eligibility_preview_exposes_only_minimal_manager_projection(self):
        officer = self.repository.create_person("虛構預覽幹部", access_level="officer")
        player = self.repository.create_person(
            "虛構球員顯示名稱", qualifications=("team_player",)
        )
        nonqualified = self.repository.create_person("虛構人工納入對象")
        event_id = self.repository.create_event(
            officer.id,
            "虛構資格活動",
            "other",
            datetime.now(timezone.utc) + timedelta(days=2),
            ("team_player",),
        )

        preview = self.repository.eligibility_preview(officer.id, event_id)

        self.assertEqual(preview["qualification_counts"], {"team_player": 1})
        self.assertEqual(preview["candidate_count"], 1)
        self.assertIn("虛構球員顯示名稱", repr(preview))
        self.assertNotIn("provider", repr(preview).lower())
        self.assertNotIn("contact", repr(preview).lower())
        self.assertEqual(set(preview["candidates"][0]), {"person_id", "display_name"})
        self.assertIn(player.id, {row["person_id"] for row in preview["candidates"]})
        self.assertIn(
            nonqualified.id,
            {row["person_id"] for row in preview["override_targets"]},
        )
        with self.assertRaises(ConflictError):
            self.repository.set_invitee_override(
                officer.id,
                event_id,
                999999,
                "include",
                "other",
                "有效理由",
                "override-missing-person",
            )
        with self.assertRaises(Exception):
            self.repository.set_invitee_override(
                officer.id,
                event_id,
                player.id,
                "exclude",
                "team_player",
                "短",
                "override-short-reason",
            )

    def test_published_edit_and_cancel_are_audited_without_changing_snapshot(self):
        officer = self.repository.create_person("虛構發布幹部", access_level="officer")
        player = self.repository.create_person(
            "虛構快照成員", qualifications=("team_player",)
        )
        start = datetime.now(timezone.utc) + timedelta(days=4)
        event_id = self.repository.create_event(
            officer.id, "發布前名稱", "meal", start, ("team_player",)
        )
        self.repository.publish_event(officer.id, event_id, "publish-once")
        snapshot = self.repository.event_invitees(event_id)
        version = self.repository.managed_event(officer.id, event_id)["version"]

        self.repository.update_event(
            officer.id,
            event_id,
            "發布後名稱",
            "social",
            start + timedelta(hours=1),
            start + timedelta(hours=2),
            ("affiliate",),
            version,
            "published-edit-once",
        )
        self.repository.cancel_event(officer.id, event_id, "cancel-once")
        self.repository.cancel_event(officer.id, event_id, "cancel-once")

        self.assertEqual(self.repository.event_invitees(event_id), snapshot)
        self.assertEqual(snapshot[0].person_id, player.id)
        self.assertEqual(
            [audit["action"] for audit in self.repository.event_audits(event_id)],
            ["published", "edited", "cancelled"],
        )
        self.assertEqual(
            self.repository.managed_event(officer.id, event_id)["status"],
            "cancelled",
        )

    def test_published_request_id_replay_requires_exact_operation_and_payload(self):
        officer = self.repository.create_person("虛構重送幹部", access_level="officer")
        start = datetime.now(timezone.utc) + timedelta(days=4)
        event_id = self.repository.create_event(
            officer.id, "虛構重送活動", "meal", start, ("staff",)
        )
        self.repository.publish_event(officer.id, event_id, "publish-replay-contract")
        version = self.repository.managed_event(officer.id, event_id)["version"]
        changed = self.repository.update_event(
            officer.id,
            event_id,
            "虛構精確更新",
            "social",
            start,
            None,
            ("staff",),
            version,
            "exact-edit-request",
        )
        self.repository.update_event(
            officer.id,
            event_id,
            "虛構精確更新",
            "social",
            start,
            None,
            ("staff",),
            version,
            "exact-edit-request",
        )
        with self.assertRaises(ConflictError):
            self.repository.update_event(
                officer.id,
                event_id,
                "虛構精確更新",
                "social",
                start,
                None,
                ("staff",),
                changed["version"],
                "exact-edit-request",
            )
        with self.assertRaises(ConflictError):
            self.repository.update_event(
                officer.id,
                event_id,
                "不同內容",
                "social",
                start,
                None,
                ("staff",),
                changed["version"],
                "exact-edit-request",
            )
        activity_id = self.repository.add_activity(
            officer.id,
            event_id,
            "精確行程",
            "meal",
            start,
            None,
            "exact-activity-request",
        )
        self.assertEqual(
            self.repository.add_activity(
                officer.id,
                event_id,
                "精確行程",
                "meal",
                start,
                None,
                "exact-activity-request",
            ),
            activity_id,
        )
        with self.assertRaises(ConflictError):
            self.repository.add_activity(
                officer.id,
                event_id,
                "碰撞行程",
                "meal",
                start,
                None,
                "exact-activity-request",
            )
        with self.assertRaises(ConflictError):
            self.repository.cancel_event(officer.id, event_id, "exact-activity-request")

    def test_published_move_checks_replay_before_boundary_noop(self):
        officer = self.repository.create_person("虛構排序幹部", access_level="officer")
        start = datetime.now(timezone.utc) + timedelta(days=4)
        event_id = self.repository.create_event(
            officer.id, "虛構排序活動", "trip", start, ("staff",)
        )
        first = self.repository.add_activity(
            officer.id, event_id, "第一站", "gathering", start, None
        )
        second = self.repository.add_activity(
            officer.id,
            event_id,
            "第二站",
            "meal",
            start + timedelta(hours=1),
            None,
        )
        self.repository.publish_event(officer.id, event_id, "publish-move-boundary")

        self.repository.move_activity(
            officer.id, event_id, second, "up", "exact-move-request"
        )
        self.repository.move_activity(
            officer.id, event_id, second, "up", "exact-move-request"
        )
        with self.assertRaises(ConflictError):
            self.repository.move_activity(
                officer.id, event_id, first, "down", "exact-move-request"
            )
        before = len(self.repository.event_audits(event_id))
        self.repository.move_activity(
            officer.id, event_id, first, "down", "new-boundary-noop"
        )
        self.assertEqual(len(self.repository.event_audits(event_id)), before)

    def test_override_and_qualification_changes_serialize_with_publish(self):
        officer = self.repository.create_person("虛構競爭幹部", access_level="officer")
        qualified = self.repository.create_person("虛構競爭球員")
        manual = self.repository.create_person("虛構競爭人工對象")
        event_id = self.repository.create_event(
            officer.id,
            "虛構競爭活動",
            "game",
            datetime.now(timezone.utc) + timedelta(days=4),
            ("team_player",),
        )
        barrier = threading.Barrier(3)
        outcomes = []

        def grant():
            barrier.wait()
            try:
                self.repository.grant_qualification(qualified.id, "team_player")
                outcomes.append("grant")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(("grant-error", error))

        def override():
            barrier.wait()
            try:
                self.repository.set_invitee_override(
                    officer.id,
                    event_id,
                    manual.id,
                    "include",
                    "other",
                    "虛構競爭人工邀請",
                    "concurrent-override",
                )
                outcomes.append("override")
            except ConflictError:
                outcomes.append("override-rejected")

        def publish():
            barrier.wait()
            try:
                self.repository.publish_event(
                    officer.id, event_id, "concurrent-publish"
                )
                outcomes.append("publish")
            except Exception as error:  # pragma: no cover - asserted below
                outcomes.append(("publish-error", error))

        threads = [threading.Thread(target=fn) for fn in (grant, override, publish)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertIn("grant", outcomes)
        self.assertIn("publish", outcomes)
        self.assertTrue(
            "override" in outcomes or "override-rejected" in outcomes, outcomes
        )
        invitees = {
            row.person_id: row for row in self.repository.event_invitees(event_id)
        }
        if "override" in outcomes:
            self.assertTrue(invitees[manual.id].included)
        else:
            self.assertNotIn(manual.id, invitees)
        # A qualification committed after publish must not retroactively change snapshot.
        if qualified.id not in invitees:
            self.assertIn(
                "team_player", self.repository.qualifications_for_person(qualified.id)
            )

    def test_stale_event_version_rolls_back_without_audit(self):
        officer = self.repository.create_person("虛構版本幹部", access_level="officer")
        start = datetime.now(timezone.utc) + timedelta(days=4)
        event_id = self.repository.create_event(
            officer.id, "原始名稱", "meal", start, ("staff",)
        )
        with self.assertRaises(ConflictError):
            self.repository.update_event(
                officer.id,
                event_id,
                "不應儲存",
                "meal",
                start,
                None,
                ("staff",),
                999,
                "stale-edit",
            )
        self.assertEqual(
            self.repository.managed_event(officer.id, event_id)["title"], "原始名稱"
        )
        self.assertEqual(self.repository.event_audits(event_id), ())

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

    def test_publish_mid_build_failure_leaves_no_partial_state(self):
        class FailingRepository(InMemoryTeamPortalRepository):
            def qualifications_for_person(self, person_id):
                if person_id == self.failure_person_id:
                    raise RuntimeError("injected snapshot failure")
                return super().qualifications_for_person(person_id)

        repository = FailingRepository()
        officer = repository.create_person("虛構失敗幹部", access_level="officer")
        repository.create_person("虛構第一球員", qualifications=("team_player",))
        failure = repository.create_person(
            "虛構失敗球員", qualifications=("team_player",)
        )
        repository.failure_person_id = failure.id
        event_id = repository.create_event(
            officer.id,
            "虛構原子發布",
            "game",
            datetime.now(timezone.utc) + timedelta(days=2),
            ("team_player",),
        )

        with self.assertRaises(RuntimeError):
            repository.publish_event(officer.id, event_id, "injected-publish")

        self.assertEqual(repository.event_invitees(event_id), [])
        self.assertEqual(repository.event_audits(event_id), ())
        self.assertEqual(
            repository.managed_event(officer.id, event_id)["status"], "draft"
        )


@unittest.skipUnless(DATABASE_URL, "isolated local PostgreSQL URL not configured")
class PostgresRepositoryContractTests(RepositoryContractMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = require_local_database_url(DATABASE_URL)
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
                      ntubtob.auth_identities, ntubtob.game_attendance_replies,
                      ntubtob.line_users, ntubtob.cancellations, ntubtob.games,
                      ntubtob.members,
                      ntubtob.people
                    RESTART IDENTITY CASCADE;
                    INSERT INTO ntubtob.members (id, name) VALUES
                      (7001, '虛構校友甲'),
                      (7002, '虛構校友乙')
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, person_id = NULL;
                    """
                )
            )
        self.repository = PostgresTeamPortalRepository(
            self.engine, allow_persisted_event_managers=True
        )

    def test_event_manager_allowlist_accepts_linked_basic_person(self):
        actor = self.repository.create_person(
            "虛構白名單管理員", access_level="basic", member_id=7001
        )
        production_repository = PostgresTeamPortalRepository(
            self.engine, event_manager_member_ids=(7001,)
        )

        event_id = production_repository.create_event(
            actor.id,
            "虛構白名單活動",
            "other",
            datetime.now(timezone.utc) + timedelta(days=1),
            ("staff",),
        )

        self.assertIsInstance(event_id, int)

    def test_event_manager_allowlist_rejects_nonallowlisted_persisted_roles(self):
        production_repository = PostgresTeamPortalRepository(
            self.engine, event_manager_member_ids=(7001,)
        )
        for access_level in ("officer", "admin"):
            with self.subTest(access_level=access_level):
                actor = self.repository.create_person(
                    f"虛構非白名單{access_level}",
                    access_level=access_level,
                    member_id=7002,
                )
                with self.assertRaises(AuthorizationError):
                    production_repository.create_event(
                        actor.id,
                        "不得建立的活動",
                        "other",
                        datetime.now(timezone.utc) + timedelta(days=1),
                        ("staff",),
                    )
                with self.engine.begin() as connection:
                    connection.execute(
                        text("UPDATE ntubtob.members SET person_id=NULL WHERE id=7002")
                    )

    def test_event_manager_preview_mode_accepts_persisted_role(self):
        actor = self.repository.create_person("虛構預覽幹部", access_level="officer")

        event_id = self.repository.create_event(
            actor.id,
            "虛構預覽活動",
            "other",
            datetime.now(timezone.utc) + timedelta(days=1),
            ("staff",),
        )

        self.assertIsInstance(event_id, int)

    def test_event_manager_allowlist_rejects_inactive_or_unlinked_person(self):
        production_repository = PostgresTeamPortalRepository(
            self.engine, event_manager_member_ids=(7001,)
        )
        inactive = self.repository.create_person(
            "虛構停用管理員",
            access_level="basic",
            status="inactive",
            member_id=7001,
        )
        unlinked = self.repository.create_person(
            "虛構未連結管理員", access_level="admin"
        )

        for actor in (inactive, unlinked):
            with self.subTest(person_id=actor.id), self.assertRaises(
                AuthorizationError
            ):
                production_repository.create_event(
                    actor.id,
                    "不得建立的活動",
                    "other",
                    datetime.now(timezone.utc) + timedelta(days=1),
                    ("staff",),
                )

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
