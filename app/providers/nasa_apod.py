from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

NASA_APOD_FIXTURES = {
    "2024-01-01": {
        "title": "Spiral Galaxy NGC 1232",
        "explanation": "A beautiful spiral galaxy captured by telescope.",
        "url": "https://apod.nasa.gov/apod/image/2401/ngc1232.jpg",
        "date": "2024-01-01",
    },
    "2024-06-15": {
        "title": "The Pillars of Creation",
        "explanation": "Iconic star-forming region in the Eagle Nebula.",
        "url": "https://apod.nasa.gov/apod/image/2406/pillars.jpg",
        "date": "2024-06-15",
    },
    "2024-10-01": {
        "title": "Aurora Over Iceland",
        "explanation": "The northern lights dance over a snowy landscape.",
        "url": "https://apod.nasa.gov/apod/image/2410/aurora.jpg",
        "date": "2024-10-01",
    },
    "default": {
        "title": "Astronomy Picture of the Day",
        "explanation": "An inspiring view of the cosmos.",
        "url": "https://apod.nasa.gov/apod/image/default.jpg",
        "date": "today",
    },
}


class NasaApodProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        date = str(params.get("date", "")).strip() if params.get("date") is not None else ""
        api_params: dict[str, Any] = {"api_key": "DEMO_KEY"}
        if date:
            api_params["date"] = date
        payload = await self.get_json("https://api.nasa.gov/planetary/apod", params=api_params)
        if not isinstance(payload, dict):
            raise ValueError("invalid APOD response")
        url = payload.get("url") or payload.get("hdurl") or ""
        return {
            "apod": {
                "title": payload.get("title", ""),
                "explanation": payload.get("explanation", ""),
                "url": url,
                "date": payload.get("date", date),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        date = ""
        if params.get("date") is not None:
            date = str(params.get("date", "")).strip()
        fixture = None
        if date:
            fixture = NASA_APOD_FIXTURES.get(date)
        if fixture is None:
            fixture = dict(NASA_APOD_FIXTURES["default"])
            if date:
                fixture["date"] = date
        return {"apod": dict(fixture)}