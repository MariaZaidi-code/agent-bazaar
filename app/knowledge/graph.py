from __future__ import annotations

from pathlib import Path
from typing import Any

from app.knowledge.ontology import Ontology
from app.schemas import ToolSpec


class ToolKnowledgeGraph:
    def __init__(self, ontology: Ontology) -> None:
        self.ontology = ontology
        self._tools: dict[str, ToolSpec] = {}

    def add(self, tool: ToolSpec) -> None:
        self._tools[tool.id] = tool

    def add_many(self, tools: list[ToolSpec]) -> None:
        for tool in tools:
            self.add(tool)

    def get(self, tool_id: str) -> ToolSpec | None:
        return self._tools.get(tool_id)

    def all(self) -> list[ToolSpec]:
        return sorted(self._tools.values(), key=lambda item: item.id)

    def by_capability(self, capability: str) -> list[ToolSpec]:
        return [tool for tool in self.all() if tool.capability == capability]

    def by_concept(self, concept: str) -> list[ToolSpec]:
        return [
            tool
            for tool in self.all()
            if any(self.ontology.is_subtype(item.concept, concept) for item in tool.inputs + tool.outputs)
        ]

    def neighbors(self, tool_id: str, limit: int = 6) -> list[ToolSpec]:
        tool = self.get(tool_id)
        if tool is None:
            return []
        concepts = {item.concept for item in tool.inputs + tool.outputs}
        scored: list[tuple[int, ToolSpec]] = []
        for other in self.all():
            if other.id == tool_id:
                continue
            other_concepts = {item.concept for item in other.inputs + other.outputs}
            shared_capability = int(other.capability == tool.capability)
            shared_concepts = len(concepts & other_concepts)
            score = shared_capability * 3 + shared_concepts
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
            required = [item.concept for item in tool.inputs if item.required]
            if not all(
                any(
                    self.ontology.check_link(available, None, required_concept, None).valid
                    for available in available_inputs
                )
                for required_concept in required
            ):
                continue
            if available_outputs:
                outputs = [item.concept for item in tool.outputs if item.required]
                if not all(
                    any(
                        self.ontology.check_link(source, None, target, None).valid
                        for source in outputs
                    )
                    for target in available_outputs
                ):
                    continue
            candidates.append(tool)
        return candidates

    def tools_by_provider(self, provider_id: str) -> list[ToolSpec]:
        return [tool for tool in self.all() if tool.provider_id == provider_id]

    def to_triples(self, trust: dict[str, dict[str, Any]] | None = None) -> list[tuple[str, str, str]]:
        triples: list[tuple[str, str, str]] = []
        for name, data in self.ontology.concepts.items():
            triples.append((f"ab:Concept/{name}", "rdf:type", "owl:Class"))
            for parent in data.get("parents", []):
                triples.append((f"ab:Concept/{name}", "rdfs:subClassOf", f"ab:Concept/{parent}"))
        for tool in self.all():
            subject = f"ab:Tool/{tool.id}"
            triples.extend(
                [
                    (subject, "rdf:type", "ab:Service"),
                    (subject, "rdfs:label", f'"{tool.name}"'),
                    (subject, "ab:provider", f"ab:Provider/{tool.provider_id}"),
                    (subject, "ab:capability", f"ab:Capability/{tool.capability}"),
                ]
            )
            for item in tool.inputs:
                triples.append((subject, "ab:hasInput", f"ab:Concept/{item.concept}"))
            for item in tool.outputs:
                triples.append((subject, "ab:hasOutput", f"ab:Concept/{item.concept}"))
            for claim in tool.claims:
                triples.append((subject, "ab:makesClaim", f'"{claim.text}"'))
            if trust and tool.provider_id in trust:
                triples.append(
                    (
                        f"ab:Provider/{tool.provider_id}",
                        "ab:hasTrust",
                        str(trust[tool.provider_id]["score"]),
                    )
                )
        return triples

    def export_jsonld(self, path: Path, trust: dict[str, dict[str, Any]] | None = None) -> bool:
        target = Path(path)
        try:
            from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace
        except ImportError:
            return False
        graph = Graph()
        AB = Namespace("https://agentbazaar.local/ontology#")
        graph.bind("ab", AB)
        graph.bind("rdf", RDF)
        graph.bind("rdfs", RDFS)
        graph.bind("owl", OWL)
        for subject, predicate, obj in self.to_triples(trust):
            subject_ref = self._uri(AB, subject)
            predicate_ref = self._uri(AB, predicate)
            if obj.startswith('"') and obj.endswith('"'):
                obj_ref: Any = Literal(obj[1:-1])
            elif predicate == "ab:hasTrust":
                obj_ref = Literal(float(obj))
            else:
                obj_ref = self._uri(AB, obj)
            graph.add((subject_ref, predicate_ref, obj_ref))
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            graph.serialize(destination=str(target), format="json-ld")
        except (OSError, Exception):
            return False
        return True

    def export_turtle(self, path: Path, trust: dict[str, dict[str, Any]] | None = None) -> bool:
        try:
            from rdflib import OWL, RDF, RDFS, Graph, Literal, Namespace
        except ImportError:
            return False
        graph = Graph()
        AB = Namespace("https://agentbazaar.local/ontology#")
        graph.bind("ab", AB)
        graph.bind("rdf", RDF)
        graph.bind("rdfs", RDFS)
        graph.bind("owl", OWL)
        for subject, predicate, obj in self.to_triples(trust):
            subject_ref = self._uri(AB, subject)
            predicate_ref = self._uri(AB, predicate)
            if obj.startswith('"') and obj.endswith('"'):
                obj_ref: Any = Literal(obj[1:-1])
            elif predicate == "ab:hasTrust":
                obj_ref = Literal(float(obj))
            else:
                obj_ref = self._uri(AB, obj)
            graph.add((subject_ref, predicate_ref, obj_ref))
        path.parent.mkdir(parents=True, exist_ok=True)
        graph.serialize(destination=str(path), format="turtle")
        return True

    @staticmethod
    def _uri(namespace: Any, value: str) -> Any:
        from rdflib import OWL, RDF, RDFS, URIRef

        fixed = {
            "rdf:type": RDF.type,
            "rdfs:subClassOf": RDFS.subClassOf,
            "rdfs:label": RDFS.label,
            "owl:Class": OWL.Class,
        }
        if value in fixed:
            return fixed[value]
        if ":" in value and not value.startswith("ab:"):
            return URIRef(value)
        clean = value.replace("ab:", "")
        return namespace[clean.replace("/", "_")]
