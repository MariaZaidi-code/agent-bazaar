from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

DOG_FIXTURE = "https://images.dog.ceo/breeds/husky/n02110185_1469.jpg"


class DogCEOProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = await self.get_json("https://dog.ceo/api/breeds/image/random")
        if not isinstance(payload, dict):
            raise ValueError("invalid dog response")
        return {"image_url": str(payload.get("message", "")), "status": str(payload.get("status", ""))}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"image_url": DOG_FIXTURE, "status": "success"}
