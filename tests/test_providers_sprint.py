from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.integration.canonical import CURATED_CAPABILITIES
from app.providers.base import BaseProvider
from app.services import AppServices

TOOLS_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "tools.json"

SPRINT_PROVIDERS = {
    "wikidata-search": ("wikidata", {"query": "Ada Lovelace"}),
    "wikivoyage-guide": ("wikivoyage", {"place": "Paris"}),
    "yahoo-finance-quote": ("yahoo-finance", {"symbol": "AAPL"}),
    "rss-feed": ("rss", {}),
    "dbpedia-summary": ("dbpedia", {"title": "Ada Lovelace"}),
    "iss-location": ("iss-location", {}),
    "open-meteo-air-quality": ("open-meteo-air", {"latitude": 31.5, "longitude": 74.3}),
    "open-meteo-marine": ("open-meteo-marine", {"latitude": 25.0, "longitude": 55.0}),
    "email-validate": ("email-validate", {"email": "person@example.com"}),
    "password-tools": ("password-tools", {"password": "CorrectHorseBatteryStaple1!"}),
    "uuid-generate": ("uuid", {"count": 2}),
    "data-transform": (
        "data-transform",
        {"data": "name,value\nalpha,1\nbeta,2", "format": "csv"},
    ),
    "ipify-ip": ("ipify", {}),
    "zenquotes-random": ("zenquotes", {}),
    "launch-library-upcoming": ("launch-library", {"limit": 2}),
    "worldbank-indicator": ("worldbank", {"country": "PAK"}),
    "dictionary-define": ("dictionary", {"word": "bazaar"}),
    "coincap-asset": ("coincap", {"asset": "bitcoin"}),
}

MISSING_PARAM_CASES = [
    ("wikidata", {"query": ""}),
    ("wikivoyage", {"place": ""}),
    ("yahoo-finance", {"symbol": ""}),
    ("dbpedia", {"title": ""}),
    ("open-meteo-air", {}),
    ("open-meteo-marine", {}),
    ("email-validate", {"email": ""}),
    ("password-tools", {"password": ""}),
    ("data-transform", {}),
    ("worldbank", {"country": ""}),
    ("dictionary", {"word": ""}),
    ("coincap", {"asset": ""}),
]

NEW_CAPABILITIES = {
    "SearchWikidata",
    "GetTravelGuide",
    "GetStockQuote",
    "GetRSSFeed",
    "GetDBpediaSummary",
    "GetISSPosition",
    "GetAirQualityForecast",
    "GetMarineForecast",
    "ValidateEmail",
    "CheckPasswordStrength",
    "GenerateUUID",
    "TransformData",
    "GetPublicIP",
    "GetQuote",
    "GetSpaceLaunches",
    "GetCountryIndicator",
    "GetWordDefinition",
}


def _catalogue() -> list[dict]:
    return json.loads(TOOLS_PATH.read_text(encoding="utf-8"))


def test_catalogue_reaches_sixty_free_keyless_executable_tools() -> None:
    entries = [e for e in _catalogue() if e.get("is_executable")]

    assert len(entries) >= 60
    for entry in entries:
        assert entry["pricing_tier"] == "free", entry["id"]
        assert entry["access_requirement"] == "keyless", entry["id"]
        assert entry["is_executable"] is True, entry["id"]


def test_new_providers_are_registered(services: AppServices) -> None:
    for tool_id, (provider_id, _) in SPRINT_PROVIDERS.items():
        provider = services.providers.by_tool(tool_id)
        assert provider is not None, tool_id
        assert provider.provider_id == provider_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_id", "params"),
    [(tool_id, params) for tool_id, (_, params) in SPRINT_PROVIDERS.items()],
    ids=list(SPRINT_PROVIDERS),
)
async def test_new_providers_return_valid_offline_payloads(services: AppServices, tool_id: str, params: dict) -> None:
    provider = services.providers.by_tool(tool_id)
    assert provider is not None
    response = await provider.call(params)

    assert response.status == "success", response.error
    assert response.source == "fixture"
    assert response.schema_valid is True, response.schema_errors


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider_id", "params"), MISSING_PARAM_CASES, ids=[c[0] for c in MISSING_PARAM_CASES])
async def test_new_providers_reject_missing_required_parameters(
    services: AppServices, provider_id: str, params: dict
) -> None:
    provider = services.providers.get(provider_id)
    assert provider is not None
    with pytest.raises(ValueError):
        await provider.execute(params)


@pytest.mark.asyncio
async def test_local_utility_providers_are_deterministic(services: AppServices) -> None:
    email = services.providers.get("email-validate")
    uuid_provider = services.providers.get("uuid")
    transform = services.providers.get("data-transform")
    assert email is not None and uuid_provider is not None and transform is not None

    disposable = await email.execute({"email": "someone@mailinator.com"})
    assert disposable["validation"]["valid"] is False
    assert disposable["validation"]["disposable"] is True

    generated = await uuid_provider.execute({"count": 3})
    assert len(generated["uuids"]) == 3
    assert all(len(value) == 36 for value in generated["uuids"])

    table = await transform.execute({"data": "a,b\n1,2\n3,4", "format": "csv"})
    assert table["table"]["row_count"] == 2
    assert table["table"]["columns"] == ["a", "b"]


def test_all_provider_tools_validate_against_the_ontology(services: AppServices) -> None:
    violations = {
        tool.id: issues for tool in services.graph.all() for issues in services.ontology.validate_tool(tool) if issues
    }

    assert violations == {}


def test_new_capabilities_are_curated(services: AppServices) -> None:
    assert NEW_CAPABILITIES <= set(services.ontology.capabilities)
    assert NEW_CAPABILITIES <= set(CURATED_CAPABILITIES)


def test_provider_base_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseProvider(None, None, None)  # type: ignore[arg-type]
