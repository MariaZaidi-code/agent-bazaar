from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone as fixed_timezone
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.providers.http_base import HTTPProvider

OFFSETS = {
    "UTC": 0.0,
    "Etc/UTC": 0.0,
    "Asia/Karachi": 5.0,
    "Asia/Kolkata": 5.5,
    "Asia/Tokyo": 9.0,
    "Europe/London": 1.0,
    "Europe/Paris": 2.0,
    "Europe/Berlin": 2.0,
    "America/New_York": -4.0,
    "America/Los_Angeles": -7.0,
    "Australia/Sydney": 10.0,
    "Asia/Dubai": 4.0,
}


def _offset_label(hours: float) -> str:
    sign = "+" if hours >= 0 else "-"
    value = abs(hours)
    whole = int(value)
    minutes = int(round((value - whole) * 60))
    return f"{sign}{whole:02d}:{minutes:02d}"


class WorldTimeProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        timezone = str(params.get("timezone", "")).strip() or "Etc/UTC"
        payload = await self.get_json(
            f"https://worldtimeapi.org/api/timezone/{quote(timezone, safe='/')}"
        )
        if not payload or "datetime" not in payload:
            raise ValueError(f"WorldTimeAPI returned no time for {timezone}")
        return {
            "time": {
                "datetime": str(payload.get("datetime") or ""),
                "timezone": str(payload.get("timezone") or timezone),
                "utc_offset": str(payload.get("utc_offset") or ""),
                "day_of_week": int(payload.get("day_of_week") or 0),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        timezone = str(params.get("timezone", "")).strip() or "Etc/UTC"
        try:
            local = datetime.now(ZoneInfo(timezone))
            utc_offset = local.strftime("%z")
            utc_offset = f"{utc_offset[:3]}:{utc_offset[3:]}" if utc_offset else "+00:00"
        except (ZoneInfoNotFoundError, ValueError):
            hours = OFFSETS.get(timezone, 0.0)
            utc_offset = _offset_label(hours)
            local = (datetime.now(UTC) + timedelta(hours=hours)).replace(
                tzinfo=fixed_timezone(timedelta(hours=hours))
            )
        return {
            "time": {
                "datetime": local.isoformat(),
                "timezone": timezone,
                "utc_offset": utc_offset,
                "day_of_week": local.isoweekday() % 7,
            }
        }


class SunriseSunsetProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        coordinates = params.get("coordinates") or {}
        if not isinstance(coordinates, dict) or "latitude" not in coordinates or "longitude" not in coordinates:
            raise ValueError("coordinates with latitude and longitude are required")
        target = str(params.get("date") or date.today().isoformat())[:10]
        payload = await self.get_json(
            "https://api.sunrise-sunset.org/json",
            params={
                "lat": coordinates["latitude"],
                "lng": coordinates["longitude"],
                "date": target,
                "formatted": 0,
            },
        )
        results = payload.get("results") or {}
        if not results.get("sunrise"):
            raise ValueError("Sunrise-Sunset returned no solar times")
        return {
            "sun": {
                "sunrise": str(results.get("sunrise") or ""),
                "sunset": str(results.get("sunset") or ""),
                "solar_noon": str(results.get("solar_noon") or ""),
                "day_length": int(float(results.get("day_length") or 0)),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        coordinates = params.get("coordinates") or {}
        if not isinstance(coordinates, dict):
            raise ValueError("coordinates are required")
        target = str(params.get("date") or date.today().isoformat())[:10]
        return {
            "sun": {
                "sunrise": f"{target}T06:00:00+05:00",
                "sunset": f"{target}T18:00:00+05:00",
                "solar_noon": f"{target}T12:00:00+05:00",
                "day_length": 43_200,
            }
        }
