from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

HN_FIXTURES = [
    {"id": 1, "title": "Offline story one", "url": "https://example.com/1", "score": 120, "by": "alice"},
    {"id": 2, "title": "Offline story two", "url": "https://example.com/2", "score": 95, "by": "bob"},
    {"id": 3, "title": "Offline story three", "url": "https://example.com/3", "score": 80, "by": "carol"},
    {"id": 4, "title": "Offline story four", "url": "https://example.com/4", "score": 60, "by": "dave"},
    {"id": 5, "title": "Offline story five", "url": "https://example.com/5", "score": 45, "by": "eve"},
]


class HackerNewsProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        raw_limit = params.get("limit", 5)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        if limit <= 0:
            raise ValueError("limit must be positive")
        ids = await self.get_json("https://hacker-news.firebaseio.com/v0/topstories.json")
        if not isinstance(ids, list):
            raise ValueError("invalid top stories response")
        stories = []
        for sid in ids[:limit]:
            item = await self.get_json(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
            )
            if not isinstance(item, dict):
                continue
            stories.append(
                {
                    "id": item.get("id", sid),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "score": item.get("score", 0),
                    "by": item.get("by", ""),
                }
            )
        return {"stories": stories}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        raw_limit = params.get("limit", 5)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        if limit <= 0:
            raise ValueError("limit must be positive")
        return {"stories": [dict(item) for item in HN_FIXTURES[:limit]]}
