from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

ITUNES_FIXTURES = [
    {
        "title": "The Matrix",
        "artist": "The Wachowskis",
        "year": 1999,
        "genre": "Sci-Fi & Fantasy",
        "preview_url": "https://audio-ssl.itunes.apple.com/itunes-assets/matrix.m4v",
    },
    {
        "title": "Inception",
        "artist": "Christopher Nolan",
        "year": 2010,
        "genre": "Action & Adventure",
        "preview_url": "https://audio-ssl.itunes.apple.com/itunes-assets/inception.m4v",
    },
    {
        "title": "Interstellar",
        "artist": "Christopher Nolan",
        "year": 2014,
        "genre": "Sci-Fi & Fantasy",
        "preview_url": "https://audio-ssl.itunes.apple.com/itunes-assets/interstellar.m4v",
    },
    {
        "title": "Dune",
        "artist": "Denis Villeneuve",
        "year": 2021,
        "genre": "Sci-Fi & Fantasy",
        "preview_url": "https://audio-ssl.itunes.apple.com/itunes-assets/dune.m4v",
    },
]


class ITunesProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://itunes.apple.com/search",
            params={"term": query, "media": "movie", "limit": 5},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid iTunes response")
        results = payload.get("results") or []
        if not isinstance(results, list):
            raise ValueError("invalid results list")
        movies = []
        for item in results[:5]:
            if not isinstance(item, dict):
                continue
            release = item.get("releaseDate", "")
            year = None
            if isinstance(release, str) and len(release) >= 4:
                try:
                    year = int(release[:4])
                except (TypeError, ValueError):
                    year = release[:4]
            movies.append(
                {
                    "title": item.get("trackName", ""),
                    "artist": item.get("artistName", ""),
                    "year": year,
                    "genre": item.get("primaryGenreName", ""),
                    "preview_url": item.get("previewUrl", ""),
                }
            )
        return {"movies": movies}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        return {"movies": [dict(movie) for movie in ITUNES_FIXTURES]}
