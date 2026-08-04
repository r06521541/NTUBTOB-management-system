import importlib
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

SERVICE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_DIR))


def install_requests_stub():
    requests = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class Timeout(RequestException):
        pass

    class HTTPError(RequestException):
        pass

    requests.RequestException = RequestException
    requests.Timeout = Timeout
    requests.HTTPError = HTTPError
    requests.get = Mock()
    sys.modules["requests"] = requests
    return requests


def install_shared_module_stubs():
    shared_module = types.ModuleType("shared_module")
    models = types.ModuleType("shared_module.models")
    games = types.ModuleType("shared_module.models.games")
    ballparks = types.ModuleType("shared_module.models.ballparks")
    settings = types.ModuleType("shared_module.settings")
    message_templates = types.ModuleType("shared_module.message_templates")
    general_message = types.ModuleType(
        "shared_module.message_templates.general_message"
    )

    games.Game = type("Game", (), {})
    ballparks.Ballpark = type("Ballpark", (), {})
    settings.local_timezone = timezone(timedelta(hours=8))
    general_message.weekday_mapping = {
        "Monday": "一",
        "Tuesday": "二",
        "Wednesday": "三",
        "Thursday": "四",
        "Friday": "五",
        "Saturday": "六",
        "Sunday": "日",
    }

    modules = {
        "shared_module": shared_module,
        "shared_module.models": models,
        "shared_module.models.games": games,
        "shared_module.models.ballparks": ballparks,
        "shared_module.settings": settings,
        "shared_module.message_templates": message_templates,
        "shared_module.message_templates.general_message": general_message,
    }
    sys.modules.update(modules)


requests = install_requests_stub()
install_shared_module_stubs()
envs = importlib.import_module("envs")
game_reminder = importlib.import_module("game_reminder")


class FakeGameDateTime:
    def astimezone(self, target_timezone):
        return self

    def __add__(self, delta):
        return self

    def strftime(self, date_format):
        values = {
            "%-m/%-d（%a）": "8/4（Tue）",
            "%a": "Tue",
            "%A": "Tuesday",
            "%-H:%M": "09:00",
        }
        return values[date_format]


class WeatherEnvironmentTests(unittest.TestCase):
    def test_weather_api_key_is_read_from_environment(self):
        fake_api_key = "test-only-environment-credential"
        with patch.dict(
            os.environ, {"WEATHER_API_KEY": fake_api_key}, clear=True
        ):
            self.assertEqual(envs.get_weather_api_key(), fake_api_key)

    def test_missing_weather_api_key_fails_safely(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "WEATHER_API_KEY is not configured"
            ):
                envs.get_weather_api_key()

    def test_blank_weather_api_key_fails_safely(self):
        with patch.dict(os.environ, {"WEATHER_API_KEY": "   "}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "WEATHER_API_KEY is not configured"
            ):
                envs.get_weather_api_key()


class WeatherRequestTests(unittest.TestCase):
    fake_api_key = "test-only-weather-credential"

    def get_weather_data(self):
        return game_reminder.get_weather_data("063", "中正區")

    @patch("game_reminder.get_weather_api_key")
    @patch("game_reminder.requests.get")
    def test_missing_configuration_is_sanitized(
        self, mock_get, mock_get_weather_api_key
    ):
        mock_get_weather_api_key.side_effect = RuntimeError(
            "WEATHER_API_KEY is not configured"
        )

        with self.assertRaisesRegex(
            game_reminder.WeatherServiceError,
            "Weather API configuration is unavailable",
        ):
            self.get_weather_data()

        mock_get.assert_not_called()

    @patch("game_reminder.get_weather_api_key")
    @patch("game_reminder.requests.get")
    def test_weather_request_uses_fake_credential_and_timeout(
        self, mock_get, mock_get_weather_api_key
    ):
        mock_get_weather_api_key.return_value = self.fake_api_key
        response = Mock()
        response.json.return_value = {
            "records": {"Locations": [{"Location": [{"status": "ok"}]}]}
        }
        mock_get.return_value = response

        result = self.get_weather_data()

        self.assertEqual(result, {"status": "ok"})
        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(
            kwargs["timeout"], game_reminder.WEATHER_REQUEST_TIMEOUT_SECONDS
        )
        self.assertEqual(kwargs["params"]["Authorization"], self.fake_api_key)
        response.raise_for_status.assert_called_once_with()

    @patch("game_reminder.get_weather_api_key")
    @patch("game_reminder.requests.get")
    def test_timeout_is_sanitized(self, mock_get, mock_get_weather_api_key):
        mock_get_weather_api_key.return_value = self.fake_api_key
        mock_get.side_effect = requests.Timeout(self.fake_api_key)

        with self.assertRaises(game_reminder.WeatherServiceError) as context:
            self.get_weather_data()

        self.assertEqual(str(context.exception), "Weather API request timed out")
        self.assertNotIn(self.fake_api_key, str(context.exception))

    @patch("game_reminder.get_weather_api_key")
    @patch("game_reminder.requests.get")
    def test_http_error_is_sanitized(self, mock_get, mock_get_weather_api_key):
        mock_get_weather_api_key.return_value = self.fake_api_key
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError(
            self.fake_api_key
        )
        mock_get.return_value = response

        with self.assertRaises(game_reminder.WeatherServiceError) as context:
            self.get_weather_data()

        self.assertEqual(str(context.exception), "Weather API request failed")
        self.assertNotIn(self.fake_api_key, str(context.exception))

    @patch("game_reminder.get_weather_api_key")
    @patch("game_reminder.requests.get")
    def test_invalid_json_is_sanitized(self, mock_get, mock_get_weather_api_key):
        mock_get_weather_api_key.return_value = self.fake_api_key
        response = Mock()
        response.json.side_effect = ValueError(self.fake_api_key)
        mock_get.return_value = response

        with self.assertRaises(game_reminder.WeatherServiceError) as context:
            self.get_weather_data()

        self.assertEqual(
            str(context.exception), "Weather API returned invalid JSON"
        )
        self.assertNotIn(self.fake_api_key, str(context.exception))

    @patch("game_reminder.get_weather_api_key")
    @patch("game_reminder.requests.get")
    def test_invalid_response_shape_fails_safely(
        self, mock_get, mock_get_weather_api_key
    ):
        mock_get_weather_api_key.return_value = self.fake_api_key
        response = Mock()
        response.json.return_value = {"records": {}}
        mock_get.return_value = response

        with self.assertRaisesRegex(
            game_reminder.WeatherServiceError,
            "Weather API returned an invalid response",
        ):
            self.get_weather_data()


class WeatherFormattingTests(unittest.TestCase):
    @patch("game_reminder.get_weather_data")
    def test_invalid_nested_response_is_sanitized(self, mock_get_weather_data):
        mock_get_weather_data.return_value = {"WeatherElement": []}

        with self.assertRaisesRegex(
            game_reminder.WeatherServiceError,
            "Weather API returned an invalid response",
        ):
            game_reminder.get_weather_string(
                datetime(2026, 8, 4),
                "明天",
                "臺北市",
                "063",
                "中正區",
            )


class GameReminderFallbackTests(unittest.TestCase):
    def make_game(self):
        game = Mock()
        game.location = "測試球場"
        game.start_datetime = FakeGameDateTime()
        game.is_offseason.return_value = False
        game.get_formatted_start_time.return_value = "1000"
        game.get_formatted_end_time.return_value = "1200"
        game.get_opponent.return_value = "測試對手"
        game.get_is_home_team.return_value = True
        return game

    def make_ballpark(self):
        ballpark = Mock()
        ballpark.city_name = "臺北市"
        ballpark.city_weather_code = "063"
        ballpark.district_name = "中正區"
        return ballpark

    @patch("game_reminder.get_weather_string")
    def test_weather_failure_sends_basic_reminder_only(self, mock_weather):
        mock_weather.side_effect = game_reminder.WeatherServiceError(
            "Weather API request failed"
        )

        with patch.object(
            game_reminder.Game,
            "search_games",
            return_value=[self.make_game()],
            create=True,
        ), patch.object(
            game_reminder.Ballpark,
            "search_by_name",
            return_value=self.make_ballpark(),
            create=True,
        ), self.assertLogs("game_reminder", level="WARNING"):
            reminder = game_reminder.get_game_reminder_string(1)

        self.assertIn("測試球場", reminder)
        self.assertIn("測試對手", reminder)
        self.assertNotIn("天氣預報", reminder)
        self.assertNotIn("降雨", reminder)
        self.assertNotIn("氣溫", reminder)
        self.assertNotIn("天候", reminder)

    @patch("game_reminder.get_weather_string")
    def test_weather_success_appends_weather_section(self, mock_weather):
        mock_weather.return_value = "測試天氣區塊"

        with patch.object(
            game_reminder.Game,
            "search_games",
            return_value=[self.make_game()],
            create=True,
        ), patch.object(
            game_reminder.Ballpark,
            "search_by_name",
            return_value=self.make_ballpark(),
            create=True,
        ):
            reminder = game_reminder.get_game_reminder_string(1)

        self.assertIn("測試天氣區塊", reminder)

    @patch("game_reminder.get_weather_string")
    def test_missing_ballpark_weather_config_sends_basic_reminder(
        self, mock_weather
    ):
        with patch.object(
            game_reminder.Game,
            "search_games",
            return_value=[self.make_game()],
            create=True,
        ), patch.object(
            game_reminder.Ballpark,
            "search_by_name",
            return_value=None,
            create=True,
        ), self.assertLogs("game_reminder", level="WARNING"):
            reminder = game_reminder.get_game_reminder_string(1)

        self.assertIn("測試球場", reminder)
        self.assertNotIn("天氣預報", reminder)
        self.assertNotIn("降雨", reminder)
        self.assertNotIn("氣溫", reminder)
        mock_weather.assert_not_called()


if __name__ == "__main__":
    unittest.main()
