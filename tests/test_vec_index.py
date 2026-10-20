"""Tests for the shared vector index and service."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from agent_bazaar.config import EmbeddingSettings, Settings
from agent_bazaar.protocols import CORRECTIONS, ONTOLOGY_TERMS, TOOL_DESCRIPTIONS, IndexItem
from agent_bazaar.vec import VectorService, build_vector_service
from agent_bazaar.vec.embedder import HashingEmbedder
from agent_bazaar.vec.index import VectorIndex


def test_upsert_and_search_returns_best_match_first() -> None:
    index = VectorIndex(dim=3)
    items = [
        IndexItem(id="a", text="alpha"),
        IndexItem(id="b", text="beta"),
        IndexItem(id="c", text="gamma"),
    ]
    index.upsert("test", items, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    hits = index.search("test", [0.9, 0.1, 0.0], k=3)
    assert [hit.id for hit in hits] == ["a", "b", "c"]
    assert hits[0].score == pytest.approx(0.993884, abs=1e-6)


def test_search_respects_k() -> None:
    index = VectorIndex(dim=3)
    items = [IndexItem(id=name, text=name) for name in ("a", "b", "c")]
    index.upsert("test", items, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert len(index.search("test", [1.0, 1.0, 1.0], k=2)) == 2
    assert len(index.search("test", [1.0, 1.0, 1.0], k=10)) == 3
    assert index.search("test", [1.0, 1.0, 1.0], k=0) == []


def test_reupsert_same_id_replaces_item() -> None:
    index = VectorIndex(dim=2)
    index.upsert("test", [IndexItem(id="x", text="old", metadata={"version": 1})], [[1.0, 0.0]])
    index.upsert("test", [IndexItem(id="x", text="new", metadata={"version": 2})], [[0.0, 1.0]])
    assert index.count("test") == 1
    assert index.get("test", "x") == IndexItem(id="x", text="new", metadata={"version": 2})
    hits = index.search("test", [0.0, 1.0], k=1)
    assert hits[0].text == "new"


def test_remove_and_unknown_collection() -> None:
    index = VectorIndex(dim=2)
    index.upsert("test", [IndexItem(id="x", text="value")], [[1.0, 0.0]])
    assert index.remove("test", "x") is True
    assert index.remove("test", "x") is False
    assert index.count("test") == 0
    assert index.search("test", [1.0, 0.0]) == []
    assert index.search("missing", [1.0, 0.0]) == []


def test_persistence_roundtrip(tmp_path: Path) -> None:
    index = VectorIndex(dim=4)
    index.upsert(
        ONTOLOGY_TERMS,
        [
            IndexItem(id="t1", text="customer identifier", metadata={"kind": "term"}),
            IndexItem(id="t2", text="shipment weight", metadata={"kind": "term", "unit": "kg"}),
        ],
        [[1.0, 0.0, 0.0, 0.0], [0.5, 0.5, 0.0, 0.0]],
    )
    index.upsert(TOOL_DESCRIPTIONS, [IndexItem(id="tool", text="scales parcels")], [[0.0, 0.0, 1.0, 2.0]])
    directory = index.persist(tmp_path / "vectors")
    loaded = VectorIndex.load(directory, dim=4)
    assert loaded.collections() == index.collections()
    assert loaded.count(ONTOLOGY_TERMS) == 2
    assert loaded.get(ONTOLOGY_TERMS, "t2") == index.get(ONTOLOGY_TERMS, "t2")
    query = [0.2, 0.3, 0.5, 0.1]
    before = index.search(ONTOLOGY_TERMS, query, k=5)
    after = loaded.search(ONTOLOGY_TERMS, query, k=5)
    assert [hit.id for hit in before] == [hit.id for hit in after]
    assert [hit.score for hit in before] == [hit.score for hit in after]


def test_cosine_distance_values() -> None:
    service = VectorService(HashingEmbedder(dim=8))
    assert service.cosine_distance([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)
    assert service.cosine_distance([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)
    assert service.cosine_distance([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(2.0)
    expected = 1.0 - 2.0 / (2.0 * np.sqrt(2.0))
    assert service.cosine_distance(np.array([2.0, 0.0]), [1.0, 1.0]) == pytest.approx(expected)
    assert service.cosine_distance([], []) == pytest.approx(1.0)
    assert service.cosine_distance([0.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_vector_service_end_to_end() -> None:
    service = VectorService(HashingEmbedder(dim=512))
    items = [
        IndexItem(
            id="term-customer",
            text="customer identifier customer id client identifier",
            metadata={"aliases": ["client id"]},
        ),
        IndexItem(id="term-weight", text="shipment weight kilograms mass", metadata={"unit": "kg"}),
        IndexItem(id="term-currency", text="invoice currency iso code money", metadata={"unit": "iso"}),
    ]
    assert service.upsert(ONTOLOGY_TERMS, items) == 3
    assert service.count(ONTOLOGY_TERMS) == 3
    hits = service.search(ONTOLOGY_TERMS, "customer identifier", k=3)
    assert len(hits) == 3
    assert hits[0].id == "term-customer"


def test_build_vector_service_uses_fallback() -> None:
    service = build_vector_service(force_fallback=True)
    assert isinstance(service, VectorService)
    assert isinstance(service.embedder, HashingEmbedder)
    assert service.count(TOOL_DESCRIPTIONS) == 0


def test_service_load_or_create_roundtrip(tmp_path: Path) -> None:
    settings = Settings(embedding=EmbeddingSettings(fallback_dim=24))
    service = VectorService.load_or_create(directory=tmp_path, settings=settings, force_fallback=True)
    service.upsert(
        CORRECTIONS,
        [IndexItem(id="c1", text="unit mismatch correction", metadata={"field": "weight"})],
    )
    service.persist(tmp_path)
    restored = VectorService.load_or_create(directory=tmp_path, settings=settings, force_fallback=True)
    assert restored.count(CORRECTIONS) == 1
    assert restored.search(CORRECTIONS, "unit mismatch correction", k=1)[0].id == "c1"
