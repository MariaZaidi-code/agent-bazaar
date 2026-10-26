"""LLM-assisted domain ontology generation with deterministic repair.

The pipeline starts from the curated seed layer, proposes concepts for fields the
seed does not cover, sanitises unit choices, merges duplicates, validates the
result against SHACL, and returns violations to the LLM for repair. Every LLM
call is cached by the client, so a generated layer can be reproduced exactly.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from rdflib import Graph

from agent_bazaar.config import Settings, get_settings
from agent_bazaar.llm.client import LLMError
from agent_bazaar.ontology.domain import (
    SEED_CONCEPTS,
    DomainConcept,
    concepts_to_graph,
    merge_concepts,
)
from agent_bazaar.ontology.ns import AB
from agent_bazaar.ontology.units import UNIT_FAMILIES, unit_def, units_in_family
from agent_bazaar.ontology.upper import UPPER_CLASSES, upper_with_units
from agent_bazaar.ontology.validator import log_violations, validate_graph
from agent_bazaar.protocols import LLMClient, ValidationResult, Violation

logger = logging.getLogger(__name__)

DATA_TYPES = ("float", "integer", "string", "boolean", "date", "datetime", "object", "array")
UPPER_PROPERTIES = (
    "hasCapability",
    "hasInput",
    "hasOutput",
    "makesClaim",
    "supportedBy",
    "providedBy",
    "hasTrust",
    "mapsTo",
    "fieldPath",
    "direction",
    "confidence",
    "unit",
    "unitOfFamily",
    "hasDataType",
    "unitBearing",
    "unitFamily",
    "defaultUnit",
    "label",
    "altLabel",
)
STOPWORDS = frozenset({"the", "of", "a", "an", "for", "is", "id"})


class ConceptProposal(BaseModel):
    label: str
    data_type: Literal["float", "integer", "string", "boolean", "date", "datetime", "object", "array"]
    parents: list[str] = Field(default_factory=lambda: ["Concept"])
    unit_family: str | None = None
    default_unit: str | None = None
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""


class ProposalBatch(BaseModel):
    model_config = ConfigDict(extra="allow")

    concepts: list[ConceptProposal] = Field(default_factory=list)


class DomainLayer(BaseModel):
    concepts: list[DomainConcept]
    source: Literal["seed", "llm", "mixed"]
    violations_found: int
    violations_fixed: int
    attempts: int
    uncovered_fields: list[str]
    batches: int
    failed_batches: int = 0


class OntologyGenerationError(Exception):
    def __init__(self, violations: list[Violation]):
        self.violations = list(violations)
        super().__init__(
            f"ontology generation failed SHACL validation with {len(self.violations)} violation(s)"
        )


def validate_unit_choices(proposals: list[ConceptProposal]) -> list[str]:
    problems: list[str] = []
    for proposal in proposals:
        family = proposal.unit_family
        if family is not None and family not in UNIT_FAMILIES:
            problems.append(
                f"{proposal.label!r}: unknown unit family {family!r}; "
                f"expected one of {sorted(UNIT_FAMILIES)}"
            )
            continue
        if proposal.default_unit is None:
            continue
        unit_name = proposal.default_unit.rsplit("#", 1)[-1]
        definition = unit_def(unit_name)
        if definition is None:
            problems.append(f"{proposal.label!r}: unknown default unit {unit_name!r}")
        elif family is None:
            problems.append(
                f"{proposal.label!r}: default unit {unit_name!r} has no unit family"
            )
        elif definition.family != family:
            problems.append(
                f"{proposal.label!r}: default unit {unit_name!r} belongs to "
                f"{definition.family!r}, not {family!r}"
            )
    return problems


def sanitize_proposals(
    proposals: list[ConceptProposal],
) -> tuple[list[ConceptProposal], list[str]]:
    problems = validate_unit_choices(proposals)
    sanitized: list[ConceptProposal] = []
    for proposal in proposals:
        changes: dict[str, Any] = {}
        family = proposal.unit_family
        if family is not None and family not in UNIT_FAMILIES:
            changes["unit_family"] = None
            if proposal.default_unit is not None:
                changes["default_unit"] = None
        elif proposal.default_unit is not None:
            unit_name = proposal.default_unit.rsplit("#", 1)[-1]
            definition = unit_def(unit_name)
            if definition is None or family is None or definition.family != family:
                changes["default_unit"] = None
            else:
                changes["default_unit"] = unit_name
        sanitized.append(proposal.model_copy(update=changes) if changes else proposal)
    return sanitized, problems


def _pascal_case(label: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", label)
    name = "".join(word[:1].upper() + word[1:] for word in words)
    return name or "Concept"


def parent_index(concepts: Sequence[DomainConcept]) -> dict[str, str]:
    """Index known concepts by local name, label and alias for parent resolution."""
    index: dict[str, str] = {"concept": "Concept"}
    for concept in concepts:
        index.setdefault(concept.local_name.lower(), concept.local_name)
        index.setdefault(concept.label.lower(), concept.local_name)
        for alias in concept.aliases:
            index.setdefault(alias.lower(), concept.local_name)
    return index


def resolve_parents(
    proposals: list[ConceptProposal], known: Sequence[DomainConcept] = ()
) -> tuple[list[ConceptProposal], list[str]]:
    """Map proposed parents onto canonical local names.

    LLM answers use labels ("Date-time instant") or names that do not exist in
    the ontology at all. Unresolvable parents are dropped and the concept falls
    back to the generic ``Concept`` parent, which keeps the layer free of orphan
    classes without spending a repair round.
    """
    index = parent_index(known)
    batch: dict[str, str] = {}
    for proposal in proposals:
        label = proposal.label.strip().lower()
        if label:
            batch.setdefault(label, _pascal_case(proposal.label))
    resolved: list[ConceptProposal] = []
    problems: list[str] = []
    for proposal in proposals:
        parents: list[str] = []
        dropped: list[str] = []
        for raw in proposal.parents:
            candidate = str(raw).strip()
            if not candidate:
                continue
            local = candidate.rsplit("#", 1)[-1]
            match = (
                index.get(local.lower())
                or index.get(candidate.lower())
                or batch.get(local.lower())
                or batch.get(candidate.lower())
            )
            if match and match not in parents:
                parents.append(match)
            elif match is None:
                dropped.append(candidate)
        if not parents:
            parents = ["Concept"]
            if dropped:
                problems.append(
                    f"{proposal.label!r}: unresolvable parent(s) {sorted(dropped)}; "
                    "re-parented to 'Concept'"
                )
        resolved.append(proposal.model_copy(update={"parents": parents}))
    return resolved, problems


def drop_seed_duplicates(
    proposals: list[ConceptProposal], known: Sequence[DomainConcept]
) -> tuple[list[ConceptProposal], list[str]]:
    """Remove proposals that restate an existing concept (label, alias or name)."""
    index = parent_index(known)
    kept: list[ConceptProposal] = []
    dropped: list[str] = []
    for proposal in proposals:
        label = proposal.label.strip().lower()
        local = _pascal_case(proposal.label).lower()
        aliases = {alias.strip().lower() for alias in proposal.aliases if alias.strip()}
        if label in index or local in index or aliases & set(index):
            dropped.append(proposal.label)
            continue
        kept.append(proposal)
    return kept, dropped


def proposals_to_concepts(
    proposals: list[ConceptProposal], known: Sequence[DomainConcept] = ()
) -> list[DomainConcept]:
    concepts: list[DomainConcept] = []
    used: set[str] = set()
    resolved, _ = resolve_parents(proposals, known)
    for proposal in resolved:
        base = _pascal_case(proposal.label)
        local_name = base
        counter = 2
        while local_name.lower() in used:
            local_name = f"{base}{counter}"
            counter += 1
        used.add(local_name.lower())
        concepts.append(
            DomainConcept(
                local_name=local_name,
                label=proposal.label,
                data_type=proposal.data_type,
                parents=list(proposal.parents),
                unit_family=proposal.unit_family,
                default_unit=proposal.default_unit,
                aliases=list(proposal.aliases),
                definition=proposal.definition,
                unit_bearing=proposal.unit_family is not None,
            )
        )
    return concepts


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", text.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _concept_tokens(concepts: list[DomainConcept]) -> set[str]:
    vocabulary: set[str] = set()
    for concept in concepts:
        vocabulary |= _tokens(concept.label)
        for alias in concept.aliases:
            vocabulary |= _tokens(alias)
    return vocabulary


def uncovered_field_samples(
    field_samples: list[dict[str, Any]], concepts: list[DomainConcept]
) -> list[dict[str, Any]]:
    vocabulary = _concept_tokens(concepts)
    uncovered: list[dict[str, Any]] = []
    for field in field_samples:
        field_tokens = _tokens(str(field.get("field_name", "")))
        if not (field_tokens & vocabulary):
            uncovered.append(field)
    return uncovered


def _prepared_seed() -> list[DomainConcept]:
    protected = {
        key
        for concept in SEED_CONCEPTS
        for key in (concept.local_name.lower(), concept.label.lower())
    }
    claimed_aliases: set[str] = set()
    prepared: list[DomainConcept] = []
    for concept in SEED_CONCEPTS:
        own = {concept.local_name.lower(), concept.label.lower()}
        aliases: list[str] = []
        for alias in concept.aliases:
            key = alias.lower()
            if key in protected and key not in own:
                continue
            if key in claimed_aliases:
                continue
            aliases.append(alias)
            claimed_aliases.add(key)
        prepared.append(concept.model_copy(update={"aliases": aliases}))
    return prepared


def _duplicate_label_violations(
    existing: list[DomainConcept], proposed: list[DomainConcept]
) -> list[Violation]:
    claimed: dict[str, str] = {}
    for concept in existing:
        claimed[concept.label.lower()] = concept.local_name
        claimed[concept.local_name.lower()] = concept.local_name
    violations: list[Violation] = []
    for concept in proposed:
        keys = (concept.label.lower(), concept.local_name.lower())
        owner = next((claimed[key] for key in keys if key in claimed), None)
        if owner is not None:
            violations.append(
                Violation(
                    message=(
                        "No duplicate concepts: label "
                        f"{concept.label!r} collides with existing concept {owner!r}."
                    ),
                    focus_node=concept.iri(),
                    value=concept.label,
                )
            )
        for key in keys:
            claimed.setdefault(key, concept.local_name)
    return violations


def _validate_proposed(
    seed: list[DomainConcept],
    proposed: list[DomainConcept],
    *,
    detect_duplicates: bool = False,
) -> tuple[list[DomainConcept], ValidationResult]:
    merged = merge_concepts([*seed, *proposed])
    graph = upper_with_units()
    for triple in concepts_to_graph(merged):
        graph.add(triple)
    result = validate_graph(graph)
    duplicates = _duplicate_label_violations(seed, proposed) if detect_duplicates else []
    violations = [*result.violations, *duplicates]
    return merged, ValidationResult(
        conforms=result.conforms and not duplicates,
        violations=violations,
        report_text=result.report_text,
    )


def _unit_family_lines() -> list[str]:
    lines: list[str] = []
    for family, spec in UNIT_FAMILIES.items():
        units = ", ".join(unit.local_name for unit in units_in_family(family))
        lines.append(f"- {family} ({spec['label']}): {units}")
    return lines


def _system_prompt() -> str:
    return (
        "You are an ontology engineer building the domain layer of the Agent Bazaar "
        "knowledge graph from API field descriptions.\n"
        f"Upper ontology classes: {', '.join(UPPER_CLASSES)}.\n"
        f"Upper ontology properties: {', '.join(UPPER_PROPERTIES)}.\n"
        f"Valid data types: {', '.join(DATA_TYPES)}.\n"
        "Valid unit families and their units:\n"
        + "\n".join(_unit_family_lines())
        + "\nPropose concepts that cover the supplied fields. Reuse the labels of existing "
        "concepts whenever they fit instead of inventing synonyms. For specialisations, "
        "put the parent concept label in parents. Set unit_family only to one of the "
        "listed family names and default_unit only to a unit from that family. Give each "
        "concept a short definition. Return one JSON object matching the ProposalBatch "
        "schema."
    )


def _proposal_user_prompt(fields: list[dict[str, Any]], existing: list[DomainConcept]) -> str:
    payload = {
        "fields": fields,
        "existing_concepts": [
            {"label": concept.label, "aliases": list(concept.aliases)} for concept in existing
        ],
    }
    return (
        "Propose domain concepts for these API fields, reusing existing concepts where "
        "they fit.\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    )


def _batch_from_concepts(concepts: list[DomainConcept]) -> ProposalBatch:
    return ProposalBatch(
        concepts=[
            ConceptProposal(
                label=concept.label,
                data_type=concept.data_type,
                parents=list(concept.parents),
                unit_family=concept.unit_family,
                default_unit=concept.default_unit,
                aliases=list(concept.aliases),
                definition=concept.definition,
            )
            for concept in concepts
        ]
    )


def _repair_user_prompt(violations: list[Violation], current: list[DomainConcept]) -> str:
    unique = list(
        dict.fromkeys((item.message, item.focus_node, item.value) for item in violations)
    )[:30]
    payload = {
        "violations": [
            {"message": message, "focus_node": focus_node, "value": value}
            for message, focus_node, value in unique
        ],
        "current_concepts": _batch_from_concepts(current).model_dump(mode="json")["concepts"],
    }
    return (
        "Repair the ontology so that it satisfies the SHACL shapes. Return the corrected "
        "complete ProposalBatch as one JSON object, keeping concepts that are already "
        "correct.\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    )


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    size = max(1, size)
    return [items[index : index + size] for index in range(0, len(items), size)]


def _log_round(
    log_path: str | Path, round_number: int, violations: list[Violation], phase: str
) -> None:
    for violation in violations:
        log_violations(
            log_path,
            {
                "round": round_number,
                "message": violation.message,
                "focus_node": violation.focus_node,
                "value": violation.value,
                "phase": phase,
            },
        )


def _uncovered_names(
    field_samples: list[dict[str, Any]], concepts: list[DomainConcept]
) -> list[str]:
    return [
        str(field.get("field_name", ""))
        for field in uncovered_field_samples(field_samples, concepts)
    ]


def _is_offline(client: LLMClient) -> bool:
    return str(getattr(client, "provider", "")).lower() == "offline"


def _seed_layer(
    field_samples: list[dict[str, Any]],
    seed: list[DomainConcept],
    *,
    batches: int = 0,
    failed_batches: int = 0,
) -> DomainLayer:
    _, validation = _validate_proposed(seed, [])
    if not validation.conforms:
        raise OntologyGenerationError(validation.violations)
    return DomainLayer(
        concepts=sorted(seed, key=lambda concept: concept.local_name),
        source="seed",
        violations_found=len(validation.violations),
        violations_fixed=0,
        attempts=0,
        uncovered_fields=_uncovered_names(field_samples, seed),
        batches=batches,
        failed_batches=failed_batches,
    )


def generate_domain_layer(
    field_samples: list[dict[str, Any]],
    client: LLMClient | None,
    *,
    settings: Settings | None = None,
    batch_size: int = 40,
    max_repair_rounds: int = 2,
    use_llm: bool = True,
    violation_log_path: str | Path | None = None,
) -> DomainLayer:
    resolved_settings = settings or get_settings()
    log_path = (
        Path(violation_log_path)
        if violation_log_path is not None
        else resolved_settings.paths.out_dir / "logs" / "ontology_violations.jsonl"
    )
    seed = _prepared_seed()
    uncovered = uncovered_field_samples(field_samples, seed)
    if client is None or not use_llm or _is_offline(client) or not uncovered:
        return _seed_layer(field_samples, seed)

    batches = 0
    failed_batches = 0
    accepted: list[ConceptProposal] = []
    system = _system_prompt()
    for batch in _chunks(uncovered, batch_size):
        batches += 1
        try:
            result = client.complete_json(
                system, _proposal_user_prompt(batch, seed), ProposalBatch, use_cache=True
            )
        except LLMError as error:
            failed_batches += 1
            logger.warning("ontology proposal batch failed: %s", error)
            continue
        sanitized, problems = sanitize_proposals(list(result.concepts))
        if problems:
            logger.warning("dropped invalid unit choices: %s", "; ".join(problems))
        fresh, duplicates = drop_seed_duplicates(sanitized, seed)
        if duplicates:
            logger.info("dropped proposals that restate seed concepts: %s", "; ".join(duplicates))
        accepted.extend(fresh)

    if not accepted:
        return _seed_layer(
            field_samples, seed, batches=batches, failed_batches=failed_batches
        )

    resolved, parent_problems = resolve_parents(accepted, seed)
    if parent_problems:
        logger.warning("resolved proposal parents locally: %s", "; ".join(parent_problems))
    proposed = proposals_to_concepts(resolved, seed)
    _, validation = _validate_proposed(seed, proposed, detect_duplicates=True)
    _log_round(log_path, 0, validation.violations, "validate")
    violations_found = len(validation.violations)
    attempts = 0

    while not validation.conforms and attempts < max_repair_rounds:
        attempts += 1
        current = merge_concepts([*seed, *proposed])
        repair_system = _system_prompt() + (
            "\nYou are repairing a previously proposed batch after SHACL validation. "
            "Fix every violation and return the complete corrected batch."
        )
        try:
            repaired = client.complete_json(
                repair_system,
                _repair_user_prompt(validation.violations, current),
                ProposalBatch,
                use_cache=True,
            )
        except LLMError as error:
            batches += 1
            failed_batches += 1
            logger.warning("ontology repair batch failed: %s", error)
            break
        batches += 1
        sanitized, problems = sanitize_proposals(list(repaired.concepts))
        if problems:
            logger.warning("dropped invalid unit choices: %s", "; ".join(problems))
        repaired_resolved, repaired_parent_problems = resolve_parents(sanitized, seed)
        if repaired_parent_problems:
            logger.warning(
                "resolved repair parents locally: %s", "; ".join(repaired_parent_problems)
            )
        proposed = proposals_to_concepts(repaired_resolved, seed)
        _, validation = _validate_proposed(seed, proposed)
        _log_round(log_path, attempts, validation.violations, "repair")

    if not validation.conforms:
        raise OntologyGenerationError(validation.violations)

    merged = merge_concepts([*seed, *proposed])
    return DomainLayer(
        concepts=sorted(merged, key=lambda concept: concept.local_name),
        source="mixed",
        violations_found=violations_found,
        violations_fixed=max(0, violations_found - len(validation.violations)),
        attempts=attempts,
        uncovered_fields=_uncovered_names(field_samples, merged),
        batches=batches,
        failed_batches=failed_batches,
    )


def domain_layer_to_graph(layer: DomainLayer, include_upper: bool = True) -> Graph:
    if include_upper:
        graph = upper_with_units()
    else:
        graph = Graph()
        graph.bind("ab", AB)
    for triple in concepts_to_graph(layer.concepts):
        graph.add(triple)
    return graph


def save_domain_layer(layer: DomainLayer, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    graph = concepts_to_graph(layer.concepts)
    graph.serialize(destination=destination, format="turtle")
    return destination
