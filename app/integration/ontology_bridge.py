"""Knowledge-layer ontology served through the ontology API of the app.

The Client/Provider/Interface layer talks to
:class:`app.knowledge.ontology.Ontology`.  This module serves the same
operations from the RDF ontology of the knowledge layer
(:class:`agent_bazaar.kg.store.KgStore`) so both branches can be merged without
touching the Client loop.

Vocabulary translation is delegated to :mod:`app.integration.canonical`: concept,
unit and capability names are mapped to the canonical knowledge-layer names
before they are served.  The knowledge layer stays the source of truth for
everything it models; the local fallback ontology (``app/data/ontology.json``)
is consulted only for the concepts the knowledge layer does not know, which are
documented in :data:`app.integration.canonical.EXTERNAL_CONCEPTS`.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from rdflib.namespace import OWL, RDFS

from agent_bazaar.kg.queries import is_subclass_or_equal
from agent_bazaar.kg.store import KgStore
from agent_bazaar.models import ConceptInfo
from agent_bazaar.ontology.ns import AB
from agent_bazaar.ontology.units import UNIT_FAMILIES, family_of, unit_def
from app.integration.canonical import (
    CURATED_CAPABILITIES,
    EXTERNAL_CONCEPTS,
    canonical_capability,
    canonical_concept,
    canonical_unit,
    is_external_concept,
    is_known_unit,
    known_units,
)
from app.knowledge.ontology import Ontology, OntologyCheck
from app.schemas import ConceptSpec, ToolSpec

LOCAL_ONTOLOGY_PATH = Path(__file__).resolve().parents[1] / "data" / "ontology.json"


def _local_name(node: Any) -> str:
    return str(node).rsplit("#", 1)[-1]


class KnowledgeOntology:
    """Serve the ontology API of the app from the RDF ontology of the knowledge layer."""

    def __init__(self, store: KgStore, *, local: Ontology | None = None) -> None:
        self.store = store
        self.local = local
        self._infos: dict[str, ConceptInfo] = {}
        for info in store.list_concepts():
            self._infos[_local_name(info.iri)] = info
        self._parents_cache: dict[str, list[str]] = {}
        self._ancestors_cache: dict[str, list[str]] = {}
        self._ancestor_names: set[str] = set()
        for name in self._infos:
            self._ancestor_names.update(self._rdf_ancestors(name))
        self._external_names: set[str] = set(EXTERNAL_CONCEPTS)
        self._class_names: set[str] = {
            _local_name(node) for node in store.graph.subjects(None, OWL.Class)
        }
        self.version = f"knowledge+{local.version}" if local is not None else "knowledge"
        self.concepts = self._concept_view()
        self.units = self._unit_view()
        self.capabilities = self._capability_view()

    # -- concept lookup ---------------------------------------------------

    def exists(self, concept: str) -> bool:
        """True when the knowledge layer or the local fallback models the concept."""
        name = canonical_concept(concept)
        if not name:
            return False
        if name in self._infos or name in self._ancestor_names:
            return True
        if self.local is not None and (name in self.local.concepts or concept in self.local.concepts):
            return True
        return is_external_concept(name)

    def ancestors(self, concept: str) -> list[str]:
        """Return the canonical ancestors of a concept from the RDF subclass closure."""
        name = canonical_concept(concept)
        if name in self._infos:
            return list(self._rdf_ancestors(name))
        local = self._local_concept(concept)
        if local is not None:
            return [canonical_concept(parent) for parent in self.local.ancestors(local)]
        return []

    def is_subtype(self, child: str, parent: str) -> bool:
        """True when the canonical child is the canonical parent or a subclass of it."""
        left = canonical_concept(child)
        right = canonical_concept(parent)
        if not left or not right:
            return False
        if left == right:
            return True
        if left in self._infos:
            return is_subclass_or_equal(self.store.graph, left, right)
        local = self._local_concept(child)
        if local is not None and self.local is not None:
            target = parent if parent in self.local.concepts else right
            return self.local.is_subtype(local, target)
        return False

    def check_capability(self, tool_capability: str, required: str) -> bool:
        """Compare the canonical capability names of the knowledge layer."""
        left = canonical_capability(tool_capability)
        right = canonical_capability(required)
        if not left or not right:
            return False
        return left == right

    # -- units -------------------------------------------------------------

    def unit_dimension(self, unit: str | None) -> str | None:
        """Return the unit family of the canonical unit in the knowledge layer."""
        if unit is None:
            return None
        name = canonical_unit(unit)
        if not name:
            return None
        family = family_of(name)
        if family is not None:
            return family
        if self.local is not None:
            local = self.local.units.get(unit) or self.local.units.get(name)
            if local is not None:
                return str(local.get("dimension") or "") or None
        return None

    def units_compatible(self, source: str | None, target: str | None) -> tuple[bool, bool]:
        """Return the (compatible, conversion_required) pair of the knowledge layer units."""
        if source is None or target is None:
            return True, False
        left = canonical_unit(source)
        right = canonical_unit(target)
        if not left or not right:
            return True, False
        if left == right:
            return True, False
        source_family = family_of(left)
        target_family = family_of(right)
        if source_family is None or target_family is None or source_family != target_family:
            return False, False
        return True, self._convertible(left, right)

    # -- links and validation ----------------------------------------------

    def check_link(
        self,
        source_concept: str,
        source_unit: str | None,
        target_concept: str,
        target_unit: str | None,
    ) -> OntologyCheck:
        """Check whether a source value can feed a target input."""
        source = canonical_concept(source_concept)
        target = canonical_concept(target_concept)
        concept_ok = self.is_subtype(source_concept, target_concept)
        units_ok, conversion = self.units_compatible(source_unit, target_unit)
        if not concept_ok:
            reason = (
                f"Concept mismatch: {source} is not a {target} "
                f"and cannot feed this input."
            )
            return OntologyCheck(False, False, units_ok, reason)
        if not units_ok:
            reason = (
                f"Unit mismatch: {source_unit or 'unitless'} cannot be converted to "
                f"{target_unit or 'unitless'}."
            )
            return OntologyCheck(False, True, False, reason)
        if conversion:
            reason = (
                f"Compatible with conversion: {source} ({source_unit}) can feed "
                f"{target} ({target_unit}) after unit conversion."
            )
        else:
            reason = f"Compatible: {source} matches {target}."
        return OntologyCheck(True, True, True, reason, conversion)

    def validate_tool(self, tool: ToolSpec) -> list[str]:
        """Report the violations of a tool against the knowledge-layer ontology."""
        violations: list[str] = []
        capability = canonical_capability(tool.capability)
        if not tool.capability:
            violations.append(f"{tool.id}: capability is missing")
        elif capability not in CURATED_CAPABILITIES:
            violations.append(f"{tool.id}: capability {tool.capability} is not in the ontology")
        if not tool.inputs:
            violations.append(f"{tool.id}: no typed inputs")
        if not tool.outputs:
            violations.append(f"{tool.id}: no typed outputs")
        for direction, concepts in (("input", tool.inputs), ("output", tool.outputs)):
            names: set[str] = set()
            for concept in concepts:
                if not concept.concept:
                    violations.append(f"{tool.id}: {direction} has an untyped field")
                    continue
                name = canonical_concept(concept.concept)
                if not self.exists(name):
                    violations.append(f"{tool.id}: {direction} concept {name} is unknown")
                if concept.unit is not None:
                    if not self._known_unit(concept.unit):
                        violations.append(f"{tool.id}: {direction} unit {concept.unit} is unknown")
                    else:
                        family = self.unit_dimension(concept.unit)
                        expected = self._expected_family(name)
                        if expected and family and expected != family:
                            violations.append(
                                f"{tool.id}: {name} has unit {concept.unit} "
                                f"of dimension {family}, expected {expected}"
                            )
                marker = f"{direction}:{concept.name or name}:{concept.unit}"
                if marker in names:
                    violations.append(f"{tool.id}: duplicate {marker}")
                names.add(marker)
        return violations

    def validate_ontology(self) -> list[str]:
        """Report orphan concepts of the knowledge-layer ontology."""
        violations: list[str] = []
        known = set(self._infos) | self._class_names | self._external_names
        for name in sorted(self._infos):
            for parent in self._parents(name):
                if canonical_concept(parent) not in known:
                    violations.append(f"Orphan concept: {name} has unknown parent {parent}")
        if self.local is not None:
            for name in sorted(self.local.concepts):
                if canonical_concept(name) not in self._external_names:
                    continue
                for parent in self.local.concepts[name].get("parents", []):
                    if canonical_concept(parent) not in known:
                        violations.append(f"Orphan concept: {name} has unknown parent {parent}")
        return violations

    # -- payloads -----------------------------------------------------------

    def concept_payload(self, concept: str) -> dict[str, Any]:
        """Return the JSON payload of a concept in the knowledge-layer vocabulary."""
        name = canonical_concept(concept)
        info = self._infos.get(name)
        if info is not None:
            return {
                "concept": name,
                "parents": [canonical_concept(parent) for parent in self._parents(name)],
                "description": info.definition or info.label,
                "fields": list(info.aliases),
                "label": info.label,
                "data_type": info.data_type,
                "unit_family": info.unit_family,
            }
        local = self._local_concept(concept)
        if local is not None and self.local is not None:
            data = self.local.concepts[local]
            return {
                "concept": name,
                "parents": [canonical_concept(parent) for parent in data.get("parents", [])],
                "description": str(data.get("description", "")),
                "fields": list(data.get("fields", [])),
            }
        return {"concept": name, "parents": [], "description": "", "fields": []}

    def unit_payload(self, unit: str) -> dict[str, Any]:
        """Return the JSON payload of a unit in the knowledge-layer vocabulary."""
        name = canonical_unit(unit) or str(unit)
        definition = unit_def(name)
        if definition is not None:
            family = definition.family
            spec = UNIT_FAMILIES.get(family, {})
            return {
                "unit": name,
                "dimension": family,
                "family": family,
                "symbol": definition.symbol,
                "label": str(spec.get("label", family)),
                "convertible": bool(definition.convertible),
                "convertible_to": sorted(self._convertible_to(family, name)),
            }
        if self.local is not None:
            data = self.local.units.get(unit) or self.local.units.get(name)
            if data is not None:
                return {"unit": name, **data}
        return {"unit": name}

    def summary(self) -> dict[str, Any]:
        """Return the summary of the served ontology.

        ``concepts`` and ``units`` count the registry of the knowledge layer; the
        concepts that are only served from the local fallback are counted
        separately in ``external_concepts``.
        """
        return {
            "version": self.version,
            "concepts": len(self._infos),
            "units": len(known_units()),
            "capabilities": len(self.capabilities),
            "violations": self.validate_ontology(),
            "external_concepts": len(self._external_names),
        }

    @staticmethod
    def input_names(tool: ToolSpec) -> list[str]:
        """Return the canonical concept names of the tool inputs."""
        return [canonical_concept(item.concept) for item in tool.inputs]

    @staticmethod
    def output_names(tool: ToolSpec) -> list[str]:
        """Return the canonical concept names of the tool outputs."""
        return [canonical_concept(item.concept) for item in tool.outputs]

    @staticmethod
    def normalize_concept(spec: ConceptSpec) -> str:
        """Return the canonical ``concept:unit`` key of a concept specification."""
        return f"{canonical_concept(spec.concept)}:{canonical_unit(spec.unit) or '-'}"

    # -- internals ----------------------------------------------------------

    def _rdf_ancestors(self, name: str) -> list[str]:
        cached = self._ancestors_cache.get(name)
        if cached is not None:
            return cached
        found: list[str] = []
        seen = {name}
        queue: deque[Any] = deque([AB[name]])
        while queue:
            current = queue.popleft()
            for parent in self.store.graph.objects(current, RDFS.subClassOf):
                parent_name = _local_name(parent)
                if parent_name in seen:
                    continue
                seen.add(parent_name)
                found.append(parent_name)
                queue.append(parent)
        self._ancestors_cache[name] = found
        return found

    def _parents(self, name: str) -> list[str]:
        cached = self._parents_cache.get(name)
        if cached is None:
            cached = sorted({_local_name(parent) for parent in self.store.graph.objects(AB[name], RDFS.subClassOf)})
            self._parents_cache[name] = cached
        return cached

    def _local_concept(self, concept: str) -> str | None:
        if self.local is None:
            return None
        name = canonical_concept(concept)
        if name in self.local.concepts:
            return name
        if concept in self.local.concepts:
            return concept
        return None

    def _known_unit(self, unit: str) -> bool:
        if is_known_unit(unit):
            return True
        if self.local is None:
            return False
        return unit in self.local.units or (canonical_unit(unit) or "") in self.local.units

    def _expected_family(self, concept: str) -> str | None:
        info = self._infos.get(concept)
        if info is None:
            return None
        if info.unit_family:
            return info.unit_family
        for parent in self._rdf_ancestors(concept):
            ancestor = self._infos.get(parent)
            if ancestor is not None and ancestor.unit_family:
                return ancestor.unit_family
        return None

    @staticmethod
    def _convertible(source: str, target: str) -> bool:
        source_def = unit_def(source)
        target_def = unit_def(target)
        if source_def is None or target_def is None:
            return False
        return bool(source_def.convertible and target_def.convertible)

    @staticmethod
    def _convertible_to(family: str, unit: str) -> list[str]:
        spec = UNIT_FAMILIES.get(family, {})
        units = spec.get("units", [])
        return sorted(
            definition.local_name
            for definition in units  # type: ignore[union-attr]
            if definition.local_name != unit and definition.convertible
        )

    def _concept_view(self) -> dict[str, dict[str, Any]]:
        concepts: dict[str, dict[str, Any]] = {}
        for name, info in self._infos.items():
            concepts[name] = {
                "parents": [canonical_concept(parent) for parent in self._parents(name)],
                "description": info.definition or info.label,
                "fields": list(info.aliases),
            }
        if self.local is not None:
            for name in sorted(self.local.concepts):
                if canonical_concept(name) not in self._external_names:
                    continue
                data = self.local.concepts[name]
                concepts[canonical_concept(name)] = {
                    "parents": [canonical_concept(parent) for parent in data.get("parents", [])],
                    "description": str(data.get("description", "")),
                    "fields": list(data.get("fields", [])),
                }
        return dict(sorted(concepts.items()))

    def _unit_view(self) -> dict[str, dict[str, Any]]:
        units: dict[str, dict[str, Any]] = {}
        for family, spec in UNIT_FAMILIES.items():
            for definition in spec["units"]:  # type: ignore[union-attr]
                units[definition.local_name] = {
                    "dimension": family,
                    "family": family,
                    "symbol": definition.symbol,
                    "convertible": bool(definition.convertible),
                }
        if self.local is not None:
            for name, data in self.local.units.items():
                key = canonical_unit(name) or name
                units.setdefault(
                    key,
                    {
                        "dimension": str(data.get("dimension", "")),
                        "family": str(data.get("dimension", "")),
                        "symbol": name,
                        "convertible": bool(data.get("convertible")),
                    },
                )
        return dict(sorted(units.items()))

    def _capability_view(self) -> dict[str, dict[str, Any]]:
        capabilities: dict[str, dict[str, Any]] = {
            name: {"description": "", "inputs": [], "outputs": []} for name in CURATED_CAPABILITIES
        }
        if self.local is not None:
            for name, data in self.local.capabilities.items():
                capabilities[canonical_capability(name)] = {
                    "description": str(data.get("description", "")),
                    "inputs": [canonical_concept(concept) for concept in data.get("inputs", [])],
                    "outputs": [canonical_concept(concept) for concept in data.get("outputs", [])],
                }
        return dict(sorted(capabilities.items()))


def build_knowledge_ontology(store: KgStore, *, local_path: Path | None = None) -> KnowledgeOntology:
    """Build the ontology bridge with the local fallback ontology when it is available."""
    path = local_path or LOCAL_ONTOLOGY_PATH
    local = Ontology.load(path) if path.exists() else None
    return KnowledgeOntology(store, local=local)
