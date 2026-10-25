from __future__ import annotations

from dataclasses import dataclass, field

from .embeddings import EmbeddingModel, HashingEmbedder, cosine_similarity


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    score: float

    def to_dict(self) -> dict[str, object]:
        return {"chunk_id": self.chunk_id, "text": self.text, "score": self.score}


@dataclass
class VectorIndex:
    embedder: EmbeddingModel = field(default_factory=HashingEmbedder)
    entries: list[tuple[str, str, list[float]]] = field(default_factory=list)

    def add(self, chunk_id: str, text: str) -> None:
        self.entries.append((chunk_id, text, self.embedder.embed(text)))

    def extend(self, chunks: list[str], prefix: str = "chunk") -> None:
        for index, chunk in enumerate(chunks):
            self.add(f"{prefix}-{index}", chunk)

    def search(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        if not self.entries:
            return []
        query_vector = self.embedder.embed(query)
        scored = [
            RetrievedChunk(chunk_id, text, cosine_similarity(query_vector, vector))
            for chunk_id, text, vector in self.entries
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(1, top_k)]

    def clear(self) -> None:
        self.entries.clear()


class DocumentRetriever:
    def __init__(self, embedder: EmbeddingModel | None = None, top_k: int = 3) -> None:
        self.embedder = embedder or HashingEmbedder()
        self.top_k = top_k

    def retrieve(self, query: str, chunks: list[str], top_k: int | None = None) -> list[str]:
        if not chunks:
            return []
        index = VectorIndex(self.embedder)
        index.extend(chunks)
        limit = top_k or self.top_k
        selected = index.search(query, top_k=limit)
        return [item.text for item in selected]

    def retrieve_scored(self, query: str, chunks: list[str], top_k: int | None = None) -> list[RetrievedChunk]:
        if not chunks:
            return []
        index = VectorIndex(self.embedder)
        index.extend(chunks)
        return index.search(query, top_k=top_k or self.top_k)
