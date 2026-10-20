"""Upper ontology loader, frozen at the end of Week 2."""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph

from agent_bazaar.ontology.units import units_graph

UPPER_TTL_PATH = Path(__file__).with_name("upper.ttl")

UPPER_CLASSES = (
    "Service",
    "Tool",
    "Provider",
    "Capability",
    "Concept",
    "Input",
    "Output",
    "Claim",
    "Evidence",
    "Mapping",
    "UnitFamily",
    "Unit",
)


def load_upper(path: str | Path | None = None) -> Graph:
    graph = Graph()
    graph.parse(Path(path) if path else UPPER_TTL_PATH, format="turtle")
    return graph


def upper_with_units() -> Graph:
    graph = load_upper()
    for triple in units_graph():
        graph.add(triple)
    return graph
