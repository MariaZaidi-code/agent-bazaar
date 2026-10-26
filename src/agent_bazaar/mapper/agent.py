"""Mapper agent orchestration: retrieval, validation, repair, persistence, drift."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent_bazaar.config import Settings, get_settings
from agent_bazaar.ingestion.models import NormalizedSpec, flatten_fields
from agent_bazaar.kg import GraphValidationError
from agent_bazaar.logging_utils import get_logger
from agent_bazaar.mapper.llm_mapper import (
    HeuristicMapper,
    LLMDecision,
    MappingLLMError,
    PromptMapper,
    resolve_concept,
)
from agent_bazaar.mapper.memory import CorrectionEntry, CorrectionMemory
from agent_bazaar.mapper.repair import RepairLoop
from agent_bazaar.mapper.retriever import MappingRetriever, RetrievedContext
from agent_bazaar.mapper.rules import (
    check_mapping,
    validate_correction,
    validate_mapping_shacl,
)
from agent_bazaar.mapper.staging import StagingQueue
from agent_bazaar.messages.schema import (
    CorrectionSubmit,
    DriftAlert,
    Feedback,
    FieldMapping,
    FieldSpec,
    ListingSubmit,
    MapRequest,
    MapResult,
)
from agent_bazaar.models import ConceptInfo, MappedField, ToolRecord
from agent_bazaar.ontology.units import UNIT_FAMILIES
from agent_bazaar.protocols import CORRECTIONS, GraphStore, LLMClient, VectorService


def _local_name(reference: str) -> str:
    text = str(reference or "").strip()
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    if "/" in text:
        return text.rstrip("/").rsplit("/", 1)[-1]
    return text


def _status_value(status: Any) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _infer_type(sample: Any) -> str:
    if isinstance(sample, dict):
        for key in ("value", "sample", "data"):
            if key in sample:
                return _infer_type(sample[key])
        return "object"
    if isinstance(sample, list):
        return "array"
    if isinstance(sample, bool):
        return "boolean"
    if isinstance(sample, int):
        return "integer"
    if isinstance(sample, float):
        return "float"
    return "string"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "capability"


class MapperAgent:
    def __init__(
        self,
        store: GraphStore,
        vector: VectorService,
        client: LLMClient | None = None,
        ingester: Any = None,
        settings: Settings | None = None,
        memory: CorrectionMemory | None = None,
        staging: StagingQueue | None = None,
        use_llm: bool | None = None,
        violation_log_path: str | Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store
        self.vector = vector
        self.client = client
        self.ingester = ingester
        self.retriever = MappingRetriever(vector)
        self.memory = memory if memory is not None else CorrectionMemory(self.settings.paths.memory_dir)
        self.staging = staging if staging is not None else StagingQueue(self.settings.paths.staging_dir)
        self.use_llm = (
            use_llm
            if use_llm is not None
            else client is not None and getattr(client, "provider", "") != "offline"
        )
        self._prompt_mapper = (
            PromptMapper(client, self.retriever, self.settings) if client is not None else None
        )
        concepts = self.store.list_concepts()
        self._heuristic_mapper = HeuristicMapper(concepts=concepts, retriever=self.retriever)
        self._repair = RepairLoop(self.settings.mapper.max_repair_attempts)
        self._index_ready = False
        self._log_path = (
            Path(violation_log_path)
            if violation_log_path is not None
            else self.settings.paths.out_dir / "logs" / "mapper_events.jsonl"
        )
        logger_name = "agent_bazaar.mapper.agent"
        if violation_log_path is not None:
            logger_name = f"{logger_name}.{abs(hash(str(self._log_path)))}"
            self._logger = get_logger(logger_name, log_file=self._log_path)
        else:
            self._logger = get_logger(logger_name)

    def _log(self, event: str, **fields: Any) -> None:
        extra = {"event": event, **fields}
        self._logger.info(event, extra=extra)

    def build_index(self) -> None:
        concepts = self.store.list_concepts()
        self.retriever.ensure_index(concepts)
        self._heuristic_mapper.concepts = list(concepts)
        self.retriever.index_corrections(self.memory.all())
        self._index_ready = True

    def _ensure_index(self) -> None:
        if not self._index_ready:
            self.build_index()

    def reindex(self) -> None:
        self.build_index()

    def _concept_index(self) -> tuple[dict[str, ConceptInfo], dict[str, str]]:
        concepts = self.store.list_concepts()
        concepts_by_iri = {concept.iri: concept for concept in concepts}
        concept_iris: dict[str, str] = {}
        for concept in concepts:
            local = _local_name(concept.iri)
            for key in (concept.label, *concept.aliases, local, concept.iri):
                if key:
                    concept_iris.setdefault(key.lower(), concept.iri)
        return concepts_by_iri, concept_iris

    def _default_unit(self, concept: ConceptInfo) -> str | None:
        if not concept.unit_bearing:
            return None
        if concept.unit:
            return concept.unit
        family = UNIT_FAMILIES.get(concept.unit_family or "")
        return str(family["canonical"]) if family else None

    def _make_mapping(
        self,
        field: FieldSpec,
        decision: LLMDecision,
        concept: ConceptInfo | None,
        source: str,
    ) -> FieldMapping:
        unit = decision.unit
        if unit is None and concept is not None:
            unit = self._default_unit(concept)
        return FieldMapping(
            field_path=field.field_path,
            concept=concept.iri if concept is not None else decision.concept,
            concept_label=concept.label if concept is not None else decision.concept,
            unit=unit,
            unit_family=concept.unit_family if concept is not None else None,
            confidence=float(decision.confidence),
            reason=decision.reason,
            status="mapped",
            source=source,
            direction=field.direction,
        )

    def _mapping_problems(
        self,
        mapping: FieldMapping,
        field: FieldSpec,
        concept: ConceptInfo | None,
        concept_iris: dict[str, str],
    ) -> list[str]:
        problems = check_mapping(mapping, field, concept, concept_iris)
        if concept is not None:
            result = validate_mapping_shacl(mapping, concept)
            problems.extend(violation.message for violation in result.violations if violation.message)
        return list(dict.fromkeys(problems))

    def _propose_fields(
        self,
        fields: list[FieldSpec],
        tool_id: str,
        context: dict[str, RetrievedContext] | None = None,
    ) -> dict[str, LLMDecision]:
        if self.use_llm and self._prompt_mapper is not None:
            try:
                return self._prompt_mapper.propose(fields, tool_id, context)
            except MappingLLMError:
                self._log("llm_fallback", tool_id=tool_id)
        return self._heuristic_mapper.propose(fields, tool_id, context)

    def _repair_proposer(
        self, tool_id: str
    ) -> Callable[[FieldSpec, str], FieldMapping | None]:
        if not self.use_llm or self._prompt_mapper is None:
            return lambda field, hint: None

        def propose(field: FieldSpec, hint: str) -> FieldMapping | None:
            try:
                decisions = self._prompt_mapper.propose([field], tool_id)
            except MappingLLMError:
                return None
            decision = decisions.get(field.field_path)
            if decision is None or decision.unmapped or not decision.concept.strip():
                return None
            concepts_by_iri, concept_iris = self._concept_index()
            concept = resolve_concept(decision.concept, concepts_by_iri, concept_iris)
            mapping = self._make_mapping(field, decision, concept, "llm")
            reason = mapping.reason or ""
            hint_text = f"repair hint: {hint}"
            reason = f"{reason}; {hint_text}" if reason else hint_text
            return mapping.model_copy(update={"reason": reason, "status": "repaired"})

        return propose

    def _llm_stats(self) -> dict[str, Any]:
        if self.client is None or not hasattr(self.client, "stats"):
            return {}
        try:
            return dict(self.client.stats)
        except Exception:
            return {}

    @staticmethod
    def _stats() -> dict[str, Any]:
        return {
            "mapped": 0,
            "unmapped": 0,
            "repaired": 0,
            "queued_for_review": 0,
            "attempts_total": 0,
        }

    def _queue_review(self, tool_id: str, field: FieldSpec, reason: str) -> None:
        self._log("queued_for_review", tool_id=tool_id, field_path=field.field_path)
        self._log("unmapped", tool_id=tool_id, field_path=field.field_path, reason=reason)

    def map_fields(self, request: MapRequest) -> MapResult:
        self._ensure_index()
        contexts = {field.field_path: self.retriever.retrieve(field) for field in request.fields}
        decisions = self._propose_fields(request.fields, request.tool_id, contexts)
        concepts_by_iri, concept_iris = self._concept_index()
        result = MapResult(tool_id=request.tool_id, correlation_id=request.correlation_id)
        stats = self._stats()
        source = "llm" if self.use_llm else "fallback"

        for field in request.fields:
            decision = decisions.get(field.field_path)
            if decision is None:
                decision = LLMDecision(
                    field_path=field.field_path,
                    unmapped=True,
                    reason="no mapping decision",
                )
            if decision.unmapped or not decision.concept.strip():
                result.unmapped.append(field)
                stats["unmapped"] += 1
                self._log("unmapped", tool_id=request.tool_id, field_path=field.field_path)
                continue

            concept = resolve_concept(decision.concept, concepts_by_iri, concept_iris)
            mapping = self._make_mapping(field, decision, concept, source)
            problems = self._mapping_problems(mapping, field, concept, concept_iris)

            if problems:
                outcome = self._repair.run(
                    field,
                    mapping,
                    problems,
                    self._repair_proposer(request.tool_id),
                    lambda candidate, field=field: self._mapping_problems(
                        candidate,
                        field,
                        resolve_concept(candidate.concept, concepts_by_iri, concept_iris),
                        concept_iris,
                    ),
                )
                stats["attempts_total"] += outcome.attempts
                self._log(
                    "repair_outcome",
                    tool_id=request.tool_id,
                    field_path=field.field_path,
                    attempts=outcome.attempts,
                    repaired=outcome.mapping is not None,
                )
                if outcome.mapping is None:
                    reason = "; ".join(outcome.problems or problems)
                    mapping = mapping.model_copy(
                        update={
                            "status": "unmapped",
                            "attempts": outcome.attempts,
                            "reason": f"{mapping.reason}; {reason}".strip("; "),
                        }
                    )
                    result.mappings.append(mapping)
                    result.unmapped.append(field)
                    stats["unmapped"] += 1
                    stats["queued_for_review"] += 1
                    self._queue_review(request.tool_id, field, reason)
                    continue
                mapping = outcome.mapping.model_copy(
                    update={"status": "repaired", "attempts": outcome.attempts}
                )
                concept = resolve_concept(mapping.concept, concepts_by_iri, concept_iris)
                stats["repaired"] += 1

            if concept is None:
                reason = f"concept {mapping.concept!r} not found in ontology"
                mapping = mapping.model_copy(update={"status": "unmapped", "reason": reason})
                result.mappings.append(mapping)
                result.unmapped.append(field)
                stats["unmapped"] += 1
                stats["queued_for_review"] += 1
                self._queue_review(request.tool_id, field, reason)
                continue

            try:
                self.store.update_mapping(
                    request.tool_id,
                    field.field_path,
                    concept.iri,
                    mapping.unit,
                    provenance={
                        "who": "mapper",
                        "why": mapping.reason,
                        "confidence": mapping.confidence,
                        "status": _status_value(mapping.status),
                        "direction": field.direction,
                    },
                )
            except GraphValidationError as error:
                reason = f"{mapping.reason}; {error}".strip("; ")
                mapping = mapping.model_copy(update={"status": "unmapped", "reason": reason})
                result.mappings.append(mapping)
                result.unmapped.append(field)
                stats["unmapped"] += 1
                stats["queued_for_review"] += 1
                self._queue_review(request.tool_id, field, str(error))
                continue

            result.mappings.append(mapping)
            stats["mapped"] += 1

        stats["llm_calls"] = self._llm_stats()
        result.stats = stats
        return result

    def _fields_from_spec(self, spec: NormalizedSpec) -> list[FieldSpec]:
        return [
            FieldSpec(
                field_path=field.path,
                name=field.name or _local_name(field.path),
                type=field.type,
                description=field.description,
                sample_value=field.sample_value,
                direction=field.direction,
                endpoint=field.endpoint,
                method=field.method,
                required=field.required,
            )
            for field in flatten_fields(spec)
        ]

    def map_spec(self, spec: NormalizedSpec, tool_id: str | None = None) -> MapResult:
        request = MapRequest(
            tool_id=tool_id or spec.tool_id,
            fields=self._fields_from_spec(spec),
        )
        return self.map_fields(request)

    def handle_listing_submit(self, message: ListingSubmit) -> MapResult:
        if self.ingester is None:
            raise ValueError("handle_listing_submit requires an ingester")
        spec = self.ingester.ingest(message.source, message.spec_format)
        request = MapRequest(
            tool_id=message.tool_id,
            fields=self._fields_from_spec(spec),
            correlation_id=message.correlation_id,
        )
        return self.map_fields(request)

    def submit_correction(self, correction: CorrectionSubmit) -> dict[str, Any]:
        concepts_by_iri, concept_iris = self._concept_index()

        def check(candidate: CorrectionSubmit) -> list[str]:
            return validate_correction(candidate, concept_iris, concepts_by_iri)

        def promote(candidate: CorrectionSubmit) -> CorrectionEntry:
            concept = resolve_concept(candidate.corrected_concept, concepts_by_iri, concept_iris)
            entry = CorrectionEntry(
                tool_id=candidate.tool_id,
                field_path=candidate.field_path,
                corrected_concept=concept.iri if concept is not None else candidate.corrected_concept,
                corrected_unit=candidate.corrected_unit,
                note=candidate.note,
                submitted_by=candidate.submitted_by or candidate.sender.value,
            )
            stored = self.memory.add(entry)
            self.vector.upsert(CORRECTIONS, self.memory.as_index_items()[-1:])
            return stored

        decision = self.staging.submit(correction, check, promote)
        self._log(
            "correction_decision",
            tool_id=correction.tool_id,
            field_path=correction.field_path,
            status=decision.status,
            reason=decision.reason,
        )
        return {
            "status": decision.status,
            "reason": decision.reason,
            "stats": self.staging.stats(),
        }

    def handle_drift_alert(self, alert: DriftAlert) -> MapResult:
        self._ensure_index()
        field_path = alert.field_path
        name = field_path.rsplit(".", 1)[-1] if "." in field_path else _local_name(field_path)
        direction = "input" if field_path.startswith("input.") else "output"
        field = FieldSpec(
            field_path=field_path,
            name=name,
            type=_infer_type(alert.new_sample),
            description=alert.old_description,
            sample_value=alert.new_sample,
            direction=direction,
        )
        context = {field_path: self.retriever.retrieve(field)}
        decisions = self._propose_fields([field], alert.tool_id, context)
        decision = decisions.get(field_path)
        concepts_by_iri, concept_iris = self._concept_index()
        result = MapResult(tool_id=alert.tool_id, correlation_id=alert.correlation_id)
        stats = self._stats()
        stats["llm_calls"] = self._llm_stats()

        if decision is None or decision.unmapped or not decision.concept.strip():
            result.unmapped.append(field)
            stats["unmapped"] = 1
            self._log("drift_unmapped", tool_id=alert.tool_id, field_path=field_path)
            result.stats = stats
            return result

        concept = resolve_concept(decision.concept, concepts_by_iri, concept_iris)
        mapping = self._make_mapping(field, decision, concept, "drift")
        problems = self._mapping_problems(mapping, field, concept, concept_iris)
        if problems or concept is None:
            reason = "; ".join(problems) or f"concept {decision.concept!r} not found in ontology"
            mapping = mapping.model_copy(update={"status": "unmapped", "reason": reason})
            result.mappings.append(mapping)
            result.unmapped.append(field)
            stats["unmapped"] = 1
            stats["queued_for_review"] = 1
            self._queue_review(alert.tool_id, field, reason)
            result.stats = stats
            return result

        old_concept = self.store.concept_for_field(alert.tool_id, field_path)
        reason = f"drift: old={old_concept} new={concept.iri}; {decision.reason}"
        try:
            self.store.update_mapping(
                alert.tool_id,
                field_path,
                concept.iri,
                mapping.unit,
                provenance={
                    "who": "mapper-drift",
                    "why": reason,
                    "confidence": mapping.confidence,
                    "status": "drift_remapped",
                    "direction": direction,
                },
            )
        except GraphValidationError as error:
            failed = mapping.model_copy(
                update={"status": "unmapped", "reason": f"{reason}; {error}"}
            )
            result.mappings.append(failed)
            result.unmapped.append(field)
            stats["unmapped"] = 1
            stats["queued_for_review"] = 1
            self._queue_review(alert.tool_id, field, str(error))
            result.stats = stats
            return result

        mapping = mapping.model_copy(update={"status": "drift_remapped", "reason": reason})
        result.mappings.append(mapping)
        stats["mapped"] = 1
        self._log("drift_remapped", tool_id=alert.tool_id, field_path=field_path)
        result.stats = stats
        return result

    def listing_to_tool_record(
        self,
        spec: NormalizedSpec,
        result: MapResult,
        capability_hints: list[str] | None = None,
        provider_id: str = "",
        provider_name: str = "",
        trust: float | None = None,
    ) -> ToolRecord:
        inputs: list[MappedField] = []
        outputs: list[MappedField] = []
        for mapping in result.mappings:
            if _status_value(mapping.status) == "unmapped":
                continue
            concept = self.store.get_concept(mapping.concept)
            concept_label = mapping.concept_label or (concept.label if concept else "")
            unit_family = concept.unit_family if concept else getattr(mapping, "unit_family", None)
            data_type = concept.data_type if concept else "string"
            direction = getattr(mapping, "direction", None)
            if direction not in ("input", "output"):
                direction = "input" if mapping.field_path.startswith("input.") else "output"
            name = mapping.field_path.rsplit(".", 1)[-1]
            mapped = MappedField(
                field_path=mapping.field_path,
                name=name,
                concept=mapping.concept,
                concept_label=concept_label,
                unit=mapping.unit,
                unit_family=unit_family,
                data_type=data_type,
                direction=direction,
                confidence=mapping.confidence,
                reason=mapping.reason,
                status=_status_value(mapping.status),
            )
            if direction == "input":
                inputs.append(mapped)
            else:
                outputs.append(mapped)

        metadata = dict(spec.metadata or {})
        capabilities: list[str] = []
        for key in ("tags", "categories"):
            value = metadata.get(key)
            if isinstance(value, str):
                capabilities = [part.strip() for part in value.split(",") if part.strip()]
            elif isinstance(value, (list, tuple, set)):
                capabilities = [str(part).strip() for part in value if str(part).strip()]
            if capabilities:
                break
        if not capabilities and capability_hints:
            capabilities = [str(hint) for hint in capability_hints if str(hint).strip()]
        if not capabilities:
            capabilities = [_slug(spec.title or spec.tool_id)]

        return ToolRecord(
            tool_id=spec.tool_id,
            name=spec.title or spec.tool_id,
            description=spec.description,
            provider_id=provider_id,
            provider_name=provider_name,
            base_url=spec.base_url,
            capabilities=capabilities,
            inputs=inputs,
            outputs=outputs,
            trust=trust,
            source=spec.source,
            version=spec.version,
            retrieved_at=spec.retrieved_at,
            metadata=metadata,
        )

    def handle_message(self, message: Any) -> Any:
        if isinstance(message, ListingSubmit):
            return self.handle_listing_submit(message)
        if isinstance(message, MapRequest):
            return self.map_fields(message)
        if isinstance(message, CorrectionSubmit):
            return self.submit_correction(message)
        if isinstance(message, DriftAlert):
            return self.handle_drift_alert(message)
        if isinstance(message, Feedback):
            return {"status": "recorded", "tool_id": message.tool_id}
        return {"status": "unsupported", "type": type(message).__name__}
