from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.knowledge.graph import ToolKnowledgeGraph
from app.knowledge.ontology import Ontology
from app.schemas import (
    ClaimSpec,
    ConceptSpec,
    CorrectionRequest,
    CorrectionResult,
    ListingIngestRequest,
    MapResultMessage,
    ToolSpec,
)


class MapperStub:
    """Staging-only adapter for Maria's Mapper.

    It validates submitted listings, mappings and corrections against the current
    ontology and keeps them staged. The real Mapper owns promotion and learning.
    """

    def __init__(self, graph: ToolKnowledgeGraph, ontology: Ontology) -> None:
        self.graph = graph
        self.ontology = ontology
        self.corrections: list[dict[str, Any]] = []
        self.listings: list[dict[str, Any]] = []

    def submit_listing(
        self, request: ListingIngestRequest, correlation_id: str
    ) -> MapResultMessage:
        tool_id = f"listing_{uuid4().hex[:10]}"
        spec = ToolSpec(
            id=tool_id,
            name=request.name,
            provider_id="pending-provider",
            description=request.description,
            capability=request.capability,
            inputs=request.inputs,
            outputs=request.outputs,
            claims=[
                ClaimSpec(text=claim.text, evidence=claim.evidence)
                for claim in request.claims
            ],
            docs_url=request.docs_url,
            execution="fixture",
        )
        violations = self.ontology.validate_tool(spec)
        accepted = not violations
        if accepted:
            self.listings.append(
                {
                    "tool_id": tool_id,
                    "name": spec.name,
                    "capability": spec.capability,
                    "status": "staged",
                    "submitted_at": datetime.now(UTC).isoformat(),
                    "correlation_id": correlation_id,
                }
            )
        return MapResultMessage(
            sender="mapper",
            recipient="client",
            correlation_id=correlation_id,
            tool_id=tool_id,
            inputs=spec.inputs,
            outputs=spec.outputs,
            violations=violations,
            accepted=accepted,
            staged=accepted,
        )

    def submit_correction(
        self, request: CorrectionRequest, correlation_id: str
    ) -> CorrectionResult:
        violations: list[str] = []
        if not self.ontology.exists(request.original_concept):
            violations.append(f"Unknown original concept {request.original_concept}")
        if not self.ontology.exists(request.corrected_concept):
            violations.append(f"Unknown corrected concept {request.corrected_concept}")
        if request.corrected_unit and request.corrected_unit not in self.ontology.units:
            violations.append(f"Unknown unit {request.corrected_unit}")
        tool = self.graph.get(request.tool_id)
        if tool is None:
            violations.append(f"Unknown tool {request.tool_id}")
        else:
            names = {item.name or item.concept for item in tool.inputs + tool.outputs}
            if request.field_name not in names:
                violations.append(f"Field {request.field_name} is not on {request.tool_id}")
        correction_id = f"corr_{uuid4().hex[:10]}"
        accepted = not violations
        if accepted:
            self.corrections.append(
                {
                    "correction_id": correction_id,
                    "tool_id": request.tool_id,
                    "field_name": request.field_name,
                    "original_concept": request.original_concept,
                    "corrected_concept": request.corrected_concept,
                    "corrected_unit": request.corrected_unit,
                    "note": request.note,
                    "status": "staged",
                    "created_at": datetime.now(UTC).isoformat(),
                    "correlation_id": correlation_id,
                }
            )
        return CorrectionResult(
            correction_id=correction_id,
            accepted=accepted,
            staged=accepted,
            violations=violations,
            message=(
                "Correction passed ontology checks and is staged for the Mapper."
                if accepted
                else "Correction rejected by ontology checks."
            ),
        )

    def staged(self) -> dict[str, Any]:
        return {"corrections": self.corrections, "listings": self.listings}

    def reset(self) -> None:
        self.corrections.clear()
        self.listings.clear()


def concept_from_payload(payload: dict[str, Any]) -> ConceptSpec:
    return ConceptSpec.model_validate(payload)
