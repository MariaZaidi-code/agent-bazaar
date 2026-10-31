from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

JOKE_FIXTURE = {"setup": "Why did the chicken cross the road?", "punchline": "To get to the other side."}


class JokeProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://official-joke-api.appspot.com/random_joke")
        if not isinstance(payload, dict):
            raise ValueError("invalid joke response")
        return {"setup": str(payload.get("setup", "")), "punchline": str(payload.get("punchline", ""))}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return dict(JOKE_FIXTURE)
