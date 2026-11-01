from __future__ import annotations

import json
from typing import Any

from app.config import Settings
from app.core.cache import Cache
from app.knowledge.graph import ToolKnowledgeGraph
from app.providers.arxiv_provider import ArxivProvider
from app.providers.base import BaseProvider
from app.providers.books import GoogleBooksProvider, OpenLibraryProvider
from app.providers.countries import CountriesProvider
from app.providers.crypto import CoinGeckoProvider
from app.providers.currency import CurrencyProvider
from app.providers.document_provider import DocumentQAProvider, DocumentStore
from app.providers.extra import (
    CoinDeskProvider,
    ExchangerateProvider,
    GitHubProvider,
    IpApiProvider,
    IsGdProvider,
    LanguageToolProvider,
    LibreTranslateProvider,
    MastodonProvider,
    MetalsProvider,
    NasaEonetProvider,
    NasaMarsProvider,
    NoaaAlertsProvider,
    NoaaTidesProvider,
    OpenAlexProvider,
    OpenAQProvider,
    OpenElevationProvider,
    OpenFDAProvider,
    OpenFoodFactsProvider,
    PubChemProvider,
    QRCodeProvider,
    RedditProvider,
    SemanticScholarProvider,
    StackExchangeProvider,
    TheSportsDBProvider,
    UpcItemDbProvider,
)
from app.providers.geonames import GeoNamesProvider
from app.providers.extra2 import (
    CoinCapProvider,
    DataTransformProvider,
    DbpediaProvider,
    DictionaryProvider,
    EmailValidateProvider,
    IpifyProvider,
    IssLocationProvider,
    LaunchLibraryProvider,
    OpenMeteoAirProvider,
    OpenMeteoMarineProvider,
    PasswordToolsProvider,
    RssFeedProvider,
    UuidProvider,
    WikidataProvider,
    WikivoyageProvider,
    WorldBankProvider,
    YahooFinanceProvider,
    ZenQuotesProvider,
)
from app.providers.geocoding import GeocodingProvider
from app.providers.holidays import HolidaysProvider
from app.providers.advice import AdviceSlipProvider
from app.providers.bored import BoredProvider
from app.providers.catfacts import CatFactsProvider
from app.providers.crossref import CrossrefProvider
from app.providers.dogceo import DogCEOProvider
from app.providers.itunes import ITunesProvider
from app.providers.jikan import JikanProvider
from app.providers.joke import JokeProvider
from app.providers.nasa_apod import NasaApodProvider
from app.providers.numbers import NumbersProvider
from app.providers.pokeapi import PokeAPIProvider
from app.providers.spacex import SpaceXProvider
from app.providers.trivia import TriviaProvider
from app.providers.usgs import UsgsProvider
from app.providers.wikipedia import WikipediaProvider
from app.providers.wttr import WttrProvider
from app.providers.mirror import MirrorProvider, make_mirror_spec
from app.providers.news import HackerNewsProvider
from app.providers.recipes import TheMealDBProvider
from app.providers.sports import EspnScoresProvider
from app.providers.sql_provider import UniversitySQLProvider
from app.providers.time import SunriseSunsetProvider, WorldTimeProvider
from app.providers.translation import MyMemoryProvider
from app.providers.tv import TVMazeProvider
from app.providers.weather import MockWeatherFahrenheitProvider, WeatherProvider
from app.schemas import ToolSpec


class ProviderRegistry:
    def __init__(
        self,
        settings: Settings,
        cache: Cache,
        graph: ToolKnowledgeGraph,
    ) -> None:
        self.settings = settings
        self.cache = cache
        self.graph = graph
        self.document_store = DocumentStore(settings)
        self.providers: dict[str, BaseProvider] = {}
        self.providers_by_tool: dict[str, BaseProvider] = {}
        self.validation: dict[str, list[str]] = {}
        self._load()

    def _load(self) -> None:
        records = json.loads(self.settings.tools_file.read_text(encoding="utf-8"))
        for record in records:
            spec = ToolSpec.model_validate(record)
            provider = self._factory(spec)
            self.register(provider)
            if "backup-eligible" in spec.tags:
                mirror_spec = make_mirror_spec(spec)
                mirror = MirrorProvider(provider, mirror_spec)
                self.register(mirror)

    def _factory(self, spec: ToolSpec) -> BaseProvider:
        mapping = {
            "nominatim": GeocodingProvider,
            "open-meteo": WeatherProvider,
            "frankfurter": CurrencyProvider,
            "rest-countries": CountriesProvider,
            "nager-date": HolidaysProvider,
            "arxiv": ArxivProvider,
            "openalex": OpenAlexProvider,
            "semanticscholar": SemanticScholarProvider,
            "github": GitHubProvider,
            "stackexchange": StackExchangeProvider,
            "openfoodfacts": OpenFoodFactsProvider,
            "languagetool": LanguageToolProvider,
            "qrcode": QRCodeProvider,
            "ipapi": IpApiProvider,
            "openelevation": OpenElevationProvider,
            "coindesk": CoinDeskProvider,
            "metals": MetalsProvider,
            "reddit": RedditProvider,
            "openaq": OpenAQProvider,
            "pubchem": PubChemProvider,
            "openfda": OpenFDAProvider,
            "university-db": UniversitySQLProvider,
            "mock-weather-fahrenheit": MockWeatherFahrenheitProvider,
            "hackernews": HackerNewsProvider,
            "itunes": ITunesProvider,
            "wttr": WttrProvider,
            "usgs": UsgsProvider,
            "wikipedia": WikipediaProvider,
            "crossref": CrossrefProvider,
            "joke": JokeProvider,
            "catfacts": CatFactsProvider,
            "dogceo": DogCEOProvider,
            "advice": AdviceSlipProvider,
            "bored": BoredProvider,
            "trivia": TriviaProvider,
            "numbers": NumbersProvider,
            "spacex": SpaceXProvider,
            "pokeapi": PokeAPIProvider,
            "jikan": JikanProvider,
            "nasa-apod": NasaApodProvider,
            "coingecko": CoinGeckoProvider,
            "tvmaze": TVMazeProvider,
            "open-library": OpenLibraryProvider,
            "google-books": GoogleBooksProvider,
            "mymemory": MyMemoryProvider,
            "worldtimeapi": WorldTimeProvider,
            "sunrise-sunset": SunriseSunsetProvider,
            "themealdb": TheMealDBProvider,
            "espn": EspnScoresProvider,
            "nasa-eonet": NasaEonetProvider,
            "noaa-alerts": NoaaAlertsProvider,
            "noaa-tides": NoaaTidesProvider,
            "exchangerate": ExchangerateProvider,
            "libretranslate": LibreTranslateProvider,
            "mastodon": MastodonProvider,
            "thesportsdb": TheSportsDBProvider,
            "upcitemdb": UpcItemDbProvider,
            "isgd": IsGdProvider,
            "nasa-mars": NasaMarsProvider,
            "wikidata": WikidataProvider,
            "wikivoyage": WikivoyageProvider,
            "yahoo-finance": YahooFinanceProvider,
            "rss": RssFeedProvider,
            "dbpedia": DbpediaProvider,
            "iss-location": IssLocationProvider,
            "open-meteo-air": OpenMeteoAirProvider,
            "open-meteo-marine": OpenMeteoMarineProvider,
            "email-validate": EmailValidateProvider,
            "password-tools": PasswordToolsProvider,
            "uuid": UuidProvider,
            "data-transform": DataTransformProvider,
            "ipify": IpifyProvider,
            "zenquotes": ZenQuotesProvider,
            "launch-library": LaunchLibraryProvider,
            "worldbank": WorldBankProvider,
            "dictionary": DictionaryProvider,
            "geonames": GeoNamesProvider,
            "coincap": CoinCapProvider,
        }
        if spec.provider_id == "document-service":
            return DocumentQAProvider(
                spec,
                self.settings,
                self.cache,
                document_store=self.document_store,
            )
        provider_class = mapping.get(spec.provider_id)
        if provider_class is None:
            raise ValueError(f"No provider implementation for {spec.provider_id}")
        return provider_class(spec, self.settings, self.cache)

    def register(self, provider: BaseProvider) -> None:
        self.providers[provider.provider_id] = provider
        self.providers_by_tool[provider.tool_id] = provider
        self.graph.add(provider.spec)
        ontology = getattr(self.graph, "ontology", None)
        self.validation[provider.tool_id] = ontology.validate_tool(provider.spec) if ontology is not None else []

    def get(self, provider_id: str) -> BaseProvider | None:
        return self.providers.get(provider_id)

    def by_tool(self, tool_id: str) -> BaseProvider | None:
        return self.providers_by_tool.get(tool_id)

    def all(self) -> list[BaseProvider]:
        return sorted(self.providers.values(), key=lambda item: item.tool_id)

    def status(self) -> list[dict[str, Any]]:
        entries = []
        for provider in self.all():
            payload = provider.status()
            payload["tool_name"] = provider.spec.name
            payload["capability"] = provider.spec.capability
            payload["claims"] = [claim.model_dump(mode="json") for claim in provider.spec.claims]
            payload["validation"] = self.validation.get(provider.tool_id, [])
            entries.append(payload)
        return entries

    def force_failure(self, tool_id: str, times: int = 1) -> bool:
        provider = self.by_tool(tool_id)
        if provider is None:
            return False
        provider.force_failure(times)
        return True

    def set_offline(self, tool_id: str, value: bool) -> bool:
        provider = self.by_tool(tool_id)
        if provider is None:
            return False
        provider.set_offline(value)
        return True

    def reset_demo(self) -> None:
        for provider in self.providers.values():
            provider.clear_failure()
            provider.set_offline(False)
