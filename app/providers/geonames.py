from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

GEONAMES_FIXTURES = [
    {"name": "London", "country": "United Kingdom", "lat": 51.5074, "lng": -0.1278, "population": 8982000},
    {"name": "Paris", "country": "France", "lat": 48.8566, "lng": 2.3522, "population": 2148000},
]


class GeoNamesProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        payload = await self.get_json(
            "https://secure.geonames.org/searchJSON",
            params={"q": query, "maxRows": 5, "username": "demo"},
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid geonames response")
        geonames = payload.get("geonames") or []
        if not isinstance(geonames, list):
            raise ValueError("invalid geonames list")
        places = []
        for item in geonames[:5]:
            if not isinstance(item, dict):
                continue
            places.append(
                {
                    "name": item.get("name", ""),
                    "country": item.get("countryName", ""),
                    "lat": item.get("lat"),
                    "lng": item.get("lng"),
                    "population": item.get("population"),
                }
            )
        return {"places": places}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        query = str(params.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        return {"places": [dict(p) for p in GEONAMES_FIXTURES]}
