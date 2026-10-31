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
    "SearchMovies",
    "GetMovieDetails",
    "SearchTVEpisodes",
    "GetTVSeason",
    "SearchPodcasts",
    "GetPodcastDetails",
    "SearchMusic",
    "GetMusicAlbum",
    "SearchEvents",
    "GetEventDetails",
    "GetWeatherAlerts",
    "GetSportsSchedule",
    "GetSportsTeams",
    "SearchOrganizations",
    "GetOrganizationFacts",
    "SearchPeople",
    "GetPersonFacts",
    "SearchProducts",
    "GetProductDetails",
    "SearchFoodProducts",
    "GetNutritionFacts",
    "SearchLocations",
    "ReverseGeocode",
    "GetElevation",
    "GetTimezone",
    "GetRoute",
    "SearchPointsOfInterest",
    "GetCountrySubdivisions",
    "GetLocationBoundary",
    "GetNearbyPlaces",
    "GetPlaceDetails",
    "GetExchangeMarkets",
    "CheckGrammar",
    "GenerateQRCode",
    "GetAirQuality",
    "GetCompoundInfo",
    "GetDrugLabel",
    "GetFoodProduct",
    "GetIPLocation",
    "GetMetalPrices",
    "GetSocialPosts",
    "SearchQuestions",
    "SearchRepositories",
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
    "search-movies": "SearchMovies",
    "movies": "SearchMovies",
    "film": "SearchMovies",
    "get-movie-details": "GetMovieDetails",
    "movie-details": "GetMovieDetails",
    "search-tv-episodes": "SearchTVEpisodes",
    "tv-episodes": "SearchTVEpisodes",
    "episodes": "SearchTVEpisodes",
    "get-tv-season": "GetTVSeason",
    "tv-season": "GetTVSeason",
    "season": "GetTVSeason",
    "search-podcasts": "SearchPodcasts",
    "podcasts": "SearchPodcasts",
    "podcast": "SearchPodcasts",
    "get-podcast-details": "GetPodcastDetails",
    "search-music": "SearchMusic",
    "music": "SearchMusic",
    "tracks": "SearchMusic",
    "get-music-album": "GetMusicAlbum",
    "album": "GetMusicAlbum",
    "search-events": "SearchEvents",
    "events": "SearchEvents",
    "get-event-details": "GetEventDetails",
    "event-details": "GetEventDetails",
    "get-weather-alerts": "GetWeatherAlerts",
    "weather-alerts": "GetWeatherAlerts",
    "alerts": "GetWeatherAlerts",
    "get-sports-schedule": "GetSportsSchedule",
    "sports-schedule": "GetSportsSchedule",
    "fixtures": "GetSportsSchedule",
    "get-sports-teams": "GetSportsTeams",
    "sports-teams": "GetSportsTeams",
    "teams": "GetSportsTeams",
    "search-organizations": "SearchOrganizations",
    "organizations": "SearchOrganizations",
    "companies": "SearchOrganizations",
    "get-organization-facts": "GetOrganizationFacts",
    "organization-facts": "GetOrganizationFacts",
    "company-profile": "GetOrganizationFacts",
    "search-people": "SearchPeople",
    "people": "SearchPeople",
    "persons": "SearchPeople",
    "get-person-facts": "GetPersonFacts",
    "person-facts": "GetPersonFacts",
    "search-products": "SearchProducts",
    "products": "SearchProducts",
    "shopping": "SearchProducts",
    "get-product-details": "GetProductDetails",
    "product-details": "GetProductDetails",
    "search-food-products": "SearchFoodProducts",
    "food": "SearchFoodProducts",
    "food-products": "SearchFoodProducts",
    "get-nutrition-facts": "GetNutritionFacts",
    "nutrition": "GetNutritionFacts",
    "search-locations": "SearchLocations",
    "places": "SearchLocations",
    "reverse-geocode": "ReverseGeocode",
    "reverse-geocoding": "ReverseGeocode",
    "get-elevation": "GetElevation",
    "elevation": "GetElevation",
    "altitude": "GetElevation",
    "get-timezone": "GetTimezone",
    "timezone-lookup": "GetTimezone",
    "get-route": "GetRoute",
    "directions": "GetRoute",
    "routing": "GetRoute",
    "search-points-of-interest": "SearchPointsOfInterest",
    "points-of-interest": "SearchPointsOfInterest",
    "poi": "SearchPointsOfInterest",
    "get-country-subdivisions": "GetCountrySubdivisions",
    "subdivisions": "GetCountrySubdivisions",
    "get-location-boundary": "GetLocationBoundary",
    "boundary": "GetLocationBoundary",
    "get-nearby-places": "GetNearbyPlaces",
    "nearby": "GetNearbyPlaces",
    "get-place-details": "GetPlaceDetails",
    "place-details": "GetPlaceDetails",
    "get-exchange-markets": "GetExchangeMarkets",
    "exchange-markets": "GetExchangeMarkets",
    "market-data": "GetExchangeMarkets",
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
    "Movie": "SearchMovies",
    "MovieTitle": "SearchMovies",
    "MovieGenre": "SearchMovies",
    "MovieRating": "GetMovieDetails",
    "MovieRuntime": "GetMovieDetails",
    "MovieReleaseYear": "GetMovieDetails",
    "TVEpisode": "SearchTVEpisodes",
    "TVEpisodeTitle": "SearchTVEpisodes",
    "TVEpisodeNumber": "SearchTVEpisodes",
    "TVSeason": "GetTVSeason",
    "TVSeasonNumber": "GetTVSeason",
    "TVNetwork": "GetTVSeason",
    "Podcast": "SearchPodcasts",
    "PodcastEpisode": "GetPodcastDetails",
    "PodcastQuery": "SearchPodcasts",
    "MusicTrack": "SearchMusic",
    "MusicAlbum": "GetMusicAlbum",
    "MusicQuery": "SearchMusic",
    "EventRecord": "SearchEvents",
    "EventName": "SearchEvents",
    "EventVenue": "SearchEvents",
    "EventStartDate": "SearchEvents",
    "EventEndDate": "SearchEvents",
    "EventCategory": "SearchEvents",
    "EventStatus": "GetEventDetails",
    "EventUrl": "GetEventDetails",
    "EventOrganizer": "GetEventDetails",
    "WeatherAlert": "GetWeatherAlerts",
    "SportsSeason": "GetSportsSchedule",
    "GameStatus": "GetSportsSchedule",
    "SportsTeam": "GetSportsTeams",
    "OrganizationRecord": "SearchOrganizations",
    "OrganizationName": "GetOrganizationFacts",
    "OrganizationType": "SearchOrganizations",
    "OrganizationUrl": "GetOrganizationFacts",
    "OrganizationCountry": "GetOrganizationFacts",
    "OrganizationFoundedYear": "GetOrganizationFacts",
    "OrganizationLogoUrl": "GetOrganizationFacts",
    "CompanyIndustry": "GetOrganizationFacts",
    "CompanyEmployeeCount": "GetOrganizationFacts",
    "PersonRecord": "SearchPeople",
    "PersonName": "GetPersonFacts",
    "PersonRole": "SearchPeople",
    "PersonBirthDate": "GetPersonFacts",
    "PersonNationality": "GetPersonFacts",
    "PersonBio": "GetPersonFacts",
    "PersonImageUrl": "GetPersonFacts",
    "Author": "SearchPeople",
    "Director": "SearchPeople",
    "Actor": "SearchPeople",
    "Athlete": "SearchPeople",
    "ProductRecord": "SearchProducts",
    "ProductName": "SearchProducts",
    "ProductBrand": "SearchProducts",
    "ProductCategory": "SearchProducts",
    "ProductPrice": "GetProductDetails",
    "ProductCurrency": "GetProductDetails",
    "ProductCode": "GetProductDetails",
    "NutritionScore": "GetNutritionFacts",
    "NutritionGrade": "GetNutritionFacts",
    "Ingredients": "GetNutritionFacts",
    "Allergens": "GetNutritionFacts",
    "ServingSize": "GetNutritionFacts",
    "ProductQuantity": "GetProductDetails",
    "LocationRecord": "SearchLocations",
    "LocationType": "SearchLocations",
    "AdministrativeArea": "GetCountrySubdivisions",
    "Neighborhood": "SearchLocations",
    "District": "GetCountrySubdivisions",
    "StreetAddress": "SearchLocations",
    "BoundingBox": "GetLocationBoundary",
    "LocationConfidence": "SearchLocations",
    "PlaceId": "SearchLocations",
    "WikidataId": "GetPlaceDetails",
    "OsmNodeId": "SearchLocations",
    "OsmWayId": "SearchLocations",
    "OsmRelationId": "SearchLocations",
    "ElevationResolution": "GetElevation",
    "TimezoneOffset": "GetTimezone",
    "CountryCurrency": "GetCountryFacts",
    "CountryLanguages": "GetCountryFacts",
    "CountryArea": "GetCountryFacts",
    "CountryPopulation": "GetCountryFacts",
    "CountryCallingCode": "GetCountryFacts",
    "CountryDrivingSide": "GetCountryFacts",
    "CountryBorders": "GetCountryFacts",
    "CountrySubregion": "GetCountryFacts",
    "OsmTags": "SearchLocations",
    "OsmPlaceRank": "SearchLocations",
    "Route": "GetRoute",
    "RouteDistance": "GetRoute",
    "RouteDuration": "GetRoute",
    "PointOfInterest": "SearchPointsOfInterest",
    "POICategory": "SearchPointsOfInterest",
    "NearbyPlace": "GetNearbyPlaces",
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
