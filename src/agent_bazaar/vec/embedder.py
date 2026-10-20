"""Embedding backends for the shared vector index."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any, ClassVar, Protocol, runtime_checkable

import numpy as np

from agent_bazaar.config import Settings, get_settings
from agent_bazaar.logging_utils import get_logger

logger = get_logger("agent_bazaar.vec.embedder")

_TOKEN_PATTERN = re.compile(r"\w+")


@runtime_checkable
class Embedder(Protocol):
    dim: int
    model_name: str

    def embed(self, text: str) -> list[float]:
        ...

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingEmbedder:
    def __init__(self, dim: int = 384, model_name: str = "hashing-fallback") -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = int(dim)
        self.model_name = model_name

    @staticmethod
    def _tokens(text: str) -> list[str]:
        lowered = text.lower()
        words = [match.group(0) for match in _TOKEN_PATTERN.finditer(lowered) if match.group(0).strip()]
        grams = [lowered[index : index + 3] for index in range(max(len(lowered) - 2, 0))]
        grams = [gram for gram in grams if gram.strip()]
        return words + grams

    def embed(self, text: str) -> list[float]:
        counts = Counter(self._tokens(text))
        vector = np.zeros(self.dim, dtype=np.float64)
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "little", signed=False)
            bucket = value % self.dim
            sign = -1.0 if value & (1 << 63) else 1.0
            vector[bucket] += sign * (1.0 + math.log(count))
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            vector[0] = 1.0
            return [float(component) for component in vector]
        vector /= norm
        return [float(component) for component in vector]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class SentenceTransformerEmbedder:
    _models: ClassVar[dict[str, Any]] = {}

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        model = SentenceTransformerEmbedder._models.get(model_name)
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
            SentenceTransformerEmbedder._models[model_name] = model
        self._model = model
        dimension = model.get_sentence_embedding_dimension()
        if dimension is None:
            raise ValueError(f"Model {model_name!r} does not expose an embedding dimension")
        self.dim = int(dimension)

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        encoded = self._model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        matrix = np.asarray(encoded, dtype=np.float64)
        return [[float(component) for component in row] for row in matrix]


_EMBEDDER_CACHE: dict[tuple[str, int, str, bool], Embedder] = {}


def build_embedder(settings: Settings | None = None, force_fallback: bool = False) -> Embedder:
    resolved = settings or get_settings()
    embedding = resolved.embedding
    key = (embedding.model, embedding.fallback_dim, embedding.use_fallback, force_fallback)
    cached = _EMBEDDER_CACHE.get(key)
    if cached is not None:
        return cached
    if force_fallback or embedding.use_fallback == "always":
        embedder: Embedder = HashingEmbedder(dim=embedding.fallback_dim)
    elif embedding.use_fallback == "never":
        embedder = SentenceTransformerEmbedder(embedding.model)
    else:
        try:
            embedder = SentenceTransformerEmbedder(embedding.model)
        except Exception as exc:
            logger.warning(
                "SentenceTransformerEmbedder unavailable for %s; using HashingEmbedder: %s",
                embedding.model,
                exc,
            )
            embedder = HashingEmbedder(dim=embedding.fallback_dim)
    _EMBEDDER_CACHE[key] = embedder
    return embedder
