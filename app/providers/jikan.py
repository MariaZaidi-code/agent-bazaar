from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

JIKAN_FIXTURES = [
    {
        "title": "Fullmetal Alchemist: Brotherhood",
        "episodes": 64,
        "score": 9.1,
        "synopsis": "Two brothers search for the Philosopher's Stone to restore their bodies.",
    },
    {
        "title": "Attack on Titan",
        "episodes": 87,
        "score": 8.5,
        "synopsis": "Humanity fights for survival against giant humanoid Titans.",
    },
    {
        "title": "Death Note",
        "episodes": 37,
        "score": 8.6,
        "synopsis": "A student finds a notebook that kills anyone whose name is written in it.",
    },
    {
        "title": "One Piece",
        "episodes": 1100,
        "score": 8.7,
        "synopsis": "A pirate crew searches for the legendary treasure One Piece.",
    },
]


class JikanProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://api.jikan.moe/v4/anime",
            params={"q": query, "limit": 5},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid Jikan response")
        data = payload.get("data") or []
        if not isinstance(data, list):
            raise ValueError("invalid anime list")
        anime = []
        for item in data[:5]:
            if not isinstance(item, dict):
                continue
            anime.append(
                {
                    "title": item.get("title", ""),
                    "episodes": item.get("episodes"),
                    "score": item.get("score"),
                    "synopsis": item.get("synopsis", "") or "",
                }
            )
        return {"anime": anime}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        return {"anime": [dict(item) for item in JIKAN_FIXTURES]}
