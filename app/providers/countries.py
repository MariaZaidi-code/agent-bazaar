from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.providers.http_base import HTTPProvider

COUNTRY_FIXTURES = {
    "japan": {
        "name": "Japan",
        "capital": "Tokyo",
        "population": 125_681_593,
        "region": "Asia",
        "currencies": ["JPY"],
        "country_code": "JP",
    },
    "pakistan": {
        "name": "Pakistan",
        "capital": "Islamabad",
        "population": 240_485_658,
        "region": "Asia",
        "currencies": ["PKR"],
        "country_code": "PK",
    },
    "germany": {
        "name": "Germany",
        "capital": "Berlin",
        "population": 83_294_633,
        "region": "Europe",
        "currencies": ["EUR"],
        "country_code": "DE",
    },
    "united states": {
        "name": "United States",
        "capital": "Washington, D.C.",
        "population": 333_287_557,
        "region": "Americas",
        "currencies": ["USD"],
        "country_code": "US",
    },
    "united kingdom": {
        "name": "United Kingdom",
        "capital": "London",
        "population": 67_736_802,
        "region": "Europe",
        "currencies": ["GBP"],
        "country_code": "GB",
    },
    "india": {
        "name": "India",
        "capital": "New Delhi",
        "population": 1_428_627_663,
        "region": "Asia",
        "currencies": ["INR"],
        "country_code": "IN",
    },
    "france": {
        "name": "France",
        "capital": "Paris",
        "population": 68_170_187,
        "region": "Europe",
        "currencies": ["EUR"],
        "country_code": "FR",
    },
    "china": {
        "name": "China",
        "capital": "Beijing",
        "population": 1_425_671_352,
        "region": "Asia",
        "currencies": ["CNY"],
        "country_code": "CN",
    },
}


class CountriesProvider(HTTPProvider):
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        country = str(params.get("country", "")).strip()
        if not country:
            raise ValueError("country is required")
        fields = "name,capital,population,region,currencies,cca2"
        payload = await self.get_json(
            f"https://restcountries.com/v3.1/name/{quote(country)}",
            params={"fields": fields},
        )
        if not isinstance(payload, list) or not payload:
            raise ValueError(f"no country found for {country}")
        first = payload[0]
        currencies = first.get("currencies") or {}
        return {
            "country": {
                "name": (first.get("name") or {}).get("common", country),
                "capital": ", ".join(first.get("capital") or []),
                "population": first.get("population", 0),
                "region": first.get("region", ""),
                "currencies": list(currencies.keys()),
                "country_code": first.get("cca2", ""),
            }
        }

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        country = str(params.get("country", "")).strip()
        if not country:
            raise ValueError("country is required")
        key = country.lower()
        fixture = COUNTRY_FIXTURES.get(key)
        if fixture is None:
            fixture = {
                "name": country.title(),
                "capital": "Not available in offline fixture",
                "population": 0,
                "region": "Unknown",
                "currencies": [],
                "country_code": "",
            }
        return {"country": dict(fixture)}
