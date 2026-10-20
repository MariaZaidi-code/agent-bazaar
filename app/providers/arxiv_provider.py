from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

from app.providers.http_base import HTTPProvider

ATOM = {"a": "http://www.w3.org/2005/Atom"}


class ArxivProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        text = await self.get_text(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": 3,
                "sortBy": "relevance",
            },
        )
        root = ET.fromstring(text)
        papers = []
        for entry in root.findall("a:entry", ATOM):
            title = " ".join((entry.findtext("a:title", "", ATOM) or "").split())
            summary = " ".join((entry.findtext("a:summary", "", ATOM) or "").split())
            published = entry.findtext("a:published", "", ATOM)
            link = entry.findtext("a:id", "", ATOM)
            authors = [
                author.findtext("a:name", "", ATOM)
                for author in entry.findall("a:author", ATOM)
            ]
            papers.append(
                {
                    "title": title,
                    "summary": summary[:700],
                    "url": link,
                    "published": published,
                    "authors": authors,
                }
            )
        if not papers:
            raise ValueError("arXiv returned no papers")
        return {"papers": papers}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        search_url = f"https://arxiv.org/search/?query={quote(query)}&searchtype=all"
        return {
            "papers": [
                {
                    "title": f"Retrieval and verification patterns for {query}",
                    "summary": (
                        "Offline demonstration record. A live arXiv search returns the actual "
                        f"papers for the topic '{query}'."
                    ),
                    "url": search_url,
                    "published": "2026-01-01T00:00:00Z",
                    "authors": ["Offline fixture"],
                },
                {
                    "title": f"Knowledge-graph grounding for tool-using agents: {query}",
                    "summary": (
                        "Offline demonstration record used when the arXiv API is unreachable. "
                        "It is clearly marked as a fixture and is not a real publication."
                    ),
                    "url": search_url,
                    "published": "2026-01-01T00:00:00Z",
                    "authors": ["Offline fixture"],
                },
            ]
        }
