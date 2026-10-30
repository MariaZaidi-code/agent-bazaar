"""LLM prompt mapping and the deterministic offline heuristic fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_bazaar.config import Settings, get_settings
from agent_bazaar.llm.client import LLMError
from agent_bazaar.mapper.retriever import MappingRetriever, RetrievedContext
from agent_bazaar.messages.schema import FieldSpec
from agent_bazaar.models import ConceptInfo
from agent_bazaar.ontology.units import UNIT_FAMILIES
from agent_bazaar.protocols import LLMClient


class MappingLLMError(Exception):
    pass


class LLMDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    field_path: str
    concept: str = ""
    unit: str | None = None
    confidence: float = 0.0
    reason: str = ""
    unmapped: bool = False


class LLMDecisionBatch(BaseModel):
    model_config = ConfigDict(extra="allow")

    decisions: list[LLMDecision] = Field(default_factory=list)


def _local_name(reference: str) -> str:
    text = reference.strip()
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    if "/" in text:
        return text.rstrip("/").rsplit("/", 1)[-1]
    if ":" in text:
        return text.rsplit(":", 1)[-1]
    return text


def resolve_concept(
    reference: str,
    concepts_by_iri: dict[str, ConceptInfo],
    concept_iris: dict[str, str],
) -> ConceptInfo | None:
    text = (reference or "").strip()
    if not text:
        return None
    if text in concepts_by_iri:
        return concepts_by_iri[text]
    iri = concept_iris.get(text.lower())
    if iri is not None:
        return concepts_by_iri.get(iri)
    iri = concept_iris.get(_local_name(text).lower())
    if iri is not None:
        return concepts_by_iri.get(iri)
    lowered = text.lower()
    for concept in concepts_by_iri.values():
        candidates = {
            concept.iri.lower(),
            concept.label.lower(),
            _local_name(concept.iri).lower(),
            *(alias.lower() for alias in concept.aliases),
        }
        if lowered in candidates:
            return concept
    return None


class PromptMapper:
    def __init__(
        self,
        client: LLMClient,
        retriever: MappingRetriever,
        settings: Settings | None = None,
    ) -> None:
        self.client = client
        self.retriever = retriever
        self.settings = settings or get_settings()

    def _system_prompt(self) -> str:
        return (
            "You are the Mapper agent of Agent Bazaar. Map each field to exactly one ontology "
            "concept from the candidates provided for that field whenever one fits. The ontology "
            "now covers Media, Event, Organization, Person, Product and Location concept families "
            "in addition to the original geo, weather, currency and reference concepts. Propose "
            "a unit only when the concept is unit-bearing, and only a unit from the concept's "
            "unit family, including the new rating, data-size and frequency units. Give a "
            "confidence between 0 and 1 and a short reason. Set unmapped to true only when "
            "nothing fits. Return JSON only, matching the LLMDecisionBatch schema with one "
            "decision per field."
        )

    @staticmethod
    def _term_payload(hit: Any) -> dict[str, Any]:
        metadata = dict(getattr(hit, "metadata", {}) or {})
        return {
            "label": metadata.get("label") or getattr(hit, "text", ""),
            "iri": metadata.get("iri", ""),
            "type": metadata.get("data_type", ""),
            "unit_family": metadata.get("unit_family") or "-",
        }

    def _correction_line(self, hit: Any) -> str:
        metadata = dict(getattr(hit, "metadata", {}) or {})
        field_path = metadata.get("field_path", "")
        concept = metadata.get("concept", "")
        unit = metadata.get("unit") or ""
        if field_path or concept:
            return f"{field_path} -> {concept} {unit}".strip()
        return str(getattr(hit, "text", ""))

    def _user_prompt(
        self,
        fields: list[FieldSpec],
        tool_id: str,
        context: dict[str, RetrievedContext],
    ) -> str:
        limit = self.settings.mapper.top_k_corrections
        payload_fields: list[dict[str, Any]] = []
        for field in fields:
            retrieved = context.get(field.field_path)
            terms = [self._term_payload(hit) for hit in (retrieved.terms if retrieved else [])]
            corrections = [
                self._correction_line(hit)
                for hit in (retrieved.corrections[:limit] if retrieved else [])
            ]
            payload_fields.append(
                {
                    "field_path": field.field_path,
                    "name": field.name,
                    "type": field.type,
                    "description": field.description,
                    "sample_value": field.sample_value,
                    "candidates": terms,
                    "corrections": corrections,
                }
            )
        payload = {"tool_id": tool_id, "fields": payload_fields}
        return (
            "Map these fields using the retrieved ontology candidates and stored corrections. "
            "Return one decision per field.\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        )

    def propose(
        self,
        fields: list[FieldSpec],
        tool_id: str,
        context: dict[str, RetrievedContext] | None = None,
    ) -> dict[str, LLMDecision]:
        if not fields:
            return {}
        if context is None:
            context = {field.field_path: self.retriever.retrieve(field) for field in fields}
        system = self._system_prompt()
        user = self._user_prompt(fields, tool_id, context)
        try:
            batch = self.client.complete_json(system, user, LLMDecisionBatch, use_cache=True)
            if isinstance(batch, dict):
                batch = LLMDecisionBatch.model_validate(batch)
        except (LLMError, ValidationError) as error:
            raise MappingLLMError(str(error)) from error

        decisions = {decision.field_path: decision for decision in batch.decisions}
        result: dict[str, LLMDecision] = {}
        for field in fields:
            decision = decisions.get(field.field_path)
            if decision is None:
                decision = LLMDecision(
                    field_path=field.field_path,
                    unmapped=True,
                    reason="no decision returned by the model",
                )
            result[field.field_path] = decision
        return result


STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "value",
        "data",
        "field",
        "result",
        "info",
    }
)
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _tokens(text: str) -> set[str]:
    expanded = _CAMEL_BOUNDARY.sub(" ", str(text or ""))
    return {
        token
        for token in _NON_ALNUM.split(expanded.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _normalized(text: str) -> str:
    return _NON_ALNUM.sub("", str(text or "").lower())


class HeuristicMapper:
    def __init__(
        self,
        concepts: list[ConceptInfo] | None = None,
        retriever: MappingRetriever | None = None,
    ) -> None:
        self.concepts = list(concepts or [])
        self.retriever = retriever

    def _candidates(self, context: dict[str, RetrievedContext] | None) -> list[ConceptInfo]:
        if self.concepts:
            return self.concepts
        if self.retriever is not None and self.retriever.concepts:
            return list(self.retriever.concepts.values())
        derived: dict[str, ConceptInfo] = {}
        for retrieved in (context or {}).values():
            for hit in retrieved.terms:
                metadata = dict(hit.metadata or {})
                iri = str(metadata.get("iri") or "")
                if not iri:
                    continue
                derived.setdefault(
                    iri,
                    ConceptInfo(
                        iri=iri,
                        label=str(metadata.get("label") or _local_name(iri)),
                        data_type=str(metadata.get("data_type") or "string"),
                        unit_family=metadata.get("unit_family"),
                        unit_bearing=bool(metadata.get("unit_bearing")),
                        aliases=list(metadata.get("aliases") or []),
                    ),
                )
        return list(derived.values())

    @staticmethod
    def _default_unit(concept: ConceptInfo) -> str | None:
        if not concept.unit_bearing:
            return None
        if concept.unit:
            return concept.unit
        family = UNIT_FAMILIES.get(concept.unit_family or "")
        return str(family["canonical"]) if family else None

    def propose(
        self,
        fields: list[FieldSpec],
        tool_id: str,
        context: dict[str, RetrievedContext] | None = None,
    ) -> dict[str, LLMDecision]:
        candidates = sorted(
            self._candidates(context),
            key=lambda concept: _local_name(concept.iri).lower(),
        )
        decisions: dict[str, LLMDecision] = {}
        for field in fields:
            field_tokens = _tokens(field.name) | _tokens(field.description)
            field_name = _normalized(field.name)
            best: ConceptInfo | None = None
            best_score = 0.0
            best_bonus = 0.0
            best_overlap: set[str] = set()
            for concept in candidates:
                concept_tokens = _tokens(concept.label) | _tokens(_local_name(concept.iri))
                for alias in concept.aliases:
                    concept_tokens |= _tokens(alias)
                if not field_tokens or not concept_tokens:
                    continue
                overlap = field_tokens & concept_tokens
                if not overlap:
                    continue
                base = len(overlap) / min(len(field_tokens), len(concept_tokens))
                bonus = 0.0
                if field_name:
                    if field_name in {
                        _normalized(_local_name(concept.iri)),
                        _normalized(concept.label),
                    }:
                        bonus = 0.4
                    elif any(field_name == _normalized(alias) for alias in concept.aliases):
                        bonus = 0.2
                score = base + bonus
                if score > best_score:
                    best = concept
                    best_score = score
                    best_bonus = bonus
                    best_overlap = set(overlap)
            if best is None or best_score < 0.34:
                decisions[field.field_path] = LLMDecision(
                    field_path=field.field_path,
                    unmapped=True,
                    confidence=0.0,
                    reason="no ontology concept shares tokens with this field",
                )
                continue
            unit = self._default_unit(best) if best.unit_bearing else None
            decisions[field.field_path] = LLMDecision(
                field_path=field.field_path,
                concept=best.iri,
                unit=unit,
                confidence=round(min(0.9, 0.4 + best_score), 2),
                reason=(
                    f"token overlap {sorted(best_overlap)} with {best.label}"
                    + (" and an exact name match" if best_bonus > 0 else "")
                ),
            )
        return decisions
