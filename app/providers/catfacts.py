from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

CAT_FACTS = ["Cats sleep 70% of their lives."]


class CatFactsProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://catfact.ninja/fact")
        if not isinstance(payload, dict):
            raise ValueError("invalid cat fact response")
        return {"fact": str(payload.get("fact", "")), "length": payload.get("length")}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"fact": CAT_FACTS[0], "length": len(CAT_FACTS[0])}
