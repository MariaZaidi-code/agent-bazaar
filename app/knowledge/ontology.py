from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas import ConceptSpec, ToolSpec


@dataclass
class OntologyCheck:
    valid: bool
    concept_ok: bool
    units_ok: bool
    reason: str
    conversion_required: bool = False


class Ontology:
    def __init__(
        self,
        concepts: dict[str, dict[str, Any]],
        units: dict[str, dict[str, Any]],
        capabilities: dict[str, dict[str, Any]],
        version: str = "local",
    ) -> None:
        self.concepts = concepts
        self.units = units
        self.capabilities = capabilities
        self.version = version

    @classmethod
    def load(cls, path: Path) -> Ontology:
        if not path.exists():
            raise FileNotFoundError(f"Ontology file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            concepts=data.get("concepts", {}),
            units=data.get("units", {}),
            capabilities=data.get("capabilities", {}),
            version=str(data.get("version", "local")),
        )

    def exists(self, concept: str) -> bool:
        return concept in self.concepts

    def ancestors(self, concept: str) -> list[str]:
        found: list[str] = []
        current = concept
        seen: set[str] = set()
        while current in self.concepts and current not in seen:
            seen.add(current)
            for parent in self.concepts[current].get("parents", []):
                if parent not in found:
                    found.append(parent)
                current = parent
                break
            else:
                break
        return found

    def is_subtype(self, child: str, parent: str) -> bool:
        return child == parent or parent in self.ancestors(child)

    def check_capability(self, tool_capability: str, required: str) -> bool:
        return tool_capability == required

    def unit_dimension(self, unit: str | None) -> str | None:
        if unit is None:
            return None
        return self.units.get(unit, {}).get("dimension")

    def units_compatible(self, source: str | None, target: str | None) -> tuple[bool, bool]:
        if source is None or target is None:
            return True, False
        if source == target:
            return True, False
        source_dim = self.unit_dimension(source)
        target_dim = self.unit_dimension(target)
        if source_dim is None or target_dim is None or source_dim != target_dim:
            return False, False
        convertible = target in self.units.get(source, {}).get("convertible", [])
        return convertible, convertible

    def check_link(
        self,
        source_concept: str,
        source_unit: str | None,
        target_concept: str,
        target_unit: str | None,
    ) -> OntologyCheck:
        concept_ok = self.is_subtype(source_concept, target_concept)
        units_ok, conversion = self.units_compatible(source_unit, target_unit)
        if not concept_ok:
            reason = (
                f"Concept mismatch: {source_concept} is not a {target_concept} "
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
                f"Compatible with conversion: {source_concept} ({source_unit}) can feed "
                f"{target_concept} ({target_unit}) after unit conversion."
            )
        else:
            reason = f"Compatible: {source_concept} matches {target_concept}."
        return OntologyCheck(True, True, True, reason, conversion)

    def validate_tool(self, tool: ToolSpec) -> list[str]:
        violations: list[str] = []
        if not tool.capability:
            violations.append(f"{tool.id}: capability is missing")
        elif tool.capability not in self.capabilities:
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
                if concept.concept not in self.concepts:
                    violations.append(
                        f"{tool.id}: {direction} concept {concept.concept} is unknown"
                    )
                if concept.unit is not None:
                    if concept.unit not in self.units:
                        violations.append(
                            f"{tool.id}: {direction} unit {concept.unit} is unknown"
                        )
                    else:
                        dimension = self.unit_dimension(concept.unit)
                        expected = self._expected_dimension(concept.concept)
                        if expected and dimension and expected != dimension:
                            violations.append(
                                f"{tool.id}: {concept.concept} has unit {concept.unit} "
                                f"of dimension {dimension}, expected {expected}"
                            )
                marker = f"{direction}:{concept.name or concept.concept}:{concept.unit}"
                if marker in names:
                    violations.append(f"{tool.id}: duplicate {marker}")
                names.add(marker)
        return violations

    def _expected_dimension(self, concept: str) -> str | None:
        if self.is_subtype(concept, "Temperature"):
            return "temperature"
        if self.is_subtype(concept, "Money"):
            return "currency"
        if self.is_subtype(concept, "Coordinates"):
            return "angle"
        return None

    def validate_ontology(self) -> list[str]:
        violations: list[str] = []
        roots = [name for name, data in self.concepts.items() if not data.get("parents")]
        if "Entity" not in roots:
            violations.append("Entity must be a root concept")
        for name, data in self.concepts.items():
            for parent in data.get("parents", []):
                if parent not in self.concepts:
                    violations.append(f"Orphan concept: {name} has unknown parent {parent}")
        for capability, data in self.capabilities.items():
            for concept in data.get("inputs", []) + data.get("outputs", []):
                if concept not in self.concepts:
                    violations.append(
                        f"Capability {capability} references unknown concept {concept}"
                    )
        return violations

    def concept_payload(self, concept: str) -> dict[str, Any]:
        data = self.concepts.get(concept, {})
        return {
            "concept": concept,
            "parents": data.get("parents", []),
            "description": data.get("description", ""),
            "fields": data.get("fields", []),
        }

    def unit_payload(self, unit: str) -> dict[str, Any]:
        return {"unit": unit, **self.units.get(unit, {})}

    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "concepts": len(self.concepts),
            "units": len(self.units),
            "capabilities": len(self.capabilities),
            "violations": self.validate_ontology(),
        }

    @staticmethod
    def input_names(tool: ToolSpec) -> list[str]:
        return [item.concept for item in tool.inputs]

    @staticmethod
    def output_names(tool: ToolSpec) -> list[str]:
        return [item.concept for item in tool.outputs]

    @staticmethod
    def normalize_concept(spec: ConceptSpec) -> str:
        return f"{spec.concept}:{spec.unit or '-'}"
