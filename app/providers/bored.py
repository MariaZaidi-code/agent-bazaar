from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

BORED_FIXTURE = {
    "activity": "Learn a new recipe",
    "type": "cooking",
    "participants": 1,
    "price": 0.0,
}


class BoredProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://www.boredapi.com/api/activity")
        if not isinstance(payload, dict):
            raise ValueError("invalid bored response")
        return {
            "activity": str(payload.get("activity", "")),
            "type": str(payload.get("type", "")),
            "participants": payload.get("participants", 1),
            "price": payload.get("price", 0.0),
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return dict(BORED_FIXTURE)
