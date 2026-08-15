import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


WEB_PORTAL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB_PORTAL_DIR))

from dashboard_weather import (  # noqa: E402
    DashboardWeatherError,
    clear_dashboard_forecast_cache,
    fictional_dashboard_forecast,
    is_weather_window,
    load_dashboard_forecast,
)


LOCAL_TIMEZONE = timezone(timedelta(hours=8))


class DashboardWeatherTest(unittest.TestCase):
    def setUp(self):
        clear_dashboard_forecast_cache()

    def game(self, start, duration=120):
        return SimpleNamespace(start_datetime=start, duration=duration)

    def test_fictional_forecast_exercises_rain_warning_layout(self):
        forecast = fictional_dashboard_forecast()

        self.assertEqual(forecast.location_label, "虛構臺北中正")
        self.assertEqual(len(forecast.points), 5)
        self.assertTrue(forecast.rain_warning)

    def test_window_opens_at_eight_two_calendar_days_before_and_closes_after_game(self):
        start = datetime(2026, 8, 15, 14, tzinfo=LOCAL_TIMEZONE)
        game = self.game(start)
        window_start = datetime(2026, 8, 13, 8, tzinfo=LOCAL_TIMEZONE)

        self.assertTrue(is_weather_window(game, window_start, LOCAL_TIMEZONE))
        self.assertFalse(
            is_weather_window(
                game, window_start - timedelta(seconds=1), LOCAL_TIMEZONE
            )
        )
        self.assertTrue(
            is_weather_window(game, start + timedelta(minutes=120), LOCAL_TIMEZONE)
        )
        self.assertFalse(
            is_weather_window(
                game, start + timedelta(minutes=120, seconds=1), LOCAL_TIMEZONE
            )
        )

    def test_missing_key_fails_without_request(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("dashboard_weather.requests.get") as get,
        ):
            with self.assertRaises(DashboardWeatherError):
                load_dashboard_forecast(
                    self.game(datetime.now(LOCAL_TIMEZONE)),
                    SimpleNamespace(
                        city_name="臺北市",
                        city_weather_code="063",
                        district_name="中正區",
                    ),
                    LOCAL_TIMEZONE,
                )
        get.assert_not_called()

    def test_forecast_matches_line_reminder_fields(self):
        start = datetime(2026, 8, 15, 14, tzinfo=LOCAL_TIMEZONE)
        payload = self._payload(start)
        response = Mock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch.dict(os.environ, {"WEATHER_API_KEY": "fictional-key"}),
            patch("dashboard_weather.requests.get", return_value=response),
        ):
            forecast = load_dashboard_forecast(
                self.game(start),
                SimpleNamespace(
                    city_name="臺北市",
                    city_weather_code="063",
                    district_name="中正區",
                ),
                LOCAL_TIMEZONE,
            )

        self.assertEqual(forecast.location_label, "臺北中正")
        self.assertEqual([point.hour for point in forecast.points], [6, 9, 12, 15, 18])
        self.assertEqual(forecast.points[0].weather, "☀️")
        self.assertEqual(forecast.points[-1].rainfall, 60)
        self.assertTrue(forecast.rain_warning)

    def test_successful_forecast_is_cached_for_the_same_place_and_date(self):
        start = datetime(2026, 8, 15, 14, tzinfo=LOCAL_TIMEZONE)
        response = Mock()
        response.json.return_value = self._payload(start)
        response.raise_for_status.return_value = None
        ballpark = SimpleNamespace(
            city_name="臺北市",
            city_weather_code="063",
            district_name="中正區",
        )
        with (
            patch.dict(os.environ, {"WEATHER_API_KEY": "fictional-key"}),
            patch("dashboard_weather.requests.get", return_value=response) as get,
        ):
            first = load_dashboard_forecast(
                self.game(start), ballpark, LOCAL_TIMEZONE
            )
            second = load_dashboard_forecast(
                self.game(start), ballpark, LOCAL_TIMEZONE
            )

        self.assertIs(first, second)
        get.assert_called_once()

    @staticmethod
    def _payload(start):
        day = start.date()

        def entries(time_key, value_name, values):
            return [
                {
                    time_key: datetime.combine(
                        day, datetime.min.time(), tzinfo=LOCAL_TIMEZONE
                    ).replace(hour=hour).isoformat(),
                    "ElementValue": [{value_name: str(value)}],
                }
                for hour, value in zip((6, 9, 12, 15, 18), values)
            ]

        return {
            "records": {
                "Locations": [
                    {
                        "Location": [
                            {
                                "WeatherElement": [
                                    {
                                        "ElementName": "天氣現象",
                                        "Time": entries(
                                            "StartTime",
                                            "WeatherCode",
                                            ("01", "02", "03", "08", "08"),
                                        ),
                                    },
                                    {
                                        "ElementName": "溫度",
                                        "Time": entries(
                                            "DataTime", "Temperature", (25, 27, 30, 29, 27)
                                        ),
                                    },
                                    {
                                        "ElementName": "3小時降雨機率",
                                        "Time": entries(
                                            "StartTime",
                                            "ProbabilityOfPrecipitation",
                                            (10, 20, 30, 50, 60),
                                        ),
                                    },
                                ]
                            }
                        ]
                    }
                ]
            }
        }


if __name__ == "__main__":
    unittest.main()
    clear_dashboard_forecast_cache,
