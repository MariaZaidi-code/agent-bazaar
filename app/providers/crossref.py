from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

CROSSREF_FIXTURES = [
    {
        "title": "Attention Is All You Need",
        "author": "Ashish Vaswani",
        "year": 2017,
        "doi": "10.48550/arXiv.1706.03762",
        "url": "https://doi.org/10.48550/arXiv.1706.03762",
    },
    {
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "author": "Jacob Devlin",
        "year": 2019,
        "doi": "10.18653/v1/N19-1423",
        "url": "https://doi.org/10.18653/v1/N19-1423",
    },
    {
        "title": "Language Models are Few-Shot Learners",
        "author": "Tom Brown",
        "year": 2020,
        "doi": "10.48550/arXiv.2005.14165",
        "url": "https://doi.org/10.48550/arXiv.2005.14165",
    },
    {
        "title": "An Image is Worth 16x16 Words",
        "author": "Alexey Dosovitskiy",
        "year": 2021,
        "doi": "10.48550/arXiv.2010.11929",
        "url": "https://doi.org/10.48550/arXiv.2010.11929",
    },
    {
        "title": "Deep Residual Learning for Image Recognition",
        "author": "Kaiming He",
        "year": 2016,
        "doi": "10.1109/CVPR.2016.90",
        "url": "https://doi.org/10.1109/CVPR.2016.90",
    },
]


class CrossrefProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://api.crossref.org/works",
            params={"query": query, "rows": 5},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid crossref response")
        message = payload.get("message") or {}
        items = message.get("items") or []
        if not isinstance(items, list):
            raise ValueError("invalid works list")
        works = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            authors = item.get("author") or []
            author = ""
            if isinstance(authors, list) and authors:
                first = authors[0] if isinstance(authors[0], dict) else {}
                given = first.get("given", "") if isinstance(first, dict) else ""
                family = first.get("family", "") if isinstance(first, dict) else ""
                author = f"{given} {family}".strip()
            year = None
            for key in ("published-print", "published-online", "created"):
                date_parts = (item.get(key) or {}).get("date-parts") if isinstance(item.get(key), dict) else None
                if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list) and date_parts[0]:
                    try:
                        year = int(date_parts[0][0])
                    except (TypeError, ValueError):
                        year = date_parts[0][0]
                    break
            titles = item.get("title") or []
            title = titles[0] if isinstance(titles, list) and titles else (titles if isinstance(titles, str) else "")
            works.append(
                {
                    "title": title,
                    "author": author,
                    "year": year,
                    "doi": item.get("DOI", "") or "",
                    "url": item.get("URL", "") or "",
                }
            )
        return {"works": works}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        return {"works": [dict(work) for work in CROSSREF_FIXTURES]}