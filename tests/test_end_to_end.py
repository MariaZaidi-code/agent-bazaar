"""End-to-end offline test: ingest -> map -> validated graph -> queries -> drift."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_bazaar.config import PathSettings, Settings, ensure_directories
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.kg import KgStore, describe_graph
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.messages.schema import CorrectionSubmit, DriftAlert
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.pipeline import derive_capabilities, onboard_spec
from agent_bazaar.vec import HashingEmbedder, VectorIndex, VectorService

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "sample_openapi.json"


@pytest.fixture()
def stack(tmp_path):
    paths = PathSettings(
        data_dir=tmp_path,
        specs_dir=tmp_path / "specs",
        cache_dir=tmp_path / "cache",
        out_dir=tmp_path / "out",
        memory_dir=tmp_path / "memory",
        staging_dir=tmp_path / "staging",
        vectors_dir=tmp_path / "vectors",
    )
    settings = Settings(paths=paths)
    ensure_directories(settings)
    ontology = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        ontology.add(triple)
    store = KgStore(graph=ontology, settings=settings)
    embedder = HashingEmbedder(settings.embedding.fallback_dim)
    vector = VectorService(embedder, VectorIndex(embedder.dim))
    mapper = MapperAgent(
        store,
        vector,
        client=None,
        ingester=IngestionUtility(settings.ingestion),
        settings=settings,
        use_llm=False,
    )
    mapper.build_index()
    return settings, store, vector, mapper


def test_onboard_map_and_query(stack):
    settings, store, vector, mapper = stack
    spec = mapper.ingester.ingest(SAMPLE)
    outcome = onboard_spec(spec, mapper, store, vector=vector, tool_id="sample-api")
    assert outcome.written, outcome.error
    assert outcome.result.mappings
    assert store.list_tools()
    warm = [m for m in outcome.result.mappings if "temperature" in m.field_path]
    if warm:
        concept = store.concept_for_field("sample-api", warm[0].field_path)
        assert concept
    capabilities = derive_capabilities(spec)
    assert capabilities
    stats = describe_graph(store.graph)
    assert stats["tools"] == 1
    assert vector.count("tool_descriptions") == 1
    saved = store.save(settings.paths.graph_path)
    assert saved.exists() and saved.stat().st_size > 0


def test_correction_staging_and_gated_learning(stack):
    settings, store, vector, mapper = stack
    spec = mapper.ingester.ingest(SAMPLE)
    outcome = onboard_spec(spec, mapper, store, vector=vector, tool_id="sample-api")
    field = outcome.result.mappings[0]
    good = CorrectionSubmit(
        tool_id="sample-api",
        field_path=field.field_path,
        corrected_concept="ab:FeelsLikeTemperature",
        corrected_unit="Celsius",
        submitted_by="tester",
    )
    decision = mapper.submit_correction(good)
    assert decision["status"] == "promoted"
    assert mapper.memory.count() == 1
    assert decision["stats"]["promoted"] == 1
    bad = CorrectionSubmit(
        tool_id="sample-api",
        field_path=field.field_path,
        corrected_concept="ab:NoSuchConcept",
        submitted_by="tester",
    )
    bad_decision = mapper.submit_correction(bad)
    assert bad_decision["status"] == "rejected"
    assert bad_decision["reason"]
    assert bad_decision["stats"]["rejected"] == 1
    assert mapper.memory.count() == 1


def test_drift_remap_updates_graph(stack):
    settings, store, vector, mapper = stack
    spec = mapper.ingester.ingest(SAMPLE)
    outcome = onboard_spec(spec, mapper, store, vector=vector, tool_id="sample-api")
    temperature = next((m for m in outcome.result.mappings if "temperature" in m.field_path), None)
    if temperature is None:
        pytest.skip("fixture has no temperature field")
    before = store.concept_for_field("sample-api", temperature.field_path)
    alert = DriftAlert(
        tool_id="sample-api",
        field_path=temperature.field_path,
        old_description="temperature in Celsius",
        new_sample={"value": 300.1},
        sender="auditor",
    )
    result = mapper.handle_drift_alert(alert)
    assert result.mappings
    after = store.concept_for_field("sample-api", temperature.field_path)
    assert after
    assert getattr(result.mappings[0].status, "value", result.mappings[0].status) == "drift_remapped"
    assert "drift" in result.mappings[0].reason.lower() or before != after
