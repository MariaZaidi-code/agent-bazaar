"""Tests for the vector embedders."""

from __future__ import annotations

import numpy as np
import pytest

from agent_bazaar.vec.embedder import HashingEmbedder, build_embedder


def test_hashing_embedder_is_deterministic() -> None:
    first = HashingEmbedder(dim=64)
    second = HashingEmbedder(dim=64)
    text = "Customer identifier alias"
    assert first.embed(text) == first.embed(text)
    assert first.embed(text) == second.embed(text)


def test_hashing_embedder_returns_unit_norm() -> None:
    embedder = HashingEmbedder(dim=64)
    vector = np.asarray(embedder.embed("shipment weight in kilograms"), dtype=np.float64)
    assert np.linalg.norm(vector) == pytest.approx(1.0)


def test_hashing_embedder_differs_for_different_text() -> None:
    embedder = HashingEmbedder(dim=64)
    assert embedder.embed("customer identifier") != embedder.embed("invoice currency")


def test_hashing_embedder_empty_text_is_safe() -> None:
    embedder = HashingEmbedder(dim=32)
    for text in ("", "   ", "\n\t"):
        vector = embedder.embed(text)
        assert len(vector) == 32
        assert vector[0] == 1.0
        assert np.linalg.norm(np.asarray(vector)) == pytest.approx(1.0)


def test_hashing_embedder_respects_dimension() -> None:
    embedder = HashingEmbedder(dim=17)
    vectors = embedder.embed_many(["alpha", "beta gamma", ""])
    assert embedder.dim == 17
    assert embedder.model_name == "hashing-fallback"
    assert len(vectors) == 3
    assert all(len(vector) == 17 for vector in vectors)


def test_build_embedder_force_fallback_and_batches_match() -> None:
    embedder = build_embedder(force_fallback=True)
    assert isinstance(embedder, HashingEmbedder)
    texts = ["customer id", "shipment weight", "invoice currency"]
    assert embedder.embed_many(texts) == [embedder.embed(text) for text in texts]
