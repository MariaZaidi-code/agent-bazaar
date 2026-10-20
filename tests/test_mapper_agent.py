"""End-to-end Mapper agent scenarios with real graph, vector and staging services."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rdflib import URIRef

from agent_bazaar.config import PathSettings, Settings
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.kg import KgStore
from agent_bazaar.llm.client import LLMError
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.mapper.llm_mapper import LLMDecision, LLMDecisionBatch
from agent_bazaar.mapper.memory import CorrectionMemory
from agent_bazaar.mapper.staging import StagingQueue
from agent_bazaar.messages.schema import (
    CorrectionSubmit,
    DriftAlert,
    FieldSpec,
    ListingSubmit,
    MapRequest,
)
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.ns import AB, tool_iri
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.protocols import CORRECTIONS
from agent_bazaar.vec import HashingEmbedder, VectorIndex, VectorService


class FakeLLM:
    provider = "fake"

    def __init__(self, script: list[Any] | None = None) -> None:
        self.script = list(script or [])
        self.prompts: list[str] = []
        self._stats: dict[str, Any] = {"calls": 0, "cache_hits": 0, "errors": 0}

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type,
        *,
        use_cache: bool = True,
        temperature: float | None = None,
    ) -> LLMDecisionBatch:
        self.prompts.append(user)
        self._stats["calls"] += 1
        if not self.script:
            self._stats["errors"] += 1
            raise LLMError("script exhausted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            self._stats["errors"] += 1
            raise item
        if isinstance(item, LLMDecisionBatch):
            return item
        return LLMDecisionBatch(decisions=[LLMDecision(**decision) for decision in item])

    def complete_text(
        self,
        system: str,
        user: str,
        *,
        use_cache: bool = True,
        temperature: float | None = None,
    ) -> str:
        return "{}"


def _settings(root: Path) -> Settings:
    return Settings(
        paths=PathSettings(
            data_dir=root,
            specs_dir=root / "specs",
            cache_dir=root / "cache",
            out_dir=root / "out",
            memory_dir=root / "memory",
            staging_dir=root / "staging",
            vectors_dir=root / "vectors",
        )
    )


def _store() -> KgStore:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    return KgStore(graph=graph)


def _agent(
    root: Path,
    client: FakeLLM | None = None,
    use_llm: bool | None = None,
    ingester: Any = None,
) -> tuple[MapperAgent, KgStore, VectorService, CorrectionMemory, StagingQueue]:
    settings = _settings(root)
    store = _store()
    vector = VectorService(HashingEmbedder(dim=384), VectorIndex(384))
    memory = CorrectionMemory(settings.paths.memory_dir)
    staging = StagingQueue(settings.paths.staging_dir)
    agent = MapperAgent(
        store,
        vector,
        client=client,
        ingester=ingester,
        settings=settings,
        memory=memory,
        staging=staging,
        use_llm=use_llm,
    )
    return agent, store, vector, memory, staging


def _status(mapping: Any) -> str:
    return mapping.status.value if hasattr(mapping.status, "value") else str(mapping.status)


def _mapping_triple(store: KgStore, tool_id: str, field_path: str, predicate: URIRef) -> str | None:
    tool = tool_iri(tool_id)
    for node in store.graph.subjects(AB.tool, tool):
        if str(store.graph.value(node, AB.fieldPath)) == field_path:
            value = store.graph.value(node, predicate)
            return str(value) if value is not None else None
    return None


def test_llm_mapping_with_repair_and_review_queue(tmp_path: Path) -> None:
    fake = FakeLLM(
        [
            [
                {
                    "field_path": "output.temperature_2m",
                    "concept": "Temperature",
                    "unit": "Celsius",
                    "confidence": 0.9,
                    "reason": "name and unit match",
                },
                {
                    "field_path": "output.city_name",
                    "concept": "City",
                    "confidence": 0.8,
                    "reason": "name match",
                },
                {
                    "field_path": "output.zwibble_flux",
                    "concept": "NoSuchConcept",
                    "confidence": 0.3,
                    "reason": "weak guess",
                },
            ],
            [
                {
                    "field_path": "output.zwibble_flux",
                    "concept": "NoSuchConcept",
                    "confidence": 0.3,
                    "reason": "still unknown",
                }
            ],
            [
                {
                    "field_path": "output.zwibble_flux",
                    "concept": "NoSuchConcept",
                    "confidence": 0.3,
                    "reason": "still unknown",
                }
            ],
        ]
    )
    agent, store, _, _, _ = _agent(tmp_path, client=fake)
    fields = [
        FieldSpec(field_path="output.temperature_2m", name="temperature_2m", type="float"),
        FieldSpec(field_path="output.city_name", name="city_name", type="string"),
        FieldSpec(field_path="output.zwibble_flux", name="zwibble_flux", type="string"),
    ]

    result = agent.map_fields(MapRequest(tool_id="weather", fields=fields))
    by_path = {mapping.field_path: mapping for mapping in result.mappings}

    assert store.concept_for_field("weather", "output.temperature_2m") == str(AB.Temperature)
    assert store.concept_for_field("weather", "output.city_name") == str(AB.City)
    assert by_path["output.temperature_2m"].unit == "Celsius"
    assert by_path["output.city_name"].unit is None
    assert _status(by_path["output.temperature_2m"]) == "mapped"
    assert _status(by_path["output.city_name"]) == "mapped"

    assert [field.field_path for field in result.unmapped] == ["output.zwibble_flux"]
    assert _status(by_path["output.zwibble_flux"]) == "unmapped"
    assert store.concept_for_field("weather", "output.zwibble_flux") is None
    assert sum("zwibble_flux" in prompt for prompt in fake.prompts) >= 2
    assert fake.stats["calls"] == 3

    stats = result.stats
    assert stats["mapped"] == 2
    assert stats["unmapped"] == 1
    assert stats["queued_for_review"] == 1
    assert stats["attempts_total"] == 3
    assert stats["llm_calls"]["calls"] == 3


def test_offline_heuristic_maps_temperature_and_rejects_gibberish(tmp_path: Path) -> None:
    agent, store, _, _, _ = _agent(tmp_path, client=None, use_llm=False)
    fields = [
        FieldSpec(field_path="output.temperature_2m", name="temperature_2m", type="float"),
        FieldSpec(field_path="output.zwibble_flux", name="zwibble_flux", type="string"),
    ]

    result = agent.map_fields(MapRequest(tool_id="offline", fields=fields))

    assert store.concept_for_field("offline", "output.temperature_2m") == str(AB.Temperature)
    assert [field.field_path for field in result.unmapped] == ["output.zwibble_flux"]
    assert result.stats["mapped"] == 1
    assert result.stats["unmapped"] == 1


def test_llm_failure_falls_back_to_the_heuristic_mapper(tmp_path: Path) -> None:
    fake = FakeLLM([LLMError("provider unavailable")])
    agent, store, _, _, _ = _agent(tmp_path, client=fake)
    result = agent.map_fields(
        MapRequest(
            tool_id="fallback",
            fields=[FieldSpec(field_path="output.temperature_2m", name="temperature_2m", type="float")],
        )
    )

    assert store.concept_for_field("fallback", "output.temperature_2m") == str(AB.Temperature)
    assert result.stats["mapped"] == 1
    assert result.stats["llm_calls"]["calls"] == 1
    assert result.stats["llm_calls"]["errors"] == 1


def test_correction_flow_promotes_rejects_and_feeds_retrieval(tmp_path: Path) -> None:
    agent, _, vector, memory, staging = _agent(tmp_path, client=None, use_llm=False)
    good = CorrectionSubmit(
        tool_id="weather",
        field_path="output.temperature_2m",
        corrected_concept="FeelsLikeTemperature",
        corrected_unit="Celsius",
        note="field is apparent temperature",
        submitted_by="reviewer",
    )

    promoted = agent.submit_correction(good)
    assert promoted["status"] == "promoted"
    assert memory.count() == 1
    assert vector.count(CORRECTIONS) >= 1

    result = agent.map_fields(
        MapRequest(
            tool_id="weather",
            fields=[FieldSpec(field_path="output.temperature_2m", name="temperature_2m", type="float")],
        )
    )
    assert result.stats["mapped"] == 1
    context = agent.retriever.retrieve(
        FieldSpec(field_path="output.temperature_2m", name="temperature_2m", type="float")
    )
    assert any(
        hit.id.startswith("corr-") and "FeelsLikeTemperature" in str(hit.metadata.get("concept"))
        for hit in context.corrections
    )

    bad = CorrectionSubmit(
        tool_id="weather",
        field_path="output.temperature_2m",
        corrected_concept="NoSuchConcept",
    )
    rejected = agent.submit_correction(bad)
    assert rejected["status"] == "rejected"
    assert "not found" in rejected["reason"]
    assert memory.count() == 1
    assert staging.stats()["rejected"] == 1


def test_drift_alert_remaps_only_the_affected_field(tmp_path: Path) -> None:
    fake = FakeLLM(
        [
            [
                {
                    "field_path": "output.temperature_2m",
                    "concept": "Temperature",
                    "unit": "Celsius",
                    "confidence": 0.9,
                    "reason": "initial mapping",
                }
            ],
            [
                {
                    "field_path": "output.temperature_2m",
                    "concept": "FeelsLikeTemperature",
                    "unit": "Celsius",
                    "confidence": 0.88,
                    "reason": "sample shifted to apparent temperature",
                }
            ],
        ]
    )
    agent, store, _, _, _ = _agent(tmp_path, client=fake)
    field = FieldSpec(field_path="output.temperature_2m", name="temperature_2m", type="float")
    initial = agent.map_fields(MapRequest(tool_id="weather", fields=[field]))
    assert initial.stats["mapped"] == 1
    assert store.concept_for_field("weather", "output.temperature_2m") == str(AB.Temperature)

    alert = DriftAlert(
        tool_id="weather",
        field_path="output.temperature_2m",
        old_description="Air temperature at two metres",
        new_sample=301.5,
    )
    result = agent.handle_drift_alert(alert)

    assert len(result.mappings) == 1
    assert _status(result.mappings[0]) == "drift_remapped"
    assert store.concept_for_field("weather", "output.temperature_2m") == str(AB.FeelsLikeTemperature)
    reason = _mapping_triple(store, "weather", "output.temperature_2m", AB.reason)
    assert reason is not None
    assert "drift" in reason
    assert str(AB.Temperature) in reason
    assert _mapping_triple(store, "weather", "output.temperature_2m", AB.status) == "drift_remapped"


def test_listing_submit_uses_real_ingestion_and_builds_tool_fields(tmp_path: Path) -> None:
    document = {
        "openapi": "3.0.3",
        "info": {
            "title": "Two Endpoint Weather API",
            "version": "1.2.0",
            "description": "Small listing used by the mapper integration test.",
        },
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/v1/weather": {
                "get": {
                    "parameters": [
                        {"name": "latitude", "in": "query", "required": True, "schema": {"type": "number"}},
                        {"name": "city", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "temperature_2m": {"type": "number"},
                                            "humidity": {"type": "number"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/v1/geo": {
                "get": {
                    "parameters": [
                        {"name": "country", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "population": {"type": "integer"},
                                            "capital": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
        },
    }
    source = tmp_path / "two_endpoints.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    utility = IngestionUtility()
    spec = utility.ingest(source)
    expected_paths = {field.path for field in spec.fields}

    agent, _, _, _, _ = _agent(tmp_path, client=None, use_llm=False, ingester=utility)
    message = ListingSubmit(tool_id="listing-tool", source=str(source))
    result = agent.handle_listing_submit(message)

    assert result.tool_id == "listing-tool"
    assert result.correlation_id == message.correlation_id
    assert {mapping.field_path for mapping in result.mappings} == expected_paths
    assert result.unmapped == []
    assert all(_status(mapping) != "unmapped" for mapping in result.mappings)

    record = agent.listing_to_tool_record(
        spec,
        result,
        provider_id="example",
        provider_name="Example Provider",
        trust=0.7,
    )
    assert record.tool_id == spec.tool_id
    assert record.name == "Two Endpoint Weather API"
    assert record.source == spec.source
    assert record.version == "1.2.0"
    assert record.base_url == "https://api.example.com"
    assert record.capabilities == ["two-endpoint-weather-api"]
    assert {field.field_path for field in [*record.inputs, *record.outputs]} == expected_paths
    assert record.outputs
    assert record.inputs
