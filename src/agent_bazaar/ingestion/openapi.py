"""Deterministic OpenAPI 3.x and Swagger 2.0 parsing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from agent_bazaar.ingestion.models import (
    EndpointInfo,
    FieldInfo,
    NormalizedSpec,
    flatten_fields,
    json_schema_to_type,
)
from agent_bazaar.protocols import IngestionError

_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_INPUT_PARAMETER_LOCATIONS = frozenset({"query", "path", "header"})
_MAX_SCHEMA_DEPTH = 3


class _ReferenceResolver:
    def __init__(self, document: dict[str, Any]) -> None:
        self._document = document

    def resolve(self, node: Any, seen: frozenset[str] = frozenset()) -> Any:
        if not isinstance(node, dict):
            return node
        reference = node.get("$ref")
        if not isinstance(reference, str) or not reference.startswith("#/"):
            return node
        if reference in seen:
            return {}
        target: Any = self._document
        for token in reference[2:].split("/"):
            key = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or key not in target:
                return {}
            target = target[key]
        return self.resolve(target, seen | {reference})


def _uses_yaml(raw_text: str, spec_format: str) -> bool:
    normalized = spec_format.strip().lower()
    if normalized in {"openapi_yaml", "yaml", "yml"}:
        return True
    if normalized in {"openapi_json", "json"}:
        return False
    return not raw_text.lstrip().startswith(("{", "["))


def _tool_id(source: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", source.stem.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "tool"


def _load_document(source: Path, raw_text: str, spec_format: str) -> dict[str, Any]:
    if _uses_yaml(raw_text, spec_format):
        try:
            loaded = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            line = mark.line + 1 if mark is not None else None
            column = mark.column + 1 if mark is not None else None
            problem = str(getattr(exc, "problem", str(exc)))
            location = f" at line {line} column {column}" if line is not None else ""
            raise IngestionError(
                "parse_error",
                f"Invalid YAML{location}: {problem}",
                source=str(source),
                details={"line": line, "column": column, "problem": problem},
            ) from exc
    else:
        try:
            loaded = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise IngestionError(
                "parse_error",
                f"Invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}",
                source=str(source),
                details={"line": exc.lineno, "column": exc.colno, "problem": exc.msg},
            ) from exc
    if not isinstance(loaded, dict):
        raise IngestionError(
            "not_openapi",
            "OpenAPI document root must be a mapping",
            source=str(source),
        )
    return loaded


def load_spec_document(source: Path, raw_text: str, spec_format: str) -> dict[str, Any]:
    """Load the raw specification text into a plain document mapping.

    The parsed document is the input of the listing metadata extraction, so it
    has to be the very same document the endpoints are parsed from.
    """
    document = _load_document(source, raw_text, spec_format)
    if "openapi" not in document and "swagger" not in document:
        raise IngestionError(
            "not_openapi",
            "Document is not an OpenAPI or Swagger specification",
            source=str(source),
        )
    return document


def _base_url(document: dict[str, Any]) -> str:
    servers = document.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"])
    if "swagger" in document:
        host = document.get("host")
        base_path = str(document.get("basePath") or "")
        if host:
            schemes = document.get("schemes")
            scheme = str(schemes[0]) if isinstance(schemes, list) and schemes else "https"
            return f"{scheme}://{host}{base_path}"
        return base_path
    return ""


def _merged_parameters(
    path_item: dict[str, Any],
    operation: dict[str, Any],
    resolver: _ReferenceResolver,
) -> list[dict[str, Any]]:
    raw_parameters: list[Any] = []
    path_parameters = path_item.get("parameters")
    if isinstance(path_parameters, list):
        raw_parameters.extend(path_parameters)
    operation_parameters = operation.get("parameters")
    if isinstance(operation_parameters, list):
        raw_parameters.extend(operation_parameters)
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_parameter in raw_parameters:
        parameter = resolver.resolve(raw_parameter)
        if not isinstance(parameter, dict):
            continue
        key = (str(parameter.get("in") or ""), str(parameter.get("name") or ""))
        merged[key] = parameter
    return list(merged.values())


def _parameter_fields(
    endpoint_path: str,
    method: str,
    path_item: dict[str, Any],
    operation: dict[str, Any],
    resolver: _ReferenceResolver,
) -> list[FieldInfo]:
    fields: list[FieldInfo] = []
    for parameter in _merged_parameters(path_item, operation, resolver):
        location = str(parameter.get("in") or "")
        if location not in _INPUT_PARAMETER_LOCATIONS:
            continue
        name = str(parameter.get("name") or f"parameter_{len(fields) + 1}")
        resolved_schema = resolver.resolve(parameter.get("schema"))
        schema = resolved_schema if isinstance(resolved_schema, dict) else parameter
        description = str(parameter.get("description") or schema.get("description") or "")
        required_value = parameter.get("required") if "required" in parameter else None
        fields.append(
            FieldInfo(
                path=f"parameters.{name}",
                name=name,
                type=json_schema_to_type(schema),
                description=description,
                direction="input",
                required=bool(required_value) if required_value is not None else None,
                endpoint=endpoint_path,
                method=method.upper(),
            )
        )
    return fields


def _json_schema(content: Any) -> Any:
    if not isinstance(content, dict):
        return None
    media = content.get("application/json")
    if not isinstance(media, dict):
        media = None
        for key in sorted(content, key=str):
            if isinstance(key, str) and "json" in key.lower():
                candidate = content[key]
                if isinstance(candidate, dict):
                    media = candidate
                    break
    if not isinstance(media, dict):
        return None
    return media.get("schema")


def _flatten_schema(
    schema: Any,
    prefix: str,
    depth: int,
    direction: str,
    endpoint_path: str,
    method: str,
    resolver: _ReferenceResolver,
) -> list[FieldInfo]:
    resolved = resolver.resolve(schema)
    if not isinstance(resolved, dict):
        return []
    properties = resolved.get("properties")
    if not isinstance(properties, dict):
        return []
    raw_required = resolved.get("required")
    required_names = {str(name) for name in raw_required} if isinstance(raw_required, list) else None
    fields: list[FieldInfo] = []
    for raw_name, raw_property in properties.items():
        name = str(raw_name)
        prop = resolver.resolve(raw_property)
        if not isinstance(prop, dict):
            continue
        local_path = f"{prefix}.{name}"
        prop_type = json_schema_to_type(prop)
        description = str(prop.get("description") or "")
        required_value = name in required_names if required_names is not None else None
        if prop_type == "array":
            fields.append(
                FieldInfo(
                    path=local_path,
                    name=name,
                    type="array",
                    description=description,
                    direction=direction,
                    required=required_value,
                    endpoint=endpoint_path,
                    method=method.upper(),
                )
            )
            items = resolver.resolve(prop.get("items"))
            if (
                depth < _MAX_SCHEMA_DEPTH
                and isinstance(items, dict)
                and isinstance(items.get("properties"), dict)
                and items.get("properties")
            ):
                fields.extend(
                    _flatten_schema(
                        items,
                        f"{local_path}[]",
                        depth + 1,
                        direction,
                        endpoint_path,
                        method,
                        resolver,
                    )
                )
        elif prop_type == "object" or isinstance(prop.get("properties"), dict):
            if depth < _MAX_SCHEMA_DEPTH:
                fields.extend(
                    _flatten_schema(
                        prop,
                        local_path,
                        depth + 1,
                        direction,
                        endpoint_path,
                        method,
                        resolver,
                    )
                )
        else:
            fields.append(
                FieldInfo(
                    path=local_path,
                    name=name,
                    type=prop_type,
                    description=description,
                    direction=direction,
                    required=required_value,
                    endpoint=endpoint_path,
                    method=method.upper(),
                )
            )
    return fields


def _request_fields(
    endpoint_path: str,
    method: str,
    path_item: dict[str, Any],
    operation: dict[str, Any],
    resolver: _ReferenceResolver,
) -> list[FieldInfo]:
    fields: list[FieldInfo] = []
    request_body = resolver.resolve(operation.get("requestBody"))
    if isinstance(request_body, dict):
        schema = _json_schema(request_body.get("content"))
        if isinstance(schema, dict):
            fields.extend(
                _flatten_schema(
                    schema,
                    "body",
                    1,
                    "input",
                    endpoint_path,
                    method,
                    resolver,
                )
            )
    for parameter in _merged_parameters(path_item, operation, resolver):
        if str(parameter.get("in") or "") != "body":
            continue
        schema = resolver.resolve(parameter.get("schema"))
        if isinstance(schema, dict):
            fields.extend(
                _flatten_schema(
                    schema,
                    "body",
                    1,
                    "input",
                    endpoint_path,
                    method,
                    resolver,
                )
            )
    return fields


def _selected_response(responses: dict[Any, Any]) -> Any | None:
    for key in ("200", 200):
        if key in responses:
            return key
    for key in responses:
        text = str(key)
        if len(text) == 3 and text.startswith("2") and (text.isdigit() or text[1:].lower() == "xx"):
            return key
    if "default" in responses:
        return "default"
    return None


def _response_fields(
    endpoint_path: str,
    method: str,
    operation: dict[str, Any],
    resolver: _ReferenceResolver,
) -> list[FieldInfo]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return []
    selected = _selected_response(responses)
    if selected is None:
        return []
    response = resolver.resolve(responses[selected])
    if not isinstance(response, dict):
        return []
    schema = _json_schema(response.get("content"))
    if not isinstance(schema, dict):
        schema = response.get("schema")
    if not isinstance(schema, dict):
        return []
    return _flatten_schema(
        schema,
        "body",
        1,
        "output",
        endpoint_path,
        method,
        resolver,
    )


def _parse_operation(
    endpoint_path: str,
    method: str,
    path_item: dict[str, Any],
    operation: dict[str, Any],
    resolver: _ReferenceResolver,
) -> EndpointInfo:
    return EndpointInfo(
        path=endpoint_path,
        method=method.upper(),
        summary=str(operation.get("summary") or ""),
        description=str(operation.get("description") or ""),
        operation_id=str(operation.get("operationId") or ""),
        parameters=_parameter_fields(endpoint_path, method, path_item, operation, resolver),
        request_fields=_request_fields(endpoint_path, method, path_item, operation, resolver),
        response_fields=_response_fields(endpoint_path, method, operation, resolver),
    )


def _parse_endpoints(
    document: dict[str, Any],
    resolver: _ReferenceResolver,
) -> list[EndpointInfo]:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return []
    endpoints: list[EndpointInfo] = []
    for endpoint_path in sorted(paths, key=str):
        path_item = resolver.resolve(paths[endpoint_path])
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            endpoints.append(
                _parse_operation(
                    str(endpoint_path),
                    method,
                    path_item,
                    operation,
                    resolver,
                )
            )
    return endpoints


def parse_openapi(
    source: Path,
    raw_text: str,
    spec_format: str,
    document: dict[str, Any] | None = None,
) -> NormalizedSpec:
    if document is None:
        document = load_spec_document(source, raw_text, spec_format)
    info = document.get("info")
    info_dict = info if isinstance(info, dict) else {}
    resolver = _ReferenceResolver(document)
    resolved_format = "openapi_yaml" if _uses_yaml(raw_text, spec_format) else "openapi_json"
    endpoints = _parse_endpoints(document, resolver)
    spec = NormalizedSpec(
        tool_id=_tool_id(source),
        source=str(source),
        spec_format=resolved_format,
        version=str(info_dict.get("version") or ""),
        title=str(info_dict.get("title") or ""),
        description=str(info_dict.get("description") or ""),
        base_url=_base_url(document),
        endpoints=endpoints,
        metadata={"source": str(source), "spec_format": resolved_format},
    )
    spec.fields = flatten_fields(spec)
    spec.metadata["endpoint_count"] = len(spec.endpoints)
    spec.metadata["field_count"] = len(spec.fields)
    return spec
