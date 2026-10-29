from __future__ import annotations

import re
from html import unescape
from typing import Any

from app.providers.http_base import HTTPProvider


def _plain_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(unescape(text).split())


class TVMazeProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("show_query", "")).strip()
        if not query:
            raise ValueError("show_query is required")
        payload = await self.get_json("https://api.tvmaze.com/search/shows", params={"q": query})
        shows = []
        for item in (payload or [])[:5]:
            show = item.get("show") or {}
            rating = show.get("rating") or {}
            shows.append(
                {
                    "name": str(show.get("name") or ""),
                    "genres": list(show.get("genres") or []),
                    "premiered": str(show.get("premiered") or ""),
                    "rating": float(rating.get("average") or 0.0),
                    "url": str(show.get("url") or ""),
                    "summary": _plain_text(show.get("summary"))[:600],
                }
            )
        if not shows:
            raise ValueError(f"TVMaze returned no shows for {query}")
        return {"shows": shows}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("show_query", "")).strip()
        if not query:
            raise ValueError("show_query is required")
        return {
            "shows": [
                {
                    "name": f"{query.title()} Stories",
                    "genres": ["Drama"],
                    "premiered": "2025-09-12",
                    "rating": 7.8,
                    "url": "https://www.tvmaze.com/shows/1/offline-fixture",
                    "summary": f"Offline fixture for a television search about {query}.",
                },
                {
                    "name": f"The {query.title()} Chronicles",
                    "genres": ["Science-Fiction"],
                    "premiered": "2024-03-01",
                    "rating": 7.2,
                    "url": "https://www.tvmaze.com/shows/2/offline-fixture",
                    "summary": f"A second deterministic TVMaze fixture for {query}.",
                },
            ]
        }
