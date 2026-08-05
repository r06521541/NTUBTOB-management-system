import importlib.util
import sys
import types
import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import Mock, patch


SERVICE_DIR = Path(__file__).resolve().parents[1]


def module(name, **attributes):
    result = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(result, attribute, value)
    return result


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def load_isolated_service_app():
    fail_calls = []

    def fail(name):
        mock = Mock(side_effect=AssertionError(f"{name} must not be called"))
        fail_calls.append(mock)
        return mock

    discord_helper = types.SimpleNamespace(
        notify_successful_log=fail("discord success notification"),
        notify_alarm_log=fail("discord alarm notification"),
        notify_management_message=fail("discord management notification"),
    )
    line_helper = types.SimpleNamespace(announce=fail("LINE announcement"))
    game = type("Game", (), {})
    for method_name in (
        "search_for_invitation",
        "search_for_invited",
        "search_cancelled_to_announce",
        "update_invitation_time",
        "update_cancellation_announcement_time",
    ):
        setattr(game, method_name, fail(f"Game.{method_name}"))

    health = load_module("game_broadcast_health", SERVICE_DIR / "health.py")
    stubs = {
        "health": health,
        "linebot": module("linebot"),
        "linebot.v3": module("linebot.v3"),
        "linebot.v3.messaging": module(
            "linebot.v3.messaging", FlexMessage=object, TextMessage=object
        ),
        "shared_module": module("shared_module"),
        "shared_module.models": module("shared_module.models"),
        "shared_module.models.games": module(
            "shared_module.models.games", Game=game
        ),
        "shared_module.message_templates": module(
            "shared_module.message_templates"
        ),
        "shared_module.message_templates.linebot_game_message": module(
            "shared_module.message_templates.linebot_game_message",
            produce_invitation_messages_by_games=fail("invitation template"),
            produce_cancellation_message_by_games=fail("cancellation template"),
        ),
        "shared_module.notify": module("shared_module.notify"),
        "shared_module.notify.discord_notify": module(
            "shared_module.notify.discord_notify",
            DiscordNotifyHelper=Mock(return_value=discord_helper),
        ),
        "shared_module.announcement": module("shared_module.announcement"),
        "shared_module.announcement.linebot": module(
            "shared_module.announcement.linebot",
            LineBotAnnouncementHelper=Mock(return_value=line_helper),
        ),
        "shared_module.linebot_config": module("shared_module.linebot_config"),
        "shared_module.settings": module(
            "shared_module.settings", local_timezone=timezone.utc
        ),
        "shared_module.line_messaging_api": module(
            "shared_module.line_messaging_api", broadcast=fail("LINE broadcast")
        ),
        "message_templates_notify_user": module(
            "message_templates_notify_user",
            new_and_old_invitation_notification="unused",
            invitation_notification="unused",
        ),
        "message_templates_user": module(
            "message_templates_user", invitation_intro="unused"
        ),
        "message_templates_management": module(
            "message_templates_management",
            invited="unused {count}",
            invite_failed="unused",
            invite_finish="unused",
            cancellation_announced="unused {count}",
            cancellation_announce_failed="unused",
            announce_cancellation_finish="unused",
            game_reminder_failed="unused",
        ),
        "game_reminder": module(
            "game_reminder", get_game_reminder_string=fail("weather reminder")
        ),
        "request_time": module(
            "request_time", get_request_time_window=fail("request time")
        ),
    }

    with patch.dict(sys.modules, stubs):
        loaded = load_module("game_broadcast_app_under_test", SERVICE_DIR / "app.py")
    return loaded.app, fail_calls


class HealthRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.fail_calls = load_isolated_service_app()

    def test_get_healthz_on_actual_app_is_side_effect_free(self):
        client = self.app.test_client()

        for _ in range(2):
            response = client.get("/healthz")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.get_json(),
                {"service": "game-broadcast-service", "status": "ok"},
            )
            self.assertEqual(response.content_type, "application/json")
            self.assertEqual(response.headers["Cache-Control"], "no-store")

        for dependency in self.fail_calls:
            dependency.assert_not_called()

    def test_route_methods_preserve_business_contract(self):
        methods_by_path = {
            rule.rule: rule.methods for rule in self.app.url_map.iter_rules()
        }
        self.assertEqual(methods_by_path["/healthz"], {"GET", "HEAD", "OPTIONS"})
        for path in (
            "/invitation-announcement/trigger",
            "/cancellation-announcement/trigger",
            "/game-reminder/trigger",
        ):
            self.assertEqual(methods_by_path[path], {"POST", "OPTIONS"})
        self.assertEqual(self.app.test_client().post("/healthz").status_code, 405)


if __name__ == "__main__":
    unittest.main()
