"""SHACL validation wrapper, duplicate-concept checks and violation logging."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pyshacl import validate
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, RDFS, SKOS

from agent_bazaar.config import get_settings
from agent_bazaar.ontology.ns import AB
from agent_bazaar.protocols import ValidationResult, Violation

SH = Namespace("http://www.w3.org/ns/shacl#")

DUPLICATE_LABEL_QUERY = """
SELECT ?value (COUNT(?concept) AS ?count)
WHERE { ?concept a <https://agent-bazaar.local/ontology#Concept> ; <http://www.w3.org/2000/01/rdf-schema#label> ?value }
GROUP BY ?value
HAVING (COUNT(?concept) > 1)
"""

DUPLICATE_ALIAS_QUERY = """
SELECT ?value (COUNT(?concept) AS ?count)
WHERE {
  ?concept a <https://agent-bazaar.local/ontology#Concept> ;
           <http://www.w3.org/2004/02/skos/core#altLabel> ?value
}
GROUP BY ?value
HAVING (COUNT(?concept) > 1)
"""

DUPLICATE_LABEL_MESSAGE = "No duplicate concepts: the same label appears on two concepts."
DUPLICATE_ALIAS_MESSAGE = "No duplicate concepts: the same alias appears on two concepts."
UNIT_FAMILY_MESSAGE = "A unit-bearing concept declares exactly one unit family."
MAPPING_UNIT_MESSAGE = (
    "A unit-bearing concept requires a unit, and the unit must belong to the concept's unit family."
)


def load_shapes(path: str | Path | None = None) -> Graph:
    path = Path(path) if path else get_settings().paths.shapes_path
    graph = Graph()
    graph.parse(path, format="turtle")
    return graph


def extract_violations(report_graph: Graph) -> list[Violation]:
    violations: list[Violation] = []
    for result in report_graph.subjects(RDF.type, SH.ValidationResult):
        severity = report_graph.value(result, SH.resultSeverity)
        source = report_graph.value(result, SH.sourceConstraintComponent)
        violations.append(
            Violation(
                message=str(report_graph.value(result, SH.resultMessage) or ""),
                focus_node=str(report_graph.value(result, SH.focusNode) or ""),
                path=str(report_graph.value(result, SH.resultPath) or ""),
                severity=str(severity).rsplit("#", 1)[-1] if severity else "Violation",
                source=str(source).rsplit("#", 1)[-1] if source else "",
                value=str(report_graph.value(result, SH.value) or ""),
            )
        )
    return violations


def duplicate_concept_violations(data_graph: Graph) -> list[Violation]:
    """Detect duplicate labels/aliases with single grouped queries (fast rule check).

    The work plan lists no-duplicate-concepts among the required checks; it runs
    on every validation together with the SHACL shapes and produces the same
    violation messages the report counts.
    """
    violations: list[Violation] = []
    for query, predicate, message in (
        (DUPLICATE_LABEL_QUERY, RDFS.label, DUPLICATE_LABEL_MESSAGE),
        (DUPLICATE_ALIAS_QUERY, SKOS.altLabel, DUPLICATE_ALIAS_MESSAGE),
    ):
        for row in data_graph.query(query):
            value = row[0]
            for node in data_graph.subjects(predicate, value):
                violations.append(
                    Violation(
                        message=message,
                        focus_node=str(node),
                        severity="Violation",
                        source="DuplicateConceptCheck",
                        value=str(value),
                    )
                )
    return violations


def unit_family_declaration_violations(data_graph: Graph) -> list[Violation]:
    violations: list[Violation] = []
    for concept in data_graph.subjects(RDF.type, AB.Concept):
        if (concept, AB.unitBearing, Literal(True)) not in data_graph:
            continue
        if next(data_graph.objects(concept, AB.unitFamily), None) is None:
            violations.append(
                Violation(
                    message=UNIT_FAMILY_MESSAGE,
                    focus_node=str(concept),
                    severity="Violation",
                    source="UnitFamilyRuleCheck",
                    value="true",
                )
            )
    return violations


def mapping_unit_violations(data_graph: Graph) -> list[Violation]:
    violations: list[Violation] = []
    for mapping in data_graph.subjects(RDF.type, AB.Mapping):
        concept = next(data_graph.objects(mapping, AB.mapsTo), None)
        if concept is None:
            continue
        unit = next(data_graph.objects(mapping, AB.unit), None)
        unit_bearing = (concept, AB.unitBearing, Literal(True)) in data_graph
        family = next(data_graph.objects(concept, AB.unitFamily), None)
        problem = ""
        if unit_bearing and unit is None:
            problem = "missing unit"
        elif unit is not None:
            if family is None and unit_bearing:
                problem = "missing unit family"
            elif family is not None and (unit, AB.unitOfFamily, family) not in data_graph:
                problem = str(unit)
        if problem:
            violations.append(
                Violation(
                    message=MAPPING_UNIT_MESSAGE,
                    focus_node=str(mapping),
                    path=str(AB.unit),
                    severity="Violation",
                    source="MappingUnitRuleCheck",
                    value=problem,
                )
            )
    return violations


def rule_check_violations(data_graph: Graph) -> list[Violation]:
    violations: list[Violation] = []
    violations.extend(duplicate_concept_violations(data_graph))
    violations.extend(unit_family_declaration_violations(data_graph))
    violations.extend(mapping_unit_violations(data_graph))
    return violations


def validate_graph(
    data_graph: Graph,
    shapes_graph: Graph | None = None,
    *,
    shapes_path: str | Path | None = None,
    inference: str = "none",
) -> ValidationResult:
    shapes = shapes_graph if shapes_graph is not None else load_shapes(shapes_path)
    conforms, report_graph, report_text = validate(
        data_graph,
        shacl_graph=shapes,
        inference=inference,
        abort_on_first=False,
        allow_infos=True,
        allow_warnings=True,
    )
    violations = extract_violations(report_graph)
    violations.extend(rule_check_violations(data_graph))
    return ValidationResult(conforms=bool(conforms) and not violations, violations=violations, report_text=report_text)


def check_data_node(data_graph: Graph, node, shapes_graph: Graph | None = None) -> ValidationResult:
    """Validate a single node (used by the Mapper's SHACL repair loop)."""
    shapes = shapes_graph if shapes_graph is not None else load_shapes()
    subgraph = Graph()
    for prefix, namespace in data_graph.namespaces():
        subgraph.bind(prefix, namespace)
    for triple in data_graph.triples((node, None, None)):
        subgraph.add(triple)
    for cls in data_graph.objects(node, RDF.type):
        for triple in data_graph.triples((None, RDF.type, cls)):
            subgraph.add(triple)
    return validate_graph(subgraph, shapes, inference="none")


def log_violations(log_path: str | Path, record: dict) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"time": datetime.now(UTC).isoformat(), **record}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
