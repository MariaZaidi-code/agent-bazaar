"""Normalised structures produced by the deterministic ingestion utility."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FieldInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    name: str
    type: str = "string"
    description: str = ""
    sample_value: Any = None
    direction: Literal["input", "output"] = "output"
    required: bool | None = None
    endpoint: str | None = None
    method: str | None = None


class EndpointInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    method: str = "GET"
    summary: str = ""
    description: str = ""
    operation_id: str = ""
    parameters: list[FieldInfo] = Field(default_factory=list)
    request_fields: list[FieldInfo] = Field(default_factory=list)
    response_fields: list[FieldInfo] = Field(default_factory=list)


class ChunkInfo(BaseModel):
    chunk_id: str
    text: str
    source: str = ""
    start: int = 0
    end: int = 0


class IngestionErrorInfo(BaseModel):
    code: str
    message: str
    source: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class NormalizedSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_id: str
    source: str
    spec_format: Literal["openapi_json", "openapi_yaml", "pdf", "docx", "text"] = "text"
    version: str = ""
    title: str = ""
    description: str = ""
    base_url: str = ""
    provider_id: str = ""
    endpoints: list[EndpointInfo] = Field(default_factory=list)
    fields: list[FieldInfo] = Field(default_factory=list)
    chunks: list[ChunkInfo] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


JSON_SCALARS = {"string": "string", "boolean": "boolean", "integer": "integer", "number": "float", "null": "string"}


def json_schema_to_type(schema: dict[str, Any] | None) -> str:
    if not isinstance(schema, dict):
        return "string"
    if "$ref" in schema and isinstance(schema["$ref"], str):
        return "object"
    schema_type = schema.get("type")
    if schema_type in JSON_SCALARS:
        return JSON_SCALARS[schema_type]
    if schema_type == "array":
        return "array"
    if schema_type == "object" or "properties" in schema:
        return "object"
    if "anyOf" in schema or "oneOf" in schema or "allOf" in schema:
        for option in schema.get("anyOf") or schema.get("oneOf") or schema.get("allOf") or []:
            resolved = json_schema_to_type(option)
            if resolved != "string":
                return resolved
    return "string"


def compose_field_path(direction: str, method: str, endpoint_path: str, local_path: str) -> str:
    """Canonical field-path convention: '{input|output}.{method}:{endpoint}.{local}'.

    Example: ``output.get:/v1/forecast.temperature_2m``. The Mapper, graph
    concept_for_field and drift handling all use this convention.
    """
    return f"{direction}.{method.lower()}:{endpoint_path}.{local_path}"


def flatten_fields(spec: NormalizedSpec) -> list[FieldInfo]:
    """Return the flattened field list, deriving it from endpoints when absent."""
    if spec.fields:
        return list(spec.fields)
    fields: list[FieldInfo] = []
    seen: set[str] = set()
    for endpoint in spec.endpoints:
        collections = (
            (endpoint.parameters, "input"),
            (endpoint.request_fields, "input"),
            (endpoint.response_fields, "output"),
        )
        for collection, direction in collections:
            for field in collection:
                path = compose_field_path(direction, endpoint.method, endpoint.path, field.path)
                if path in seen:
                    continue
                seen.add(path)
                fields.append(field.model_copy(update={"path": path, "direction": direction}))
    return fields
