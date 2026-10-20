"""Deterministic mapping rules and minimal SHACL validation for the Mapper."""

from __future__ import annotations

import hashlib
from functools import lru_cache

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from agent_bazaar.models import ConceptInfo
from agent_bazaar.messages.schema import CorrectionSubmit, FieldMapping, FieldSpec
from agent_bazaar.ontology.ns import AB, TOOL, unit_iri
from agent_bazaar.ontology.units import family_of
from agent_bazaar.ontology.validator import ValidationResult, load_shapes, validate_graph

TYPE_COMPATIBILITY: dict[str, set[str]] = {
    "integer": {"integer"},
    "float": {"integer", "float"},
    "string": {"integer", "float", "string", "date", "datetime", "boolean"},
    "boolean": {"boolean"},
    "date": {"string", "date"},
    "datetime": {"string", "date", "datetime"},
    "array": {"array"},
    "object": {"string", "array", "object"},
}


def check_type_compatibility(field_type: str, concept_data_type: str) -> tuple[bool, str]:
    field_kind = (field_type or "string").strip().lower()
    concept_kind = (concept_data_type or "string").strip().lower()
    accepted = TYPE_COMPATIBILITY.get(concept_kind)
    if accepted is None:
        return True, ""
    if field_kind in accepted:
        return True, ""
    return (
        False,
        f"field type {field_kind!r} is incompatible with concept data type {concept_kind!r}",
    )


def _local_name(reference: str) -> str:
    text = reference.strip()
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    if "/" in text:
        return text.rstrip("/").rsplit("/", 1)[-1]
    if ":" in text:
        return text.rsplit(":", 1)[-1]
    return text


def _resolve_reference(reference: str, concept_iris: dict[str, str]) -> str | None:
    key = reference.strip().lower()
    if not key:
        return None
    iri = concept_iris.get(key)
    if iri is not None:
        return iri
    local = _local_name(reference).lower()
    iri = concept_iris.get(local)
    if iri is not None:
        return iri
    for candidate in concept_iris.values():
        if candidate == reference.strip():
            return candidate
    return None


def check_mapping(
    mapping: FieldMapping,
    field: FieldSpec | None,
    concept: ConceptInfo | None,
    concept_iris: dict[str, str],
) -> list[str]:
    problems: list[str] = []
    reference = mapping.concept.strip()
    if not reference:
        problems.append("mapping has no concept")
    elif concept is None and _resolve_reference(reference, concept_iris) is None:
        problems.append(f"concept {reference!r} not found in ontology")

    if concept is not None and field is not None:
        compatible, message = check_type_compatibility(field.type, concept.data_type)
        if not compatible:
            problems.append(message)

    if concept is not None:
        if concept.unit_bearing:
            if not mapping.unit:
                problems.append(
                    f"concept {concept.label!r} requires a unit from {concept.unit_family or 'its unit family'}"
                )
            else:
                unit_family = family_of(mapping.unit)
                if unit_family is None:
                    problems.append(f"unknown unit {mapping.unit!r}")
                elif concept.unit_family and unit_family != concept.unit_family:
                    problems.append(
                        f"unit {mapping.unit!r} belongs to {unit_family}, "
                        f"but concept {concept.label!r} requires {concept.unit_family}"
                    )
        elif mapping.unit:
            problems.append(
                f"concept {concept.label!r} is not unit-bearing but a unit {mapping.unit!r} was provided"
            )

    if mapping.confidence < 0.0 or mapping.confidence > 1.0:
        problems.append(f"confidence {mapping.confidence} is outside [0, 1]")

    return problems


@lru_cache(maxsize=1)
def _cached_shapes() -> Graph:
    return load_shapes()


def _direction(mapping: FieldMapping) -> str:
    value = getattr(mapping, "direction", None)
    if value in ("input", "output"):
        return value
    return "input" if mapping.field_path.startswith("input.") else "output"


def validate_mapping_shacl(
    mapping: FieldMapping,
    concept: ConceptInfo,
    shapes_graph: Graph | None = None,
) -> ValidationResult:
    graph = Graph()
    graph.bind("ab", AB)
    concept_node = URIRef(concept.iri)
    graph.add((concept_node, RDF.type, OWL.Class))
    graph.add((concept_node, RDF.type, AB.Concept))
    graph.add((concept_node, RDFS.label, Literal(concept.label)))
    graph.add((concept_node, AB.hasDataType, Literal(concept.data_type)))
    graph.add((concept_node, RDFS.subClassOf, AB.Concept))
    graph.add((concept_node, AB.unitBearing, Literal(bool(concept.unit_bearing))))
    if concept.unit_family:
        graph.add((concept_node, AB.unitFamily, AB[concept.unit_family]))

    digest = hashlib.sha1(f"{mapping.field_path}|{concept.iri}".encode("utf-8")).hexdigest()[:12]
    mapping_node = AB[f"mapping-{digest}"]
    tool_node = TOOL[f"mapper-{digest}"]
    graph.add((mapping_node, RDF.type, AB.Mapping))
    graph.add((mapping_node, AB.tool, tool_node))
    graph.add((mapping_node, AB.fieldPath, Literal(mapping.field_path)))
    graph.add((mapping_node, AB.direction, Literal(_direction(mapping))))
    graph.add((mapping_node, AB.mapsTo, concept_node))
    graph.add((mapping_node, AB.confidence, Literal(str(float(mapping.confidence)), datatype=XSD.decimal)))
    if mapping.unit:
        unit_node = unit_iri(_local_name(mapping.unit))
        graph.add((mapping_node, AB.unit, unit_node))
        unit_family = family_of(mapping.unit)
        if unit_family:
            graph.add((unit_node, AB.unitOfFamily, AB[unit_family]))

    shapes = shapes_graph if shapes_graph is not None else _cached_shapes()
    return validate_graph(graph, shapes, inference="none")


def validate_correction(
    correction: CorrectionSubmit,
    concept_iris: dict[str, str],
    concepts_by_iri: dict[str, ConceptInfo],
) -> list[str]:
    problems: list[str] = []
    iri = _resolve_reference(correction.corrected_concept, concept_iris)
    if iri is None and correction.corrected_concept.strip() in concepts_by_iri:
        iri = correction.corrected_concept.strip()
    concept = concepts_by_iri.get(iri) if iri is not None else None
    if concept is None:
        problems.append(f"concept {correction.corrected_concept!r} not found in ontology")
        return problems

    if correction.corrected_unit:
        unit_family = family_of(correction.corrected_unit)
        if unit_family is None:
            problems.append(f"unknown unit {correction.corrected_unit!r}")
        elif concept.unit_family is None:
            problems.append(
                f"concept {concept.label!r} does not declare a unit family for unit "
                f"{correction.corrected_unit!r}"
            )
        elif unit_family != concept.unit_family:
            problems.append(
                f"unit {correction.corrected_unit!r} belongs to {unit_family}, "
                f"but concept {concept.label!r} requires {concept.unit_family}"
            )
    elif concept.unit_bearing:
        problems.append(
            f"concept {concept.label!r} requires a unit from {concept.unit_family or 'its unit family'}"
        )

    return problems
