"""Tests for the RDF-backed ontology bridge of the app."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import Literal
from rdflib.namespace import RDF, RDFS

from agent_bazaar.kg.store import KgStore
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.ns import AB
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.ontology.validator import load_shapes
from app.integration.canonical import CURATED_CAPABILITIES, EXTERNAL_CONCEPTS, known_units
from app.integration.ontology_bridge import KnowledgeOntology, build_knowledge_ontology
from app.schemas import ConceptSpec, ToolSpec

TOOLS_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "tools.json"


def build_store() -> KgStore:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    return KgStore(graph=graph, shapes=load_shapes())


def weather_tool(
    capability: str = "weather-api",
    inputs: list[ConceptSpec] | None = None,
    outputs: list[ConceptSpec] | None = None,
) -> ToolSpec:
    return ToolSpec(
        id="open-meteo-forecast",
        name="Open-Meteo Forecast",
        provider_id="open-meteo",
        description="Hourly weather forecast",
        capability=capability,
        inputs=inputs
        if inputs is not None
        else [ConceptSpec(concept="Coordinates", name="coordinates", unit="degrees")],
        outputs=outputs
        if outputs is not None
        else [ConceptSpec(concept="Temperature", name="temperature", unit="C")],
    )


@pytest.fixture
def store() -> KgStore:
    return build_store()


@pytest.fixture
def ontology(store: KgStore) -> KnowledgeOntology:
    return build_knowledge_ontology(store)


def test_exists_for_a_knowledge_layer_concept(ontology: KnowledgeOntology) -> None:
    assert ontology.exists("Temperature") is True
    assert ontology.exists("LocationName") is True
    assert ontology.exists("Coordinates") is True
    assert ontology.exists("NoSuchConcept") is False


def test_exists_for_an_external_concept(ontology: KnowledgeOntology) -> None:
    assert ontology.exists("ResearchPaper") is True
    assert ontology.exists("AnswerFromDocument") is True
    assert ontology.exists("TabularAnswer") is True


def test_is_subtype_uses_the_rdf_closure(ontology: KnowledgeOntology) -> None:
    assert ontology.is_subtype("Temperature", "Concept") is True
    assert ontology.is_subtype("FeelsLikeTemperature", "Temperature") is True
    assert ontology.is_subtype("Coordinates", "Position") is True
    assert ontology.is_subtype("Temperature", "Humidity") is False
    assert ontology.is_subtype("ResearchPaper", "Entity") is True


def test_ancestors_are_canonical(ontology: KnowledgeOntology) -> None:
    assert ontology.ancestors("Temperature") == ["Concept"]
    assert ontology.ancestors("FeelsLikeTemperature")[:2] == ["Temperature", "Concept"]
    assert ontology.ancestors("ResearchPaper") == ["Entity"]
    assert ontology.ancestors("NoSuchConcept") == []


def test_check_capability_matches_derived_slugs(ontology: KnowledgeOntology) -> None:
    assert ontology.check_capability("weather-api", "GetWeatherForecast") is True
    assert ontology.check_capability("GetWeatherForecast", "GetWeatherForecast") is True
    assert ontology.check_capability("ConvertCurrency", "GetWeatherForecast") is False


def test_unit_dimension_maps_to_the_knowledge_layer_families(ontology: KnowledgeOntology) -> None:
    assert ontology.unit_dimension("C") == "TemperatureUnit"
    assert ontology.unit_dimension("degrees") == "AngleUnit"
    assert ontology.unit_dimension("USD") == "CurrencyUnit"
    assert ontology.unit_dimension(None) is None
    assert ontology.unit_dimension("Bananas") is None


def test_units_compatible_reports_a_conversion(ontology: KnowledgeOntology) -> None:
    assert ontology.units_compatible("C", "F") == (True, True)
    assert ontology.units_compatible("C", "C") == (True, False)
    assert ontology.units_compatible("C", "Percent") == (False, False)
    assert ontology.units_compatible("C", None) == (True, False)
    assert ontology.units_compatible("USD", "EUR") == (True, False)


def test_check_link_rejects_a_wrong_unit(ontology: KnowledgeOntology) -> None:
    check = ontology.check_link("Temperature", "Celsius", "Temperature", "Percent")

    assert check.valid is False
    assert check.concept_ok is True
    assert check.units_ok is False
    assert "Unit mismatch" in check.reason


def test_check_link_accepts_a_compatible_unit(ontology: KnowledgeOntology) -> None:
    check = ontology.check_link("Temperature", "Celsius", "Temperature", "Fahrenheit")

    assert check.valid is True
    assert check.concept_ok is True
    assert check.units_ok is True
    assert check.conversion_required is True
    assert "Compatible with conversion" in check.reason

    same = ontology.check_link("FeelsLikeTemperature", "Celsius", "Temperature", "Celsius")
    assert same.valid is True
    assert same.conversion_required is False


def test_check_link_rejects_a_wrong_concept(ontology: KnowledgeOntology) -> None:
    check = ontology.check_link("Temperature", "Celsius", "Humidity", "Celsius")

    assert check.valid is False
    assert check.concept_ok is False
    assert check.units_ok is True
    assert "Concept mismatch" in check.reason


def test_validate_tool_reports_unknown_concepts(ontology: KnowledgeOntology) -> None:
    tool = weather_tool(inputs=[ConceptSpec(concept="NoSuchConcept", name="thing")])

    violations = ontology.validate_tool(tool)

    assert any("input concept NoSuchConcept is unknown" in item for item in violations)


def test_validate_tool_reports_unknown_units(ontology: KnowledgeOntology) -> None:
    tool = weather_tool(outputs=[ConceptSpec(concept="Temperature", name="temperature", unit="Bananas")])

    violations = ontology.validate_tool(tool)

    assert any("output unit Bananas is unknown" in item for item in violations)


def test_validate_tool_reports_a_unit_family_mismatch(ontology: KnowledgeOntology) -> None:
    tool = weather_tool(outputs=[ConceptSpec(concept="Temperature", name="temperature", unit="Percent")])

    violations = ontology.validate_tool(tool)

    assert any("expected TemperatureUnit" in item for item in violations)


def test_validate_tool_reports_an_unknown_capability(ontology: KnowledgeOntology) -> None:
    tool = weather_tool(capability="mystery-capability")

    violations = ontology.validate_tool(tool)

    assert any("capability mystery-capability is not in the ontology" in item for item in violations)


def test_validate_tool_accepts_a_valid_tool(ontology: KnowledgeOntology) -> None:
    assert ontology.validate_tool(weather_tool()) == []


def test_validate_tool_accepts_external_concepts(ontology: KnowledgeOntology) -> None:
    tool = ToolSpec(
        id="arxiv-search",
        name="arXiv Research Search",
        provider_id="arxiv",
        description="Search recent research papers.",
        capability="SearchResearchPapers",
        inputs=[ConceptSpec(concept="ResearchTopic", name="query")],
        outputs=[ConceptSpec(concept="ResearchPaper", name="papers")],
    )

    assert ontology.validate_tool(tool) == []


def test_summary_counts_the_knowledge_layer_concepts(ontology: KnowledgeOntology, store: KgStore) -> None:
    summary = ontology.summary()

    assert summary["concepts"] == len(store.list_concepts())
    assert summary["concepts"] > 0
    assert summary["units"] == len(known_units())
    assert summary["capabilities"] == len(CURATED_CAPABILITIES)
    assert summary["external_concepts"] == len(EXTERNAL_CONCEPTS)
    assert summary["violations"] == []


def test_validate_ontology_reports_unknown_parents() -> None:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    graph.add((AB.Orphan, RDF.type, AB.Concept))
    graph.add((AB.Orphan, RDFS.label, Literal("Orphan")))
    graph.add((AB.Orphan, RDFS.subClassOf, AB.NoSuchParent))
    store = KgStore(graph=graph, shapes=load_shapes())
    ontology = build_knowledge_ontology(store)

    violations = ontology.validate_ontology()

    assert any("Orphan concept: Orphan has unknown parent NoSuchParent" in item for item in violations)


def test_payloads_use_the_canonical_names(ontology: KnowledgeOntology) -> None:
    concept = ontology.concept_payload("Coordinates")
    assert concept["concept"] == "Position"
    assert concept["parents"] == ["Concept"]

    unit = ontology.unit_payload("C")
    assert unit["unit"] == "Celsius"
    assert unit["dimension"] == "TemperatureUnit"

    spec = ConceptSpec(concept="Coordinates", unit="degrees")
    assert ontology.normalize_concept(spec) == "Position:Degree"


def test_input_and_output_names_are_canonical(ontology: KnowledgeOntology) -> None:
    tool = weather_tool()

    assert ontology.input_names(tool) == ["Position"]
    assert ontology.output_names(tool) == ["Temperature"]


def test_the_bridge_serves_the_app_ontology_view(ontology: KnowledgeOntology) -> None:
    assert "Temperature" in ontology.concepts
    assert "ResearchPaper" in ontology.concepts
    assert "Celsius" in ontology.units
    assert ontology.capabilities["GetWeatherForecast"]["outputs"] == ["Temperature"]


def test_the_seeded_app_tools_validate_against_the_bridge(ontology: KnowledgeOntology) -> None:
    raw = json.loads(TOOLS_PATH.read_text(encoding="utf-8"))

    for item in raw:
        tool = ToolSpec(
            id=item["id"],
            name=item["name"],
            provider_id=item["provider_id"],
            description=item["description"],
            capability=item["capability"],
            inputs=[ConceptSpec(**spec) for spec in item["inputs"]],
            outputs=[ConceptSpec(**spec) for spec in item["outputs"]],
        )
        assert ontology.validate_tool(tool) == [], item["id"]


def test_build_knowledge_ontology_loads_the_local_fallback(store: KgStore) -> None:
    ontology = build_knowledge_ontology(store)

    assert ontology.local is not None
    assert ontology.local.version == "0.1-local"
    assert ontology.exists("ResearchPaper") is True


def test_the_bridge_works_without_the_local_fallback(store: KgStore) -> None:
    ontology = KnowledgeOntology(store)

    assert ontology.exists("Temperature") is True
    assert ontology.exists("ResearchPaper") is True
    assert ontology.units_compatible("C", "F") == (True, True)
    assert ontology.local is None
