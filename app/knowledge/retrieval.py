from __future__ import annotations

import math
import re
from collections import Counter

from app.knowledge.graph import ToolKnowledgeGraph
from app.schemas import ToolSpec

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "what",
    "which",
    "who",
    "how",
    "my",
    "me",
    "i",
    "we",
    "you",
    "can",
    "do",
    "does",
    "this",
    "that",
    "into",
    "about",
    "using",
}


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in TOKEN_RE.findall(text.lower())
        if token not in STOP_WORDS and len(token) > 1
    ]


class TfidfIndex:
    def __init__(self, documents: dict[str, str]) -> None:
        self.documents = documents
        self.term_frequencies: dict[str, Counter[str]] = {}
        self.vectors: dict[str, dict[str, float]] = {}
        self.idf: dict[str, float] = {}
        self._build()

    def _build(self) -> None:
        total = max(1, len(self.documents))
        document_frequency: Counter[str] = Counter()
        for doc_id, text in self.documents.items():
            tokens = tokenize(text)
            counts = Counter(tokens)
            self.term_frequencies[doc_id] = counts
            document_frequency.update(set(tokens))
        for term, frequency in document_frequency.items():
            self.idf[term] = math.log((1 + total) / (1 + frequency)) + 1.0
        for doc_id, counts in self.term_frequencies.items():
            self.vectors[doc_id] = self._vectorize_counts(counts)

    def _vectorize_counts(self, counts: Counter[str]) -> dict[str, float]:
        if not counts:
            return {}
        max_count = max(counts.values())
        vector: dict[str, float] = {}
        for term, count in counts.items():
            tf = 0.5 + 0.5 * (count / max_count)
            vector[term] = tf * self.idf.get(term, 1.0)
        norm = math.sqrt(sum(value * value for value in vector.values()))
        if norm:
            for term in vector:
                vector[term] /= norm
        return vector

    def vectorize_query(self, query: str) -> dict[str, float]:
        return self._vectorize_counts(Counter(tokenize(query)))

    @staticmethod
    def cosine(left: dict[str, float], right: dict[str, float]) -> float:
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(term, 0.0) for term, value in left.items())

    def search(self, query: str, top_k: int = 8) -> list[tuple[str, float]]:
        query_vector = self.vectorize_query(query)
        scores = [
            (doc_id, self.cosine(query_vector, vector))
            for doc_id, vector in self.vectors.items()
        ]
        scores.sort(key=lambda item: (-item[1], item[0]))
        return scores[:top_k]

    def rank(self, query: str, doc_ids: list[str]) -> list[tuple[str, float]]:
        query_vector = self.vectorize_query(query)
        scores = [
            (doc_id, self.cosine(query_vector, self.vectors.get(doc_id, {})))
            for doc_id in doc_ids
        ]
        scores.sort(key=lambda item: (-item[1], item[0]))
        return scores


class GraphRAGRetriever:
    def __init__(
        self,
        graph: ToolKnowledgeGraph,
        top_k: int = 8,
        expansion: int = 3,
    ) -> None:
        self.graph = graph
        self.top_k = top_k
        self.expansion = expansion
        self.rebuild()

    def rebuild(self) -> None:
        documents = {tool.id: tool.search_text for tool in self.graph.all()}
        self.index = TfidfIndex(documents)

    def search(
        self,
        query: str,
        top_k: int | None = None,
        capability: str | None = None,
        expand: bool = True,
    ) -> list[tuple[ToolSpec, float, list[str]]]:
        limit = top_k or self.top_k
        allowed = {
            tool.id
            for tool in self.graph.all()
            if capability is None or tool.capability == capability
        }
        if not allowed:
            return []
        ranked = [(doc_id, score) for doc_id, score in self.index.search(query, 50) if doc_id in allowed]
        if not ranked:
            ranked = [(doc_id, 0.0) for doc_id in allowed]
        maximum = max((score for _, score in ranked), default=0.0)
        results: dict[str, tuple[float, list[str]]] = {}
        for doc_id, score in ranked[:limit]:
            normalized = (score / maximum) if maximum > 0 else 0.35
            results[doc_id] = (normalized, [f"lexical similarity {score:.2f}"])
        if expand:
            seeds = list(results.keys())[: self.expansion]
            for seed in seeds:
                seed_score = results[seed][0]
                for neighbor in self.graph.neighbors(seed, limit=self.expansion):
                    if capability is not None and neighbor.capability != capability:
                        continue
                    bonus = max(0.35, seed_score * 0.35)
                    if neighbor.id not in results:
                        results[neighbor.id] = (
                            bonus,
                            [f"graph neighbour of {seed}"],
                        )
                    elif results[neighbor.id][0] < bonus:
                        results[neighbor.id] = (
                            bonus,
                            results[neighbor.id][1] + [f"graph neighbour of {seed}"],
                        )
        ordered = sorted(results.items(), key=lambda item: (-item[1][0], item[0]))[:limit]
        output = []
        for doc_id, (score, reasons) in ordered:
            tool = self.graph.get(doc_id)
            if tool is not None:
                output.append((tool, round(score, 4), reasons))
        return output
