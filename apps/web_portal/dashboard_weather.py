import os
import threading
import time as monotonic_time
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional, Sequence

import requests


WEATHER_API_BASE_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
WEATHER_REQUEST_TIMEOUT_SECONDS = 10
WEATHER_CACHE_TTL_SECONDS = 15 * 60
FORECAST_HOURS = (6, 9, 12, 15, 18)

# Keep the portal presentation aligned with the LINE reminder's CWA weather icons.
WEATHER_EMOJI = {
    "01": "☀️",
    "02": "🌤️",
    "03": "⛅",
    "04": "🌥️",
    "05": "🌥️",
    "06": "☁️",
    "07": "☁️",
    "08": "🌧️",
    "09": "🌧️",
    "10": "🌧️",
    "11": "☔",
    "12": "🌧️",
    "13": "🌧️",
    "14": "🌧️",
    "15": "⛈️",
    "16": "⛈️",
    "17": "⛈️",
    "18": "⛈️",
    "19": "🌦️",
    "20": "🌧️",
    "21": "⛈️",
    "22": "⛈️",
    "23": "❄️",
    "24": "🌫️",
    "25": "🌫️",
    "26": "🌫️",
    "27": "🌫️",
    "28": "🌫️",
    "29": "🌧️",
    "30": "🌧️",
    "31": "🌧️",
    "32": "🌧️",
    "33": "⛈️",
    "34": "⛈️",
    "35": "⛈️",
    "36": "⛈️",
    "37": "🌧️",
    "38": "🌧️",
    "39": "🌧️",
    "40": "🌧️",
    "41": "⛈️",
    "42": "❄️",
}

_forecast_cache = {}
_forecast_cache_lock = threading.Lock()


class DashboardWeatherError(RuntimeError):
    pass


@dataclass(frozen=True)
class ForecastPoint:
    hour: int
    weather: str
    rainfall: int
    temperature: int


@dataclass(frozen=True)
class DashboardForecast:
    location_label: str
    points: Sequence[ForecastPoint]

    @property
    def rain_warning(self) -> bool:
        return any(point.rainfall >= 50 for point in self.points)


def fictional_dashboard_forecast() -> DashboardForecast:
    return DashboardForecast(
        location_label="虛構臺北中正",
        points=(
            ForecastPoint(6, "🌤️", 10, 24),
            ForecastPoint(9, "⛅", 20, 27),
            ForecastPoint(12, "🌦️", 40, 30),
            ForecastPoint(15, "🌧️", 60, 28),
            ForecastPoint(18, "☁️", 30, 26),
        ),
    )


def is_weather_window(game, now: datetime, local_timezone) -> bool:
    start = game.start_datetime
    if start.tzinfo is None:
        start = start.replace(tzinfo=local_timezone)
    else:
        start = start.astimezone(local_timezone)
    window_start = datetime.combine(
        start.date() - timedelta(days=2), time(hour=8), tzinfo=local_timezone
    )
    end = start + timedelta(minutes=game.duration)
    return window_start <= now.astimezone(local_timezone) <= end


def load_dashboard_forecast(game, ballpark, local_timezone) -> DashboardForecast:
    api_key = os.environ.get("WEATHER_API_KEY", "").strip()
    if not api_key:
        raise DashboardWeatherError("Weather API configuration is unavailable")

    target_date = game.start_datetime.astimezone(local_timezone).date().isoformat()
    cache_key = (
        ballpark.city_weather_code,
        ballpark.district_name,
        target_date,
    )
    now = monotonic_time.monotonic()
    with _forecast_cache_lock:
        cached = _forecast_cache.get(cache_key)
        if cached is not None and now - cached[0] < WEATHER_CACHE_TTL_SECONDS:
            return cached[1]

    api = f"{WEATHER_API_BASE_URL}/F-D0047-{ballpark.city_weather_code}"
    try:
        response = requests.get(
            api,
            params={
                "Authorization": api_key,
                "elementName": "Wx,AT,T,PoP6h",
                "LocationName": ballpark.district_name,
            },
            timeout=WEATHER_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise DashboardWeatherError("Weather API request failed") from None

    try:
        location = payload["records"]["Locations"][0]["Location"][0]
        points = _parse_points(location, game.start_datetime, local_timezone)
    except (KeyError, IndexError, TypeError, ValueError, StopIteration):
        raise DashboardWeatherError("Weather API returned an invalid response") from None

    city = _trim_administrative_suffix(ballpark.city_name)
    district = _trim_administrative_suffix(ballpark.district_name)
    forecast = DashboardForecast(f"{city}{district}", points)
    with _forecast_cache_lock:
        _forecast_cache[cache_key] = (now, forecast)
    return forecast


def clear_dashboard_forecast_cache() -> None:
    """Clear process-local weather data; intended for deterministic tests."""
    with _forecast_cache_lock:
        _forecast_cache.clear()


def _parse_points(location, target_datetime, local_timezone):
    target_date = target_datetime.astimezone(local_timezone).date()
    targets = {
        datetime.combine(target_date, time(hour), tzinfo=local_timezone): hour
        for hour in FORECAST_HOURS
    }
    elements = {item["ElementName"]: item for item in location["WeatherElement"]}
    temperatures = _data_time_values(elements["溫度"], "Temperature", targets)
    weathers = _start_time_values(elements["天氣現象"], "WeatherCode", targets)
    rainfalls = _start_time_values(
        elements["3小時降雨機率"], "ProbabilityOfPrecipitation", targets
    )
    if not all(
        hour in values
        for values in (temperatures, weathers, rainfalls)
        for hour in FORECAST_HOURS
    ):
        raise ValueError("Incomplete forecast")
    return tuple(
        ForecastPoint(
            hour=hour,
            weather=WEATHER_EMOJI.get(weathers[hour], "❓"),
            rainfall=int(rainfalls[hour]),
            temperature=int(temperatures[hour]),
        )
        for hour in FORECAST_HOURS
    )


def _data_time_values(element, value_name, targets):
    values = {}
    for entry in element["Time"]:
        timestamp = datetime.fromisoformat(entry["DataTime"])
        timestamp = timestamp.astimezone(next(iter(targets)).tzinfo)
        if timestamp in targets:
            values[targets[timestamp]] = entry["ElementValue"][0][value_name]
    return values


def _start_time_values(element, value_name, targets):
    values = {}
    for entry in element["Time"]:
        timestamp = datetime.fromisoformat(entry["StartTime"])
        timestamp = timestamp.astimezone(next(iter(targets)).tzinfo)
        hour = targets.get(timestamp)
        if hour is not None:
            values[hour] = entry["ElementValue"][0][value_name]
    return values


def _trim_administrative_suffix(value: str) -> str:
    return value[:-1] if len(value) > 2 else value
