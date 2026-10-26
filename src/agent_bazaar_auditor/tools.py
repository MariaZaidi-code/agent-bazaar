from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .claims import Claim
from .enums import ClaimType
from .utils import stable_id


@dataclass
class ToolSpec:
    tool_id: str
    name: str
    category: str
    documentation: list[str]
    claims: list[Claim] = field(default_factory=list)
    provider_kind: str = "api"
    mockable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def documentation_text(self) -> str:
        return "\n".join(self.documentation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "category": self.category,
            "documentation": list(self.documentation),
            "claims": [claim.to_dict() for claim in self.claims],
            "provider_kind": self.provider_kind,
            "mockable": self.mockable,
            "metadata": dict(self.metadata),
        }


def _claim(
    tool_id: str,
    text: str,
    claim_type: ClaimType,
    *,
    field_path: str | None = None,
    expected_type: str | None = None,
    expected_unit: str | None = None,
    expected_min: float | None = None,
    expected_max: float | None = None,
    expected_limit: int | None = None,
    probeable: bool = True,
    metadata: dict[str, Any] | None = None,
) -> Claim:
    return Claim(
        id=stable_id(tool_id, claim_type.value, text),
        tool_id=tool_id,
        text=text,
        claim_type=claim_type,
        field_path=field_path,
        expected_type=expected_type,
        expected_unit=expected_unit,
        expected_min=expected_min,
        expected_max=expected_max,
        expected_limit=expected_limit,
        probeable=probeable,
        source_text=text,
        metadata=metadata or {},
    )


def _auth(tool_id: str, text: str = "No API key is required.", expects_key: bool = False) -> Claim:
    return _claim(
        tool_id,
        text,
        ClaimType.AUTHENTICATION,
        expected_type="boolean",
        probeable=True,
        metadata={"expects_key": expects_key},
    )


def _field(
    tool_id: str,
    text: str,
    field_path: str,
    expected_type: str,
    *,
    unit: str | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    claim_type: ClaimType = ClaimType.OUTPUT_FIELD,
    probeable: bool = True,
) -> Claim:
    return _claim(
        tool_id,
        text,
        claim_type,
        field_path=field_path,
        expected_type=expected_type,
        expected_unit=unit,
        expected_min=minimum,
        expected_max=maximum,
        probeable=probeable,
    )


def build_catalog() -> dict[str, ToolSpec]:
    tools = [
        ToolSpec(
            tool_id="open-meteo",
            name="Open-Meteo",
            category="weather",
            provider_kind="api",
            documentation=[
                "Open-Meteo returns current weather for a coordinate. The response includes the field `temperature_2m` in degrees Celsius.",
                "No API key is required for the forecast endpoint.",
                "Forecasts are available up to 16 days.",
                "The response includes `wind_speed_10m` in km/h.",
            ],
            claims=[
                _field("open-meteo", "Returns temperature in degrees Celsius.", "current.temperature_2m", "number", unit="celsius", minimum=-90, maximum=60, claim_type=ClaimType.UNIT),
                _auth("open-meteo"),
                _claim("open-meteo", "Supports forecasts up to 16 days.", ClaimType.LIMIT, expected_limit=16, expected_type="number", probeable=True),
                _field("open-meteo", "Returns wind speed in km/h.", "current.wind_speed_10m", "number", unit="km", minimum=0, maximum=500, claim_type=ClaimType.UNIT),
            ],
            metadata={"endpoint": "https://api.open-meteo.com/v1/forecast"},
        ),
        ToolSpec(
            tool_id="frankfurter",
            name="Frankfurter",
            category="currency",
            provider_kind="api",
            documentation=[
                "Frankfurter converts currencies using reference exchange rates. The response includes `rates` as an object mapping currency codes to numbers.",
                "No API key is required.",
                "Reference rates are published on working days.",
            ],
            claims=[
                _field("frankfurter", "Returns exchange rates as a JSON object.", "rates", "object"),
                _auth("frankfurter"),
                _claim("frankfurter", "Rates are updated on working days.", ClaimType.AVAILABILITY, probeable=False),
            ],
            metadata={"endpoint": "https://api.frankfurter.app/latest"},
        ),
        ToolSpec(
            tool_id="nominatim",
            name="Nominatim",
            category="geocoding",
            provider_kind="api",
            documentation=[
                "Nominatim returns geocoding results as a JSON array. Each result includes `lat` and `lon` as strings in decimal degrees.",
                "No API key is required.",
                "A descriptive User-Agent header is required by the usage policy.",
            ],
            claims=[
                _field("nominatim", "Returns geocoding results as a JSON array.", "", "array"),
                _field("nominatim", "Returns latitude and longitude as strings.", "lat", "string"),
                _auth("nominatim"),
                _claim("nominatim", "A descriptive User-Agent header is required.", ClaimType.BEHAVIOUR, probeable=False),
            ],
            metadata={"endpoint": "https://nominatim.openstreetmap.org/search"},
        ),
        ToolSpec(
            tool_id="rest-countries",
            name="REST Countries",
            category="country-facts",
            provider_kind="api",
            documentation=[
                "REST Countries returns country records as a JSON array. The response includes `name.common`, `capital` and `population`; population is a number.",
                "No API key is required.",
            ],
            claims=[
                _field("rest-countries", "Returns the common country name.", "name.common", "string"),
                _field("rest-countries", "Returns country population as a number.", "population", "number"),
                _auth("rest-countries"),
            ],
            metadata={"endpoint": "https://restcountries.com/v3.1/name"},
        ),
        ToolSpec(
            tool_id="nager-date",
            name="Nager.Date",
            category="holidays",
            provider_kind="api",
            documentation=[
                "Nager.Date returns public holidays as a JSON array. Each holiday includes `date` and `name`.",
                "No API key is required.",
                "Holiday calendars are available for many countries.",
            ],
            claims=[
                _field("nager-date", "Returns public holidays as a JSON array.", "", "array"),
                _field("nager-date", "Each holiday includes a date field.", "date", "string"),
                _auth("nager-date"),
            ],
            metadata={"endpoint": "https://date.nager.at/api/v3/PublicHolidays"},
        ),
        ToolSpec(
            tool_id="arxiv",
            name="arXiv Search",
            category="research",
            provider_kind="api",
            documentation=[
                "arXiv search returns an Atom XML feed with `entry` elements containing `title` and `summary`.",
                "No API key is required.",
                "Results are sorted by relevance by default.",
            ],
            claims=[
                _field("arxiv", "Returns an Atom feed with entry elements.", "", "xml"),
                _field("arxiv", "Each entry contains a title.", "title", "string"),
                _auth("arxiv"),
                _claim("arxiv", "Results are sorted by relevance by default.", ClaimType.BEHAVIOUR, probeable=False),
            ],
            metadata={"endpoint": "https://export.arxiv.org/api/query"},
        ),
        ToolSpec(
            tool_id="open-library",
            name="Open Library",
            category="books",
            provider_kind="api",
            documentation=[
                "Open Library search returns `docs` as a JSON array. Each doc has `title`, `author_name` and `first_publish_year`.",
                "No API key is required.",
            ],
            claims=[
                _field("open-library", "Returns search results in a docs array.", "docs", "array"),
                _field("open-library", "Each doc contains a title.", "title", "string"),
                _auth("open-library"),
            ],
            metadata={"endpoint": "https://openlibrary.org/search.json"},
        ),
        ToolSpec(
            tool_id="dog-ceo",
            name="Dog CEO",
            category="images",
            provider_kind="api",
            documentation=[
                "Dog CEO returns a random dog image URL in the `message` field.",
                "The `status` field is `success`.",
                "No API key is required.",
            ],
            claims=[
                _field("dog-ceo", "Returns an image URL in the message field.", "message", "string"),
                _field("dog-ceo", "Returns status success.", "status", "string"),
                _auth("dog-ceo"),
            ],
            metadata={"endpoint": "https://dog.ceo/api/breeds/image/random"},
        ),
        ToolSpec(
            tool_id="cat-fact",
            name="Cat Fact",
            category="facts",
            provider_kind="api",
            documentation=[
                "Cat Fact returns a random fact in the `fact` field and its length in `length`. The `fact` field is a string and `length` is a number.",
                "No API key is required.",
            ],
            claims=[
                _field("cat-fact", "Returns a fact string.", "fact", "string"),
                _field("cat-fact", "Returns the fact length as a number.", "length", "number"),
                _auth("cat-fact"),
            ],
            metadata={"endpoint": "https://catfact.ninja/fact"},
        ),
        ToolSpec(
            tool_id="joke-api",
            name="Official Joke API",
            category="humour",
            provider_kind="api",
            documentation=[
                "The Joke API returns `setup`, `punchline` and `type` fields.",
                "No API key is required.",
            ],
            claims=[
                _field("joke-api", "Returns a setup field.", "setup", "string"),
                _field("joke-api", "Returns a punchline field.", "punchline", "string"),
                _auth("joke-api"),
            ],
            metadata={"endpoint": "https://official-joke-api.appspot.com/random_joke"},
        ),
        ToolSpec(
            tool_id="ipify",
            name="IPify",
            category="network",
            provider_kind="api",
            documentation=[
                "IPify returns the public IP address in the `ip` field.",
                "No API key is required.",
            ],
            claims=[
                _field("ipify", "Returns the public IP address.", "ip", "string"),
                _auth("ipify"),
            ],
            metadata={"endpoint": "https://api.ipify.org"},
        ),
        ToolSpec(
            tool_id="usgs-earthquake",
            name="USGS Earthquake",
            category="geoscience",
            provider_kind="api",
            documentation=[
                "USGS returns GeoJSON with a `features` array. Each feature has `properties.mag` as a number and `properties.place` as a string.",
                "No API key is required.",
            ],
            claims=[
                _field("usgs-earthquake", "Returns a features array.", "features", "array"),
                _field("usgs-earthquake", "Each feature has a magnitude number.", "properties.mag", "number"),
                _auth("usgs-earthquake"),
            ],
            metadata={"endpoint": "https://earthquake.usgs.gov/fdsnws/event/1/query"},
        ),
        ToolSpec(
            tool_id="worldtime",
            name="World Time",
            category="time",
            provider_kind="api",
            documentation=[
                "World Time returns the current date and time for a timezone in `datetime` and the `timezone` name.",
                "No API key is required.",
            ],
            claims=[
                _field("worldtime", "Returns the current datetime.", "datetime", "string"),
                _field("worldtime", "Returns the timezone name.", "timezone", "string"),
                _auth("worldtime"),
            ],
            metadata={"endpoint": "https://worldtimeapi.org/api/timezone"},
        ),
        ToolSpec(
            tool_id="datamuse",
            name="Datamuse",
            category="language",
            provider_kind="api",
            documentation=[
                "Datamuse returns word suggestions as a JSON array. Each item has `word` and `score`.",
                "No API key is required.",
            ],
            claims=[
                _field("datamuse", "Returns word suggestions as a JSON array.", "", "array"),
                _field("datamuse", "Each suggestion has a word.", "word", "string"),
                _auth("datamuse"),
            ],
            metadata={"endpoint": "https://api.datamuse.com/words"},
        ),
        ToolSpec(
            tool_id="coingecko",
            name="CoinGecko",
            category="crypto",
            provider_kind="api",
            documentation=[
                "CoinGecko returns simple cryptocurrency prices. The response maps coin ids to objects with numeric currency rates, for example `bitcoin.usd` is a number.",
                "No API key is required for the free endpoint.",
                "The free endpoint is rate limited.",
            ],
            claims=[
                _field("coingecko", "Returns bitcoin price in USD as a number.", "bitcoin.usd", "number", minimum=0),
                _auth("coingecko"),
                _claim("coingecko", "The free endpoint is rate limited.", ClaimType.LIMIT, probeable=False),
            ],
            metadata={"endpoint": "https://api.coingecko.com/api/v3/simple/price"},
        ),
    ]
    return {tool.tool_id: tool for tool in tools}


def catalog_list() -> list[ToolSpec]:
    return list(build_catalog().values())
