"""Tests for deterministic mapper rules and minimal SHACL validation."""

from __future__ import annotations

from agent_bazaar.mapper.rules import (
    TYPE_COMPATIBILITY,
    check_mapping,
    check_type_compatibility,
    validate_correction,
    validate_mapping_shacl,
)
from agent_bazaar.messages.schema import CorrectionSubmit, FieldMapping, FieldSpec
from agent_bazaar.models import ConceptInfo
from agent_bazaar.ontology.ns import AB


def _temperature() -> ConceptInfo:
    return ConceptInfo(
        iri=str(AB.Temperature),
        label="Temperature",
        data_type="float",
        unit_family="TemperatureUnit",
        unit="Celsius",
        unit_bearing=True,
        aliases=["temp", "temperature_2m"],
    )


def _field() -> FieldSpec:
    return FieldSpec(
        field_path="output.get:/v1/forecast.temperature_2m",
        name="temperature_2m",
        type="float",
    )


def _mapping(unit: str | None = "Celsius") -> FieldMapping:
    return FieldMapping(
        field_path="output.get:/v1/forecast.temperature_2m",
        concept=str(AB.Temperature),
        concept_label="Temperature",
        unit=unit,
        confidence=0.9,
    )


def test_type_table_is_lax_but_directional() -> None:
    assert "integer" in TYPE_COMPATIBILITY["float"]
    assert "integer" in TYPE_COMPATIBILITY["string"]
    assert "float" in TYPE_COMPATIBILITY["string"]
    assert "datetime" in TYPE_COMPATIBILITY["string"]
    assert "date" in TYPE_COMPATIBILITY["datetime"]
    assert "array" in TYPE_COMPATIBILITY["object"]

    assert check_type_compatibility("integer", "float")[0] is True
    assert check_type_compatibility("float", "integer")[0] is False
    assert check_type_compatibility("string", "date")[0] is True
    assert check_type_compatibility("object", "string")[0] is False
    compatible, message = check_type_compatibility("array", "float")
    assert compatible is False
    assert "incompatible" in message


def test_check_mapping_flags_unit_family_mismatch() -> None:
    concept = _temperature()
    problems = check_mapping(
        _mapping("Percent"),
        _field(),
        concept,
        {"temperature": concept.iri},
    )
    assert any("TemperatureUnit" in problem for problem in problems)


def test_check_mapping_flags_missing_unit() -> None:
    concept = _temperature()
    problems = check_mapping(
        _mapping(None),
        _field(),
        concept,
        {"temperature": concept.iri},
    )
    assert any("requires a unit" in problem for problem in problems)


def test_check_mapping_flags_unknown_concept_and_confidence() -> None:
    mapping = _mapping()
    mapping.concept = "NoSuchConcept"
    mapping.confidence = 1.5
    problems = check_mapping(mapping, _field(), None, {"temperature": str(AB.Temperature)})
    assert any("not found" in problem for problem in problems)
    assert any("confidence" in problem for problem in problems)


def test_shacl_accepts_valid_temperature_celsius_mapping() -> None:
    result = validate_mapping_shacl(_mapping("Celsius"), _temperature())
    assert result.conforms is True
    assert result.violations == []


def test_shacl_rejects_percent_on_temperature() -> None:
    result = validate_mapping_shacl(_mapping("Percent"), _temperature())
    assert result.conforms is False
    assert result.violations
    assert any("unit" in violation.message.lower() for violation in result.violations)


def test_validate_correction_accepts_known_concept_and_unit() -> None:
    concept = _temperature()
    correction = CorrectionSubmit(
        tool_id="weather",
        field_path="output.temperature_2m",
        corrected_concept="Temperature",
        corrected_unit="Celsius",
    )
    problems = validate_correction(correction, {"temperature": concept.iri}, {concept.iri: concept})
    assert problems == []


def test_validate_correction_rejects_unknown_concept() -> None:
    concept = _temperature()
    correction = CorrectionSubmit(
        tool_id="weather",
        field_path="output.temperature_2m",
        corrected_concept="NoSuchConcept",
    )
    problems = validate_correction(correction, {"temperature": concept.iri}, {concept.iri: concept})
    assert problems
    assert "not found" in problems[0]
