import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch


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
    line_helper = types.SimpleNamespace(announce=Mock())
    line_helper_constructor = Mock(
        side_effect=AssertionError(
            "LineBotAnnouncementHelper must not be constructed during import"
        )
    )
    crawler = type(
        "CrawlerClient",
        (),
        {"__init__": lambda self, url: None, "get_games": fail("crawler")},
    )
    game = type("Game", (), {"search_for_invited": fail("database query")})

    health = load_module("notify_cron_health", SERVICE_DIR / "health.py")
    stubs = {
        "health": health,
        "shared_module": module("shared_module"),
        "shared_module.games_crawler_client": module(
            "shared_module.games_crawler_client", CrawlerClient=crawler
        ),
        "shared_module.models": module("shared_module.models"),
        "shared_module.models.games": module(
            "shared_module.models.games", Game=game
        ),
        "shared_module.message_templates": module(
            "shared_module.message_templates"
        ),
        "shared_module.message_templates.linebot_game_message": module(
            "shared_module.message_templates.linebot_game_message"
        ),
        "shared_module.notify": module("shared_module.notify"),
        "shared_module.notify.discord_notify": module(
            "shared_module.notify.discord_notify",
            DiscordNotifyHelper=Mock(return_value=discord_helper),
        ),
        "shared_module.announcement": module("shared_module.announcement"),
        "shared_module.announcement.linebot": module(
            "shared_module.announcement.linebot",
            LineBotAnnouncementHelper=line_helper_constructor,
        ),
        "shared_module.message_templates.line_notify_message": module(
            "shared_module.message_templates.line_notify_message",
            generate_error_message=fail("error template"),
            generate_schedule_message_for_team=fail("schedule template"),
        ),
        "shared_module.attendance_analyzer": module(
            "shared_module.attendance_analyzer",
            get_attendance_of_game=fail("attendance database query"),
        ),
        "shared_module.message_templates.linebot_attendance_message": module(
            "shared_module.message_templates.linebot_attendance_message",
            produce_attendance_message_text=fail("attendance template"),
        ),
        "shared_module.portal_data": module("shared_module.portal_data"),
        "shared_module.portal_data.runtime": module(
            "shared_module.portal_data.runtime",
            is_rollout_freeze_enabled=lambda: os.environ.get(
                "PORTAL_DATA_ROLLOUT_FREEZE_ENABLED"
            )
            == "true",
        ),
        "envs": module("envs", game_crawl_api="unused"),
        "message_templates": module(
            "message_templates",
            run_future_game_announcement_successful="unused",
            run_future_game_announcement="unused {result}",
            run_game_attendance_count_successful="unused",
            run_game_attendance_count="unused {result}",
        ),
    }

    with patch.dict(sys.modules, stubs):
        loaded = load_module("notify_cron_app_under_test", SERVICE_DIR / "app.py")
    return loaded, line_helper_constructor, line_helper, fail_calls


class HealthRouteTests(unittest.TestCase):
    def setUp(self):
        (
            self.app_module,
            self.line_helper_constructor,
            self.line_helper,
            self.fail_calls,
        ) = load_isolated_service_app()
        self.app = self.app_module.app

    def test_get_healthz_on_actual_app_is_side_effect_free(self):
        client = self.app.test_client()

        for _ in range(2):
            response = client.get("/healthz")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.get_json(),
                {"service": "notify-cronjob-service", "status": "ok"},
            )
            self.assertEqual(response.content_type, "application/json")
            self.assertEqual(response.headers["Cache-Control"], "no-store")

        for dependency in self.fail_calls:
            dependency.assert_not_called()
        self.line_helper_constructor.assert_not_called()

    def test_announce_lazily_constructs_and_reuses_line_helper(self):
        self.line_helper_constructor.side_effect = None
        self.line_helper_constructor.return_value = self.line_helper

        self.app_module.announce("first message")
        self.app_module.announce("second message")

        self.line_helper_constructor.assert_called_once_with()
        self.assertEqual(
            self.line_helper.announce.call_args_list,
            [call("first message"), call("second message")],
        )

    def test_route_methods_preserve_business_contract(self):
        methods_by_path = {
            rule.rule: rule.methods for rule in self.app.url_map.iter_rules()
        }
        self.assertEqual(methods_by_path["/healthz"], {"GET", "HEAD", "OPTIONS"})
        for path in (
            "/run-future-game-announcement",
            "/run-game-attendance-count",
        ):
            self.assertEqual(methods_by_path[path], {"POST", "OPTIONS"})
        self.assertEqual(self.app.test_client().post("/healthz").status_code, 405)

    def test_frozen_attendance_count_is_successful_zero_side_effect_noop(self):
        with patch.dict(
            os.environ,
            {"PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "true"},
            clear=False,
        ):
            response = self.app.test_client().post("/run-game-attendance-count")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"classification": "rollout_freeze", "status": "ok"},
        )
        for dependency in self.fail_calls:
            dependency.assert_not_called()
        self.line_helper_constructor.assert_not_called()

    def test_freeze_does_not_block_non_attendance_announcement_route(self):
        crawler = Mock()
        crawler.get_games.return_value = []
        with patch.dict(
            os.environ,
            {"PORTAL_DATA_ROLLOUT_FREEZE_ENABLED": "true"},
            clear=False,
        ), patch.object(
            self.app_module, "CrawlerClient", return_value=crawler
        ), patch.object(
            self.app_module, "generate_schedule_message_for_team", return_value="safe"
        ), patch.object(
            self.app_module, "announce"
        ) as announce, patch.object(
            self.app_module, "notify_successful_log"
        ) as notify_success:
            response = self.app.test_client().post("/run-future-game-announcement")

        self.assertEqual(response.status_code, 200)
        crawler.get_games.assert_called_once_with()
        announce.assert_called_once_with("safe")
        notify_success.assert_called_once_with(
            self.app_module.message_templates.run_future_game_announcement_successful
        )


if __name__ == "__main__":
    unittest.main()
