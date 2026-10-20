"""RDF namespaces used across the knowledge layer."""

from __future__ import annotations

from rdflib import Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS, XSD

AB = Namespace("https://agent-bazaar.local/ontology#")
TOOL = Namespace("https://agent-bazaar.local/tool/")
UNIT = Namespace("https://agent-bazaar.local/unit#")

STANDARD_PREFIXES: dict[str, Namespace] = {
    "ab": AB,
    "tool": TOOL,
    "unit": UNIT,
    "owl": OWL,
    "rdf": RDF,
    "rdfs": RDFS,
    "sh": SH,
    "skos": SKOS,
    "xsd": XSD,
}


def tool_iri(tool_id: str) -> URIRef:
    return TOOL[tool_id]


def unit_iri(local_name: str) -> URIRef:
    return UNIT[local_name]
