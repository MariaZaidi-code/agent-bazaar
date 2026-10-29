"""Domain layer concepts: curated seed, merge helpers and Turtle serialisation.

The seed set is the offline fallback for the LLM generation pipeline and the
hand-reviewed starting point for the four best-covered domains (geo, weather,
currency and general reference data), reported honestly in the proposal's
limitations.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from rdflib import Graph, Literal
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from agent_bazaar.ontology.ns import AB, unit_iri


class DomainConcept(BaseModel):
    model_config = ConfigDict(extra="allow")

    local_name: str
    label: str
    data_type: str = "string"
    parents: list[str] = Field(default_factory=lambda: ["Concept"])
    unit_family: str | None = None
    default_unit: str | None = None
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""
    unit_bearing: bool = False

    def iri(self) -> str:
        return str(AB[self.local_name])


def _concept(
    local_name: str,
    label: str,
    data_type: str,
    aliases: list[str] | None = None,
    *,
    parents: list[str] | None = None,
    unit_family: str | None = None,
    default_unit: str | None = None,
    definition: str = "",
) -> DomainConcept:
    return DomainConcept(
        local_name=local_name,
        label=label,
        data_type=data_type,
        parents=parents or ["Concept"],
        unit_family=unit_family,
        default_unit=default_unit,
        aliases=aliases or [],
        definition=definition,
        unit_bearing=unit_family is not None,
    )


SEED_CONCEPTS: list[DomainConcept] = [
    # -- geo ---------------------------------------------------------------
    _concept("Position", "Position", "object", ["location", "coords", "coordinates", "geometry"]),
    _concept("Latitude", "Latitude", "float", ["lat"], unit_family="AngleUnit", default_unit="Degree"),
    _concept("Longitude", "Longitude", "float", ["lon", "lng", "long"], unit_family="AngleUnit", default_unit="Degree"),
    _concept("Address", "Address", "string", ["street_address", "formatted_address"]),
    _concept("City", "City", "string", ["town", "municipality", "city_name"]),
    _concept("Region", "Region", "string", ["state", "province", "county"]),
    _concept("PostalCode", "Postal code", "string", ["zip", "zip_code", "postcode"]),
    _concept("CountryName", "Country name", "string", ["country_name", "nation"]),
    _concept("CountryCode", "Country code", "string", ["iso_code", "country_code", "cc", "alpha2", "alpha3"]),
    _concept("PlaceName", "Place name", "string", ["place", "location_name", "display_name"]),
    _concept("Timezone", "Timezone", "string", ["time_zone", "tz", "timezone_id"]),
    _concept("Elevation", "Elevation", "float", ["altitude", "height"], unit_family="LengthUnit", default_unit="Metre"),
    # -- weather ------------------------------------------------------------
    _concept("Temperature", "Temperature", "float", ["temp", "temperature_c", "temp_c", "temperature_2m"], unit_family="TemperatureUnit", default_unit="Celsius"),
    _concept("FeelsLikeTemperature", "Feels-like temperature", "float", ["apparent_temperature", "feels_like", "heat_index"], parents=["Temperature"], unit_family="TemperatureUnit", default_unit="Celsius"),
    _concept("DewPoint", "Dew point", "float", ["dew_point", "dewpoint"], unit_family="TemperatureUnit", default_unit="Celsius"),
    _concept("WindSpeed", "Wind speed", "float", ["wind_speed", "windspeed", "wind_speed_10m"], unit_family="SpeedUnit", default_unit="MetrePerSecond"),
    _concept("WindDirection", "Wind direction", "integer", ["wind_deg", "wind_direction", "winddir"], unit_family="AngleUnit", default_unit="Degree"),
    _concept("Humidity", "Relative humidity", "float", ["rh", "relative_humidity"], unit_family="PercentageUnit", default_unit="Percent"),
    _concept("Precipitation", "Precipitation", "float", ["rain", "precip", "precipitation_sum", "rainfall"], unit_family="PrecipitationUnit", default_unit="Millimetre"),
    _concept("Pressure", "Atmospheric pressure", "float", ["pressure_msl", "surface_pressure", "barometric_pressure"], unit_family="PressureUnit", default_unit="Hectopascal"),
    _concept("CloudCover", "Cloud cover", "float", ["clouds", "cloudiness", "cloud_cover"], unit_family="PercentageUnit", default_unit="Percent"),
    _concept("WeatherCondition", "Weather condition", "string", ["condition", "weather", "weather_description"]),
    _concept("WeatherCode", "Weather code", "integer", ["weather_code", "wmo_code", "condition_code"]),
    _concept("UVIndex", "UV index", "float", ["uv", "uv_index"]),
    _concept("Visibility", "Visibility", "float", ["visibility_distance"], unit_family="LengthUnit", default_unit="Metre"),
    _concept("SunriseTime", "Sunrise time", "datetime", ["sunrise"]),
    _concept("SunsetTime", "Sunset time", "datetime", ["sunset"]),
    _concept("Forecast", "Forecast", "object", ["prediction", "forecast_data", "daily"]),
    # -- currency -----------------------------------------------------------
    _concept("Currency", "Currency", "string", ["currency_name"]),
    _concept("CurrencyCode", "Currency code", "string", ["currency_code", "iso_currency"], parents=["CountryCode"]),
    _concept("ExchangeRate", "Exchange rate", "float", ["rate", "fx_rate", "conversion_rate", "exchange_rate"]),
    _concept("MoneyAmount", "Money amount", "float", ["amount", "value", "money", "price"]),
    _concept("BaseCurrency", "Base currency", "string", ["base", "from_currency"]),
    _concept("QuoteCurrency", "Quote currency", "string", ["quote", "to_currency", "target_currency"]),
    # -- general reference ---------------------------------------------------
    _concept("Country", "Country", "object", ["country_record", "country_info"]),
    _concept("Holiday", "Holiday", "object", ["holiday_record", "public_holiday"]),
    _concept("HolidayName", "Holiday name", "string", ["holiday_name"], parents=["Name"]),
    _concept("HolidayDate", "Holiday date", "date", ["holiday_date", "local_date"], parents=["ISODate"]),
    _concept("Capital", "Capital", "string", ["capital_city"]),
    _concept("Language", "Language", "string", ["languages", "language_code"]),
    _concept("Population", "Population", "integer", ["pop", "population_count"], unit_family="CountUnit", default_unit="Count"),
    _concept("AreaSize", "Area", "float", ["area", "land_area", "surface_area"], unit_family="AreaUnit", default_unit="SquareKilometre"),
    _concept("FlagUrl", "Flag URL", "string", ["flag", "flag_link"], parents=["Url"]),
    _concept("Distance", "Distance", "float", ["distance_km", "range"], unit_family="LengthUnit", default_unit="Metre"),
    _concept("Duration", "Duration", "float", ["duration_s", "elapsed", "length"], unit_family="DurationUnit", default_unit="Second"),
    _concept("Speed", "Speed", "float", ["velocity"], unit_family="SpeedUnit", default_unit="MetrePerSecond"),
    _concept("Mass", "Mass", "float", ["weight"], unit_family="MassUnit", default_unit="Kilogram"),
    _concept("Percentage", "Percentage", "float", ["percent", "share", "ratio"], unit_family="PercentageUnit", default_unit="Percent"),
    _concept("ISODate", "ISO date", "date", ["date", "day", "calendar_date"]),
    _concept("DateTime", "Date-time instant", "datetime", ["timestamp", "time", "datetime_utc", "iso_time"], parents=["ISODate"]),
    _concept("Name", "Name", "string", ["title", "label", "display_name_text"]),
    _concept("Description", "Description", "string", ["summary", "text", "details"]),
    _concept("Identifier", "Identifier", "string", ["id", "key", "code"]),
    _concept("Count", "Count", "integer", ["total", "total_count", "number_of_results"], unit_family="CountUnit", default_unit="Count"),
    _concept("Rank", "Rank", "integer", ["position_rank", "order", "index"]),
    _concept("Rating", "Rating", "float", ["score", "stars"]),
    _concept("BooleanFlag", "Boolean flag", "boolean", ["enabled", "is_active", "has_more", "success"]),
    _concept("Url", "URL", "string", ["link", "href", "website"]),
    _concept("Email", "Email", "string", ["email_address"]),
    _concept("PhoneNumber", "Phone number", "string", ["phone", "telephone"]),
    # -- news ---------------------------------------------------------------
    _concept("NewsTopic", "News topic", "string", ["news_query", "headline_topic"]),
    _concept("NewsArticle", "News article", "object", ["story_record", "headline_record"]),
    # -- crypto -------------------------------------------------------------
    _concept("CryptoAsset", "Crypto asset", "string", ["coin", "token"]),
    _concept("CryptoPrice", "Crypto price", "object", ["coin_price", "crypto_quote"]),
    # -- television ---------------------------------------------------------
    _concept("ShowQuery", "Show query", "string", ["show_title", "series_title"]),
    _concept("TVShow", "TV show", "object", ["television_show", "series_record"]),
    # -- books --------------------------------------------------------------
    _concept("BookQuery", "Book query", "string", ["book_title", "book_subject"]),
    _concept("Book", "Book", "object", ["book_record", "bibliographic_record", "volume"]),
    # -- translation --------------------------------------------------------
    _concept("LanguageCode", "Language code", "string", ["lang_code", "iso_language_code"]),
    _concept("Translation", "Translation", "object", ["translated_text"]),
    # -- time and sun -------------------------------------------------------
    _concept("TimezoneName", "Timezone name", "string", ["iana_timezone_name", "tz_name"]),
    _concept("CurrentTime", "Current time", "object", ["local_time", "clock_time"]),
    _concept("SunTimes", "Sun times", "object", ["solar_times", "sunrise_sunset"]),
    # -- food ---------------------------------------------------------------
    _concept("RecipeQuery", "Recipe query", "string", ["dish_name", "recipe_search"]),
    _concept("Recipe", "Recipe", "object", ["recipe_record", "meal_recipe"]),
    # -- sports -------------------------------------------------------------
    _concept("SportsLeague", "Sports league", "string", ["league_name", "competition_name"]),
    _concept("SportsScore", "Sports score", "object", ["game_score", "match_score"]),
]


def concepts_to_graph(concepts: list[DomainConcept]) -> Graph:
    graph = Graph()
    graph.bind("ab", AB)
    for concept in concepts:
        subject = AB[concept.local_name]
        graph.add((subject, RDF.type, OWL.Class))
        graph.add((subject, RDF.type, AB.Concept))
        graph.add((subject, RDFS.label, Literal(concept.label)))
        graph.add((subject, AB.hasDataType, Literal(concept.data_type)))
        for parent in concept.parents:
            graph.add((subject, RDFS.subClassOf, AB[parent]))
        if concept.unit_bearing:
            graph.add((subject, AB.unitBearing, Literal(True)))
        if concept.unit_family:
            graph.add((subject, AB.unitFamily, AB[concept.unit_family]))
        if concept.default_unit:
            graph.add((subject, AB.defaultUnit, unit_iri(concept.default_unit)))
        for alias in concept.aliases:
            graph.add((subject, SKOS.altLabel, Literal(alias)))
        if concept.definition:
            graph.add((subject, RDFS.comment, Literal(concept.definition)))
    return graph


def merge_concepts(concepts: list[DomainConcept]) -> list[DomainConcept]:
    """Merge duplicate concepts by local name, label or alias, keeping the richer record."""
    merged: dict[str, DomainConcept] = {}
    claimed: dict[str, str] = {}
    for concept in concepts:
        keys = [concept.local_name.lower(), concept.label.lower(), *(a.lower() for a in concept.aliases)]
        owner = next((claimed[k] for k in keys if k in claimed), None)
        if owner is None:
            merged[concept.local_name] = concept
            for key in keys:
                claimed[key] = concept.local_name
            continue
        existing = merged[owner]
        combined_aliases = sorted({*existing.aliases, *concept.aliases, concept.label})
        combined_parents = sorted({*existing.parents, *concept.parents})
        merged[owner] = existing.model_copy(
            update={
                "aliases": combined_aliases,
                "parents": combined_parents,
                "definition": existing.definition or concept.definition,
                "unit_family": existing.unit_family or concept.unit_family,
                "default_unit": existing.default_unit or concept.default_unit,
                "unit_bearing": existing.unit_bearing or concept.unit_bearing,
            }
        )
    return sorted(merged.values(), key=lambda c: c.local_name)


def save_concepts(concepts: list[DomainConcept], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    graph = concepts_to_graph(concepts)
    graph.serialize(destination=path, format="turtle")
    return path


def load_concepts(path: str | Path) -> list[DomainConcept]:
    graph = Graph()
    graph.parse(path, format="turtle")
    concepts: list[DomainConcept] = []
    for subject in graph.subjects(RDF.type, AB.Concept):
        local = str(subject).rsplit("#", 1)[-1]
        label = graph.value(subject, RDFS.label)
        data_type = graph.value(subject, AB.hasDataType)
        parents = [str(p).rsplit("#", 1)[-1] for p in graph.objects(subject, RDFS.subClassOf)]
        unit_family = graph.value(subject, AB.unitFamily)
        default_unit = graph.value(subject, AB.defaultUnit)
        aliases = [str(a) for a in graph.objects(subject, SKOS.altLabel)]
        definition = graph.value(subject, RDFS.comment)
        bearing = graph.value(subject, AB.unitBearing)
        concepts.append(
            DomainConcept(
                local_name=local,
                label=str(label) if label else local,
                data_type=str(data_type) if data_type else "string",
                parents=parents or ["Concept"],
                unit_family=str(unit_family).rsplit("#", 1)[-1] if unit_family else None,
                default_unit=str(default_unit).rsplit("#", 1)[-1] if default_unit else None,
                aliases=aliases,
                definition=str(definition) if definition else "",
                unit_bearing=bool(bearing),
            )
        )
    return sorted(concepts, key=lambda c: c.local_name)
