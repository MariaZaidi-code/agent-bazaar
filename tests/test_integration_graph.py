"""Tests for the RDF-backed tool-graph adapter of the app."""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph
from rdflib.namespace import RDF

from agent_bazaar.kg.store import KgStore
from agent_bazaar.models import ClaimRecord, MappedField, ToolRecord
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.ns import AB, tool_iri
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.ontology.validator import load_shapes
from app.integration.graph_adapter import RdfToolGraph
from app.knowledge.graph import ToolKnowledgeGraph
from app.knowledge.ontology import Ontology
from app.schemas import ConceptSpec, ToolSpec

ONTOLOGY_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"


def build_store() -> KgStore:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    return KgStore(graph=graph, shapes=load_shapes())


def weather_record(tool_id: str = "open-meteo-forecast", provider_id: str = "open-meteo") -> ToolRecord:
    return ToolRecord(
        tool_id=tool_id,
        name="Open-Meteo Forecast",
        description="Hourly weather forecast",
        provider_id=provider_id,
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


def custom_record(tool_id: str, capability: str, concept: str, unit: str | None = None) -> ToolRecord:
    return ToolRecord(
        tool_id=tool_id,
        name="Custom Tool",
        description="A tool outside the curated taxonomy",
        provider_id="custom-provider",
        provider_name="Custom Provider",
        capabilities=[capability],
        outputs=[
            MappedField(
                field_path="output.get:/v1/custom.value",
                name="value",
                concept=concept,
                unit=unit,
                direction="output",
                confidence=0.5,
                reason="field name matches the concept",
                status="mapped",
            )
        ],
        source="openapi",
        version="v1",
    )


def local_graph() -> ToolKnowledgeGraph:
    graph = ToolKnowledgeGraph(Ontology.load(ONTOLOGY_PATH))
    graph.add(
        ToolSpec(
            id="nominatim-geocode",
            name="OpenStreetMap Nominatim Geocoder",
            provider_id="nominatim",
            description="Resolve a place name to coordinates.",
            capability="GeocodeLocation",
            inputs=[ConceptSpec(concept="LocationName", name="location")],
            outputs=[ConceptSpec(concept="Coordinates", name="coordinates", unit="degrees")],
        )
    )
    return graph


def test_all_and_get_expose_the_rdf_tool() -> None:
    store = build_store()
    store.write_tool(weather_record())
    graph = RdfToolGraph(store)

    tools = graph.all()
    assert [tool.id for tool in tools] == ["open-meteo-forecast"]
    tool = tools[0]
    assert tool.name == "Open-Meteo Forecast"
    assert tool.description == "Hourly weather forecast"
    assert tool.provider_id == "open-meteo"
    assert tool.capability == "GetWeatherForecast"
    assert tool.execution == "fixture"
    assert [item.concept for item in tool.inputs] == ["Latitude"]
    assert [item.concept for item in tool.outputs] == ["Temperature"]
    assert tool.inputs[0].name == "latitude"
    assert tool.inputs[0].unit == "Degree"
    assert tool.outputs[0].name == "temperature_2m"
    assert tool.outputs[0].unit == "Celsius"
    assert tool.outputs[0].datatype == "float"
    assert [claim.text for claim in tool.claims] == ["Free forecasts"]

    fetched = graph.get("open-meteo-forecast")
    assert fetched is not None
    assert fetched.id == "open-meteo-forecast"
    assert graph.get("missing-tool") is None


def test_by_capability_matches_the_curated_taxonomy() -> None:
    store = build_store()
    store.write_tool(weather_record())
    graph = RdfToolGraph(store)

    assert [tool.id for tool in graph.by_capability("GetWeatherForecast")] == ["open-meteo-forecast"]
    assert [tool.id for tool in graph.by_capability("weather-forecast")] == ["open-meteo-forecast"]
    assert graph.by_capability("ConvertCurrency") == []


def test_capability_falls_back_to_concepts_then_to_general() -> None:
    store = build_store()
    store.write_tool(custom_record("mystery-tool", "mystery-capability", "Temperature", unit="Celsius"))
    store.write_tool(custom_record("plain-tool", "plain-capability", "Description"))
    graph = RdfToolGraph(store)

    assert graph.get("mystery-tool") is not None
    assert graph.get("mystery-tool").capability == "GetWeatherForecast"
    assert graph.get("plain-tool") is not None
    assert graph.get("plain-tool").capability == "general"


def test_compatible_substitutes_find_second_tool_with_same_output() -> None:
    store = build_store()
    store.write_tool(weather_record())
    store.write_tool(weather_record("open-meteo-forecast-backup", provider_id="open-meteo-backup"))
    graph = RdfToolGraph(store)

    substitutes = graph.compatible_substitutes(
        "GetWeatherForecast",
        ["Latitude"],
        ["Temperature"],
        exclude={"open-meteo-forecast"},
    )
    assert [tool.id for tool in substitutes] == ["open-meteo-forecast-backup"]

    without_inputs = graph.compatible_substitutes("GetWeatherForecast", [], ["Temperature"])
    assert [tool.id for tool in without_inputs] == []

    wrong_output = graph.compatible_substitutes("GetWeatherForecast", ["Latitude"], ["Holiday"])
    assert wrong_output == []


def test_neighbors_share_concepts() -> None:
    store = build_store()
    store.write_tool(weather_record())
    store.write_tool(weather_record("open-meteo-forecast-backup", provider_id="open-meteo-backup"))
    graph = RdfToolGraph(store)

    neighbors = graph.neighbors("open-meteo-forecast", limit=5)
    assert [tool.id for tool in neighbors] == ["open-meteo-forecast-backup"]
    assert graph.neighbors("missing-tool") == []


def test_export_turtle_writes_a_file(tmp_path: Path) -> None:
    store = build_store()
    store.write_tool(weather_record())
    graph = RdfToolGraph(store)

    target = tmp_path / "nested" / "knowledge_graph.ttl"
    assert graph.export_turtle(target) is True
    assert target.exists()

    parsed = Graph()
    parsed.parse(target, format="turtle")
    assert (tool_iri("open-meteo-forecast"), RDF.type, AB.Tool) in parsed
    assert (tool_iri("open-meteo-forecast"), AB.hasOutput, AB.Temperature) in parsed


def test_export_turtle_annotates_trust(tmp_path: Path) -> None:
    store = build_store()
    store.write_tool(weather_record())
    graph = RdfToolGraph(store)

    target = tmp_path / "knowledge_graph.ttl"
    assert graph.export_turtle(target, trust={"open-meteo": {"score": 0.75}}) is True

    parsed = Graph()
    parsed.parse(target, format="turtle")
    trust = parsed.value(AB["provider-open-meteo"], AB.hasTrust)
    assert trust is not None
    assert float(str(trust)) == 0.75


def test_local_only_tools_are_still_served() -> None:
    store = build_store()
    store.write_tool(weather_record())
    graph = RdfToolGraph(store, local_graph=local_graph())

    assert [tool.id for tool in graph.all()] == ["nominatim-geocode", "open-meteo-forecast"]

    local_tool = graph.get("nominatim-geocode")
    assert local_tool is not None
    assert local_tool.provider_id == "nominatim"
    assert local_tool.capability == "GeocodeLocation"

    rdf_tool = graph.get("open-meteo-forecast")
    assert rdf_tool is not None
    assert rdf_tool.execution == "fixture"

    assert [tool.id for tool in graph.by_capability("GeocodeLocation")] == ["nominatim-geocode"]
