from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any, Protocol

TOKEN_PATTERN = re.compile(r"[a-z0-9_.:/°%-]+")
INFORMATIVE_KEYS = {"status", "type", "code", "currency", "base", "timezone", "tag"}
INFORMATIVE_SUFFIXES = ("unit", "units", "_unit", "_units")


class EmbeddingModel(Protocol):
    name: str
    dimensions: int

    def embed(self, text: str) -> list[float]:
        ...


class HashingEmbedder:
    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 32:
            raise ValueError("embedding dimensions must be at least 32")
        self.dimensions = dimensions
        self.name = f"hashing-ngram-{dimensions}"

    def embed(self, text: str) -> list[float]:
        tokens = TOKEN_PATTERN.findall(text.lower())
        features: Counter[str] = Counter(tokens)
        for token in tokens:
            padded = f"_{token}_"
            if len(padded) <= 3:
                continue
            for index in range(len(padded) - 2):
                features[padded[index : index + 3]] += 1
        vector = [0.0] * self.dimensions
        for feature, count in features.items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign * (1.0 + math.log1p(count))
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self._model = SentenceTransformer(model_name)
        self.dimensions = int(self._model.get_sentence_embedding_dimension())

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same length")
    return float(sum(a * b for a, b in zip(left, right, strict=False)))


def cosine_distance(left: list[float], right: list[float]) -> float:
    return max(0.0, min(2.0, 1.0 - cosine_similarity(left, right)))


def _informative_value(key: str, value: str) -> bool:
    lowered = key.lower()
    if lowered in INFORMATIVE_KEYS:
        return True
    return any(lowered == suffix or lowered.endswith(suffix) for suffix in INFORMATIVE_SUFFIXES)


def _shape(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {str(item_key): _shape(item_value, str(item_key)) for item_key, item_value in sorted(value.items())}
    if isinstance(value, list):
        if not value:
            return ["empty"]
        signatures = [_shape(item, key) for item in value[:3]]
        unique: list[Any] = []
        for signature in signatures:
            if signature not in unique:
                unique.append(signature)
        return ["array", unique]
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    text = str(value).strip()
    if _informative_value(key, text):
        normalized = text.lower().replace("°", "").replace("degrees", "").strip()
        return f"string={normalized[:24]}"
    return "string"


def payload_summary(payload: Any) -> str:
    shaped = _shape(payload)
    lines: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            lines.append(f"{path or 'root'}:object")
            for key in sorted(node):
                child = f"{path}.{key}" if path else key
                walk(node[key], child)
            return
        if isinstance(node, list):
            lines.append(f"{path or 'root'}:array")
            if len(node) > 1:
                for signature in node[1]:
                    walk(signature, f"{path or 'root'}[]")
                return
            if node and node[0] != "empty":
                walk(node[0], f"{path or 'root'}[]")
            return
        lines.append(f"{path or 'root'}:{node}")

    walk(shaped, "")
    return "\n".join(lines[:600])


def summary_embedding(embedder: EmbeddingModel, payload: Any) -> tuple[str, list[float]]:
    summary = payload_summary(payload)
    return summary, embedder.embed(summary)
