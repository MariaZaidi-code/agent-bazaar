from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

SPACEX_FIXTURES = {
    "latest": {
        "name": "Starlink Group",
        "flight_number": 100,
        "date_utc": "2024-01-01T00:00:00.000Z",
        "success": True,
        "details": "Offline fixture launch.",
        "rocket": "Falcon 9",
    }
}


class SpaceXProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://api.spacexdata.com/v4/launches/latest")
        if not isinstance(payload, dict):
            raise ValueError("invalid SpaceX response")
        rocket = payload.get("rocket")
        if isinstance(rocket, dict):
            rocket_name = rocket.get("name", "")
        else:
            rocket_name = str(rocket or "")
        return {
            "launch": {
                "name": payload.get("name", ""),
                "flight_number": payload.get("flight_number"),
                "date_utc": payload.get("date_utc", ""),
                "success": payload.get("success"),
                "details": payload.get("details") or "",
                "rocket": rocket_name,
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"launch": dict(SPACEX_FIXTURES["latest"])}
