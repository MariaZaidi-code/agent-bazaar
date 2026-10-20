"""Tests for deterministic OpenAPI and Swagger ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from agent_bazaar.ingestion.models import NormalizedSpec
from agent_bazaar.ingestion.utility import IngestionUtility, derive_tool_id

FIXTURES = Path(__file__).parent / "fixtures"


def _fields(spec: NormalizedSpec) -> dict[str, object]:
    return {field.path: field for field in spec.fields}


def test_json_spec_extracts_endpoints_fields_and_metadata() -> None:
    source = FIXTURES / "sample_openapi.json"
    spec = IngestionUtility().ingest(source)
    fields = _fields(spec)

    assert spec.tool_id == "sample-openapi"
    assert spec.source == str(source)
    assert spec.spec_format == "openapi_json"
    assert spec.title == "Weather and Translation API"
    assert spec.version == "1.0.0"
    assert spec.description == "Small sample API used by ingestion tests."
    assert spec.base_url == "https://api.example.com"
    assert spec.retrieved_at is not None
    assert spec.metadata["source"] == str(source)
    assert spec.metadata["spec_format"] == "openapi_json"
    assert spec.metadata["endpoint_count"] == 3
    assert spec.metadata["field_count"] == len(spec.fields)

    assert [(endpoint.path, endpoint.method) for endpoint in spec.endpoints] == [
        ("/v1/forecast", "GET"),
        ("/v1/locations/{city}", "GET"),
        ("/v1/translate", "POST"),
    ]

    expected_paths = {
        "input.get:/v1/forecast.parameters.latitude",
        "input.get:/v1/forecast.parameters.longitude",
        "input.get:/v1/forecast.parameters.X-API-Key",
        "output.get:/v1/forecast.body.temperature_2m",
        "output.get:/v1/forecast.body.humidity",
        "output.get:/v1/forecast.body.current.temperature_2m",
        "output.get:/v1/forecast.body.current.wind_speed",
        "output.get:/v1/forecast.body.daily",
        "output.get:/v1/forecast.body.daily[].date",
        "output.get:/v1/forecast.body.daily[].temperature_min",
        "input.post:/v1/translate.body.text",
        "input.post:/v1/translate.body.target_language",
        "input.post:/v1/translate.body.format",
        "output.post:/v1/translate.body.translated_text",
        "output.post:/v1/translate.body.confidence",
        "input.get:/v1/locations/{city}.parameters.city",
        "input.get:/v1/locations/{city}.parameters.limit",
        "output.get:/v1/locations/{city}.body.name",
        "output.get:/v1/locations/{city}.body.country",
        "output.get:/v1/locations/{city}.body.elevation",
    }
    assert expected_paths <= set(fields)

    assert fields["input.get:/v1/forecast.parameters.latitude"].type == "float"
    assert fields["input.get:/v1/forecast.parameters.latitude"].required is True
    assert fields["input.get:/v1/forecast.parameters.X-API-Key"].type == "string"
    assert fields["input.get:/v1/forecast.parameters.X-API-Key"].required is False
    assert fields["output.get:/v1/forecast.body.temperature_2m"].type == "float"
    assert (
        fields["output.get:/v1/forecast.body.temperature_2m"].description
        == "Air temperature at two metres."
    )
    assert fields["output.get:/v1/forecast.body.humidity"].type == "integer"
    assert fields["output.get:/v1/forecast.body.daily"].type == "array"
    assert fields["output.get:/v1/forecast.body.daily[].temperature_min"].type == "float"
    assert fields["input.post:/v1/translate.body.text"].type == "string"
    assert fields["input.post:/v1/translate.body.text"].required is True
    assert fields["input.post:/v1/translate.body.format"].required is False
    assert fields["input.get:/v1/locations/{city}.parameters.city"].type == "string"
    assert fields["input.get:/v1/locations/{city}.parameters.limit"].type == "integer"


def test_yaml_spec_matches_json_field_paths() -> None:
    utility = IngestionUtility()
    json_spec = utility.ingest(FIXTURES / "sample_openapi.json")
    yaml_spec = utility.ingest(FIXTURES / "sample_openapi.yaml")

    assert yaml_spec.spec_format == "openapi_yaml"
    assert yaml_spec.title == json_spec.title
    assert yaml_spec.version == json_spec.version
    assert yaml_spec.base_url == json_spec.base_url
    assert {field.path for field in yaml_spec.fields} == {
        field.path for field in json_spec.fields
    }
    assert [(endpoint.path, endpoint.method) for endpoint in yaml_spec.endpoints] == [
        (endpoint.path, endpoint.method) for endpoint in json_spec.endpoints
    ]


def test_swagger_2_spec_parses_host_base_path_and_fields(tmp_path: Path) -> None:
    document = {
        "swagger": "2.0",
        "info": {"title": "Legacy API", "version": "2.0.0"},
        "host": "legacy.example.com",
        "basePath": "/v2",
        "schemes": ["https"],
        "paths": {
            "/ping": {
                "get": {
                    "parameters": [
                        {"name": "q", "in": "query", "type": "string"},
                    ],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "schema": {
                                "type": "object",
                                "properties": {"ok": {"type": "boolean"}},
                            },
                        }
                    },
                }
            }
        },
    }
    source = tmp_path / "legacy_swagger.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    spec = IngestionUtility().ingest(source)
    fields = _fields(spec)

    assert spec.base_url == "https://legacy.example.com/v2"
    assert fields["input.get:/ping.parameters.q"].type == "string"
    assert fields["output.get:/ping.body.ok"].type == "boolean"


def test_malformed_json_returns_parse_error_object(tmp_path: Path) -> None:
    source = tmp_path / "broken.json"
    source.write_text('{"openapi": "3.0.0", "paths": {', encoding="utf-8")
    spec, error = IngestionUtility().try_ingest(source)

    assert spec is None
    assert error is not None
    assert error.code == "parse_error"
    assert error.source == str(source)
    assert error.details["line"] == 1
    assert "line 1" in error.message


def test_non_openapi_json_returns_not_openapi(tmp_path: Path) -> None:
    source = tmp_path / "not_a_spec.json"
    source.write_text(json.dumps({"name": "widget", "version": 1}), encoding="utf-8")
    spec, error = IngestionUtility().try_ingest(source)

    assert spec is None
    assert error is not None
    assert error.code == "not_openapi"


def test_unsupported_suffix_returns_unsupported_format(tmp_path: Path) -> None:
    source = tmp_path / "spec.xml"
    source.write_text("<spec />", encoding="utf-8")
    spec, error = IngestionUtility().try_ingest(source)

    assert spec is None
    assert error is not None
    assert error.code == "unsupported_format"


def test_explicit_spec_format_overrides_suffix(tmp_path: Path) -> None:
    source = tmp_path / "spec.custom"
    source.write_text((FIXTURES / "sample_openapi.json").read_text(encoding="utf-8"), encoding="utf-8")
    utility = IngestionUtility()

    spec = utility.ingest(source, spec_format="openapi_json")
    assert spec.spec_format == "openapi_json"
    assert spec.metadata["endpoint_count"] == 3

    ignored, error = utility.try_ingest(source)
    assert ignored is None
    assert error is not None
    assert error.code == "unsupported_format"


def test_derive_tool_id_normalizes_stem() -> None:
    assert derive_tool_id(Path("Some Spec (v2) ---.json")) == "some-spec-v2"
    assert derive_tool_id(Path("___")) == "tool"
