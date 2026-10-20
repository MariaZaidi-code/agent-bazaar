from __future__ import annotations

import hashlib
from typing import Any

from app.providers.http_base import HTTPProvider

GAZETTEER: dict[str, tuple[float, float, str, str]] = {
    "lahore": (31.5497, 74.3436, "Lahore, Punjab, Pakistan", "PK"),
    "karachi": (24.8607, 67.0011, "Karachi, Sindh, Pakistan", "PK"),
    "islamabad": (33.6844, 73.0479, "Islamabad, Pakistan", "PK"),
    "rawalpindi": (33.5651, 73.0169, "Rawalpindi, Punjab, Pakistan", "PK"),
    "faisalabad": (31.4504, 73.1350, "Faisalabad, Punjab, Pakistan", "PK"),
    "multan": (30.1575, 71.5249, "Multan, Punjab, Pakistan", "PK"),
    "tokyo": (35.6762, 139.6503, "Tokyo, Japan", "JP"),
    "japan": (36.2048, 138.2529, "Japan", "JP"),
    "london": (51.5072, -0.1276, "London, England, United Kingdom", "GB"),
    "new york": (40.7128, -74.0060, "New York, United States", "US"),
    "paris": (48.8566, 2.3522, "Paris, France", "FR"),
    "berlin": (52.5200, 13.4050, "Berlin, Germany", "DE"),
    "delhi": (28.6139, 77.2090, "Delhi, India", "IN"),
    "beijing": (39.9042, 116.4074, "Beijing, China", "CN"),
    "dubai": (25.2048, 55.2708, "Dubai, United Arab Emirates", "AE"),
    "sydney": (-33.8688, 151.2093, "Sydney, Australia", "AU"),
}


class GeocodingProvider(HTTPProvider):
    min_interval_seconds = 1.0

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        location = str(params.get("location", "")).strip()
        if not location:
            raise ValueError("location is required")
        payload = await self.get_json(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": location,
                "format": "jsonv2",
                "limit": 1,
                "addressdetails": 1,
            },
        )
        if not payload:
            raise ValueError(f"no coordinates found for {location}")
        first = payload[0]
        address = first.get("address") or {}
        return {
            "coordinates": {
                "latitude": float(first["lat"]),
                "longitude": float(first["lon"]),
                "display_name": first.get("display_name") or location,
                "country_code": str(address.get("country_code", "")).upper(),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        location = str(params.get("location", "")).strip()
        if not location:
            raise ValueError("location is required")
        key = location.lower()
        if key in GAZETTEER:
            latitude, longitude, display_name, country_code = GAZETTEER[key]
        else:
            digest = hashlib.sha256(key.encode("utf-8")).digest()
            latitude = round(15 + (digest[0] / 255) * 55, 4)
            longitude = round(-10 + (digest[1] / 255) * 130, 4)
            display_name = location
            country_code = ""
        return {
            "coordinates": {
                "latitude": latitude,
                "longitude": longitude,
                "display_name": display_name,
                "country_code": country_code,
            }
        }
