"""Tool-graph adapter that serves the app from the RDF knowledge graph.

The Client/Provider/Interface layer talks to
:class:`app.knowledge.graph.ToolKnowledgeGraph`.  This module exposes the same
operations on top of the shared RDF knowledge graph
(:class:`agent_bazaar.kg.store.KgStore`) so both branches can be merged without
touching the Client loop.

Vocabulary translation is delegated to :mod:`app.integration.canonical`: RDF
concepts, units and capabilities are mapped to the curated names of the app
before a tool is served.  Tools that only exist in the local catalogue (for
example providers that were never written to RDF) are still resolved through the
optional ``local_graph``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from agent_bazaar.kg.queries import is_subclass_or_equal
from agent_bazaar.kg.store import KgStore
from agent_bazaar.models import ToolSummary
from agent_bazaar.ontology.ns import AB, tool_iri
from app.integration.canonical import (
    CURATED_CAPABILITIES,
    canonical_capability,
    canonical_concept,
    canonical_unit,
    capability_for_concepts,
)
from app.schemas import ClaimSpec, ConceptSpec, ToolSpec

if TYPE_CHECKING:
    from app.knowledge.graph import ToolKnowledgeGraph

FALLBACK_CAPABILITY = "general"


class RdfToolGraph:
    """Serve the tool-graph API of the app from the RDF knowledge graph."""

    def __init__(
        self,
        store: KgStore,
        *,
        local_graph: ToolKnowledgeGraph | None = None,
        ontology: object | None = None,
    ) -> None:
        self.store = store
        self.local_graph = local_graph
        self.ontology = ontology
        self._added: dict[str, ToolSpec] = {}

    def add(self, tool: ToolSpec) -> None:
        """Keep a tool that is not part of the RDF graph reachable."""
        self._added[tool.id] = tool
        if self.local_graph is not None:
            self.local_graph.add(tool)

    def all(self) -> list[ToolSpec]:
        tools: dict[str, ToolSpec] = {}
        for summary in self.store.list_tools():
            spec = self._spec(summary)
            tools.setdefault(spec.id, spec)
        for tool in self._local_tools():
            tools.setdefault(tool.id, tool)
        return sorted(tools.values(), key=lambda item: item.id)

    def get(self, tool_id: str) -> ToolSpec | None:
        for summary in self.store.list_tools():
            if summary.tool_id == tool_id:
                return self._spec(summary)
        for tool in self._local_tools():
            if tool.id == tool_id:
                return tool
        return None

    def by_capability(self, capability: str) -> list[ToolSpec]:
        target = canonical_capability(capability)
        return [tool for tool in self.all() if canonical_capability(tool.capability) == target]

    def by_concept(self, concept: str) -> list[ToolSpec]:
        target = canonical_concept(concept)
        return [
            tool
            for tool in self.all()
            if any(canonical_concept(item.concept) == target for item in tool.inputs + tool.outputs)
        ]

    def tools_by_provider(self, provider_id: str) -> list[ToolSpec]:
        return [tool for tool in self.all() if tool.provider_id == provider_id]

    def neighbors(self, tool_id: str, limit: int = 6) -> list[ToolSpec]:
        source = self.get(tool_id)
        if source is None:
            return []
        concepts = {canonical_concept(item.concept) for item in source.inputs + source.outputs}
        capability = canonical_capability(source.capability)
        scored: list[tuple[int, ToolSpec]] = []
        for other in self.all():
            if other.id == tool_id:
                continue
            other_concepts = {canonical_concept(item.concept) for item in other.inputs + other.outputs}
            shared_capability = int(canonical_capability(other.capability) == capability)
            score = shared_capability * 3 + len(concepts & other_concepts)
            if score:
                scored.append((score, other))
        scored.sort(key=lambda item: (-item[0], item[1].id))
        return [tool for _, tool in scored[:limit]]

    def compatible_substitutes(
        self,
        capability: str,
        available_inputs: list[str],
        available_outputs: list[str] | None,
        exclude: set[str] | None = None,
    ) -> list[ToolSpec]:
        excluded = exclude or set()
        candidates: list[ToolSpec] = []
        for tool in self.by_capability(capability):
            if tool.id in excluded:
                continue
            required = [canonical_concept(item.concept) for item in tool.inputs if item.required]
            if not all(
                any(self._is_subtype(available, required_concept) for available in available_inputs)
                for required_concept in required
            ):
                continue
            if available_outputs:
                outputs = [canonical_concept(item.concept) for item in tool.outputs if item.required]
                if not all(
                    any(self._is_subtype(source, target) for source in outputs)
                    for target in available_outputs
                ):
                    continue
            candidates.append(tool)
        return candidates

    def export_turtle(self, path: Path, trust: dict[str, dict[str, Any]] | None = None) -> bool:
        target = Path(path)
        try:
            self.store.save(target)
        except OSError:
            return False
        if not trust:
            return True
        graph = Graph()
        for prefix, namespace in self.store.graph.namespaces():
            graph.bind(prefix, namespace)
        for triple in self.store.graph:
            graph.add(triple)
        for provider_id, data in trust.items():
            score = data.get("score")
            if score is None:
                continue
            try:
                value = Literal(float(score))
            except (TypeError, ValueError):
                continue
            for provider in self._provider_nodes(provider_id):
                graph.add((provider, AB.hasTrust, value))
        try:
            graph.serialize(destination=str(target), format="turtle")
        except OSError:
            return False
        return True

    def _local_tools(self) -> list[ToolSpec]:
        tools: dict[str, ToolSpec] = {}
        if self.local_graph is not None:
            for tool in self.local_graph.all():
                tools[tool.id] = tool
        for tool_id, tool in self._added.items():
            tools.setdefault(tool_id, tool)
        return list(tools.values())

    def _spec(self, summary: ToolSummary) -> ToolSpec:
        node = URIRef(summary.iri) if summary.iri else tool_iri(summary.tool_id)
        inputs, outputs = self._fields(node)
        return ToolSpec(
            id=summary.tool_id,
            name=summary.name or summary.tool_id,
            provider_id=summary.provider_id,
            description=self._description(node),
            capability=self._capability(summary, outputs),
            inputs=inputs,
            outputs=outputs,
            claims=self._claims(node),
            execution="fixture",
        )

    def _description(self, node: URIRef) -> str:
        value = self.store.graph.value(node, AB.description)
        return str(value) if value is not None else ""

    def _capability(self, summary: ToolSummary, outputs: list[ConceptSpec]) -> str:
        for raw in summary.capabilities:
            candidate = canonical_capability(raw)
            if candidate in CURATED_CAPABILITIES:
                return candidate
        inferred = capability_for_concepts(item.concept for item in outputs)
        return inferred or FALLBACK_CAPABILITY

    def _fields(self, node: URIRef) -> tuple[list[ConceptSpec], list[ConceptSpec]]:
        inputs: list[ConceptSpec] = []
        outputs: list[ConceptSpec] = []
        for mapping in sorted(self.store.graph.subjects(AB.tool, node), key=str):
            concept_node = self.store.graph.value(mapping, AB.mapsTo)
            if concept_node is None:
                continue
            direction = str(self.store.graph.value(mapping, AB.direction) or "")
            spec = self._concept_spec(mapping, str(concept_node))
            if direction == "input":
                inputs.append(spec)
            elif direction == "output":
                outputs.append(spec)
        return inputs, outputs

    def _concept_spec(self, mapping: URIRef, concept_iri: str) -> ConceptSpec:
        concept = canonical_concept(concept_iri)
        unit = canonical_unit(self.store.graph.value(mapping, AB.unit))
        info = self.store.get_concept(concept_iri)
        field_path = str(self.store.graph.value(mapping, AB.fieldPath) or "")
        return ConceptSpec(
            concept=concept,
            name=self._field_name(field_path, concept),
            unit=unit,
            datatype=info.data_type if info is not None else "string",
        )

    def _claims(self, node: URIRef) -> list[ClaimSpec]:
        claims: list[ClaimSpec] = []
        for claim_node in sorted(self.store.graph.objects(node, AB.makesClaim), key=str):
            text = self.store.graph.value(claim_node, AB.claimText)
            if text is None:
                continue
            source = self.store.graph.value(claim_node, AB.source)
            claims.append(ClaimSpec(text=str(text), evidence=str(source) if source is not None else ""))
        return claims

    def _provider_nodes(self, provider_id: str) -> list[URIRef]:
        nodes: list[URIRef] = []
        for node in self.store.graph.subjects(RDF.type, AB.Provider):
            value = self.store.graph.value(node, AB.providerId)
            if value is not None and str(value) == provider_id:
                nodes.append(node)
        fallback = AB[f"provider-{provider_id}"]
        if (fallback, None, None) in self.store.graph and fallback not in nodes:
            nodes.append(fallback)
        return nodes

    def _is_subtype(self, child: str, parent: str) -> bool:
        left = canonical_concept(child)
        right = canonical_concept(parent)
        if not left or not right:
            return False
        if left == right:
            return True
        return is_subclass_or_equal(self.store.graph, left, right)

    @staticmethod
    def _field_name(field_path: str, concept: str) -> str:
        if not field_path:
            return concept
        name = field_path.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
        return name or concept
