"""Tests for subsumption-aware knowledge graph queries."""

from __future__ import annotations

import pytest
from rdflib import Literal
from rdflib.namespace import RDFS

from agent_bazaar.kg import KgStore
from agent_bazaar.models import MappedField, ToolRecord
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.ns import AB, tool_iri
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.ontology.validator import load_shapes

CITY_PATH = "input.get:/weather.city"
TEMPERATURE_PATH = "output.get:/weather.temperature"


def build_store() -> KgStore:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    return KgStore(graph=graph, shapes=load_shapes())


def tool_record(tool_id: str, output_concept: str, unit: str = "Celsius") -> ToolRecord:
    return ToolRecord(
        tool_id=tool_id,
        name=tool_id.replace("-", " ").title(),
        provider_id="weather-provider",
        provider_name="Weather Provider",
        capabilities=["weather-forecast"],
        inputs=[
            MappedField(
                field_path=CITY_PATH,
                name="city",
                concept="City",
                direction="input",
                confidence=0.9,
                reason="city parameter",
            )
        ],
        outputs=[
            MappedField(
                field_path=f"output.get:/weather.{tool_id}",
                name="temperature",
                concept=output_concept,
                direction="output",
                unit=unit,
                confidence=0.85,
                reason="temperature response field",
            )
        ],
        trust=0.9,
        source="openapi",
        version="v1",
    )


def _tool_output_path(tool_id: str) -> str:
    return f"output.get:/weather.{tool_id}"


@pytest.fixture()
def store() -> KgStore:
    store = build_store()
    store.write_tool(tool_record("tool-a", "Temperature"))
    store.write_tool(tool_record("tool-b", "FeelsLikeTemperature"))
    return store


def test_tools_by_capability_matches_local_name_and_label(store: KgStore) -> None:
    assert [tool.tool_id for tool in store.tools_by_capability("weather-forecast")] == ["tool-a", "tool-b"]
    store.graph.add((AB["capability-weather-forecast"], RDFS.label, Literal("Weather Forecast")))
    assert [tool.tool_id for tool in store.tools_by_capability("Weather Forecast")] == ["tool-a", "tool-b"]


def test_tools_by_io_uses_subsumption(store: KgStore) -> None:
    assert [tool.tool_id for tool in store.tools_by_io("City", "Temperature")] == ["tool-a", "tool-b"]
    assert [tool.tool_id for tool in store.tools_by_io("City", "FeelsLikeTemperature")] == ["tool-b"]


def test_compatible_substitutes(store: KgStore) -> None:
    substitutes = store.compatible_substitutes("tool-a")
    assert [tool.tool_id for tool in substitutes] == ["tool-b"]
    assert "tool-a" not in [tool.tool_id for tool in substitutes]
    assert (AB.FeelsLikeTemperature, RDFS.subClassOf, AB.Temperature) in store.graph


def test_concept_lookup(store: KgStore) -> None:
    concept = store.get_concept(str(AB.Temperature))
    assert concept is not None
    assert concept.data_type == "float"
    assert concept.unit_family == "TemperatureUnit"
    assert concept.unit_bearing is True
    assert store.get_concept("NoSuchConcept") is None


def test_update_mapping_replaces_concept_and_convenience(store: KgStore) -> None:
    assert store.update_mapping(
        "tool-a",
        _tool_output_path("tool-a"),
        "FeelsLikeTemperature",
        unit="Celsius",
        provenance={"who": "maria", "why": "manual correction", "status": "corrected"},
    )
    assert store.concept_for_field("tool-a", _tool_output_path("tool-a")) == str(AB.FeelsLikeTemperature)
    tool = tool_iri("tool-a")
    assert (tool, AB.hasOutput, AB.Temperature) not in store.graph
    assert (tool, AB.hasOutput, AB.FeelsLikeTemperature) in store.graph
    assert store.validate().conforms


def test_lists_are_sorted_and_sane(store: KgStore) -> None:
    tools = store.list_tools()
    assert [tool.tool_id for tool in tools] == ["tool-a", "tool-b"]
    labels = {concept.label for concept in store.list_concepts()}
    assert {"City", "Temperature", "Feels-like temperature"} <= labels
    assert store.validate().conforms
