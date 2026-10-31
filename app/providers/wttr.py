from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.providers.http_base import HTTPProvider

WTTR_FIXTURES = {
    "london": {"city": "London", "temp_c": 12.0, "condition": "Partly cloudy", "humidity": 72},
    "lahore": {"city": "Lahore", "temp_c": 34.0, "condition": "Sunny", "humidity": 45},
    "new york": {"city": "New York", "temp_c": 18.0, "condition": "Overcast", "humidity": 60},
    "tokyo": {"city": "Tokyo", "temp_c": 22.0, "condition": "Light rain", "humidity": 80},
    "paris": {"city": "Paris", "temp_c": 15.0, "condition": "Clear", "humidity": 55},
}


class WttrProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        city = str(params.get("city", "")).strip()
        if not city:
            raise ValueError("city is required")
        payload = await self.get_json(f"https://wttr.in/{quote(city)}", params={"format": "j1"})
        if not isinstance(payload, dict):
            raise ValueError("invalid weather response")
        current = (payload.get("current_condition") or [{}])[0]
        if not isinstance(current, dict):
            raise ValueError("invalid current condition")
        desc = current.get("weatherDesc") or [{}]
        first_desc = desc[0] if isinstance(desc, list) and desc else {}
        condition = first_desc.get("value", "") if isinstance(first_desc, dict) else ""
        temp_raw = current.get("temp_C")
        try:
            temp_c = float(temp_raw)
        except (TypeError, ValueError):
            temp_c = None
        humidity_raw = current.get("humidity")
        try:
            humidity = int(humidity_raw)
        except (TypeError, ValueError):
            try:
                humidity = float(humidity_raw)
            except (TypeError, ValueError):
                humidity = humidity_raw
        return {
            "weather": {
                "city": city,
                "temp_c": temp_c,
                "condition": condition,
                "humidity": humidity,
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        city = str(params.get("city", "")).strip()
        if not city:
            raise ValueError("city is required")
        fixture = WTTR_FIXTURES.get(city.lower())
        if fixture is None:
            fixture = {
                "city": city.title(),
                "temp_c": 20.0,
                "condition": "Unknown (offline fixture)",
                "humidity": 50,
            }
        return {"weather": dict(fixture)}