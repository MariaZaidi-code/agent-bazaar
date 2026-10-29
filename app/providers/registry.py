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
from app.providers.geocoding import GeocodingProvider
from app.providers.holidays import HolidaysProvider
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
            "university-db": UniversitySQLProvider,
            "mock-weather-fahrenheit": MockWeatherFahrenheitProvider,
            "hackernews": HackerNewsProvider,
            "coingecko": CoinGeckoProvider,
            "tvmaze": TVMazeProvider,
            "open-library": OpenLibraryProvider,
            "google-books": GoogleBooksProvider,
            "mymemory": MyMemoryProvider,
            "worldtimeapi": WorldTimeProvider,
            "sunrise-sunset": SunriseSunsetProvider,
            "themealdb": TheMealDBProvider,
            "espn": EspnScoresProvider,
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
        self.validation[provider.tool_id] = (
            ontology.validate_tool(provider.spec) if ontology is not None else []
        )

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
            payload["claims"] = [
                claim.model_dump(mode="json") for claim in provider.spec.claims
            ]
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
