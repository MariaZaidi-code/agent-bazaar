from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

ADVICE_FIXTURE = "Always test your code before shipping."


class AdviceSlipProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://api.adviceslip.com/advice")
        if not isinstance(payload, dict):
            raise ValueError("invalid advice response")
        slip = payload.get("slip") or {}
        return {"advice": str(slip.get("advice", "")), "id": slip.get("id")}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"advice": ADVICE_FIXTURE, "id": 1}
