import importlib.util
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask, g

FUNCTION_DIR = Path(__file__).resolve().parents[1]


class FakeWebhookHandler:
    def __init__(self, _secret):
        pass

    def default(self):
        return lambda function: function

    def handle(self, _body, _signature):
        pass


class FakeMessage:
    def __init__(self, **values):
        self.__dict__.update(values)


class FakeAttendanceReply:
    add = Mock()
    search_by_member_id = Mock()
    search_single_game_reply_of_member = Mock()

    def __init__(self, game_id, line_user_id, member_id, reply):
        self.game_id = game_id
        self.line_user_id = line_user_id
        self.member_id = member_id
        self.reply = reply


class AttendanceReplyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_modules = {}
        cls.stub_names = []
        cls._install_stubs()
        cls.original_channel_secret = os.environ.get("CHANNEL_SECRET")
        cls.original_channel_token = os.environ.get("CHANNEL_ACCESS_TOKEN")
        os.environ["CHANNEL_SECRET"] = "fake-channel-secret"
        os.environ["CHANNEL_ACCESS_TOKEN"] = "fake-channel-token"
        sys.path.insert(0, str(FUNCTION_DIR))
        spec = importlib.util.spec_from_file_location(
            "line_webhook_attendance_test", FUNCTION_DIR / "webhook.py"
        )
        cls.webhook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.webhook)
        cls.app = Flask(__name__)

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(FUNCTION_DIR))
        for key, original in (
            ("CHANNEL_SECRET", cls.original_channel_secret),
            ("CHANNEL_ACCESS_TOKEN", cls.original_channel_token),
        ):
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original
        for name in reversed(cls.stub_names):
            original = cls.original_modules[name]
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    @classmethod
    def _stub(cls, name, **attributes):
        cls.original_modules[name] = sys.modules.get(name)
        cls.stub_names.append(name)
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        sys.modules[name] = module

    @classmethod
    def _install_stubs(cls):
        cls._stub("linebot", __path__=[])
        cls._stub("linebot.v3", WebhookHandler=FakeWebhookHandler, __path__=[])
        cls._stub("linebot.v3.messaging", __path__=[])
        cls._stub("linebot.v3.messaging.models", __path__=[])
        cls._stub("linebot.v3.messaging.models.message", Message=FakeMessage)
        cls._stub(
            "linebot.v3.messaging",
            TextMessage=FakeMessage,
            FlexMessage=FakeMessage,
            PushMessageRequest=FakeMessage,
            ApiException=RuntimeError,
            __path__=[],
        )
        webhook_types = {
            name: type(name, (), {})
            for name in (
                "Event",
                "FollowEvent",
                "UnfollowEvent",
                "MessageEvent",
                "TextMessageContent",
                "StickerMessageContent",
                "PostbackEvent",
            )
        }
        cls._stub("linebot.v3.webhooks", **webhook_types)

        cls._stub("shared_module", __path__=[])
        cls._stub("shared_module.models", __path__=[])
        cls._stub("shared_module.models.line_users", LineUser=type("LineUser", (), {}))
        cls._stub("shared_module.models.games", Game=type("Game", (), {}))
        cls._stub(
            "shared_module.models.line_groups", LineGroup=type("LineGroup", (), {})
        )
        cls._stub(
            "shared_module.models.game_attendance_replies",
            GameAttendanceReply=FakeAttendanceReply,
        )
        cls._stub("shared_module.message_templates", __path__=[])
        cls._stub(
            "shared_module.message_templates.linebot_game_message",
            produce_invitation_messages_by_games=Mock(),
            produce_message_of_game_query_attendance=Mock(),
        )
        cls._stub(
            "shared_module.message_templates.general_message",
            reply_text_mapping={1: "attending", 2: "absent", 5: "pending"},
        )
        cls._stub("shared_module.notify", __path__=[])
        cls._stub(
            "shared_module.notify.discord_notify",
            DiscordNotifyHelper=lambda: types.SimpleNamespace(
                notify_successful_log=Mock(),
                notify_alarm_log=Mock(),
                notify_management_message=Mock(),
            ),
        )
        cls._stub("shared_module.attendance_analyzer", get_attendance_of_game=Mock())
        cls._stub(
            "shared_module.message_templates.linebot_attendance_message",
            produce_attendance_message=Mock(),
        )
        cls._stub("shared_module.line_messaging_api", reply=Mock())
        cls._stub("shared_module.portal_data", __path__=[])
        cls._stub(
            "shared_module.portal_data.domain",
            AuthorizationError=type("AuthorizationError", (Exception,), {}),
            ConflictError=type("ConflictError", (Exception,), {}),
            ValidationError=type("ValidationError", (Exception,), {}),
        )
        cls._stub(
            "shared_module.portal_data.runtime",
            get_identity_lifecycle_repository=Mock(),
            is_phase_c_enabled=lambda: os.environ.get("PORTAL_DATA_PHASE_C_ENABLED")
            == "true",
        )

    def setUp(self):
        FakeAttendanceReply.add.reset_mock()
        FakeAttendanceReply.search_by_member_id.reset_mock(return_value=True)
        FakeAttendanceReply.search_by_member_id.return_value = [object()]
        FakeAttendanceReply.search_single_game_reply_of_member.reset_mock(
            return_value=True
        )
        FakeAttendanceReply.search_single_game_reply_of_member.return_value = []
        self.webhook.Game.search_by_id = Mock(return_value=self.make_game())
        self.webhook.notify_management_message = Mock()

    @staticmethod
    def make_game(*, hours_from_now=48, cancelled=False):
        return types.SimpleNamespace(
            start_datetime=datetime.now(timezone.utc) + timedelta(hours=hours_from_now),
            cancellation_time=datetime.now(timezone.utc) if cancelled else None,
            generate_verbal_summary_for_team=lambda: "Fictional game",
        )

    def run_reply(self, query="id=23&reply=1", **user_values):
        user = types.SimpleNamespace(
            id=9,
            member_id=7,
            has_replied=True,
            member=types.SimpleNamespace(name="Demo Member"),
        )
        user.__dict__.update(user_values)
        with self.app.test_request_context(), patch.object(
            self.webhook.requests.sessions.Session,
            "request",
            side_effect=AssertionError("attendance reply must not use HTTP"),
        ):
            g.user = user
            g.user_id = "fake-line-subject"
            g.messages_to_reply = []
            self.webhook.handle_postback_reply_game_attendance(query)
            return [message.text for message in g.messages_to_reply]

    def test_new_reply_is_stored_and_acknowledged_without_http(self):
        messages = self.run_reply()

        FakeAttendanceReply.add.assert_called_once()
        saved = FakeAttendanceReply.add.call_args.args[0]
        self.assertEqual(
            (saved.game_id, saved.line_user_id, saved.member_id, saved.reply),
            (23, 9, 7, 1),
        )
        self.assertIn("Fictional game", messages[0])
        self.webhook.notify_management_message.assert_not_called()

    def test_same_reply_is_acknowledged_without_duplicate_write(self):
        FakeAttendanceReply.search_single_game_reply_of_member.return_value = [
            types.SimpleNamespace(reply=1)
        ]

        messages = self.run_reply()

        FakeAttendanceReply.add.assert_not_called()
        self.assertIn("沒變", messages[0])

    def test_unpaired_user_stops_before_game_or_database_queries(self):
        messages = self.run_reply(member_id=None)

        self.assertTrue(messages)
        self.webhook.Game.search_by_id.assert_not_called()
        FakeAttendanceReply.search_by_member_id.assert_not_called()
        FakeAttendanceReply.add.assert_not_called()

    def test_user_without_first_message_stops_before_game_queries(self):
        messages = self.run_reply(has_replied=False)

        self.assertTrue(messages)
        self.webhook.Game.search_by_id.assert_not_called()
        FakeAttendanceReply.add.assert_not_called()

    def test_past_game_does_not_write_or_notify(self):
        self.webhook.Game.search_by_id.return_value = self.make_game(hours_from_now=-1)

        messages = self.run_reply()

        self.assertIn("結束", messages[0])
        FakeAttendanceReply.add.assert_not_called()
        self.webhook.notify_management_message.assert_not_called()

    def test_cancelled_game_does_not_write_or_notify(self):
        self.webhook.Game.search_by_id.return_value = self.make_game(cancelled=True)

        messages = self.run_reply()

        self.assertIn("取消", messages[0])
        FakeAttendanceReply.add.assert_not_called()
        self.webhook.notify_management_message.assert_not_called()

    def test_late_changed_reply_keeps_management_notification(self):
        self.webhook.Game.search_by_id.return_value = self.make_game(hours_from_now=2)

        self.run_reply()

        FakeAttendanceReply.add.assert_called_once()
        self.webhook.notify_management_message.assert_called_once()

    def test_first_reply_keeps_existing_hint(self):
        FakeAttendanceReply.search_by_member_id.return_value = []

        messages = self.run_reply()

        self.assertGreaterEqual(len(messages), 2)
        self.assertEqual(
            messages[-1],
            self.webhook.message_templates_user.first_game_reply_hint,
        )

    def test_phase_c_reply_uses_person_repository_without_legacy_member_write(self):
        person = types.SimpleNamespace(
            id=44, preferred_name=lambda: "Fake Guest Formal"
        )
        repository = types.SimpleNamespace(
            resolve_line_principal=Mock(
                return_value=types.SimpleNamespace(person=person)
            ),
            reply_to_game=Mock(return_value=True),
        )
        runtime = sys.modules["shared_module.portal_data.runtime"]
        runtime.get_identity_lifecycle_repository.return_value = repository

        with patch.dict(os.environ, {"PORTAL_DATA_PHASE_C_ENABLED": "true"}):
            messages = self.run_reply()

        repository.resolve_line_principal.assert_called_once_with("fake-line-subject")
        repository.reply_to_game.assert_called_once_with(44, 23, 1, 9)
        FakeAttendanceReply.add.assert_not_called()
        self.assertIn("Fictional game", messages[0])


if __name__ == "__main__":
    unittest.main()
