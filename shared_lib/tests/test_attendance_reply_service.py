import logging
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from shared_lib.shared_module.attendance_reply import (
    AttendanceReplyCommand,
    AttendanceReplyNotification,
    AttendanceReplyService,
    NotificationStatus,
)


class AttendanceReplyServiceTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)
        self.repository = SimpleNamespace(reply_to_game=Mock(return_value=True))
        self.notifier = Mock()
        self.logger = Mock(spec=logging.Logger)
        self.service = AttendanceReplyService(
            self.repository,
            self.notifier,
            clock=lambda: self.now,
            logger=self.logger,
        )

    def command(self, *, starts_in=timedelta(hours=6), reply=1):
        return AttendanceReplyCommand(
            person_id=44,
            game_id=23,
            reply=reply,
            game_start=self.now + starts_in,
            notification=AttendanceReplyNotification(
                game_summary="Fictional game",
                person_name="Fake Player",
                reply_label="attending",
            ),
            user_id=9,
        )

    def test_changed_reply_is_persisted_before_urgent_notification(self):
        calls = []
        self.repository.reply_to_game.side_effect = (
            lambda *args: calls.append("persisted") or True
        )
        self.notifier.side_effect = lambda _notification: calls.append("notified")

        result = self.service.reply(self.command())

        self.assertEqual(calls, ["persisted", "notified"])
        self.repository.reply_to_game.assert_called_once_with(44, 23, 1, 9)
        self.assertTrue(result.changed)
        self.assertTrue(result.urgent)
        self.assertEqual(result.notification_status, NotificationStatus.SUCCEEDED)

    def test_same_reply_does_not_notify(self):
        self.repository.reply_to_game.return_value = False

        result = self.service.reply(self.command())

        self.assertFalse(result.changed)
        self.assertFalse(result.urgent)
        self.assertEqual(result.notification_status, NotificationStatus.NOT_REQUIRED)
        self.notifier.assert_not_called()

    def test_reply_more_than_twelve_hours_before_game_does_not_notify(self):
        result = self.service.reply(self.command(starts_in=timedelta(hours=13)))

        self.assertTrue(result.changed)
        self.assertFalse(result.urgent)
        self.assertEqual(result.notification_status, NotificationStatus.NOT_REQUIRED)
        self.notifier.assert_not_called()

    def test_reply_exactly_twelve_hours_before_game_does_not_notify(self):
        result = self.service.reply(self.command(starts_in=timedelta(hours=12)))

        self.assertTrue(result.changed)
        self.assertFalse(result.urgent)
        self.assertEqual(result.notification_status, NotificationStatus.NOT_REQUIRED)
        self.notifier.assert_not_called()

    def test_reply_just_inside_twelve_hours_notifies(self):
        result = self.service.reply(
            self.command(starts_in=timedelta(hours=12) - timedelta(microseconds=1))
        )

        self.assertTrue(result.urgent)
        self.assertEqual(result.notification_status, NotificationStatus.SUCCEEDED)
        self.notifier.assert_called_once()

    def test_notification_failure_is_a_safe_result_after_persistence(self):
        self.notifier.side_effect = RuntimeError("fake secret-bearing SDK detail")

        result = self.service.reply(self.command())

        self.repository.reply_to_game.assert_called_once()
        self.assertTrue(result.changed)
        self.assertEqual(result.notification_status, NotificationStatus.FAILED)
        self.assertEqual(result.notification_error, "attendance_notification_failed")
        self.logger.warning.assert_called_once_with(
            "attendance_reply_notification_failed"
        )

    def test_repository_failure_propagates_without_notification(self):
        failure = RuntimeError("repository rejected reply")
        self.repository.reply_to_game.side_effect = failure

        with self.assertRaises(RuntimeError) as raised:
            self.service.reply(self.command())

        self.assertIs(raised.exception, failure)
        self.notifier.assert_not_called()

    def test_invalid_reply_is_left_to_repository_contract(self):
        failure = ValueError("invalid reply")
        self.repository.reply_to_game.side_effect = failure

        with self.assertRaises(ValueError):
            self.service.reply(self.command(reply=99))

        self.repository.reply_to_game.assert_called_once_with(44, 23, 99, 9)
        self.notifier.assert_not_called()

    def test_absent_user_id_preserves_three_argument_repository_caller(self):
        command = self.command()
        command = AttendanceReplyCommand(
            person_id=command.person_id,
            game_id=command.game_id,
            reply=command.reply,
            game_start=command.game_start,
            notification=command.notification,
        )

        self.service.reply(command)

        self.repository.reply_to_game.assert_called_once_with(44, 23, 1)

    def test_naive_game_start_fails_before_repository(self):
        command = self.command()
        command = AttendanceReplyCommand(
            person_id=command.person_id,
            game_id=command.game_id,
            reply=command.reply,
            game_start=command.game_start.replace(tzinfo=None),
            notification=command.notification,
            user_id=command.user_id,
        )

        with self.assertRaises(ValueError):
            self.service.reply(command)

        self.repository.reply_to_game.assert_not_called()
        self.notifier.assert_not_called()

    def test_naive_clock_fails_before_persistence(self):
        service = AttendanceReplyService(
            self.repository,
            self.notifier,
            clock=lambda: datetime(2026, 8, 18, 12),
            logger=self.logger,
        )

        with self.assertRaises(ValueError):
            service.reply(self.command())

        self.repository.reply_to_game.assert_not_called()
        self.notifier.assert_not_called()

    def test_notification_message_preserves_existing_management_contract(self):
        notification = self.command().notification

        self.assertEqual(
            notification.management_message(),
            "緊急！Fake Player臨時回覆Fictional game這場：\nattending",
        )

    def test_game_already_started_at_notification_time_does_not_notify(self):
        result = self.service.reply(self.command(starts_in=timedelta(0)))

        self.assertTrue(result.changed)
        self.assertFalse(result.urgent)
        self.notifier.assert_not_called()


if __name__ == "__main__":
    unittest.main()
