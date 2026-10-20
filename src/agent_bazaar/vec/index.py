"""In-memory vector index and the shared vector service."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from agent_bazaar.config import Settings, get_settings
from agent_bazaar.logging_utils import get_logger
from agent_bazaar.protocols import IndexItem, SearchHit
from agent_bazaar.vec.embedder import Embedder, build_embedder

logger = get_logger("agent_bazaar.vec.index")

_MANIFEST_NAME = "manifest.json"
_UNSAFE_COLLECTION_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass
class _Entry:
    vector: np.ndarray
    text: str
    metadata: dict[str, Any]


def _collection_stem(collection: str) -> str:
    digest = hashlib.sha256(collection.encode("utf-8")).hexdigest()[:16]
    safe = _UNSAFE_COLLECTION_CHARS.sub("_", collection).strip("._") or "collection"
    return f"{safe[:48]}-{digest}"


class VectorIndex:
    def __init__(self, dim: int) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = int(dim)
        self._records: dict[str, dict[str, _Entry]] = {}

    def upsert(
        self,
        collection: str,
        items: Iterable[IndexItem],
        vectors: list[list[float]] | None = None,
    ) -> int:
        item_list = list(items)
        vector_list = list(vectors) if vectors is not None else None
        if vector_list is not None and len(vector_list) != len(item_list):
            raise ValueError("vectors must align with items")
        records = self._records.setdefault(collection, {})
        for position, item in enumerate(item_list):
            if vector_list is None:
                vector = np.zeros(self.dim, dtype=np.float32)
            else:
                vector = np.asarray(vector_list[position], dtype=np.float32).reshape(-1)
                if vector.shape != (self.dim,):
                    raise ValueError(f"item {item.id!r} has an invalid vector dimension")
            records[item.id] = _Entry(
                vector=vector.copy(),
                text=item.text,
                metadata=dict(item.metadata),
            )
        return len(item_list)

    def remove(self, collection: str, item_id: str) -> bool:
        records = self._records.get(collection)
        if records is None or item_id not in records:
            return False
        del records[item_id]
        if not records:
            self._records.pop(collection, None)
        return True

    def get(self, collection: str, item_id: str) -> IndexItem | None:
        entry = self._records.get(collection, {}).get(item_id)
        if entry is None:
            return None
        return IndexItem(id=item_id, text=entry.text, metadata=dict(entry.metadata))

    def search(
        self,
        collection: str,
        query_vector: list[float] | np.ndarray,
        k: int = 5,
    ) -> list[SearchHit]:
        records = self._records.get(collection)
        if not records or k <= 0:
            return []
        ids = list(records)
        matrix = np.stack([records[item_id].vector for item_id in ids]).astype(np.float32, copy=False)
        query = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        if query.shape != (self.dim,):
            raise ValueError("query_vector dimension does not match index dimension")
        norms = np.linalg.norm(matrix, axis=1)
        denominators = norms * float(np.linalg.norm(query))
        scores = np.zeros(len(ids), dtype=np.float32)
        np.divide(matrix @ query, denominators, out=scores, where=denominators > 0)
        ranked = sorted(zip(ids, scores), key=lambda pair: (-float(pair[1]), pair[0]))
        return [
            SearchHit(
                id=item_id,
                score=round(float(score), 6),
                text=records[item_id].text,
                metadata=dict(records[item_id].metadata),
            )
            for item_id, score in ranked[:k]
        ]

    def count(self, collection: str) -> int:
        return len(self._records.get(collection, {}))

    def collections(self) -> list[str]:
        return sorted(self._records)

    def clear(self, collection: str) -> None:
        self._records.pop(collection, None)

    def persist(self, directory: str | Path) -> Path:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, Any] = {"version": 1, "dim": self.dim, "collections": {}}
        for collection in sorted(self._records):
            records = self._records[collection]
            stem = _collection_stem(collection)
            manifest["collections"][collection] = stem
            ids = list(records)
            if ids:
                matrix = np.stack([records[item_id].vector for item_id in ids]).astype(np.float32, copy=False)
            else:
                matrix = np.zeros((0, self.dim), dtype=np.float32)
            np.savez(target / f"{stem}.npz", ids=np.asarray(ids, dtype=np.str_), vectors=matrix)
            with (target / f"{stem}.jsonl").open("w", encoding="utf-8") as handle:
                for item_id in ids:
                    entry = records[item_id]
                    payload = {"id": item_id, "text": entry.text, "metadata": entry.metadata}
                    handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        manifest_path = target / _MANIFEST_NAME
        temporary = manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        temporary.replace(manifest_path)
        return target

    @classmethod
    def load(cls, directory: str | Path, dim: int) -> VectorIndex:
        source = Path(directory)
        manifest_path = source / _MANIFEST_NAME
        if not manifest_path.exists():
            raise FileNotFoundError(f"No vector index manifest at {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stored_dim = int(manifest.get("dim", dim))
        if stored_dim != dim:
            raise ValueError(f"Persisted index dimension {stored_dim} does not match {dim}")
        index = cls(dim)
        for collection, stem in (manifest.get("collections") or {}).items():
            with np.load(source / f"{stem}.npz", allow_pickle=False) as archive:
                ids = [str(item_id) for item_id in archive["ids"].tolist()]
                matrix = np.asarray(archive["vectors"], dtype=np.float32)
            if matrix.shape != (len(ids), dim):
                raise ValueError(f"Persisted vectors for {collection!r} have an unexpected shape")
            rows = [
                json.loads(line)
                for line in (source / f"{stem}.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if len(rows) != len(ids):
                raise ValueError(f"Persisted rows for {collection!r} are inconsistent")
            records: dict[str, _Entry] = {}
            for position, item_id in enumerate(ids):
                row = rows[position]
                if str(row.get("id")) != item_id:
                    raise ValueError(f"Persisted rows for {collection!r} are misaligned")
                records[item_id] = _Entry(
                    vector=matrix[position].copy(),
                    text=str(row.get("text", "")),
                    metadata=dict(row.get("metadata") or {}),
                )
            index._records[str(collection)] = records
        return index

    @classmethod
    def persisted_dim(cls, directory: str | Path) -> int | None:
        manifest_path = Path(directory) / _MANIFEST_NAME
        if not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        stored_dim = manifest.get("dim")
        if isinstance(stored_dim, bool) or not isinstance(stored_dim, int):
            return None
        return stored_dim


class VectorService:
    def __init__(self, embedder: Embedder, index: VectorIndex | None = None) -> None:
        self.embedder = embedder
        self.index = index if index is not None else VectorIndex(embedder.dim)

    def embed(self, text: str) -> list[float]:
        return [float(component) for component in self.embedder.embed(text)]

    def search(self, collection: str, query: str, k: int = 5) -> list[SearchHit]:
        return self.index.search(collection, self.embed(query), k=k)

    def cosine_distance(self, a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
        first = np.asarray(a, dtype=np.float64).reshape(-1)
        second = np.asarray(b, dtype=np.float64).reshape(-1)
        if first.size == 0 or second.size == 0:
            return 1.0
        if first.size != second.size:
            raise ValueError("vectors must have the same dimension")
        first_norm = float(np.linalg.norm(first))
        second_norm = float(np.linalg.norm(second))
        if first_norm == 0.0 or second_norm == 0.0:
            return 1.0
        cosine = float(np.dot(first, second) / (first_norm * second_norm))
        return float(1.0 - np.clip(cosine, -1.0, 1.0))

    def upsert(self, collection: str, items: Iterable[IndexItem]) -> int:
        item_list = list(items)
        vectors = self.embedder.embed_many([item.text for item in item_list])
        return self.index.upsert(collection, item_list, vectors=vectors)

    def count(self, collection: str) -> int:
        return self.index.count(collection)

    def persist(self, directory: str | Path | None = None) -> Path:
        target = Path(directory) if directory is not None else get_settings().paths.vectors_dir
        return self.index.persist(target)

    @classmethod
    def load_or_create(
        cls,
        directory: str | Path | None = None,
        settings: Settings | None = None,
        force_fallback: bool = False,
    ) -> VectorService:
        resolved = settings or get_settings()
        target = Path(directory) if directory is not None else resolved.paths.vectors_dir
        embedder = build_embedder(settings=resolved, force_fallback=force_fallback)
        persisted_dim = VectorIndex.persisted_dim(target)
        if persisted_dim == embedder.dim:
            try:
                index = VectorIndex.load(target, embedder.dim)
            except Exception as exc:
                logger.warning("Could not load vector index from %s; starting fresh: %s", target, exc)
                index = VectorIndex(embedder.dim)
        else:
            if persisted_dim is not None:
                logger.warning(
                    "Persisted vector index dimension %s does not match embedder dimension %s; starting fresh",
                    persisted_dim,
                    embedder.dim,
                )
            index = VectorIndex(embedder.dim)
        return cls(embedder=embedder, index=index)
