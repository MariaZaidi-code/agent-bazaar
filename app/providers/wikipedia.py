from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.providers.http_base import HTTPProvider


class WikipediaProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        title = str(params.get("title", "")).strip()
        if not title:
            raise ValueError("title is required")
        slug = quote(title.replace(" ", "_"), safe="")
        payload = await self.get_json(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid wikipedia response")
        page_title = payload.get("title") or title
        extract = payload.get("extract") or ""
        content_urls = payload.get("content_urls") or {}
        desktop = content_urls.get("desktop") or {}
        url = desktop.get("page") or f"https://en.wikipedia.org/wiki/{slug}"
        return {"article": {"title": page_title, "extract": extract, "url": url}}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        title = str(params.get("title", "")).strip()
        if not title:
            raise ValueError("title is required")
        return {
            "article": {
                "title": title,
                "extract": f"Offline summary for {title}.",
                "url": f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}",
            }
        }
