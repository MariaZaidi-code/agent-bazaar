from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import AppServices

TOOLS_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "tools.json"

SAMPLE_VALUES = {
    "LocationName": "Lahore",
    "Coordinates": {"latitude": 31.55, "longitude": 74.34},
    "MoneyAmount": 100,
    "CurrencyCode": "USD",
    "CountryName": "Japan",
    "CountryCode": "PK",
    "Number": 2026,
    "ResearchTopic": "machine learning",
    "NaturalLanguageQuery": "How many students are enrolled?",
    "NewsTopic": "technology",
    "CryptoAsset": "bitcoin",
    "ShowQuery": "Breaking Bad",
    "BookQuery": "machine learning",
    "LanguageCode": "en",
    "TimezoneName": "Asia/Tokyo",
    "RecipeQuery": "biryani",
    "SportsLeague": "NBA",
    "Text": "hello",
}

TEXT_VALUES = {
    "text": "hello",
    "barcode": "012345678901",
    "url": "https://example.com",
    "email": "person@example.com",
    "password": "S3cure!Passphrase",
    "data": "name,value\nalpha,1\nbeta,2",
    "query": "machine learning",
    "title": "Ada Lovelace",
    "word": "bazaar",
    "place": "Paris",
    "symbol": "AAPL",
}

SKIP = {"document-qa"}


def _catalogue() -> list[dict]:
    return json.loads(TOOLS_PATH.read_text(encoding="utf-8"))


def _params(entry: dict) -> dict:
    params: dict = {}
    for spec in entry.get("inputs", []):
        if not spec.get("required"):
            continue
        concept = spec.get("concept", "Text")
        name = spec.get("name", "")
        if concept == "Text" and name in TEXT_VALUES:
            params[name] = TEXT_VALUES[name]
        else:
            params[name] = SAMPLE_VALUES.get(concept, "sample")
    return params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry",
    [entry for entry in _catalogue() if entry["id"] not in SKIP and entry.get("is_executable")],
    ids=[entry["id"] for entry in _catalogue() if entry["id"] not in SKIP and entry.get("is_executable")],
)
async def test_every_catalogue_tool_has_a_valid_offline_fixture(services: AppServices, entry: dict) -> None:
    provider = services.providers.by_tool(entry["id"])
    assert provider is not None, entry["id"]

    response = await provider.call(_params(entry))

    assert response.status == "success", (entry["id"], response.error)
    assert response.schema_valid is True, (entry["id"], response.schema_errors)


def test_every_catalogue_tool_declares_ownership_and_docs() -> None:
    for entry in _catalogue():
        assert entry["provider_id"], entry["id"]
        assert entry["docs_url"].startswith("http"), entry["id"]
        assert entry["outputs"], entry["id"]
