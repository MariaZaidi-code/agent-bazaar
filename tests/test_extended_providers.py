from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.integration.canonical import CURATED_CAPABILITIES
from app.providers.mirror import MirrorProvider
from app.services import AppServices

NEW_PROVIDERS = {
    "hackernews-search": "hackernews",
    "coingecko-price": "coingecko",
    "tvmaze-search": "tvmaze",
    "open-library-search": "open-library",
    "google-books-search": "google-books",
    "mymemory-translate": "mymemory",
    "worldtime-current": "worldtimeapi",
    "sunrise-sunset-times": "sunrise-sunset",
    "themealdb-recipes": "themealdb",
    "espn-scores": "espn",
}

OFFLINE_PARAMS = {
    "hackernews-search": {"news_query": "artificial intelligence"},
    "coingecko-price": {"asset": "bitcoin", "currency": "USD"},
    "tvmaze-search": {"show_query": "Breaking Bad"},
    "open-library-search": {"book_query": "machine learning"},
    "google-books-search": {"book_query": "machine learning"},
    "mymemory-translate": {
        "text": "good morning",
        "source_language": "en",
        "target_language": "ur",
    },
    "worldtime-current": {"timezone": "Asia/Tokyo"},
    "sunrise-sunset-times": {
        "coordinates": {"latitude": 31.55, "longitude": 74.34},
        "date": "2026-10-30",
    },
    "themealdb-recipes": {"recipe_query": "biryani"},
    "espn-scores": {"league": "NBA"},
}

PLANNER_CASES = [
    ("Latest news about artificial intelligence", "SearchNews", {"news_query": "artificial intelligence"}),
    ("What is the price of bitcoin in USD?", "GetCryptoPrice", {"asset": "bitcoin", "currency": "USD"}),
    ("Find TV shows like Breaking Bad", "SearchTVShows", {"show_query": "Breaking Bad"}),
    ("Recommend books about machine learning", "SearchBooks", {"book_query": "machine learning"}),
    (
        "Translate good morning from English to Urdu",
        "TranslateText",
        {"text": "good morning", "source_language": "en", "target_language": "ur"},
    ),
    ("What time is it in Tokyo?", "GetCurrentTime", {"timezone": "Asia/Tokyo"}),
    ("Recipe for chicken biryani", "SearchRecipes", {"recipe_query": "chicken biryani"}),
    ("NBA scores", "GetSportsScores", {"league": "NBA"}),
]

CLIENT_CASES = [
    ("Latest news about artificial intelligence", "Latest news"),
    ("What is the bitcoin price in USD?", "bitcoin"),
    ("Find TV shows like Breaking Bad", "TV shows found"),
    ("Recommend books about machine learning", "Books found"),
    ("Translate good morning to Urdu", "Translation (en to ur)"),
    ("What time is it in Tokyo?", "Current time in Asia/Tokyo"),
    ("Sunrise in Lahore tomorrow", "Sunrise"),
    ("Recipe for chicken biryani", "Recipes found"),
    ("NBA scores", "Latest scores"),
]


def test_provider_registry_reaches_twenty_five(services: AppServices) -> None:
    providers = services.providers.all()
    assert len(providers) >= 25
    assert {provider.tool_id for provider in providers} >= set(NEW_PROVIDERS)


def test_new_providers_are_primary_and_not_backup_eligible(services: AppServices) -> None:
    entries = {tool.id: tool for tool in services.graph.all()}
    for tool_id, provider_id in NEW_PROVIDERS.items():
        tool = entries[tool_id]
        assert tool.provider_id == provider_id
        assert "backup-eligible" not in tool.tags
        assert not isinstance(services.providers.by_tool(tool_id), MirrorProvider)


def test_extended_capabilities_are_curated(services: AppServices) -> None:
    expected = {
        "SearchNews",
        "GetCryptoPrice",
        "SearchTVShows",
        "SearchBooks",
        "TranslateText",
        "GetCurrentTime",
        "GetSunTimes",
        "SearchRecipes",
        "GetSportsScores",
    }
    assert expected <= set(CURATED_CAPABILITIES)
    assert expected <= set(services.ontology.capabilities)
    assert services.ontology.summary()["capabilities"] == len(CURATED_CAPABILITIES)
    assert len(CURATED_CAPABILITIES) >= 10


@pytest.mark.parametrize("tool_id", sorted(OFFLINE_PARAMS))
async def test_new_provider_offline_payloads_are_schema_valid(
    services: AppServices, tool_id: str
) -> None:
    provider = services.providers.by_tool(tool_id)
    assert provider is not None

    response = await provider.call(OFFLINE_PARAMS[tool_id])

    assert response.status == "success", response.error
    assert response.schema_valid, response.schema_errors
    assert response.source == "fixture"


@pytest.mark.parametrize(("task", "capability", "slots"), PLANNER_CASES)
async def test_planner_detects_extended_intents(
    services: AppServices, task: str, capability: str, slots: dict[str, object]
) -> None:
    goals, _ = await services.planner.decompose(task)

    goal = next(item for item in goals if item.capability == capability)
    for key, value in slots.items():
        assert goal.slots[key] == value


async def test_planner_links_sunrise_to_geocoding(services: AppServices) -> None:
    goals, _ = await services.planner.decompose("Sunrise in Lahore tomorrow")

    assert [goal.capability for goal in goals] == ["GeocodeLocation", "GetSunTimes"]
    assert goals[1].depends_on == [goals[0].id]
    assert goals[1].slots["date"] == (date.today() + timedelta(days=1)).isoformat()
    assert "coordinates" not in goals[1].slots


async def test_extended_client_tasks_complete_offline(services: AppServices) -> None:
    for task, fragment in CLIENT_CASES:
        result = await services.client.run(task)

        assert result.status == "completed", (task, result.error)
        assert fragment in result.answer, (task, result.answer)
        assert result.plan is not None
        assert all(step.status == "completed" for step in result.plan.steps), task
