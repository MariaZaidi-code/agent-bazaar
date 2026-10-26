"""End-to-end wiring: listing -> ingestion -> mapping -> validated graph write."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel

from agent_bazaar.ingestion.models import NormalizedSpec, flatten_fields
from agent_bazaar.logging_utils import get_logger
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.messages.schema import FieldSpec, MapResult
from agent_bazaar.models import MappedField, ToolRecord
from agent_bazaar.protocols import TOOL_DESCRIPTIONS, GraphStore, IndexItem, VectorService

LOGGER = get_logger("agent_bazaar.pipeline")

GENERIC_TITLE_TOKENS = {
    "api",
    "apis",
    "open",
    "public",
    "free",
    "rest",
    "service",
    "services",
    "data",
    "official",
    "unofficial",
    "the",
    "and",
    "for",
    "v1",
    "v2",
    "v3",
}


class OnboardOutcome(BaseModel):
    record: ToolRecord
    result: MapResult
    written: bool
    error: str = ""


def slugify(value: str, fallback: str = "capability") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or fallback


def derive_provider_id(spec: NormalizedSpec) -> str:
    metadata_provider = str(spec.metadata.get("provider_id") or "").strip()
    if metadata_provider:
        return slugify(metadata_provider, "provider")
    host = urlparse(spec.base_url).netloc or str(spec.metadata.get("host") or "")
    host = host.split(":")[0].removeprefix("www.")
    return slugify(host.rsplit(".", 1)[0] if "." in host else host, "provider")


def derive_capabilities(spec: NormalizedSpec, hints: list[str] | None = None) -> list[str]:
    candidates: list[str] = []
    for key in ("tags", "categories", "capabilities"):
        value = spec.metadata.get(key)
        if isinstance(value, list):
            candidates.extend(str(item) for item in value)
        elif isinstance(value, str):
            candidates.extend(value.split(","))
    if hints:
        candidates.extend(hints)
    if not candidates:
        words = re.split(r"[^a-zA-Z0-9]+", spec.title or spec.tool_id)
        meaningful = [w for w in words if w and w.lower() not in GENERIC_TITLE_TOKENS and len(w) > 2]
        word = "-".join(meaningful[:2]) or spec.tool_id
        candidates.append(word + "-api")
    capabilities = sorted({slugify(c, "general") for c in candidates if str(c).strip()})
    return capabilities or ["general"]


def spec_fields(spec: NormalizedSpec) -> list[FieldSpec]:
    fields = flatten_fields(spec)
    return [
        FieldSpec(
            field_path=field.path,
            name=field.name,
            type=field.type,
            description=field.description,
            sample_value=field.sample_value,
            direction=field.direction,
            endpoint=field.endpoint,
            method=field.method,
            required=field.required,
        )
        for field in fields
    ]


def tool_id_for_spec(spec: NormalizedSpec, existing: set[str] | None = None) -> str:
    base = slugify(spec.tool_id or spec.title or "tool", "tool")
    if not existing or base not in existing:
        return base
    counter = 2
    while f"{base}-{counter}" in existing:
        counter += 1
    return f"{base}-{counter}"


def listing_facts(spec: NormalizedSpec) -> dict[str, Any]:
    """The commercial, access and documentation facts captured during ingestion."""
    listing = spec.metadata.get("listing")
    return dict(listing) if isinstance(listing, dict) else {}


def mapping_coverage_of(result: MapResult) -> float:
    """Share of the listing's fields the Mapper typed, weighted by confidence.

    Same formula as ``kg.quality.mapping_coverage``, but computed from the
    mapping result because the unmapped fields are not written to the graph.
    """
    mappings = list(result.mappings)
    if not mappings:
        return 0.0
    mapped = 0
    confidence_total = 0.0
    for mapping in mappings:
        status = mapping.status.value if hasattr(mapping.status, "value") else str(mapping.status)
        if status in ("mapped", "repaired", "drift_remapped"):
            mapped += 1
        confidence_total += float(mapping.confidence or 0.0)
    coverage = mapped / len(mappings)
    mean_confidence = confidence_total / len(mappings)
    return round(coverage * (0.5 + 0.5 * min(1.0, mean_confidence)), 4)


def apply_listing_facts(record: ToolRecord, spec: NormalizedSpec, result: MapResult) -> ToolRecord:
    """Carry the listing metadata and the mapping statistics into the tool record."""
    listing = listing_facts(spec)
    sub_scores = listing.get("doc_sub_scores")
    price_amount = listing.get("price_amount")
    probe_budget = listing.get("probe_budget_per_minute")
    record.pricing_tier = str(listing.get("pricing_tier") or "unknown")
    record.access_requirement = str(listing.get("access_requirement") or "unknown")
    record.price_amount = float(price_amount) if isinstance(price_amount, (int, float)) else None
    record.price_currency = str(listing.get("price_currency") or "")
    record.rate_limit_policy = str(listing.get("rate_limit_policy") or "")
    record.probe_budget_per_minute = int(probe_budget) if isinstance(probe_budget, (int, float)) else None
    record.licence = str(listing.get("licence") or "")
    record.terms_url = str(listing.get("terms_url") or "")
    record.doc_quality = float(listing.get("doc_quality") or 0.0)
    record.doc_sub_scores = (
        {str(key): float(value) for key, value in sub_scores.items()} if isinstance(sub_scores, dict) else {}
    )
    record.tier_evidence = [str(item) for item in listing.get("tier_evidence") or []]
    record.access_evidence = [str(item) for item in listing.get("access_evidence") or []]
    metadata = dict(record.metadata)
    metadata["mapping_coverage"] = mapping_coverage_of(result)
    provenance = listing.get("provenance")
    metadata["provenance"] = dict(provenance) if isinstance(provenance, dict) else {}
    record.metadata = metadata
    return record


def onboard_spec(
    spec: NormalizedSpec,
    mapper: MapperAgent,
    store: GraphStore,
    vector: VectorService | None = None,
    capability_hints: list[str] | None = None,
    trust: float | None = None,
    write: bool = True,
    tool_id: str | None = None,
) -> OnboardOutcome:
    tool_id = tool_id or spec.tool_id
    result = mapper.map_spec(spec, tool_id=tool_id)
    record = mapper.listing_to_tool_record(
        spec,
        result,
        capability_hints=derive_capabilities(spec, capability_hints),
        provider_id=derive_provider_id(spec),
        trust=trust,
    )
    record.tool_id = tool_id
    apply_listing_facts(record, spec, result)
    written = False
    error = ""
    if write:
        try:
            store.write_tool(record)
            written = True
        except Exception as exc:
            error = str(exc)
            LOGGER.warning("tool write failed", extra={"event": "write_tool_failed", "tool_id": tool_id})
    if written and vector is not None:
        index_tool_description(vector, record)
    return OnboardOutcome(record=record, result=result, written=written, error=error)


def index_tool_description(vector: VectorService, record: ToolRecord) -> int:
    capabilities = ", ".join(record.capabilities)
    inputs = ", ".join(f"{field.field_path}:{field.concept_label}" for field in record.inputs)
    outputs = ", ".join(f"{field.field_path}:{field.concept_label}" for field in record.outputs)
    text = (
        f"Tool {record.name} ({record.tool_id}) by {record.provider_name or record.provider_id}. "
        f"Capabilities: {capabilities}. Inputs: {inputs}. Outputs: {outputs}. {record.description}"
    )
    item = IndexItem(
        id=f"tool-{record.tool_id}",
        text=text,
        metadata={
            "tool_id": record.tool_id,
            "name": record.name,
            "capabilities": record.capabilities,
            "provider_id": record.provider_id,
            "iri": "",
        },
    )
    return vector.upsert(TOOL_DESCRIPTIONS, [item])


def mapping_to_mapped_field(mapping: Any, direction: str) -> MappedField:
    return MappedField(
        field_path=mapping.field_path,
        name=mapping.field_path.rsplit(".", 1)[-1],
        concept=mapping.concept,
        concept_label=mapping.concept_label,
        unit=mapping.unit,
        unit_family=mapping.unit_family,
        direction=direction,
        confidence=mapping.confidence,
        reason=mapping.reason,
        status=mapping.status.value if hasattr(mapping.status, "value") else str(mapping.status),
    )
