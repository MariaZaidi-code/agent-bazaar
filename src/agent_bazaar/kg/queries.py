"""Subsumption-aware query helpers over the Agent Bazaar knowledge graph."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable

from rdflib import Graph, Node, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from agent_bazaar.kg.quality import is_executable, mapping_coverage
from agent_bazaar.models import ConceptInfo, ToolSummary
from agent_bazaar.ontology.ns import AB, tool_iri

_CAPABILITY_PREFIX = "capability-"


def concept_local_name(value: str) -> str:
    return value.split("#", 1)[1] if "#" in value else value


def resolve_concept_iri(value: str) -> URIRef:
    if "://" in value or value.startswith("urn:"):
        return URIRef(value)
    return AB[value]


def local_name(value: Node | str) -> str:
    text = str(value)
    if "#" in text:
        return text.rsplit("#", 1)[-1]
    if "/" in text:
        return text.rstrip("/").rsplit("/", 1)[-1]
    return text


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "capability"


def _walk(graph: Graph, start: str, *, upward: bool) -> set[str]:
    seen = {start}
    queue: deque[Node] = deque([URIRef(start)])
    while queue:
        current = queue.popleft()
        neighbours = graph.objects(current, RDFS.subClassOf) if upward else graph.subjects(RDFS.subClassOf, current)
        for neighbour in neighbours:
            text = str(neighbour)
            if text not in seen:
                seen.add(text)
                queue.append(neighbour)
    return seen


def superclass_closure(graph: Graph, concept_iri: str) -> set[str]:
    return _walk(graph, str(resolve_concept_iri(concept_iri)), upward=True)


def descendant_closure(graph: Graph, concept_iri: str) -> set[str]:
    return _walk(graph, str(resolve_concept_iri(concept_iri)), upward=False)


def subclass_closure(graph: Graph, concept_iri: str) -> set[str]:
    start = str(resolve_concept_iri(concept_iri))
    return _walk(graph, start, upward=True) | _walk(graph, start, upward=False)


def is_subclass_or_equal(graph: Graph, child: str, parent: str) -> bool:
    return str(resolve_concept_iri(parent)) in superclass_closure(graph, child)


def _tool_nodes(graph: Graph) -> list[Node]:
    return sorted(set(graph.subjects(RDF.type, AB.Tool)), key=str)


def _tool_id(graph: Graph, node: Node) -> str:
    value = graph.value(node, AB.toolId)
    if value is not None and str(value):
        return str(value)
    return local_name(node)


def _capability_names(graph: Graph, node: Node) -> list[str]:
    names: set[str] = set()
    for capability in graph.objects(node, AB.hasCapability):
        labels = [str(label) for label in graph.objects(capability, RDFS.label)]
        if labels:
            names.update(labels)
        else:
            names.add(local_name(capability).removeprefix(_CAPABILITY_PREFIX))
    return sorted(names, key=str.lower)


def _provider_id(graph: Graph, node: Node) -> str:
    provider = graph.value(node, AB.providedBy)
    if provider is None:
        return ""
    value = graph.value(provider, AB.providerId)
    if value is not None and str(value):
        return str(value)
    return local_name(provider).removeprefix("provider-")


def _trust(graph: Graph, node: Node) -> float | None:
    value = graph.value(node, AB.hasTrust)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _offering(graph: Graph, node: Node) -> Node | None:
    return graph.value(node, AB.hasOffering)


def _text_fact(graph: Graph, node: Node, predicate: URIRef, default: str = "") -> str:
    value = graph.value(node, predicate)
    return str(value) if value is not None else default


def _decimal_fact(graph: Graph, node: Node, predicate: URIRef) -> float | None:
    value = graph.value(node, predicate)
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _integer_fact(graph: Graph, node: Node, predicate: URIRef) -> int:
    value = graph.value(node, predicate)
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except ValueError:
        return 0


def _pricing_tier(graph: Graph, node: Node) -> str:
    offering = _offering(graph, node)
    if offering is None:
        return "unknown"
    return _text_fact(graph, offering, AB.pricingTier, "unknown") or "unknown"


def _access_requirement(graph: Graph, node: Node) -> str:
    offering = _offering(graph, node)
    if offering is None:
        return "unknown"
    return _text_fact(graph, offering, AB.accessRequirement, "unknown") or "unknown"


def _licence(graph: Graph, node: Node) -> str:
    offering = _offering(graph, node)
    if offering is None:
        return ""
    return _text_fact(graph, offering, AB.licence)


def tool_summary(graph: Graph, node: Node) -> ToolSummary:
    tool_id = _tool_id(graph, node)
    offering = _offering(graph, node)
    pricing_tier = _pricing_tier(graph, node)
    access_requirement = _access_requirement(graph, node)
    licence = _licence(graph, node)
    rating_value = _decimal_fact(graph, offering, AB.ratingValue) if offering is not None else None
    rating_count = _integer_fact(graph, offering, AB.ratingCount) if offering is not None else 0
    doc_quality = _decimal_fact(graph, offering, AB.docQuality) if offering is not None else None
    return ToolSummary(
        tool_id=tool_id,
        iri=str(node),
        name=str(graph.value(node, AB.name) or tool_id),
        capabilities=_capability_names(graph, node),
        provider_id=_provider_id(graph, node),
        trust=_trust(graph, node),
        score=None,
        reason="",
        pricing_tier=pricing_tier,
        access_requirement=access_requirement,
        rating_value=rating_value,
        rating_count=rating_count,
        doc_quality=doc_quality or 0.0,
        mapping_coverage=mapping_coverage(graph, tool_id),
        is_executable=is_executable(pricing_tier, access_requirement, licence),
        licence=licence,
    )


def tool_summaries(graph: Graph, nodes: Iterable[Node]) -> list[ToolSummary]:
    summaries = [tool_summary(graph, node) for node in nodes]
    return sorted(summaries, key=lambda summary: (summary.tool_id, summary.iri))


def _capability_matches(graph: Graph, capability: Node, query: str, query_slug: str) -> bool:
    text = str(capability)
    if "://" in query and text == query:
        return True
    lowered = query.lower()
    local = local_name(capability)
    local_unprefixed = local.removeprefix(_CAPABILITY_PREFIX)
    if local.lower() == lowered or local_unprefixed.lower() == lowered:
        return True
    if _slug(local_unprefixed) == query_slug:
        return True
    for label in graph.objects(capability, RDFS.label):
        label_text = str(label)
        if label_text.lower() == lowered or _slug(label_text) == query_slug:
            return True
    return False


def tools_by_capability(graph: Graph, capability: str) -> list[ToolSummary]:
    query = capability.strip()
    query_slug = _slug(query)
    nodes = [
        node
        for node in _tool_nodes(graph)
        if any(_capability_matches(graph, cap, query, query_slug) for cap in graph.objects(node, AB.hasCapability))
    ]
    return tool_summaries(graph, nodes)


def tools_by_io(graph: Graph, input_concept: str, output_concept: str) -> list[ToolSummary]:
    acceptable_inputs = superclass_closure(graph, input_concept)
    acceptable_outputs = descendant_closure(graph, output_concept)
    nodes: list[Node] = []
    for node in _tool_nodes(graph):
        inputs = {str(value) for value in graph.objects(node, AB.hasInput)}
        outputs = {str(value) for value in graph.objects(node, AB.hasOutput)}
        if inputs & acceptable_inputs and outputs & acceptable_outputs:
            nodes.append(node)
    return tool_summaries(graph, nodes)


def tools_by_access(graph: Graph, access_requirement: str) -> list[ToolSummary]:
    """Tools whose offering declares the given access requirement."""
    nodes = [node for node in _tool_nodes(graph) if _access_requirement(graph, node) == access_requirement]
    return tool_summaries(graph, nodes)


def tools_by_pricing_tier(graph: Graph, pricing_tier: str) -> list[ToolSummary]:
    """Tools whose offering declares the given pricing tier."""
    nodes = [node for node in _tool_nodes(graph) if _pricing_tier(graph, node) == pricing_tier]
    return tool_summaries(graph, nodes)


def executable_tools(graph: Graph, *, require_known_licence: bool = False) -> list[ToolSummary]:
    """Tools that may be executed: free and keyless.

    A known licence is only demanded when the caller asks for it, which keeps
    this rule identical to the Client policy default.
    """
    nodes = [
        node
        for node in _tool_nodes(graph)
        if is_executable(
            _pricing_tier(graph, node),
            _access_requirement(graph, node),
            _licence(graph, node),
            require_known_licence=require_known_licence,
        )
    ]
    return tool_summaries(graph, nodes)


def _accepts(graph: Graph, candidate_input: str, required_input: str) -> bool:
    return required_input == candidate_input or required_input in descendant_closure(graph, candidate_input)


def compatible_substitutes(graph: Graph, tool_id: str) -> list[ToolSummary]:
    source = tool_iri(tool_id)
    if (source, RDF.type, AB.Tool) not in graph:
        return []
    source_capabilities = set(graph.objects(source, AB.hasCapability))
    source_inputs = [str(value) for value in graph.objects(source, AB.hasInput)]
    source_outputs = [str(value) for value in graph.objects(source, AB.hasOutput)]
    nodes: list[Node] = []
    for candidate in _tool_nodes(graph):
        if candidate == source:
            continue
        candidate_capabilities = set(graph.objects(candidate, AB.hasCapability))
        if not source_capabilities & candidate_capabilities:
            continue
        candidate_inputs = [str(value) for value in graph.objects(candidate, AB.hasInput)]
        candidate_outputs = [str(value) for value in graph.objects(candidate, AB.hasOutput)]
        inputs_ok = all(
            _accepts(graph, candidate_input, required)
            for candidate_input in candidate_inputs
            for required in source_inputs
        )
        outputs_ok = all(
            any(output in descendant_closure(graph, required) for output in candidate_outputs)
            for required in source_outputs
        )
        if inputs_ok and outputs_ok:
            nodes.append(candidate)
    return tool_summaries(graph, nodes)


def concept_for_field(graph: Graph, tool_id: str, field_path: str) -> str | None:
    tool = tool_iri(tool_id)
    for mapping in sorted(graph.subjects(AB.fieldPath, None), key=str):
        if (mapping, AB.tool, tool) not in graph:
            continue
        if str(graph.value(mapping, AB.fieldPath)) != field_path:
            continue
        concept = graph.value(mapping, AB.mapsTo)
        return str(concept) if concept is not None else None
    return None


def concept_info(graph: Graph, iri: str) -> ConceptInfo | None:
    subject = resolve_concept_iri(iri)
    if (subject, RDF.type, AB.Concept) not in graph:
        return None
    label = graph.value(subject, RDFS.label)
    data_type = graph.value(subject, AB.hasDataType)
    unit_family = graph.value(subject, AB.unitFamily)
    default_unit = graph.value(subject, AB.defaultUnit)
    unit_bearing = graph.value(subject, AB.unitBearing)
    definition = graph.value(subject, RDFS.comment)
    parents = sorted({local_name(parent) for parent in graph.objects(subject, RDFS.subClassOf)})
    aliases = sorted({str(alias) for alias in graph.objects(subject, SKOS.altLabel)})
    return ConceptInfo(
        iri=str(subject),
        label=str(label) if label is not None else local_name(subject),
        data_type=str(data_type) if data_type is not None else "string",
        unit_family=local_name(unit_family) if unit_family is not None else None,
        unit=local_name(default_unit) if default_unit is not None else None,
        unit_bearing=bool(unit_bearing.toPython()) if unit_bearing is not None else False,
        parents=parents,
        aliases=aliases,
        definition=str(definition) if definition is not None else "",
    )


def list_concepts(graph: Graph) -> list[ConceptInfo]:
    nodes = sorted(set(graph.subjects(RDF.type, AB.Concept)), key=str)
    infos = [concept_info(graph, str(node)) for node in nodes]
    return sorted((info for info in infos if info is not None), key=lambda info: local_name(info.iri).lower())


def list_tools(graph: Graph) -> list[ToolSummary]:
    return tool_summaries(graph, _tool_nodes(graph))


def describe_graph(graph: Graph) -> dict[str, int]:
    return {
        "tools": len(set(graph.subjects(RDF.type, AB.Tool))),
        "concepts": len(set(graph.subjects(RDF.type, AB.Concept))),
        "mappings": len(set(graph.subjects(RDF.type, AB.Mapping))),
        "claims": len(set(graph.subjects(RDF.type, AB.Claim))),
    }
