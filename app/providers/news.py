from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.providers.http_base import HTTPProvider


class HackerNewsProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("news_query", "")).strip()
        if not query:
            raise ValueError("news_query is required")
        payload = await self.get_json(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": 5},
        )
        articles = []
        for hit in (payload.get("hits") or [])[:5]:
            title = str(hit.get("title") or hit.get("story_title") or "").strip()
            if not title:
                continue
            object_id = str(hit.get("objectID") or "")
            articles.append(
                {
                    "title": title,
                    "url": str(hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"),
                    "author": str(hit.get("author") or ""),
                    "published_at": str(hit.get("created_at") or ""),
                    "points": int(hit.get("points") or 0),
                    "source": "Hacker News",
                }
            )
        if not articles:
            raise ValueError(f"Hacker News returned no stories for {query}")
        return {"articles": articles}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("news_query", "")).strip()
        if not query:
            raise ValueError("news_query is required")
        search_url = f"https://hn.algolia.com/?q={quote(query)}"
        return {
            "articles": [
                {
                    "title": f"Offline briefing: {query}",
                    "url": search_url,
                    "author": "offline-fixture",
                    "published_at": "2026-10-20T12:00:00Z",
                    "points": 128,
                    "source": "Hacker News (offline fixture)",
                },
                {
                    "title": f"Community discussion about {query}",
                    "url": search_url,
                    "author": "offline-fixture",
                    "published_at": "2026-10-19T08:30:00Z",
                    "points": 64,
                    "source": "Hacker News (offline fixture)",
                },
            ]
        }
