from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

USGS_FIXTURES = [
    {"place": "10 km N of Ridgecrest, CA", "magnitude": 6.4, "time": 1700000000000, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/eq1"},
    {"place": "5 km SW of Searles Valley, CA", "magnitude": 5.4, "time": 1699999000000, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/eq2"},
    {"place": "20 km E of Little Lake, CA", "magnitude": 4.8, "time": 1699998000000, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/eq3"},
    {"place": "Near the coast of Oregon", "magnitude": 4.2, "time": 1699997000000, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/eq4"},
    {"place": "Southern Alaska", "magnitude": 5.9, "time": 1699996000000, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/eq5"},
    {"place": "Puerto Rico region", "magnitude": 3.7, "time": 1699995000000, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/eq6"},
]


class UsgsProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        min_magnitude = self._parse_min_magnitude(params.get("min_magnitude", 4.5))
        limit = self._parse_limit(params.get("limit", 5))
        payload = await self.get_json(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson",
        )
        if not isinstance(payload, dict):
            raise ValueError("invalid USGS response")
        features = payload.get("features") or []
        if not isinstance(features, list):
            raise ValueError("invalid features list")
        earthquakes = []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            props = feature.get("properties")
            if not isinstance(props, dict):
                continue
            magnitude = props.get("mag")
            try:
                mag_value = float(magnitude)
            except (TypeError, ValueError):
                continue
            if mag_value < min_magnitude:
                continue
            earthquakes.append(
                {
                    "place": props.get("place", "") or "",
                    "magnitude": magnitude,
                    "time": props.get("time"),
                    "url": props.get("url", "") or "",
                }
            )
            if len(earthquakes) >= limit:
                break
        return {"earthquakes": earthquakes}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        min_magnitude = self._parse_min_magnitude(params.get("min_magnitude", 4.5))
        limit = self._parse_limit(params.get("limit", 5))
        earthquakes = [
            dict(item) for item in USGS_FIXTURES if float(item["magnitude"]) >= min_magnitude
        ][:limit]
        return {"earthquakes": earthquakes}

    @staticmethod
    def _parse_min_magnitude(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("min_magnitude must be a number") from exc

    @staticmethod
    def _parse_limit(value: Any) -> int:
        try:
            limit = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        if limit <= 0:
            raise ValueError("limit must be positive")
        return limit
