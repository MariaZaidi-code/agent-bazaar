"""SHACL-validated RDF knowledge graph store."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, Node, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from agent_bazaar.config import Settings, get_settings
from agent_bazaar.kg.quality import build_profile, offering_iri, offering_triples
from agent_bazaar.kg.queries import (
    compatible_substitutes as query_compatible_substitutes,
    concept_for_field as query_concept_for_field,
    concept_info as query_concept_info,
    concept_local_name,
    describe_graph as query_describe_graph,
    executable_tools as query_executable_tools,
    list_concepts as query_list_concepts,
    list_tools as query_list_tools,
    subclass_closure as query_subclass_closure,
    tools_by_access as query_tools_by_access,
    tools_by_capability as query_tools_by_capability,
    tools_by_io as query_tools_by_io,
    tools_by_pricing_tier as query_tools_by_pricing_tier,
)
from agent_bazaar.models import (
    ConceptInfo,
    MappedField,
    ToolQualityProfile,
    ToolRecord,
    ToolSummary,
)
from agent_bazaar.ontology.ns import AB, STANDARD_PREFIXES, tool_iri, unit_iri
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.ontology.validator import load_shapes, validate_graph
from agent_bazaar.protocols import ValidationResult

VALID_ACCESS_REQUIREMENTS = frozenset({"keyless", "api_key", "paid_key"})

_OFFERING_FACT_PREDICATES = (
    AB.pricingTier,
    AB.accessRequirement,
    AB.priceAmount,
    AB.priceCurrency,
    AB.rateLimit,
    AB.probeBudgetPerMinute,
    AB.docQuality,
    AB.docSubScores,
    AB.mappingCoverage,
    AB.licence,
    AB.termsUrl,
    AB.tierEvidence,
    AB.accessEvidence,
    AB.provenance,
    AB.lastSeen,
)


class GraphValidationError(Exception):
    def __init__(self, result: ValidationResult) -> None:
        self.result = result
        details: list[str] = []
        for violation in result.violations[:3]:
            label = violation.message or violation.source or "SHACL violation"
            location = f" [{violation.focus_node}]" if violation.focus_node else ""
            details.append(f"{label}{location}")
        summary = "; ".join(details) or "unknown SHACL violation"
        super().__init__(f"Graph failed SHACL validation with {len(result.violations)} violation(s): {summary}")


class KgStore:
    def __init__(
        self,
        graph: Graph | None = None,
        shapes: Graph | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.graph = graph if graph is not None else Graph()
        self.shapes = shapes if shapes is not None else load_shapes(self.settings.paths.shapes_path)
        self.ontology_graph = Graph()
        for prefix, namespace in self.graph.namespaces():
            if prefix:
                self.ontology_graph.bind(prefix, namespace)
        for triple in self.graph:
            self.ontology_graph.add(triple)

    @classmethod
    def build_default(
        cls,
        load_existing: bool = True,
        ontology_path: str | Path | None = None,
        graph_path: str | Path | None = None,
    ) -> KgStore:
        settings = get_settings()
        graph = upper_with_units()
        ontology_graph = Graph()
        for triple in graph:
            ontology_graph.add(triple)
        domain_path = Path(ontology_path) if ontology_path is not None else settings.paths.ontology_path
        if domain_path.exists():
            domain_graph = Graph()
            domain_graph.parse(domain_path, format="turtle")
            for triple in domain_graph:
                graph.add(triple)
                ontology_graph.add(triple)
        shapes = load_shapes(settings.paths.shapes_path)
        existing_path = Path(graph_path) if graph_path is not None else settings.paths.graph_path
        if load_existing and existing_path.exists():
            existing_graph = Graph()
            existing_graph.parse(existing_path, format="turtle")
            for triple in existing_graph:
                graph.add(triple)
        store = cls(graph=graph, shapes=shapes, settings=settings)
        store.ontology_graph = ontology_graph
        return store

    def _candidate(self) -> Graph:
        candidate = Graph()
        for prefix, namespace in self.graph.namespaces():
            if prefix:
                candidate.bind(prefix, namespace)
        for prefix, namespace in STANDARD_PREFIXES.items():
            candidate.bind(prefix, namespace)
        for triple in self.graph:
            candidate.add(triple)
        return candidate

    def _commit(self, candidate: Graph) -> None:
        result = validate_graph(candidate, self.shapes)
        if not result.conforms:
            raise GraphValidationError(result)
        self.graph = candidate

    @staticmethod
    def _mapping_iri(tool_id: str, field_path: str, direction: str) -> URIRef:
        digest = hashlib.sha1(f"{tool_id}|{field_path}|{direction}".encode()).hexdigest()[:12]
        return AB[f"mapping-{digest}"]

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = "".join(character if character.isalnum() else "-" for character in value.strip().lower())
        slug = "-".join(part for part in cleaned.split("-") if part)
        return slug or "capability"

    @staticmethod
    def _replace(graph: Graph, subject: Node, predicate: URIRef, obj: Node | None) -> None:
        for old in list(graph.objects(subject, predicate)):
            graph.remove((subject, predicate, old))
        if obj is not None:
            graph.add((subject, predicate, obj))

    @staticmethod
    def _decimal(value: float) -> Literal:
        return Literal(str(value), datatype=XSD.decimal)

    @staticmethod
    def _unit_node(unit: str) -> URIRef:
        return unit_iri(concept_local_name(unit))

    def _add_mapping(
        self,
        graph: Graph,
        tool: URIRef,
        tool_id: str,
        field: MappedField,
        *,
        recorded_by: str,
    ) -> URIRef:
        direction = field.direction
        mapping = self._mapping_iri(tool_id, field.field_path, direction)
        concept = AB[concept_local_name(field.concept)]
        graph.add((mapping, RDF.type, AB.Mapping))
        graph.add((mapping, AB.fieldPath, Literal(field.field_path)))
        graph.add((mapping, AB.direction, Literal(direction)))
        graph.add((mapping, AB.mapsTo, concept))
        graph.add((mapping, AB.confidence, self._decimal(field.confidence)))
        graph.add((mapping, AB.reason, Literal(field.reason)))
        graph.add((mapping, AB.status, Literal(field.status)))
        graph.add((mapping, AB.attempts, Literal(int(getattr(field, "attempts", 0) or 0), datatype=XSD.integer)))
        graph.add((mapping, AB.recordedAt, Literal(datetime.now(UTC))))
        graph.add((mapping, AB.recordedBy, Literal(recorded_by)))
        graph.add((mapping, AB.tool, tool))
        graph.add((tool, AB.hasFieldMapping, mapping))
        if field.unit:
            graph.add((mapping, AB.unit, self._unit_node(field.unit)))
        if direction == "input":
            graph.add((tool, AB.hasInput, concept))
        else:
            graph.add((tool, AB.hasOutput, concept))
        return mapping

    def _write_offering(self, graph: Graph, record: ToolRecord) -> None:
        """Write the commercial and documentation facts of a tool as an offering.

        An offering asserts a known access requirement, so a record without one
        keeps no offering: absence of evidence is never read as "free".
        """
        if record.access_requirement not in VALID_ACCESS_REQUIREMENTS:
            return
        offering = offering_iri(record.tool_id)
        for predicate in _OFFERING_FACT_PREDICATES:
            self._replace(graph, offering, predicate, None)
        metadata = record.metadata if isinstance(record.metadata, dict) else {}
        offering_triples(
            graph,
            record.tool_id,
            pricing_tier=record.pricing_tier,
            access_requirement=record.access_requirement,
            price_amount=record.price_amount,
            price_currency=record.price_currency,
            rate_limit_policy=record.rate_limit_policy,
            probe_budget_per_minute=record.probe_budget_per_minute,
            doc_quality=record.doc_quality,
            doc_sub_scores=record.doc_sub_scores or None,
            mapping_coverage_value=self._optional_float(metadata.get("mapping_coverage")),
            licence=record.licence,
            terms_url=record.terms_url,
            tier_evidence=record.tier_evidence,
            access_evidence=record.access_evidence,
            provenance=self._optional_mapping(metadata.get("provenance")),
            last_seen=record.retrieved_at.isoformat(),
        )

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_mapping(value: Any) -> dict[str, Any] | None:
        return dict(value) if isinstance(value, dict) else None

    @staticmethod
    def _stored_count(graph: Graph, subject: Node, predicate: URIRef) -> int:
        value = graph.value(subject, predicate)
        if value is None:
            return 0
        try:
            return int(float(str(value)))
        except ValueError:
            return 0

    def write_tool(self, record: ToolRecord) -> None:
        candidate = self._candidate()
        tool = tool_iri(record.tool_id)
        provider = AB[f"provider-{record.provider_id}"]
        candidate.add((provider, RDF.type, AB.Provider))
        candidate.add((provider, AB.providerId, Literal(record.provider_id)))
        candidate.add((provider, AB.name, Literal(record.provider_name)))
        candidate.add((tool, RDF.type, AB.Tool))
        candidate.add((tool, AB.toolId, Literal(record.tool_id)))
        candidate.add((tool, AB.name, Literal(record.name)))
        if record.description:
            candidate.add((tool, AB.description, Literal(record.description)))
        candidate.add((tool, AB.source, Literal(record.source)))
        candidate.add((tool, AB.version, Literal(record.version)))
        if record.trust is not None:
            candidate.add((tool, AB.hasTrust, self._decimal(record.trust)))
        candidate.add((tool, AB.providedBy, provider))
        for capability in record.capabilities:
            capability_node = AB[f"capability-{self._slug(capability)}"]
            candidate.add((capability_node, RDF.type, AB.Capability))
            candidate.add((capability_node, RDFS.label, Literal(capability)))
            candidate.add((tool, AB.hasCapability, capability_node))
        for index, claim in enumerate(record.claims):
            claim_node = AB[f"claim-{record.tool_id}-{index}"]
            candidate.add((claim_node, RDF.type, AB.Claim))
            candidate.add((claim_node, AB.claimId, Literal(claim.claim_id)))
            candidate.add((claim_node, AB.claimText, Literal(claim.text)))
            candidate.add((claim_node, AB.source, Literal(claim.source)))
            candidate.add((tool, AB.makesClaim, claim_node))
        for field in [*record.inputs, *record.outputs]:
            self._add_mapping(candidate, tool, record.tool_id, field, recorded_by="mapper")
        self._write_offering(candidate, record)
        self._commit(candidate)

    def _find_mapping(self, graph: Graph, tool: URIRef, field_path: str, direction: str | None) -> Node | None:
        for mapping in sorted(graph.subjects(AB.fieldPath, Literal(field_path)), key=str):
            if (mapping, AB.tool, tool) not in graph:
                continue
            if direction is not None:
                stored = graph.value(mapping, AB.direction)
                if stored is None or str(stored) != direction:
                    continue
            return mapping
        return None

    def _rebuild_tool_io(self, graph: Graph, tool: URIRef) -> None:
        for predicate in (AB.hasInput, AB.hasOutput):
            for value in list(graph.objects(tool, predicate)):
                graph.remove((tool, predicate, value))
        for mapping in graph.subjects(AB.tool, tool):
            concept = graph.value(mapping, AB.mapsTo)
            direction = graph.value(mapping, AB.direction)
            if concept is None:
                continue
            if str(direction) == "input":
                graph.add((tool, AB.hasInput, concept))
            elif str(direction) == "output":
                graph.add((tool, AB.hasOutput, concept))

    def update_mapping(
        self,
        tool_id: str,
        field_path: str,
        concept: str,
        unit: str | None = None,
        provenance: dict | None = None,
    ) -> bool:
        details = dict(provenance or {})
        tool = tool_iri(tool_id)
        requested_direction = details.get("direction")
        direction = requested_direction if requested_direction in ("input", "output") else None
        candidate = self._candidate()
        mapping = self._find_mapping(candidate, tool, field_path, direction)
        concept_node = AB[concept_local_name(concept)]
        unit_node = self._unit_node(unit) if unit else None
        confidence = details.get("confidence")
        if confidence is None:
            confidence = 1.0 if details.get("source") == "correction" else 0.0
        reason = str(details.get("why", ""))
        status = str(details.get("status", "updated"))
        recorded_by = str(details.get("who", "system"))
        now = Literal(datetime.now(UTC))
        if mapping is None:
            mapping_direction = direction or "output"
            mapping = self._mapping_iri(tool_id, field_path, mapping_direction)
            candidate.add((mapping, RDF.type, AB.Mapping))
            candidate.add((mapping, AB.fieldPath, Literal(field_path)))
            candidate.add((mapping, AB.direction, Literal(mapping_direction)))
            candidate.add((mapping, AB.attempts, Literal(0, datatype=XSD.integer)))
            candidate.add((mapping, AB.tool, tool))
            candidate.add((tool, AB.hasFieldMapping, mapping))
        self._replace(candidate, mapping, AB.mapsTo, concept_node)
        self._replace(candidate, mapping, AB.unit, unit_node)
        self._replace(candidate, mapping, AB.confidence, self._decimal(float(confidence)))
        self._replace(candidate, mapping, AB.reason, Literal(reason))
        self._replace(candidate, mapping, AB.status, Literal(status))
        self._replace(candidate, mapping, AB.recordedAt, now)
        self._replace(candidate, mapping, AB.recordedBy, Literal(recorded_by))
        self._rebuild_tool_io(candidate, tool)
        self._commit(candidate)
        return True

    def tools_by_capability(self, capability: str) -> list[ToolSummary]:
        return query_tools_by_capability(self.graph, capability)

    def tools_by_io(self, input_concept: str, output_concept: str) -> list[ToolSummary]:
        return query_tools_by_io(self.graph, input_concept, output_concept)

    def tools_by_access(self, access_requirement: str) -> list[ToolSummary]:
        return query_tools_by_access(self.graph, access_requirement)

    def tools_by_pricing_tier(self, pricing_tier: str) -> list[ToolSummary]:
        return query_tools_by_pricing_tier(self.graph, pricing_tier)

    def executable_tools(self, *, require_known_licence: bool = False) -> list[ToolSummary]:
        return query_executable_tools(self.graph, require_known_licence=require_known_licence)

    def tool_quality_profile(self, tool_id: str) -> ToolQualityProfile:
        return build_profile(self.graph, tool_id)

    def candidate_facts(self, tool_ids: Iterable[str]) -> dict[str, ToolQualityProfile]:
        return {tool_id: build_profile(self.graph, tool_id) for tool_id in tool_ids}

    def update_tool_quality(
        self,
        tool_id: str,
        *,
        rating_value: float | None = None,
        rating_count: int | None = None,
        rating_source: str = "",
        doc_quality: float | None = None,
        mapping_coverage: float | None = None,
        licence: str | None = None,
        pricing_tier: str | None = None,
        access_requirement: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> ToolQualityProfile:
        """Update the offering facts of a tool in one validated write.

        The write goes through the same SHACL-validating path as every other
        write, so an offering that violates the shapes is rejected and the
        graph stays untouched.
        """
        candidate = self._candidate()
        tool = tool_iri(tool_id)
        if (tool, RDF.type, AB.Tool) not in candidate:
            raise ValueError(f"Unknown tool: {tool_id}")
        offering = candidate.value(tool, AB.hasOffering)
        if offering is None:
            if access_requirement is None:
                raise ValueError(
                    f"access_requirement is required to create the offering of {tool_id}"
                )
            offering = offering_iri(tool_id)
            candidate.add((tool, AB.hasOffering, offering))
            candidate.add((offering, RDF.type, AB.Offering))
            candidate.add((offering, AB.pricingTier, Literal("unknown")))
        if pricing_tier is not None:
            self._replace(candidate, offering, AB.pricingTier, Literal(str(pricing_tier)))
        if access_requirement is not None:
            self._replace(candidate, offering, AB.accessRequirement, Literal(str(access_requirement)))
        if rating_value is not None:
            self._replace(candidate, offering, AB.ratingValue, self._decimal(float(rating_value)))
            count = (
                rating_count
                if rating_count is not None
                else self._stored_count(candidate, offering, AB.ratingCount)
            )
            self._replace(candidate, offering, AB.ratingCount, Literal(int(count), datatype=XSD.integer))
        elif rating_count is not None:
            self._replace(candidate, offering, AB.ratingCount, Literal(int(rating_count), datatype=XSD.integer))
        if rating_source:
            self._replace(candidate, offering, AB.ratingSource, Literal(str(rating_source)))
        if doc_quality is not None:
            self._replace(candidate, offering, AB.docQuality, self._decimal(float(doc_quality)))
        if mapping_coverage is not None:
            self._replace(candidate, offering, AB.mappingCoverage, self._decimal(float(mapping_coverage)))
        if licence is not None:
            self._replace(candidate, offering, AB.licence, Literal(str(licence)))
        if provenance is not None:
            self._replace(
                candidate,
                offering,
                AB.provenance,
                Literal(json.dumps(provenance, sort_keys=True, default=str)),
            )
        self._commit(candidate)
        return build_profile(self.graph, tool_id)

    def compatible_substitutes(self, tool_id: str) -> list[ToolSummary]:
        return query_compatible_substitutes(self.graph, tool_id)

    def concept_for_field(self, tool_id: str, field_path: str) -> str | None:
        return query_concept_for_field(self.graph, tool_id, field_path)

    def get_concept(self, iri: str) -> ConceptInfo | None:
        return query_concept_info(self.graph, iri)

    def list_concepts(self) -> list[ConceptInfo]:
        return query_list_concepts(self.graph)

    def list_tools(self) -> list[ToolSummary]:
        return query_list_tools(self.graph)

    def validate(self) -> ValidationResult:
        return validate_graph(self.graph, self.shapes)

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.settings.paths.graph_path
        target.parent.mkdir(parents=True, exist_ok=True)
        self.graph.serialize(destination=str(target), format="turtle")
        return target

    def subclass_closure(self, concept_iri: str) -> set[str]:
        return query_subclass_closure(self.graph, concept_iri)

    def describe_graph(self) -> dict[str, int]:
        return query_describe_graph(self.graph)
