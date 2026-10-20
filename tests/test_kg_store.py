"""Tests for the SHACL-validated knowledge graph store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import Graph
from rdflib.namespace import RDF

from agent_bazaar.ingestion.models import EndpointInfo, FieldInfo, NormalizedSpec
from agent_bazaar.kg import (
    GraphValidationError,
    KgStore,
    load_normalized_specs,
    load_specs_summary,
    write_normalized_spec,
)
from agent_bazaar.models import ClaimRecord, MappedField, ToolRecord
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.ns import AB, tool_iri
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.ontology.validator import load_shapes


def build_store() -> KgStore:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    return KgStore(graph=graph, shapes=load_shapes())


def valid_record(tool_id: str = "open-meteo-forecast") -> ToolRecord:
    return ToolRecord(
        tool_id=tool_id,
        name="Open-Meteo Forecast",
        description="Hourly weather forecast",
        provider_id="open-meteo",
        provider_name="Open-Meteo",
        base_url="https://api.open-meteo.com",
        capabilities=["weather-forecast"],
        inputs=[
            MappedField(
                field_path="input.get:/v1/forecast.latitude",
                name="latitude",
                concept="Latitude",
                direction="input",
                unit="Degree",
                confidence=0.95,
                reason="parameter name matches latitude",
                status="mapped",
            )
        ],
        outputs=[
            MappedField(
                field_path="output.get:/v1/forecast.temperature_2m",
                name="temperature_2m",
                concept="Temperature",
                direction="output",
                unit="Celsius",
                confidence=0.9,
                reason="sample values and name match temperature",
                status="mapped",
            )
        ],
        claims=[ClaimRecord(claim_id="claim-1", text="Free forecasts", source="open-meteo docs")],
        trust=0.8,
        source="openapi",
        version="v1",
    )


def test_write_valid_record() -> None:
    store = build_store()
    before = len(store.graph)
    store.write_tool(valid_record())
    tool = tool_iri("open-meteo-forecast")
    assert len(store.graph) > before
    assert (tool, RDF.type, AB.Tool) in store.graph
    assert (tool, AB.hasInput, AB.Latitude) in store.graph
    assert (tool, AB.hasOutput, AB.Temperature) in store.graph
    assert (tool, AB.hasCapability, AB["capability-weather-forecast"]) in store.graph
    mappings = set(store.graph.subjects(RDF.type, AB.Mapping))
    assert len(mappings) == 2
    assert all((mapping, AB.tool, tool) in store.graph for mapping in mappings)
    assert store.concept_for_field("open-meteo-forecast", "output.get:/v1/forecast.temperature_2m") == str(
        AB.Temperature
    )
    assert store.validate().conforms


def test_write_invalid_concept_leaves_graph_untouched() -> None:
    store = build_store()
    before = len(store.graph)
    record = valid_record("bad-concept")
    record.outputs[0].concept = "NoSuchConcept"
    with pytest.raises(GraphValidationError) as error:
        store.write_tool(record)
    assert not error.value.result.conforms
    assert len(store.graph) == before
    assert (tool_iri("bad-concept"), RDF.type, AB.Tool) not in store.graph


def test_write_invalid_unit_leaves_graph_untouched() -> None:
    store = build_store()
    before = len(store.graph)
    record = valid_record("bad-unit")
    record.outputs[0].unit = "Percent"
    with pytest.raises(GraphValidationError):
        store.write_tool(record)
    assert len(store.graph) == before


def test_save_writes_parseable_turtle(tmp_path: Path) -> None:
    store = build_store()
    store.write_tool(valid_record())
    target = store.save(tmp_path / "nested" / "graph.ttl")
    assert target.exists()
    parsed = Graph()
    parsed.parse(target, format="turtle")
    assert (tool_iri("open-meteo-forecast"), RDF.type, AB.Tool) in parsed


def test_loader_roundtrip_and_malformed_skip(tmp_path: Path) -> None:
    spec = NormalizedSpec(
        tool_id="sample-tool",
        source="sample.json",
        title="Sample",
        endpoints=[EndpointInfo(path="/v1/things")],
        fields=[FieldInfo(path="output.get:/v1/things.name", name="name")],
    )
    written = write_normalized_spec(spec, tmp_path)
    assert written.exists()
    (tmp_path / "wrapped.json").write_text(
        json.dumps({"spec": spec.model_dump(mode="json")}), encoding="utf-8"
    )
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    loaded = load_normalized_specs(tmp_path)
    assert [item.tool_id for item in loaded] == ["sample-tool", "sample-tool"]
    summary = load_specs_summary(tmp_path)
    assert summary[0]["endpoint_count"] == 1
    assert summary[0]["field_count"] == 1
