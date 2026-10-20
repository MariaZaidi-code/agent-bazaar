"""Mapper agent behind the mapper adapter API of the app.

The app talks to :class:`app.agents.mapper_stub.MapperStub`. This adapter
offers the same API but routes every submission through the knowledge layer's
:class:`agent_bazaar.mapper.agent.MapperAgent` and the SHACL-validated
:class:`agent_bazaar.kg.store.KgStore`.

Differences to the stub that the lead has to know about:

* a listing is mapped by the Mapper and, when every field passes the ontology
  checks, written to the RDF graph through ``KgStore.write_tool``. A rejected
  listing is rolled back and never reaches the graph;
* a correction is validated by the Mapper, promoted into its correction memory
  and, when the rules pass, applied to the graph through
  ``KgStore.update_mapping``;
* ``staged`` keeps the meaning of the stub: the submission is recorded in the
  staging ledger of the adapter. The knowledge layer promotes a submission
  right away, so the promotion state is reported in the message and in the
  ledger instead of in the flag.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent_bazaar.ingestion.models import FieldInfo, NormalizedSpec
from agent_bazaar.kg import GraphValidationError, KgStore
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.messages.schema import MapResult
from agent_bazaar.models import ConceptInfo
from agent_bazaar.ontology.ns import AB, tool_iri
from agent_bazaar.ontology.units import family_of
from app.agents.mapper_stub import MapperStub
from app.integration.canonical import (
    canonical_capability,
    canonical_concept,
    canonical_unit,
    concept_iri,
    is_external_concept,
    is_known_unit,
)
from app.integration.messages import (
    build_field_path,
    concept_specs_to_field_specs,
    correction_request_to_submit,
    field_name_from_path,
    local_name,
    to_canonical_specs,
    to_correction_result,
    to_map_result_message,
)
from app.schemas import (
    ConceptSpec,
    CorrectionRequest,
    CorrectionResult,
    ListingIngestRequest,
    MapResultMessage,
)

PROVIDER_ID = "pending-provider"


def _status_value(status: Any) -> str:
    return status.value if hasattr(status, "value") else str(status)


class KnowledgeMapper:
    """Adapter that runs the knowledge layer's Mapper behind the app's API."""

    def __init__(
        self,
        mapper: MapperAgent,
        store: KgStore,
        *,
        local_stub: MapperStub | None = None,
    ) -> None:
        self.mapper = mapper
        self.store = store
        self.local_stub = local_stub
        self.corrections: list[dict[str, Any]] = []
        self.listings: list[dict[str, Any]] = []

    def submit_listing(self, request: ListingIngestRequest, correlation_id: str) -> MapResultMessage:
        """Map a submitted listing and promote it into the knowledge graph."""
        tool_id = f"listing_{uuid4().hex[:10]}"
        result = MapResult(tool_id=tool_id, correlation_id=correlation_id)
        spec, declared = self._build_spec(request, tool_id)
        violations = self._validate_declarations(request)
        promoted = False
        if not violations:
            snapshot = self.store.graph
            result = self.mapper.map_spec(spec, tool_id=tool_id).model_copy(
                update={"correlation_id": correlation_id}
            )
            violations.extend(self._validate_result(result, declared))
            if not violations:
                try:
                    promoted = self._promote_listing(spec, result, request)
                except GraphValidationError as error:
                    violations.append(f"the listing does not fit the graph: {error}")
            if violations:
                self.store.graph = snapshot
        external = self._external_specs(declared, result)
        message = to_map_result_message(
            result,
            tool_id,
            violations,
            data_types=self._data_types(),
            extra_inputs=external["input"],
            extra_outputs=external["output"],
        )
        self.listings.append(
            {
                "tool_id": tool_id,
                "name": request.name,
                "capability": canonical_capability(request.capability),
                "status": self._listing_status(message.accepted, promoted),
                "staged": message.staged,
                "promoted": promoted,
                "submitted_at": datetime.now(UTC).isoformat(),
                "correlation_id": correlation_id,
                "violations": list(violations),
                "inputs": [item.model_dump(mode="json") for item in message.inputs],
                "outputs": [item.model_dump(mode="json") for item in message.outputs],
            }
        )
        return message

    def submit_correction(self, request: CorrectionRequest, correlation_id: str) -> CorrectionResult:
        """Validate a correction, promote it and apply it to the graph."""
        correction_id = f"corr_{uuid4().hex[:10]}"
        violations = self._validate_correction(request)
        status = "rejected"
        reason = "; ".join(violations)
        stats: dict[str, Any] = {}
        field_path = ""
        if not violations:
            field_path = self._resolve_field_path(request)
            submit = correction_request_to_submit(request, field_path=field_path).model_copy(
                update={"correlation_id": correlation_id}
            )
            decision = self.mapper.submit_correction(submit)
            status = str(decision.get("status") or "pending_review")
            reason = str(decision.get("reason") or "")
            stats = dict(decision.get("stats") or {})
            if status == "promoted":
                error = self._apply_correction(request, field_path)
                if error:
                    status = "rejected"
                    reason = error
            violations = [] if status == "promoted" else [reason or "the correction was not promoted"]
        accepted = status == "promoted"
        message = self._correction_message(status, reason)
        result = to_correction_result(
            correction_id,
            accepted,
            accepted or status == "pending_review",
            violations,
            message,
        )
        self.corrections.append(
            {
                "correction_id": correction_id,
                "tool_id": request.tool_id,
                "field_name": request.field_name,
                "field_path": field_path,
                "original_concept": request.original_concept,
                "corrected_concept": request.corrected_concept,
                "corrected_unit": request.corrected_unit,
                "note": request.note,
                "status": status,
                "staged": result.staged,
                "created_at": datetime.now(UTC).isoformat(),
                "correlation_id": correlation_id,
                "violations": list(violations),
                "stats": stats,
            }
        )
        return result

    def staged(self) -> dict[str, Any]:
        """Return the submitted listings and corrections for inspection."""
        return {"corrections": self.corrections, "listings": self.listings}

    def reset(self) -> None:
        """Clear the staging ledger. The knowledge graph is never touched."""
        self.corrections.clear()
        self.listings.clear()

    def _concept_info(self, concept: str | None) -> ConceptInfo | None:
        if not concept:
            return None
        return self.store.get_concept(concept_iri(canonical_concept(concept)))

    def _data_types(self) -> dict[str, str]:
        return {local_name(concept.iri): concept.data_type for concept in self.store.list_concepts()}

    def _validate_declarations(self, request: ListingIngestRequest) -> list[str]:
        violations: list[str] = []
        for direction, concepts in (("input", request.inputs), ("output", request.outputs)):
            for concept in concepts:
                violations.extend(self._validate_concept(concept, direction))
        return violations

    def _validate_concept(self, concept: ConceptSpec, direction: str) -> list[str]:
        name = str(concept.concept or "").strip()
        if not name:
            return [f"{direction} field {concept.name or '?'} has no concept"]
        canonical = canonical_concept(name)
        if is_external_concept(canonical):
            if self.local_stub is not None and not self.local_stub.ontology.exists(name):
                return [f"{direction} concept {name} is unknown to the local ontology"]
            return []
        info = self._concept_info(canonical)
        if info is None:
            return [f"{direction} concept {name} is unknown to the knowledge layer"]
        unit = canonical_unit(concept.unit)
        if unit is None:
            return []
        if not is_known_unit(unit):
            return [f"{direction} unit {concept.unit} is unknown to the knowledge layer"]
        if info.unit_family and family_of(unit) != info.unit_family:
            return [
                f"{direction} unit {concept.unit} does not match the unit family "
                f"{info.unit_family} of concept {canonical}"
            ]
        return []

    def _validate_result(
        self,
        result: MapResult,
        declared: dict[str, ConceptSpec],
    ) -> list[str]:
        violations: list[str] = []
        mapped = {mapping.field_path for mapping in result.mappings}
        for mapping in result.mappings:
            if _status_value(mapping.status) == "unmapped":
                if self._is_external_field(mapping.field_path, declared):
                    continue
                reason = f": {mapping.reason}" if mapping.reason else ""
                violations.append(
                    f"field {mapping.field_path} could not be mapped to a known concept{reason}"
                )
                continue
            info = self._concept_info(mapping.concept)
            if info is None:
                violations.append(f"concept {mapping.concept} is unknown to the knowledge layer")
                continue
            unit = canonical_unit(mapping.unit)
            if unit is None:
                if info.unit_bearing:
                    violations.append(
                        f"concept {info.label} requires a unit from {info.unit_family or 'its unit family'}"
                    )
                continue
            if not is_known_unit(unit):
                violations.append(f"unit {mapping.unit} is unknown to the knowledge layer")
                continue
            if info.unit_family and family_of(unit) != info.unit_family:
                violations.append(
                    f"unit {mapping.unit} does not match the unit family "
                    f"{info.unit_family} of concept {info.label}"
                )
        for field in result.unmapped:
            if field.field_path in mapped:
                continue
            if self._is_external_field(field.field_path, declared):
                continue
            violations.append(f"field {field.field_path} could not be mapped to a known concept")
        return violations

    @staticmethod
    def _is_external_field(field_path: str, declared: dict[str, ConceptSpec]) -> bool:
        """True when a field declares a concept the knowledge layer does not know."""
        concept = declared.get(field_path)
        if concept is None:
            return False
        return is_external_concept(canonical_concept(concept.concept))

    def _external_specs(
        self,
        declared: dict[str, ConceptSpec],
        result: MapResult,
    ) -> dict[str, list[ConceptSpec]]:
        """Collect the declared fields whose concept is external to the knowledge layer."""
        mapped = {
            mapping.field_path
            for mapping in result.mappings
            if _status_value(mapping.status) != "unmapped"
        }
        collected: dict[str, list[ConceptSpec]] = {"input": [], "output": []}
        for path, concept in declared.items():
            if path in mapped or not self._is_external_field(path, declared):
                continue
            direction = "input" if path.startswith("input.") else "output"
            collected[direction].append(concept)
        return {
            direction: to_canonical_specs(concepts) for direction, concepts in collected.items()
        }

    def _build_spec(
        self,
        request: ListingIngestRequest,
        tool_id: str,
    ) -> tuple[NormalizedSpec, dict[str, ConceptSpec]]:
        """Build the knowledge-layer field set of a listing.

        The declared concept of every field is kept next to its field path so
        the adapter can tell an unmapped field apart from a field whose
        concept is external to the knowledge layer.
        """
        data_types = self._data_types()
        fields: list[FieldInfo] = []
        declared: dict[str, ConceptSpec] = {}
        for direction, concepts in (("input", request.inputs), ("output", request.outputs)):
            specs = concept_specs_to_field_specs(concepts, direction=direction, data_types=data_types)
            for spec, concept in zip(specs, concepts, strict=False):
                declared[spec.field_path] = concept
                fields.append(
                    FieldInfo(
                        path=spec.field_path,
                        name=spec.name,
                        type=spec.type,
                        description=spec.description,
                        direction=spec.direction,
                        required=spec.required,
                    )
                )
        spec = NormalizedSpec(
            tool_id=tool_id,
            source="app:listing",
            spec_format="text",
            title=request.name,
            description=request.description,
            base_url=request.docs_url,
            provider_id=PROVIDER_ID,
            fields=fields,
            metadata={
                "capability": canonical_capability(request.capability),
                "docs_url": request.docs_url,
            },
        )
        return spec, declared

    def _promote_listing(
        self,
        spec: NormalizedSpec,
        result: MapResult,
        request: ListingIngestRequest,
    ) -> bool:
        """Write a mapped listing into the graph. False when nothing can be written."""
        record = self.mapper.listing_to_tool_record(
            spec,
            result,
            capability_hints=[canonical_capability(request.capability)],
            provider_id=spec.provider_id,
        )
        if not record.outputs:
            return False
        self.store.write_tool(record)
        return True

    @staticmethod
    def _listing_status(accepted: bool, promoted: bool) -> str:
        if not accepted:
            return "rejected"
        return "promoted" if promoted else "staged"

    def _validate_correction(self, request: CorrectionRequest) -> list[str]:
        violations: list[str] = []
        if not self._known_tool(request.tool_id):
            violations.append(f"Unknown tool {request.tool_id}")
        original = canonical_concept(request.original_concept)
        if original and not is_external_concept(original) and self._concept_info(original) is None:
            violations.append(f"Unknown original concept {request.original_concept}")
        corrected = canonical_concept(request.corrected_concept)
        if not corrected:
            violations.append("The correction has no corrected concept")
            return violations
        if is_external_concept(corrected):
            return violations
        info = self._concept_info(corrected)
        if info is None:
            violations.append(f"Unknown corrected concept {request.corrected_concept}")
            return violations
        unit = canonical_unit(request.corrected_unit)
        if unit is None:
            return violations
        if not is_known_unit(unit):
            violations.append(f"Unknown unit {request.corrected_unit}")
            return violations
        if info.unit_family and family_of(unit) != info.unit_family:
            violations.append(
                f"Unit {request.corrected_unit} does not match the unit family "
                f"{info.unit_family} of concept {corrected}"
            )
        return violations

    def _known_tool(self, tool_id: str) -> bool:
        if any(tool.tool_id == tool_id for tool in self.store.list_tools()):
            return True
        if self.local_stub is not None:
            return self.local_stub.graph.get(tool_id) is not None
        return False

    def _tool_fields(self, tool_id: str) -> list[tuple[str, str]]:
        tool = tool_iri(tool_id)
        fields: list[tuple[str, str]] = []
        for mapping in self.store.graph.subjects(AB.tool, tool):
            path = self.store.graph.value(mapping, AB.fieldPath)
            if path is None:
                continue
            concept = self.store.graph.value(mapping, AB.mapsTo)
            fields.append((str(path), local_name(concept) if concept is not None else ""))
        return sorted(fields)

    def _resolve_field_path(self, request: CorrectionRequest) -> str:
        """Resolve the knowledge-layer field path a correction refers to.

        The app addresses a field by name, the knowledge layer by path. The
        path is looked up in the graph of the tool (exact path, field name or
        mapped concept) and, when the tool is only known to the local app
        graph, rebuilt from the field name. When nothing matches, the field
        name is used verbatim.
        """
        field_name = str(request.field_name or "").strip()
        fields = self._tool_fields(request.tool_id)
        for path, _ in fields:
            if path == field_name:
                return path
        for path, _ in fields:
            if field_name_from_path(path) == field_name:
                return path
        original = canonical_concept(request.original_concept)
        for path, concept in fields:
            if original and canonical_concept(concept) == original:
                return path
        if self.local_stub is not None:
            tool = self.local_stub.graph.get(request.tool_id)
            if tool is not None:
                for direction, concepts in (("input", tool.inputs), ("output", tool.outputs)):
                    for concept in concepts:
                        name = concept.name or concept.concept
                        if name == field_name or concept.concept == field_name:
                            return build_field_path(direction, name)
        return field_name

    def _field_direction(self, tool_id: str, field_path: str) -> str:
        tool = tool_iri(tool_id)
        for mapping in self.store.graph.subjects(AB.tool, tool):
            path = self.store.graph.value(mapping, AB.fieldPath)
            if path is None or str(path) != field_path:
                continue
            direction = self.store.graph.value(mapping, AB.direction)
            if direction is not None:
                return str(direction)
        return "input" if field_path.startswith("input.") else "output"

    def _apply_correction(self, request: CorrectionRequest, field_path: str) -> str:
        """Apply a promoted correction to the graph through the validated store."""
        concept = canonical_concept(request.corrected_concept)
        unit = canonical_unit(request.corrected_unit)
        try:
            self.store.update_mapping(
                request.tool_id,
                field_path,
                concept_iri(concept),
                unit,
                provenance={
                    "who": "correction",
                    "why": request.note or f"corrected to {concept}",
                    "confidence": 1.0,
                    "status": "corrected",
                    "direction": self._field_direction(request.tool_id, field_path),
                },
            )
        except GraphValidationError as error:
            return f"the correction does not fit the graph: {error}"
        return ""

    @staticmethod
    def _correction_message(status: str, reason: str) -> str:
        if status == "promoted":
            return "Correction passed the ontology checks and was applied to the knowledge graph."
        label = (
            "Correction was queued for review."
            if status == "pending_review"
            else "Correction rejected by the ontology checks."
        )
        return f"{label} {reason}".strip() if reason else label
