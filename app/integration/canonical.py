"""Canonical concept, unit and capability names shared with the knowledge layer.

The Client/Provider/Interface layer historically carried a small local fallback
ontology (``app/data/ontology.json``) with its own naming (``C``, ``F``,
``LocationName``, ``Coordinates``). The knowledge layer owns the canonical
ontology in RDF (``src/agent_bazaar/ontology``). This module is the single
translation point between the two vocabularies so no other module has to
hard-code aliases.

Rules:

* Concept and unit names are matched case-insensitively, with or without the
  ``ab:`` prefix or a full IRI.
* Concepts that are missing from the published RDF artifacts (document QA,
  research-paper and Sprint 1 provider concepts) are listed in
  :data:`EXTERNAL_CONCEPTS`; validation treats them as external rather than
  invalid, and a rebuild removes the fallback.
"""

from __future__ import annotations

from collections.abc import Iterable

from agent_bazaar.ontology.ns import AB
from agent_bazaar.ontology.units import UNIT_FAMILIES, compatible_units

# Local fallback name -> canonical knowledge-layer concept local name.
CONCEPT_ALIASES: dict[str, str] = {
    "LocationName": "PlaceName",
    "CityName": "City",
    "Coordinates": "Position",
    "Money": "MoneyAmount",
    "Text": "Description",
    "Number": "Count",
    "DateTimeISO": "DateTime",
    "iso8601": "DateTime",
}

# Local fallback unit -> canonical knowledge-layer unit local name.
UNIT_ALIASES: dict[str, str] = {
    "C": "Celsius",
    "F": "Fahrenheit",
    "K": "Kelvin",
    "degrees": "Degree",
    "deg": "Degree",
}

# Concepts that only exist in the local fallback ontology.
EXTERNAL_CONCEPTS: frozenset[str] = frozenset(
    {
        "ResearchPaper",
        "ResearchTopic",
        "NaturalLanguageQuery",
        "TabularAnswer",
        "DocumentReference",
        "DocumentQuestion",
        "AnswerFromDocument",
        "Entity",
        "Service",
        "Capability",
        "Claim",
        "Evidence",
        "Provider",
        "NewsTopic",
        "NewsArticle",
        "CryptoAsset",
        "CryptoPrice",
        "ShowQuery",
        "TVShow",
        "BookQuery",
        "Book",
        "LanguageCode",
        "Translation",
        "TimezoneName",
        "CurrentTime",
        "SunTimes",
        "RecipeQuery",
        "Recipe",
        "SportsLeague",
        "SportsScore",
    }
)

# Curated capability taxonomy of the Client layer.
CURATED_CAPABILITIES: tuple[str, ...] = (
    "GeocodeLocation",
    "GetWeatherForecast",
    "ConvertCurrency",
    "GetCountryFacts",
    "GetPublicHolidays",
    "SearchResearchPapers",
    "QueryStructuredData",
    "AnswerFromDocument",
    "SearchNews",
    "GetCryptoPrice",
    "SearchTVShows",
    "SearchBooks",
    "TranslateText",
    "GetCurrentTime",
    "GetSunTimes",
    "SearchRecipes",
    "GetSportsScores",
)

# Derived capability slug -> curated capability.
CAPABILITY_ALIASES: dict[str, str] = {
    "weather-api": "GetWeatherForecast",
    "weather-forecast": "GetWeatherForecast",
    "get-weather-forecast": "GetWeatherForecast",
    "forecast": "GetWeatherForecast",
    "weather": "GetWeatherForecast",
    "climate": "GetWeatherForecast",
    "geocode-location": "GeocodeLocation",
    "geocode": "GeocodeLocation",
    "geocoding": "GeocodeLocation",
    "location": "GeocodeLocation",
    "place": "GeocodeLocation",
    "city": "GeocodeLocation",
    "address": "GeocodeLocation",
    "convert-currency": "ConvertCurrency",
    "currency": "ConvertCurrency",
    "exchange-rate": "ConvertCurrency",
    "money": "ConvertCurrency",
    "get-country-facts": "GetCountryFacts",
    "country": "GetCountryFacts",
    "country-facts": "GetCountryFacts",
    "get-public-holidays": "GetPublicHolidays",
    "holiday": "GetPublicHolidays",
    "holidays": "GetPublicHolidays",
    "search-research-papers": "SearchResearchPapers",
    "research": "SearchResearchPapers",
    "arxiv": "SearchResearchPapers",
    "query-structured-data": "QueryStructuredData",
    "structured-data": "QueryStructuredData",
    "sql": "QueryStructuredData",
    "answer-from-document": "AnswerFromDocument",
    "document": "AnswerFromDocument",
    "document-qa": "AnswerFromDocument",
    "search-news": "SearchNews",
    "news": "SearchNews",
    "headlines": "SearchNews",
    "hacker-news": "SearchNews",
    "hackernews": "SearchNews",
    "get-crypto-price": "GetCryptoPrice",
    "crypto": "GetCryptoPrice",
    "cryptocurrency": "GetCryptoPrice",
    "coin-price": "GetCryptoPrice",
    "bitcoin": "GetCryptoPrice",
    "search-tv-shows": "SearchTVShows",
    "tv": "SearchTVShows",
    "television": "SearchTVShows",
    "shows": "SearchTVShows",
    "search-books": "SearchBooks",
    "books": "SearchBooks",
    "book-search": "SearchBooks",
    "library": "SearchBooks",
    "translate-text": "TranslateText",
    "translate": "TranslateText",
    "translation": "TranslateText",
    "language": "TranslateText",
    "get-current-time": "GetCurrentTime",
    "time": "GetCurrentTime",
    "clock": "GetCurrentTime",
    "timezone": "GetCurrentTime",
    "get-sun-times": "GetSunTimes",
    "sunrise": "GetSunTimes",
    "sunset": "GetSunTimes",
    "solar-times": "GetSunTimes",
    "search-recipes": "SearchRecipes",
    "recipes": "SearchRecipes",
    "recipe": "SearchRecipes",
    "cooking": "SearchRecipes",
    "get-sports-scores": "GetSportsScores",
    "sports": "GetSportsScores",
    "scores": "GetSportsScores",
    "scoreboard": "GetSportsScores",
}

# Canonical concept -> curated capability used when a tool has no capability.
CONCEPT_CAPABILITY: dict[str, str] = {
    "Temperature": "GetWeatherForecast",
    "FeelsLikeTemperature": "GetWeatherForecast",
    "Humidity": "GetWeatherForecast",
    "WindSpeed": "GetWeatherForecast",
    "Precipitation": "GetWeatherForecast",
    "Pressure": "GetWeatherForecast",
    "Forecast": "GetWeatherForecast",
    "PlaceName": "GeocodeLocation",
    "City": "GeocodeLocation",
    "Address": "GeocodeLocation",
    "Position": "GeocodeLocation",
    "Latitude": "GeocodeLocation",
    "Longitude": "GeocodeLocation",
    "PostalCode": "GeocodeLocation",
    "Currency": "ConvertCurrency",
    "CurrencyCode": "ConvertCurrency",
    "ExchangeRate": "ConvertCurrency",
    "MoneyAmount": "ConvertCurrency",
    "Country": "GetCountryFacts",
    "CountryCode": "GetCountryFacts",
    "CountryName": "GetCountryFacts",
    "Capital": "GetCountryFacts",
    "Population": "GetCountryFacts",
    "Holiday": "GetPublicHolidays",
    "HolidayName": "GetPublicHolidays",
    "HolidayDate": "GetPublicHolidays",
    "ResearchPaper": "SearchResearchPapers",
    "ResearchTopic": "SearchResearchPapers",
    "TabularAnswer": "QueryStructuredData",
    "AnswerFromDocument": "AnswerFromDocument",
    "DocumentReference": "AnswerFromDocument",
    "NewsArticle": "SearchNews",
    "NewsTopic": "SearchNews",
    "CryptoPrice": "GetCryptoPrice",
    "CryptoAsset": "GetCryptoPrice",
    "TVShow": "SearchTVShows",
    "ShowQuery": "SearchTVShows",
    "Book": "SearchBooks",
    "BookQuery": "SearchBooks",
    "Translation": "TranslateText",
    "LanguageCode": "TranslateText",
    "CurrentTime": "GetCurrentTime",
    "TimezoneName": "GetCurrentTime",
    "SunTimes": "GetSunTimes",
    "Recipe": "SearchRecipes",
    "RecipeQuery": "SearchRecipes",
    "SportsScore": "GetSportsScores",
    "SportsLeague": "GetSportsScores",
}


def _strip(value: str) -> str:
    text = str(value or "").strip()
    if "#" in text:
        text = text.rsplit("#", 1)[-1]
    elif text.startswith("ab:"):
        text = text[3:]
    return text


def canonical_concept(name: str | None) -> str:
    """Map any concept reference to the canonical knowledge-layer local name."""
    text = _strip(str(name or ""))
    if not text:
        return ""
    lowered = text.lower()
    if lowered in {key.lower() for key in CONCEPT_ALIASES}:
        for key, value in CONCEPT_ALIASES.items():
            if key.lower() == lowered:
                return value
    return text


def is_external_concept(name: str | None) -> bool:
    return canonical_concept(name) in EXTERNAL_CONCEPTS


def concept_iri(name: str | None) -> str:
    return str(AB[canonical_concept(name)])


def canonical_unit(name: str | None) -> str | None:
    """Map a unit reference to the canonical unit name, or None when unitless."""
    text = _strip(str(name or ""))
    if not text:
        return None
    lowered = text.lower()
    for key, value in UNIT_ALIASES.items():
        if key.lower() == lowered:
            return value
    return text


def known_units() -> set[str]:
    names: set[str] = set()
    for family in UNIT_FAMILIES.values():
        for unit in family["units"]:
            names.add(unit.local_name)
    return names


def is_known_unit(name: str | None) -> bool:
    unit = canonical_unit(name)
    return bool(unit) and unit in known_units()


def units_compatible(source: str | None, target: str | None) -> bool:
    """True when the canonical units are the same or convertible."""
    left = canonical_unit(source)
    right = canonical_unit(target)
    if left is None or right is None:
        return True
    if left == right:
        return True
    return compatible_units(left, right)


def canonical_capability(name: str | None) -> str:
    """Map a capability slug to the curated capability taxonomy."""
    text = str(name or "").strip()
    if not text:
        return ""
    if text in CURATED_CAPABILITIES:
        return text
    lowered = text.lower()
    for key, value in CAPABILITY_ALIASES.items():
        if key.lower() == lowered:
            return value
    return text


def capability_for_concepts(concepts: Iterable[str]) -> str | None:
    """Infer a curated capability from the canonical concepts of a tool."""
    for concept in concepts:
        canonical = canonical_concept(concept)
        capability = CONCEPT_CAPABILITY.get(canonical)
        if capability:
            return capability
    return None
