"""Retrieval of similar ontology terms and stored corrections for mapping."""

from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict

from agent_bazaar.config import get_settings
from agent_bazaar.mapper.memory import CorrectionEntry, _correction_item
from agent_bazaar.messages.schema import FieldSpec
from agent_bazaar.models import ConceptInfo
from agent_bazaar.protocols import CORRECTIONS, ONTOLOGY_TERMS, IndexItem, SearchHit, VectorService


class RetrievedContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    terms: list[SearchHit]
    corrections: list[SearchHit]
    query: str


def _local_name(iri: str) -> str:
    if "#" in iri:
        return iri.rsplit("#", 1)[-1]
    if "/" in iri:
        return iri.rstrip("/").rsplit("/", 1)[-1]
    return iri


class MappingRetriever:
    def __init__(
        self,
        vector: VectorService,
        top_k_terms: int | None = None,
        top_k_corrections: int | None = None,
    ) -> None:
        settings = get_settings()
        self.vector = vector
        self.top_k_terms = top_k_terms if top_k_terms is not None else settings.mapper.top_k_terms
        self.top_k_corrections = (
            top_k_corrections
            if top_k_corrections is not None
            else settings.mapper.top_k_corrections
        )
        self.concepts: dict[str, ConceptInfo] = {}

    def query_text(self, field: FieldSpec) -> str:
        parts = [field.name, field.type, field.description, str(field.sample_value)]
        return " ".join(part.strip() for part in parts if part and part.strip())

    def retrieve(self, field: FieldSpec) -> RetrievedContext:
        query = self.query_text(field)
        terms = self.vector.search(ONTOLOGY_TERMS, query, k=self.top_k_terms)
        corrections = self.vector.search(CORRECTIONS, query, k=self.top_k_corrections)
        return RetrievedContext(terms=terms, corrections=corrections, query=query)

    def ensure_index(self, concepts: list[ConceptInfo]) -> int:
        items: list[IndexItem] = []
        for concept in concepts:
            local = _local_name(concept.iri)
            items.append(
                IndexItem(
                    id=f"concept-{local}",
                    text=(
                        f"{concept.label} ({local}) type {concept.data_type} "
                        f"aliases: {concept.aliases} unitfamily {concept.unit_family or '-'}"
                    ),
                    metadata={
                        "iri": concept.iri,
                        "label": concept.label,
                        "local": local,
                        "data_type": concept.data_type,
                        "unit_family": concept.unit_family,
                        "unit_bearing": concept.unit_bearing,
                        "aliases": list(concept.aliases),
                        "kind": "concept",
                    },
                )
            )
            self.concepts[concept.iri] = concept
        return self.vector.upsert(ONTOLOGY_TERMS, items)

    def index_corrections(self, entries: Iterable[CorrectionEntry]) -> int:
        items = [_correction_item(entry) for entry in entries]
        return self.vector.upsert(CORRECTIONS, items)
