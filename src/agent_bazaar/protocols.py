"""Frozen interface contracts between knowledge layer components.

Implementations live in vec/, kg/, ingestion/ and llm/. The Mapper and the
evaluation harness code against these Protocols, which keeps the integration
contract stable while components are developed independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable

from pydantic import BaseModel

from agent_bazaar.models import ConceptInfo, ToolQualityProfile, ToolRecord, ToolSummary

ONTOLOGY_TERMS = "ontology_terms"
TOOL_DESCRIPTIONS = "tool_descriptions"
CORRECTIONS = "corrections"


@dataclass(frozen=True)
class SearchHit:
    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IndexItem:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Violation:
    message: str
    focus_node: str = ""
    path: str = ""
    severity: str = "Violation"
    source: str = ""
    value: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "message": self.message,
            "focus_node": self.focus_node,
            "path": self.path,
            "severity": self.severity,
            "source": self.source,
            "value": self.value,
        }


@dataclass(frozen=True)
class ValidationResult:
    conforms: bool
    violations: list[Violation] = field(default_factory=list)
    report_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conforms": self.conforms,
            "violation_count": len(self.violations),
            "violations": [v.to_dict() for v in self.violations],
        }


class IngestionError(Exception):
    def __init__(self, code: str, message: str, source: str = "", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.source = source
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "source": self.source, "details": self.details}}


@runtime_checkable
class VectorService(Protocol):
    def embed(self, text: str) -> list[float]:
        ...

    def search(self, collection: str, query: str, k: int = 5) -> list[SearchHit]:
        ...

    def cosine_distance(self, a: list[float] | Any, b: list[float] | Any) -> float:
        ...

    def upsert(self, collection: str, items: Iterable[IndexItem]) -> int:
        ...

    def count(self, collection: str) -> int:
        ...


@runtime_checkable
class LLMClient(Protocol):
    def complete_text(self, system: str, user: str, *, use_cache: bool = True, temperature: float | None = None) -> str:
        ...

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        *,
        use_cache: bool = True,
        temperature: float | None = None,
    ) -> Any:
        ...

    @property
    def stats(self) -> dict[str, Any]:
        ...


@runtime_checkable
class Ingester(Protocol):
    def ingest(self, source: str | Path, spec_format: str = "auto") -> Any:
        ...


@runtime_checkable
class MapperService(Protocol):
    def map_fields(self, request) -> Any:
        ...

    def submit_correction(self, correction) -> Any:
        ...

    def handle_drift_alert(self, alert) -> Any:
        ...

    def reindex(self) -> None:
        ...


@runtime_checkable
class GraphStore(Protocol):
    def write_tool(self, record: ToolRecord) -> None:
        ...

    def tools_by_capability(self, capability: str) -> list[ToolSummary]:
        ...

    def tools_by_io(self, input_concept: str, output_concept: str) -> list[ToolSummary]:
        ...

    def compatible_substitutes(self, tool_id: str) -> list[ToolSummary]:
        ...

    def concept_for_field(self, tool_id: str, field_path: str) -> str | None:
        ...

    def get_concept(self, iri: str) -> ConceptInfo | None:
        ...

    def list_concepts(self) -> list[ConceptInfo]:
        ...

    def list_tools(self) -> list[ToolSummary]:
        ...

    def tool_quality_profile(self, tool_id: str) -> ToolQualityProfile:
        ...

    def tools_by_access(self, access_requirement: str) -> list[ToolSummary]:
        ...

    def tools_by_pricing_tier(self, tier: str) -> list[ToolSummary]:
        ...

    def executable_tools(self) -> list[ToolSummary]:
        ...

    def candidate_facts(self, tool_ids: list[str]) -> dict[str, ToolQualityProfile]:
        ...

    def update_mapping(
        self,
        tool_id: str,
        field_path: str,
        concept: str,
        unit: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> bool:
        ...

    def validate(self) -> ValidationResult:
        ...

    def save(self, path: str | Path | None = None) -> Path:
        ...
