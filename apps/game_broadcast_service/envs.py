import os

channel_access_token = os.environ.get("CHANNEL_ACCESS_TOKEN")
channel_secret = os.environ.get("CHANNEL_SECRET")


def get_weather_api_key() -> str:
    api_key = os.environ.get("WEATHER_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError("WEATHER_API_KEY is not configured")
    return api_key
