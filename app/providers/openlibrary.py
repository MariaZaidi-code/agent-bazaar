from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

BOOK_FIXTURES = [
    {"title": "The Hobbit", "author": "J.R.R. Tolkien", "year": 1937, "key": "/works/OL26270W"},
    {"title": "1984", "author": "George Orwell", "year": 1949, "key": "/works/OL7353617W"},
    {"title": "Dune", "author": "Frank Herbert", "year": 1965, "key": "/works/OL102833W"},
    {"title": "Neuromancer", "author": "William Gibson", "year": 1984, "key": "/works/OL48355W"},
    {"title": "Foundation", "author": "Isaac Asimov", "year": 1951, "key": "/works/OL46125W"},
]


class OpenLibraryProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": 5},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid search response")
        docs = payload.get("docs") or []
        books = []
        for doc in docs[:5]:
            authors = doc.get("author_name") or []
            books.append(
                {
                    "title": doc.get("title", ""),
                    "author": authors[0] if authors else "",
                    "year": doc.get("first_publish_year"),
                    "key": doc.get("key", ""),
                }
            )
        return {"books": books}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        return {"books": [dict(book) for book in BOOK_FIXTURES]}
