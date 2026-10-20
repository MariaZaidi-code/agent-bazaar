"""Integration tests for the free-first ranking policy in the application.

The policy semantics live in :mod:`app.agents.ranking_policy` and are owned by
the policy lead.  These tests cover the wiring: the settings surface, the
catalogue facts, the ranking the Client performs, the gates that keep a
non-executable tool out of the execution chain and the trace that makes the
decision explainable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_bazaar.kg.store import KgStore
from agent_bazaar.models import MappedField, ToolRecord
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.ontology.validator import load_shapes
from app.config import Settings
from app.integration.graph_adapter import RdfToolGraph
from app.schemas import BreakerStatus, Candidate, ClaimLabel, ConceptSpec, SubGoal, ToolSpec
from app.services import AppServices

TOOLS_FILE = Path(__file__).resolve().parents[1] / "app" / "data" / "tools.json"

EXPECTED_PROFILES = {
    "open-meteo-forecast": ("free", "keyless", "CC-BY-4.0"),
    "frankfurter-currency": ("free", "keyless", "CC0-1.0"),
    "nominatim-geocode": ("free", "keyless", "ODbL"),
    "restcountries-facts": ("free", "keyless", "MPL-2.0"),
    "nager-holidays": ("free", "keyless", "MIT"),
    "arxiv-search": ("free", "keyless", "CC0-1.0"),
    "university-sql": ("free", "keyless", "sample data"),
    "document-qa": ("free", "keyless", "user documents"),
    "mock-weather-fahrenheit": ("free", "keyless", "mock"),
}

SUBGOAL = SubGoal(
    id="sg-weather",
    capability="GetWeatherForecast",
    description="weather forecast for a place",
    intent="weather",
    slots={"location": "Lahore"},
)


def make_tool(
    tool_id: str,
    *,
    pricing_tier: str = "free",
    access_requirement: str = "keyless",
    licence: str = "MIT",
    doc_quality: float = 1.0,
    mapping_coverage: float = 1.0,
) -> ToolSpec:
    """Build a weather tool with a commercial profile."""
    return ToolSpec(
        id=tool_id,
        name=tool_id,
        provider_id=f"{tool_id}-provider",
        description="test tool",
        capability="GetWeatherForecast",
        inputs=[ConceptSpec(name="location", concept="LocationName")],
        outputs=[ConceptSpec(name="forecast", concept="Temperature", unit="C")],
        pricing_tier=pricing_tier,
        access_requirement=access_requirement,
        licence=licence,
        doc_quality=doc_quality,
        mapping_coverage=mapping_coverage,
        is_executable=pricing_tier == "free" and access_requirement == "keyless",
    )


def make_candidate(
    tool: ToolSpec,
    *,
    relevance: float = 1.0,
    trust: float = 0.8,
    claim_label: ClaimLabel = ClaimLabel.supported,
    demoted: bool = False,
    breaker_state: BreakerStatus = BreakerStatus.closed,
) -> Candidate:
    """Build a candidate with the facts the policy weighs."""
    return Candidate(
        tool=tool,
        relevance=relevance,
        trust=trust,
        claim_label=claim_label,
        demoted=demoted,
        breaker_state=breaker_state,
    )


def catalogue() -> list[dict]:
    return json.loads(TOOLS_FILE.read_text(encoding="utf-8"))


def test_settings_expose_the_free_first_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings()

    assert settings.pricing_policy == "prefer_free"
    assert settings.tier_order == ["free", "freemium", "paid", "unknown"]
    assert settings.doc_quality_weight == 0.4
    assert settings.mapping_coverage_weight == 0.3
    assert settings.chain_fit_weight == 0.3
    assert settings.min_rating_count == 3
    assert settings.rating_floor == 0.5
    assert settings.require_known_licence is False

    monkeypatch.setenv("AB_PRICING_POLICY", "ignore")
    monkeypatch.setenv("AB_REQUIRE_KNOWN_LICENCE", "true")
    monkeypatch.setenv("AB_MIN_RATING_COUNT", "5")
    overridden = Settings()

    assert overridden.pricing_policy == "ignore"
    assert overridden.require_known_licence is True
    assert overridden.min_rating_count == 5


def test_catalogue_tools_stay_free_keyless_and_executable() -> None:
    entries = {entry["id"]: entry for entry in catalogue()}

    assert set(EXPECTED_PROFILES) == set(entries)
    for tool_id, (tier, access, licence) in EXPECTED_PROFILES.items():
        entry = entries[tool_id]
        assert (entry["pricing_tier"], entry["access_requirement"]) == (tier, access)
        assert entry["licence"] == licence
        assert entry["is_executable"] is True


def test_free_tool_outranks_a_paid_tool_with_a_better_score(services: AppServices) -> None:
    free = make_candidate(make_tool("free-tool"), relevance=0.4, trust=0.4)
    paid = make_candidate(
        make_tool("paid-tool", pricing_tier="paid", access_requirement="paid_key"),
        relevance=1.0,
        trust=0.9,
    )

    ranked = services.client.rank_candidates([paid, free], SUBGOAL, [SUBGOAL])

    assert [item.tool.id for item in ranked] == ["free-tool", "paid-tool"]
    assert ranked[0].score < ranked[1].score
    assert ranked[0].reasons
    assert any("not executable" in reason for reason in ranked[1].reasons)


def test_key_required_tool_is_not_executable_and_is_not_selected(
    services: AppServices,
) -> None:
    keyed = make_candidate(
        make_tool("keyed-tool", access_requirement="api_key"),
        relevance=1.0,
        trust=0.9,
    )
    keyless = make_candidate(make_tool("keyless-tool"), relevance=0.4, trust=0.4)

    ranked = services.client.rank_candidates([keyed, keyless], SUBGOAL, [SUBGOAL])

    assert not services.client._executable(keyed.tool, services.client.ranking_policy())
    assert services.client._executable(keyless.tool, services.client.ranking_policy())
    assert any("not executable" in reason for reason in keyed.reasons)
    assert not any("not executable" in reason for reason in keyless.reasons)
    assert [item.tool.id for item in ranked] == ["keyed-tool", "keyless-tool"]


async def test_key_required_tool_is_never_executed(services: AppServices) -> None:
    services.graph.add(
        make_tool("keyed-weather", access_requirement="api_key")
    )
    services.retriever.rebuild()

    result = await services.client.run("What is the temperature in Lahore tomorrow?")

    assert result.status == "completed"
    assert result.plan is not None
    weather_step = next(
        step for step in result.plan.steps if step.capability == "GetWeatherForecast"
    )
    assert weather_step.tool_id == "open-meteo-forecast"
    group = next(
        group
        for group in result.candidate_lists
        if group.capability == "GetWeatherForecast"
    )
    keyed = next(item for item in group.candidates if item.tool.id == "keyed-weather")
    assert any("not executable" in reason for reason in keyed.reasons)


async def test_paid_tool_is_kept_in_the_shortlist_but_never_executed(
    services: AppServices,
) -> None:
    services.graph.add(
        make_tool("paid-weather", pricing_tier="paid", access_requirement="paid_key")
    )
    services.retriever.rebuild()

    result = await services.client.run("What is the temperature in Lahore tomorrow?")

    assert result.status == "completed"
    assert result.plan is not None
    weather_step = next(
        step for step in result.plan.steps if step.capability == "GetWeatherForecast"
    )
    assert weather_step.tool_id == "open-meteo-forecast"
    group = next(
        group
        for group in result.candidate_lists
        if group.capability == "GetWeatherForecast"
    )
    paid = next(item for item in group.candidates if item.tool.id == "paid-weather")
    assert any("not executable" in reason for reason in paid.reasons)
    assert paid.tool.pricing_tier == "paid"


def test_demoted_provider_and_open_breaker_score_zero(services: AppServices) -> None:
    demoted = make_candidate(
        make_tool("demoted-tool"), relevance=1.0, trust=0.9, demoted=True
    )
    blocked = make_candidate(
        make_tool("blocked-tool"),
        relevance=1.0,
        trust=0.9,
        breaker_state=BreakerStatus.open,
    )

    ranked = services.client.rank_candidates([demoted, blocked], SUBGOAL, [SUBGOAL])

    assert [item.score for item in ranked] == [0.0, 0.0]
    assert all(not item.eligible for item in ranked)
    assert any("demoted by the trust registry" in reason for reason in demoted.reasons)
    assert any("circuit breaker open" in reason for reason in blocked.reasons)


def test_contradicted_claim_penalty_applies(services: AppServices) -> None:
    clean = make_candidate(make_tool("clean-tool"), relevance=1.0, trust=0.8)
    contradicted = make_candidate(
        make_tool("contradicted-tool"),
        relevance=1.0,
        trust=0.8,
        claim_label=ClaimLabel.contradicted,
    )

    ranked = services.client.rank_candidates([clean, contradicted], SUBGOAL, [SUBGOAL])
    scores = {item.tool.id: item.score for item in ranked}

    assert scores["contradicted-tool"] == pytest.approx(
        scores["clean-tool"] * services.settings.contradicted_penalty,
        rel=1e-6,
    )
    assert any(
        "contradicted claim penalty applied" in reason
        for reason in contradicted.reasons
    )


async def test_policy_reasons_are_recorded_in_the_trace(services: AppServices) -> None:
    result = await services.client.run("What is the temperature in Lahore tomorrow?")

    shortlist = next(
        event for event in result.trace if event.event_type == "graphrag_shortlist"
    )
    assert shortlist.data["policy"]["pricing_policy"] == "prefer_free"
    assert shortlist.data["free_first_compliance"] is True
    assert shortlist.data["policy"]["tier_order"] == [
        "free",
        "freemium",
        "paid",
        "unknown",
    ]
    entry = None
    for event in result.trace:
        if event.event_type != "graphrag_shortlist":
            continue
        entry = next(
            (
                item
                for item in event.data["ranked"]
                if item["tool_id"] == "open-meteo-forecast"
            ),
            None,
        )
        if entry is not None:
            break
    assert entry is not None
    assert entry["pricing_tier"] == "free"
    assert entry["executable"] is True
    assert "pricing tier free" in entry["reasons"]
    assert "no api key required" in entry["reasons"]
    assert any(reason.startswith("doc quality") for reason in entry["reasons"])


def build_store() -> KgStore:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    return KgStore(graph=graph, shapes=load_shapes())


def test_graph_adapter_maps_the_offering_facts() -> None:
    store = build_store()
    store.write_tool(
        ToolRecord(
            tool_id="paid-weather",
            name="Paid Weather",
            description="Paid forecast",
            provider_id="paid-provider",
            capabilities=["weather-forecast"],
            inputs=[
                MappedField(
                    field_path="input.get:/v1/paid.latitude",
                    name="latitude",
                    concept="Latitude",
                    direction="input",
                    unit="Degree",
                    confidence=0.9,
                    reason="name matches",
                    status="mapped",
                )
            ],
            outputs=[
                MappedField(
                    field_path="output.get:/v1/paid.temperature",
                    name="temperature",
                    concept="Temperature",
                    direction="output",
                    unit="Celsius",
                    confidence=0.8,
                    reason="name matches",
                    status="mapped",
                )
            ],
            pricing_tier="free",
            access_requirement="keyless",
            licence="MIT",
            doc_quality=0.7,
        )
    )
    store.update_tool_quality("paid-weather", rating_value=0.8, rating_count=4)

    tool = RdfToolGraph(store).get("paid-weather")

    assert tool is not None
    assert tool.pricing_tier == "free"
    assert tool.access_requirement == "keyless"
    assert tool.rating_value == 0.8
    assert tool.rating_count == 4
    assert tool.doc_quality == 0.7
    assert tool.mapping_coverage > 0.0
    assert tool.licence == "MIT"
    assert tool.is_executable is True
