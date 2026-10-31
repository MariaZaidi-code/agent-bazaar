from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.providers.http_base import HTTPProvider


class OpenLibraryProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("book_query", "")).strip()
        if not query:
            raise ValueError("book_query is required")
        payload = await self.get_json(
            "https://openlibrary.org/search.json",
            params={
                "q": query,
                "limit": 5,
                "fields": "title,author_name,first_publish_year,key",
            },
        )
        books = []
        for doc in (payload.get("docs") or [])[:5]:
            key = str(doc.get("key") or "")
            books.append(
                {
                    "title": str(doc.get("title") or ""),
                    "author": ", ".join(str(item) for item in doc.get("author_name") or []),
                    "first_publish_year": int(doc.get("first_publish_year") or 0),
                    "url": f"https://openlibrary.org{key}" if key else "",
                    "key": key,
                }
            )
        if not books:
            raise ValueError(f"Open Library returned no books for {query}")
        return {"books": books}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("book_query", "")).strip()
        if not query:
            raise ValueError("book_query is required")
        search_url = f"https://openlibrary.org/search?q={quote(query)}"
        return {
            "books": [
                {
                    "title": f"Offline introduction to {query}",
                    "author": "Open Library fixture",
                    "first_publish_year": 2024,
                    "url": search_url,
                    "key": "/works/OL_OFFLINE_1",
                },
                {
                    "title": f"Applied {query}: a reader",
                    "author": "Open Library fixture",
                    "first_publish_year": 2023,
                    "url": search_url,
                    "key": "/works/OL_OFFLINE_2",
                },
            ]
        }


class GoogleBooksProvider(HTTPProvider):
    min_interval_seconds = 1.0

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("book_query", "")).strip()
        if not query:
            raise ValueError("book_query is required")
        payload = await self.get_json(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": query, "maxResults": 5, "printType": "books"},
        )
        books = []
        for item in (payload.get("items") or [])[:5]:
            volume = item.get("volumeInfo") or {}
            published = str(volume.get("publishedDate") or "")
            year = int(published[:4]) if published[:4].isdigit() else 0
            item_id = str(item.get("id") or "")
            books.append(
                {
                    "title": str(volume.get("title") or ""),
                    "author": ", ".join(str(name) for name in volume.get("authors") or []),
                    "first_publish_year": year,
                    "url": str(volume.get("infoLink") or item.get("selfLink") or ""),
                    "key": item_id,
                }
            )
        if not books:
            raise ValueError(f"Google Books returned no books for {query}")
        return {"books": books}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("book_query", "")).strip()
        if not query:
            raise ValueError("book_query is required")
        search_url = f"https://www.google.com/search?tbm=bks&q={quote(query)}"
        return {
            "books": [
                {
                    "title": f"Google Books fixture: {query}",
                    "author": "Google Books fixture",
                    "first_publish_year": 2025,
                    "url": search_url,
                    "key": "offline-volume-1",
                },
                {
                    "title": f"Practical notes on {query}",
                    "author": "Google Books fixture",
                    "first_publish_year": 2022,
                    "url": search_url,
                    "key": "offline-volume-2",
                },
            ]
        }
