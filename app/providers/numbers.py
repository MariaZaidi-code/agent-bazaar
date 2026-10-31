from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

NUMBERS_FIXTURE = "42 is the Answer to the Ultimate Question of Life, the Universe, and Everything."


class NumbersProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        number = params.get("number", "random")
        payload = await self.get_json(f"http://numbersapi.com/{number}/trivia", params={"json": True})
        if not isinstance(payload, dict):
            raise ValueError("invalid numbers response")
        return {
            "text": str(payload.get("text", "")),
            "number": payload.get("number"),
            "found": payload.get("found", True),
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"text": NUMBERS_FIXTURE, "number": 42, "found": True}
