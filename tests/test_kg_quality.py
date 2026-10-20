"""Tests for the tool quality profile: offerings, executability and ratings."""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Literal
from rdflib.namespace import RDF, XSD

from agent_bazaar.ingestion.models import NormalizedSpec
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.kg import GraphValidationError, KgStore
from agent_bazaar.kg.quality import mapping_coverage
from agent_bazaar.messages.schema import MapResult
from agent_bazaar.models import MappedField, ToolRecord
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.ns import AB, tool_iri
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.ontology.validator import load_shapes
from agent_bazaar.pipeline import onboard_spec

FIXTURES = Path(__file__).parent / "fixtures"


def build_store() -> KgStore:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    return KgStore(graph=graph, shapes=load_shapes())


def tool_record(
    tool_id: str = "free-tool",
    pricing_tier: str = "free",
    access_requirement: str = "keyless",
    licence: str = "MIT",
) -> ToolRecord:
    return ToolRecord(
        tool_id=tool_id,
        name=tool_id.replace("-", " ").title(),
        provider_id="weather-provider",
        provider_name="Weather Provider",
        base_url="https://api.example.com",
        capabilities=["weather-forecast"],
        inputs=[
            MappedField(
                field_path="input.get:/weather.city",
                name="city",
                concept="City",
                direction="input",
                confidence=0.9,
                reason="city parameter",
            )
        ],
        outputs=[
            MappedField(
                field_path="output.get:/weather.temperature",
                name="temperature",
                concept="Temperature",
                direction="output",
                unit="Celsius",
                confidence=0.7,
                reason="temperature response field",
            )
        ],
        trust=0.8,
        source="openapi",
        version="v1",
        pricing_tier=pricing_tier,
        access_requirement=access_requirement,
        licence=licence,
        doc_quality=0.75,
        doc_sub_scores={"description": 0.5, "examples": 1.0},
        tier_evidence=["free tier"],
        access_evidence=["no security scheme declared"],
    )


class StubMapper:
    """A mapper that only builds the record; the pipeline carries the facts."""

    def map_spec(self, spec: NormalizedSpec, tool_id: str | None = None) -> MapResult:
        return MapResult(tool_id=tool_id or spec.tool_id)

    def listing_to_tool_record(
        self,
        spec: NormalizedSpec,
        result: MapResult,
        capability_hints: list[str] | None = None,
        provider_id: str = "",
        provider_name: str = "",
        trust: float | None = None,
    ) -> ToolRecord:
        return ToolRecord(
            tool_id=spec.tool_id,
            name=spec.title or spec.tool_id,
            description=spec.description,
            provider_id=provider_id or "example",
            provider_name=provider_name or "Example",
            capabilities=list(capability_hints or ["weather-forecast"]),
            outputs=[
                MappedField(
                    field_path="output.get:/v1/forecast.body.temperature_2m",
                    name="temperature_2m",
                    concept="Temperature",
                    direction="output",
                    unit="Celsius",
                    confidence=0.8,
                    reason="temperature response field",
                )
            ],
            trust=trust,
            source=spec.source,
            version=spec.version,
        )


def test_write_tool_creates_offering_and_profile_round_trips() -> None:
    store = build_store()
    store.write_tool(tool_record())

    tool = tool_iri("free-tool")
    offering = AB["offering-free-tool"]
    assert (tool, AB.hasOffering, offering) in store.graph
    assert (offering, RDF.type, AB.Offering) in store.graph
    assert (offering, AB.pricingTier, Literal("free")) in store.graph
    assert (offering, AB.accessRequirement, Literal("keyless")) in store.graph

    profile = store.tool_quality_profile("free-tool")
    assert profile.pricing_tier == "free"
    assert profile.access_requirement == "keyless"
    assert profile.licence == "MIT"
    assert profile.doc_quality == 0.75
    assert profile.doc_sub_scores == {"description": 0.5, "examples": 1.0}
    assert profile.tier_evidence == ["free tier"]
    assert profile.access_evidence == ["no security scheme declared"]
    assert profile.rating_value is None
    assert profile.rating_count == 0
    assert profile.is_executable is True
    assert store.validate().conforms


def test_record_without_listing_facts_keeps_no_offering() -> None:
    store = build_store()
    record = tool_record()
    record.pricing_tier = "unknown"
    record.access_requirement = "unknown"
    store.write_tool(record)

    assert list(store.graph.objects(tool_iri("free-tool"), AB.hasOffering)) == []
    profile = store.tool_quality_profile("free-tool")
    assert profile.pricing_tier == "unknown"
    assert profile.access_requirement == "unknown"
    assert profile.is_executable is False


def test_executable_tools_lists_only_free_keyless_tools() -> None:
    store = build_store()
    store.write_tool(tool_record("free-tool"))
    store.write_tool(
        tool_record("paid-tool", pricing_tier="paid", access_requirement="paid_key", licence="Commercial")
    )
    store.write_tool(tool_record("free-without-licence", licence=""))

    assert [tool.tool_id for tool in store.executable_tools()] == [
        "free-tool",
        "free-without-licence",
    ]
    assert [
        tool.tool_id for tool in store.executable_tools(require_known_licence=True)
    ] == ["free-tool"]

    paid = store.tools_by_pricing_tier("paid")
    assert [tool.tool_id for tool in paid] == ["paid-tool"]
    assert paid[0].is_executable is False

    assert [tool.tool_id for tool in store.tools_by_access("paid_key")] == ["paid-tool"]
    assert [tool.tool_id for tool in store.tools_by_access("keyless")] == [
        "free-tool",
        "free-without-licence",
    ]
    assert store.tools_by_pricing_tier("free")[0].is_executable is True


def test_update_tool_quality_writes_rating_and_rejects_invalid_offering() -> None:
    store = build_store()
    store.write_tool(tool_record())

    profile = store.update_tool_quality(
        "free-tool",
        rating_value=0.9,
        rating_count=5,
        rating_source="developers",
    )
    assert profile.rating_value == 0.9
    assert profile.rating_count == 5
    assert profile.rating_confidence == pytest.approx(5 / 7, abs=1e-4)
    offering = AB["offering-free-tool"]
    assert (offering, AB.ratingValue, Literal("0.9", datatype=XSD.decimal)) in store.graph
    assert (offering, AB.ratingCount, Literal(5, datatype=XSD.integer)) in store.graph
    assert (offering, AB.ratingSource, Literal("developers")) in store.graph

    with pytest.raises(GraphValidationError):
        store.update_tool_quality("free-tool", pricing_tier="gold")
    assert store.tool_quality_profile("free-tool").pricing_tier == "free"
    assert store.validate().conforms


def test_write_tool_rejects_an_invalid_offering() -> None:
    store = build_store()
    before = len(store.graph)

    with pytest.raises(GraphValidationError):
        store.write_tool(tool_record("gold-tool", pricing_tier="gold"))
    assert len(store.graph) == before
    assert list(store.graph.objects(tool_iri("gold-tool"), AB.hasOffering)) == []


def test_candidate_facts_returns_profiles_for_requested_tools() -> None:
    store = build_store()
    store.write_tool(tool_record("free-tool"))
    store.write_tool(
        tool_record("paid-tool", pricing_tier="paid", access_requirement="paid_key", licence="Commercial")
    )

    facts = store.candidate_facts(["free-tool", "paid-tool"])
    assert set(facts) == {"free-tool", "paid-tool"}
    assert facts["free-tool"].pricing_tier == "free"
    assert facts["free-tool"].is_executable is True
    assert facts["paid-tool"].pricing_tier == "paid"
    assert facts["paid-tool"].access_requirement == "paid_key"
    assert facts["paid-tool"].is_executable is False


def test_mapping_coverage_is_computed_from_the_mapping_nodes() -> None:
    store = build_store()
    store.write_tool(tool_record())

    assert mapping_coverage(store.graph, "free-tool") == pytest.approx(0.9, abs=1e-4)
    assert store.tool_quality_profile("free-tool").mapping_coverage == pytest.approx(0.9, abs=1e-4)

    store.update_mapping(
        "free-tool",
        "output.get:/weather.humidity",
        "City",
        provenance={"status": "unmapped", "who": "tester"},
    )
    assert mapping_coverage(store.graph, "free-tool") == pytest.approx(0.5111, abs=1e-4)
    assert store.tool_quality_profile("free-tool").mapping_coverage == pytest.approx(0.5111, abs=1e-4)


def test_ingestion_captures_the_listing_metadata() -> None:
    spec = IngestionUtility().ingest(FIXTURES / "sample_openapi.json")

    listing = spec.metadata["listing"]
    assert listing["tool_id"] == "sample-openapi"
    assert listing["access_requirement"] == "keyless"
    assert listing["pricing_tier"] == "unknown"
    assert listing["doc_quality"] >= 0.0
    assert listing["access_evidence"]


def test_onboard_spec_carries_the_listing_facts_into_the_graph() -> None:
    store = build_store()
    spec = IngestionUtility().ingest(FIXTURES / "sample_openapi.json")

    outcome = onboard_spec(spec, StubMapper(), store, tool_id="sample-api")
    assert outcome.written, outcome.error
    assert outcome.record.access_requirement == "keyless"
    assert outcome.record.pricing_tier == "unknown"

    profile = store.tool_quality_profile("sample-api")
    assert profile.access_requirement == "keyless"
    assert profile.pricing_tier == "unknown"
    assert (AB["offering-sample-api"], AB.accessRequirement, Literal("keyless")) in store.graph
