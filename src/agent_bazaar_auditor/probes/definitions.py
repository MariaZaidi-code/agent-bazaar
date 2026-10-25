from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ..utils import stable_id

USER_AGENT = "agent-bazaar-auditor/0.1 (University of Central Punjab course project)"


@dataclass
class FieldSpec:
    path: str
    expected_type: str
    required: bool = True
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "expected_type": self.expected_type,
            "required": self.required,
            "unit": self.unit,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "description": self.description,
        }


@dataclass
class ProbeDefinition:
    tool_id: str
    endpoint: str
    params: dict[str, Any]
    headers: dict[str, str]
    expected_fields: dict[str, FieldSpec]
    fixture: Any
    fixture_status: int = 200
    unit_paths: dict[str, str] = field(default_factory=dict)
    limit_paths: dict[str, str] = field(default_factory=dict)
    min_interval_seconds: float = 1.0
    cache_ttl_seconds: int = 3600
    notes: str = ""
    probeable: bool = True
    safe_input: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return stable_id("probe", self.tool_id)

    @property
    def mapped_fields(self) -> list[str]:
        return list(self.expected_fields.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "endpoint": self.endpoint,
            "params": dict(self.params),
            "headers": dict(self.headers),
            "expected_fields": {key: value.to_dict() for key, value in self.expected_fields.items()},
            "unit_paths": dict(self.unit_paths),
            "limit_paths": dict(self.limit_paths),
            "min_interval_seconds": self.min_interval_seconds,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "notes": self.notes,
            "probeable": self.probeable,
            "safe_input": dict(self.safe_input),
        }


def _days(count: int) -> list[str]:
    start = date(2026, 10, 23)
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def build_probe_definitions() -> dict[str, ProbeDefinition]:
    definitions = [
        ProbeDefinition(
            tool_id="open-meteo",
            endpoint="https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 31.5497,
                "longitude": 74.3436,
                "current": "temperature_2m,wind_speed_10m",
                "forecast_days": 16,
                "timezone": "auto",
            },
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "current.temperature_2m": FieldSpec("current.temperature_2m", "number", unit="celsius", minimum=-90, maximum=60),
                "current.wind_speed_10m": FieldSpec("current.wind_speed_10m", "number", unit="km", minimum=0, maximum=500),
                "current_units.temperature_2m": FieldSpec("current_units.temperature_2m", "string"),
                "current_units.wind_speed_10m": FieldSpec("current_units.wind_speed_10m", "string"),
                "daily.time": FieldSpec("daily.time", "array"),
            },
            fixture={
                "latitude": 31.55,
                "longitude": 74.34,
                "generationtime_ms": 0.12,
                "utc_offset_seconds": 18000,
                "timezone": "Asia/Karachi",
                "current": {
                    "time": "2026-10-23T12:00",
                    "temperature_2m": 25.0,
                    "wind_speed_10m": 12.0,
                },
                "current_units": {
                    "temperature_2m": "°C",
                    "wind_speed_10m": "km/h",
                },
                "daily": {"time": _days(16)},
            },
            unit_paths={
                "current.temperature_2m": "current_units.temperature_2m",
                "current.wind_speed_10m": "current_units.wind_speed_10m",
            },
            limit_paths={"16": "daily.time"},
            min_interval_seconds=1.0,
            notes="Open-Meteo free forecast endpoint. No key. Cache one response per hour.",
        ),
        ProbeDefinition(
            tool_id="frankfurter",
            endpoint="https://api.frankfurter.app/latest",
            params={"from": "USD", "to": "PKR"},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "rates": FieldSpec("rates", "object"),
                "base": FieldSpec("base", "string"),
                "date": FieldSpec("date", "string"),
            },
            fixture={
                "amount": 1.0,
                "base": "USD",
                "date": "2026-10-23",
                "rates": {"PKR": 278.5, "EUR": 0.92, "GBP": 0.79},
            },
            notes="Frankfurter reference exchange rates. No key.",
        ),
        ProbeDefinition(
            tool_id="nominatim",
            endpoint="https://nominatim.openstreetmap.org/search",
            params={"q": "Lahore", "format": "jsonv2", "limit": 1},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
            expected_fields={
                "lat": FieldSpec("lat", "string"),
                "lon": FieldSpec("lon", "string"),
                "display_name": FieldSpec("display_name", "string"),
            },
            fixture=[
                {
                    "place_id": 123456,
                    "licence": "ODbL",
                    "osm_type": "relation",
                    "osm_id": 12345,
                    "lat": "31.5656822",
                    "lon": "74.3141829",
                    "display_name": "Lahore, Punjab, Pakistan",
                    "class": "place",
                    "type": "city",
                }
            ],
            min_interval_seconds=1.2,
            notes="Nominatim usage policy requires a descriptive User-Agent and at most one request per second. Campaign is cached.",
        ),
        ProbeDefinition(
            tool_id="rest-countries",
            endpoint="https://restcountries.com/v3.1/name/pakistan",
            params={"fields": "name,capital,population,currencies"},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "name.common": FieldSpec("name.common", "string"),
                "capital": FieldSpec("capital", "array"),
                "population": FieldSpec("population", "number", minimum=0),
            },
            fixture=[
                {
                    "name": {"common": "Pakistan", "official": "Islamic Republic of Pakistan"},
                    "capital": ["Islamabad"],
                    "population": 241499431,
                    "currencies": {"PKR": {"name": "Pakistani rupee", "symbol": "Rs"}},
                }
            ],
            notes="REST Countries v3.1. No key.",
        ),
        ProbeDefinition(
            tool_id="nager-date",
            endpoint="https://date.nager.at/api/v3/PublicHolidays/2026/PK",
            params={},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "date": FieldSpec("date", "string"),
                "name": FieldSpec("name", "string"),
            },
            fixture=[
                {"date": "2026-02-05", "localName": "Kashmir Solidarity Day", "name": "Kashmir Solidarity Day", "countryCode": "PK"},
                {"date": "2026-03-23", "localName": "Pakistan Day", "name": "Pakistan Day", "countryCode": "PK"},
            ],
            notes="Nager.Date public holidays. No key.",
        ),
        ProbeDefinition(
            tool_id="arxiv",
            endpoint="https://export.arxiv.org/api/query",
            params={"search_query": "all:multi-agent", "start": 0, "max_results": 1},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "feed.entry": FieldSpec("feed.entry", "array"),
                "feed.entry.title": FieldSpec("feed.entry.title", "string"),
            },
            fixture={
                "feed": {
                    "title": "arXiv Query: multi-agent",
                    "updated": "2026-10-23T00:00:00Z",
                    "entry": [
                        {
                            "id": "http://arxiv.org/abs/2601.00001v1",
                            "title": "Verifying Third-Party Tools for Agentic Systems",
                            "summary": "A controlled study of claim verification and drift monitoring.",
                            "published": "2026-01-01T00:00:00Z",
                        }
                    ],
                }
            },
            min_interval_seconds=3.0,
            notes="arXiv Atom API. Results are cached for one day; requests are throttled.",
        ),
        ProbeDefinition(
            tool_id="open-library",
            endpoint="https://openlibrary.org/search.json",
            params={"q": "agent based modeling", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "docs": FieldSpec("docs", "array"),
                "title": FieldSpec("title", "string"),
            },
            fixture={
                "numFound": 1,
                "start": 0,
                "docs": [
                    {
                        "title": "Agent-Based and Individual-Based Modeling",
                        "author_name": ["Steven F. Railsback", "Volker Grimm"],
                        "first_publish_year": 2011,
                    }
                ],
            },
            notes="Open Library search. No key.",
        ),
        ProbeDefinition(
            tool_id="dog-ceo",
            endpoint="https://dog.ceo/api/breeds/image/random",
            params={},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "message": FieldSpec("message", "string"),
                "status": FieldSpec("status", "string"),
            },
            fixture={
                "message": "https://images.dog.ceo/breeds/beagle/n02088364_1000.jpg",
                "status": "success",
            },
            notes="Dog CEO random image. No key.",
        ),
        ProbeDefinition(
            tool_id="cat-fact",
            endpoint="https://catfact.ninja/fact",
            params={},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "fact": FieldSpec("fact", "string"),
                "length": FieldSpec("length", "number", minimum=1),
            },
            fixture={
                "fact": "Cats have five toes on each front paw and four on each back paw.",
                "length": 64,
            },
            notes="Cat Fact random fact. No key.",
        ),
        ProbeDefinition(
            tool_id="joke-api",
            endpoint="https://official-joke-api.appspot.com/random_joke",
            params={},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "setup": FieldSpec("setup", "string"),
                "punchline": FieldSpec("punchline", "string"),
                "type": FieldSpec("type", "string"),
            },
            fixture={
                "type": "programming",
                "setup": "Why did the developer go broke?",
                "punchline": "Because he used up all his cache.",
                "id": 42,
            },
            notes="Official Joke API. No key.",
        ),
        ProbeDefinition(
            tool_id="ipify",
            endpoint="https://api.ipify.org",
            params={"format": "json"},
            headers={"User-Agent": USER_AGENT},
            expected_fields={"ip": FieldSpec("ip", "string")},
            fixture={"ip": "203.0.113.10"},
            notes="IPify public IP endpoint. No key.",
        ),
        ProbeDefinition(
            tool_id="usgs-earthquake",
            endpoint="https://earthquake.usgs.gov/fdsnws/event/1/query",
            params={"format": "geojson", "limit": 1, "orderby": "time"},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "features": FieldSpec("features", "array"),
                "properties.mag": FieldSpec("properties.mag", "number"),
                "properties.place": FieldSpec("properties.place", "string"),
            },
            fixture={
                "type": "FeatureCollection",
                "metadata": {"generated": 1761200000000, "count": 1},
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "mag": 4.5,
                            "place": "120 km SW of Muzaffarabad, Pakistan",
                            "time": 1761190000000,
                        },
                        "geometry": {"type": "Point", "coordinates": [73.1, 34.2, 10.0]},
                        "id": "us7000demo",
                    }
                ],
            },
            notes="USGS earthquake GeoJSON. No key.",
        ),
        ProbeDefinition(
            tool_id="worldtime",
            endpoint="https://worldtimeapi.org/api/timezone/Asia/Karachi",
            params={},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "datetime": FieldSpec("datetime", "string"),
                "timezone": FieldSpec("timezone", "string"),
                "utc_offset": FieldSpec("utc_offset", "string"),
            },
            fixture={
                "abbreviation": "PKT",
                "client_ip": "203.0.113.10",
                "datetime": "2026-10-23T12:00:00.000000+05:00",
                "day_of_week": 5,
                "day_of_year": 296,
                "timezone": "Asia/Karachi",
                "utc_offset": "+05:00",
                "utc_datetime": "2026-10-23T07:00:00.000000+00:00",
            },
            notes="World Time API. No key. The public service is occasionally unavailable; cached fixtures are used for the demo.",
        ),
        ProbeDefinition(
            tool_id="datamuse",
            endpoint="https://api.datamuse.com/words",
            params={"ml": "agent", "max": 2},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "word": FieldSpec("word", "string"),
                "score": FieldSpec("score", "number"),
            },
            fixture=[
                {"word": "agent", "score": 1000},
                {"word": "proxy", "score": 900},
            ],
            notes="Datamuse word suggestions. No key.",
        ),
        ProbeDefinition(
            tool_id="coingecko",
            endpoint="https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
            headers={"User-Agent": USER_AGENT},
            expected_fields={
                "bitcoin.usd": FieldSpec("bitcoin.usd", "number", minimum=0),
            },
            fixture={"bitcoin": {"usd": 65000.0}},
            min_interval_seconds=5.0,
            cache_ttl_seconds=600,
            notes="CoinGecko free endpoint. Rate limited, so probes are cached and throttled.",
        ),
    ]
    return {definition.tool_id: definition for definition in definitions}


def probe_definition_list() -> list[ProbeDefinition]:
    return list(build_probe_definitions().values())
