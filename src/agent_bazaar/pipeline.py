"""End-to-end wiring: listing -> ingestion -> mapping -> validated graph write."""

from __future__ import annotations

import re
from dataclasses import dataclass
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
