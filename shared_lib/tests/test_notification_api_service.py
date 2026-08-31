import base64
import json
import unittest
from datetime import datetime, timedelta, timezone

from shared_module.mobile_api import (
    BasicApiService,
    InvalidArgument,
    MobilePrincipal,
    NotFound,
)

NOW = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
PRINCIPAL = MobilePrincipal("session", 23, 7, "basic", "Member", 1)


class FakeNotificationRepository:
    def __init__(self):
        self.rows = [
            {
                "id": 3,
                "type": "event_updated",
                "title": "場地異動",
                "body": "比賽改到第二球場。",
                "created_at": NOW - timedelta(minutes=1),
                "visible_until": NOW - timedelta(minutes=1) + timedelta(days=90),
                "read_at": None,
                "destination_type": "event",
                "destination_event_id": 91,
            },
            {
                "id": 2,
                "type": "game_reminder",
                "title": "比賽提醒",
                "body": "明天上午集合。",
                "created_at": NOW - timedelta(minutes=2),
                "visible_until": NOW - timedelta(minutes=2) + timedelta(days=90),
                "read_at": NOW - timedelta(seconds=30),
            },
            {
                "id": 1,
                "type": "attendance_reminder",
                "title": "請回覆出席",
                "body": "請在今晚前回覆。",
                "created_at": NOW - timedelta(minutes=3),
                "visible_until": NOW - timedelta(minutes=3) + timedelta(days=90),
                "read_at": None,
            },
        ]
        self.calls = []

    def notification_page(self, person_id, now, cursor, limit, unread_only):
        self.calls.append((person_id, cursor, limit, unread_only))
        rows = self.rows
        if unread_only:
            rows = [row for row in rows if row["read_at"] is None]
        if cursor is not None:
            rows = [row for row in rows if (row["created_at"], row["id"]) < cursor]
        return [
            {**row, "_cursor_created_at": row["created_at"]} for row in rows[:limit]
        ]

    def notification_detail(self, person_id, notification_id, now):
        self.calls.append((person_id, notification_id))
        return next((row for row in self.rows if row["id"] == notification_id), None)

    def notification_unread_count(self, person_id, now):
        self.calls.append((person_id, "count"))
        return sum(row["read_at"] is None for row in self.rows)

    def mark_notification_read(self, person_id, notification_id, now):
        self.calls.append((person_id, notification_id, "read"))
        row = self.notification_detail(person_id, notification_id, now)
        if row is None:
            return None
        changed = row["read_at"] is None
        if changed:
            row["read_at"] = now
        return row["read_at"], changed

    def mark_all_notifications_read(self, person_id, now):
        self.calls.append((person_id, "read-all"))
        changed = 0
        for row in self.rows:
            if row["read_at"] is None:
                row["read_at"] = now
                changed += 1
        return changed, 0


class NotificationApiServiceTest(unittest.TestCase):
    def setUp(self):
        self.repository = FakeNotificationRepository()
        self.service = BasicApiService(
            object(), object(), self.repository, clock=lambda: NOW
        )

    def test_list_uses_principal_scope_and_deterministic_keyset_cursor(self):
        first = self.service.notifications_page(PRINCIPAL, None, 2, False)
        second = self.service.notifications_page(
            PRINCIPAL, first["next_cursor"], 2, False
        )

        self.assertEqual(
            [item["id"] for item in first["items"]],
            ["notification_3", "notification_2"],
        )
        self.assertEqual([item["id"] for item in second["items"]], ["notification_1"])
        self.assertEqual(self.repository.calls[0][0], PRINCIPAL.person_id)
        self.assertEqual(
            self.repository.calls[1][1],
            (self.repository.rows[1]["created_at"], 2),
        )

    def test_cursor_and_bounds_fail_before_repository_read(self):
        oversized_id_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "created_at": NOW.isoformat(),
                    "notification_id": 9_223_372_036_854_775_808,
                }
            ).encode("utf-8")
        ).decode("ascii")
        for cursor, limit in (
            ("not-a-cursor", 20),
            (oversized_id_cursor, 20),
            (None, 0),
            (None, 101),
        ):
            with self.subTest(cursor=cursor, limit=limit):
                with self.assertRaises(InvalidArgument):
                    self.service.notifications_page(PRINCIPAL, cursor, limit, False)
        self.assertEqual(self.repository.calls, [])

    def test_detail_count_and_read_mutations_are_principal_only_and_idempotent(self):
        detail = self.service.notification(PRINCIPAL, 3)
        self.assertEqual(detail["body"], "比賽改到第二球場。")
        self.assertEqual(
            detail["destination"], {"type": "event", "event_id": "event_91"}
        )
        self.assertEqual(self.service.notification_unread_count(PRINCIPAL), 2)

        first = self.service.mark_notification_read(PRINCIPAL, 3)
        replay = self.service.mark_notification_read(PRINCIPAL, 3)
        self.assertTrue(first["changed"])
        self.assertFalse(replay["changed"])
        self.assertEqual(first["read_at"], replay["read_at"])

        self.assertEqual(
            self.service.mark_all_notifications_read(PRINCIPAL),
            {"changed_count": 1, "unread_count": 0},
        )
        self.assertEqual(
            self.service.mark_all_notifications_read(PRINCIPAL),
            {"changed_count": 0, "unread_count": 0},
        )
        self.assertTrue(
            all(call[0] == PRINCIPAL.person_id for call in self.repository.calls)
        )

    def test_invisible_or_other_recipient_detail_is_nonleaking_not_found(self):
        with self.assertRaises(NotFound):
            self.service.notification(PRINCIPAL, 999)
        with self.assertRaises(NotFound):
            self.service.mark_notification_read(PRINCIPAL, 999)

    def test_early_expiry_is_rejected_by_service_dto(self):
        self.repository.rows[0]["visible_until"] -= timedelta(seconds=1)
        with self.assertRaisesRegex(
            InvalidArgument, "stored notification visibility is malformed"
        ):
            self.service.notification(PRINCIPAL, 3)

    def test_notification_ids_are_bounded_before_repository(self):
        for operation in (
            self.service.notification,
            self.service.mark_notification_read,
        ):
            for notification_id in (0, 9_223_372_036_854_775_808):
                with self.subTest(
                    operation=operation.__name__, notification_id=notification_id
                ):
                    with self.assertRaisesRegex(
                        InvalidArgument, "notification_id is malformed"
                    ):
                        operation(PRINCIPAL, notification_id)
        self.assertEqual(self.repository.calls, [])


if __name__ == "__main__":
    unittest.main()
