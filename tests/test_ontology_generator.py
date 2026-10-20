"""Tests for the LLM-assisted domain ontology generation pipeline."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from agent_bazaar.llm.client import LLMError
from agent_bazaar.ontology import generator
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.generator import (
    ConceptProposal,
    ProposalBatch,
    domain_layer_to_graph,
    drop_seed_duplicates,
    generate_domain_layer,
    proposals_to_concepts,
    resolve_parents,
    sanitize_proposals,
    uncovered_field_samples,
    validate_unit_choices,
)
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.ontology.validator import validate_graph
from agent_bazaar.protocols import Violation, ValidationResult


class FakeLLM:
    def __init__(self, responses: list[BaseModel | Exception] | None = None) -> None:
        self.provider = "fake"
        self.responses = responses or []
        self.calls = 0

    def complete_text(
        self, system: str, user: str, *, use_cache: bool = True, temperature: float | None = None
    ) -> str:
        return ""

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        *,
        use_cache: bool = True,
        temperature: float | None = None,
    ) -> Any:
        index = min(self.calls, len(self.responses) - 1)
        response = self.responses[index]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def stats(self) -> dict[str, Any]:
        return {}


def _field(field_name: str) -> dict[str, Any]:
    return {"field_name": field_name, "type": "float", "description": "", "tool_id": "t"}


def _assert_graph_conforms(concepts) -> None:
    graph = upper_with_units()
    for triple in concepts_to_graph(concepts):
        graph.add(triple)
    result = validate_graph(graph)
    assert result.conforms, result.report_text


def test_offline_seed_path_is_clean() -> None:
    layer = generate_domain_layer([], None)

    assert layer.source == "seed"
    assert layer.violations_found == 0
    assert layer.violations_fixed == 0
    assert layer.attempts == 0
    assert layer.batches == 0
    assert len(layer.concepts) >= 40
    _assert_graph_conforms(layer.concepts)
    assert validate_graph(domain_layer_to_graph(layer)).conforms


def test_seed_collisions_are_dropped_without_a_repair_round(tmp_path) -> None:
    llm = FakeLLM(
        [
            ProposalBatch(
                concepts=[
                    ConceptProposal(
                        label="Thermal reading", data_type="float", aliases=["temp"]
                    )
                ]
            ),
            ProposalBatch(concepts=[]),
        ]
    )
    log_path = tmp_path / "violations.jsonl"

    layer = generate_domain_layer(
        [_field("zwibble_flux")], llm, violation_log_path=log_path
    )

    assert llm.calls == 1
    assert layer.attempts == 0
    assert validate_graph(domain_layer_to_graph(layer)).conforms


def test_repair_loop_runs_when_validation_still_fails(tmp_path, monkeypatch) -> None:
    calls = {"count": 0}
    real_validate = generator.validate_graph

    def flaky_validate(graph, *args, **kwargs):
        calls["count"] += 1
        result = real_validate(graph, *args, **kwargs)
        if calls["count"] <= 2:
            return ValidationResult(
                conforms=False,
                violations=[Violation(message="forced violation", focus_node="urn:x")],
                report_text=result.report_text,
            )
        return result

    monkeypatch.setattr(generator, "validate_graph", flaky_validate)
    llm = FakeLLM(
        [
            ProposalBatch(
                concepts=[ConceptProposal(label="Thermal reading", data_type="float")]
            ),
            ProposalBatch(
                concepts=[ConceptProposal(label="Thermal reading", data_type="float")]
            ),
        ]
    )
    log_path = tmp_path / "violations.jsonl"

    layer = generate_domain_layer(
        [_field("zwibble_flux")], llm, violation_log_path=log_path
    )

    assert layer.attempts >= 1
    assert layer.violations_found >= 1
    assert llm.calls >= 2
    assert validate_graph(domain_layer_to_graph(layer)).conforms
    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert any(entry["phase"] == "repair" for entry in entries)


def test_sanitize_invalid_unit_family() -> None:
    proposal = ConceptProposal(
        label="Temperature",
        data_type="float",
        unit_family="Fahrenheit",
        default_unit="Fahrenheit",
    )

    problems = validate_unit_choices([proposal])
    sanitized, sanitize_problems = sanitize_proposals([proposal])
    concepts = proposals_to_concepts(sanitized)

    assert problems
    assert sanitize_problems
    assert sanitized[0].unit_family is None
    assert sanitized[0].default_unit is None
    assert concepts[0].unit_bearing is False


def test_parents_are_resolved_against_the_seed() -> None:
    proposal = ConceptProposal(
        label="Air temperature reading",
        data_type="float",
        parents=["Temperature", "Date-time instant"],
    )

    resolved, problems = resolve_parents([proposal], SEED_CONCEPTS)
    concepts = proposals_to_concepts(resolved, SEED_CONCEPTS)

    assert not problems
    assert concepts[0].parents == ["Temperature", "DateTime"]


def test_unresolvable_parents_fall_back_to_concept_root() -> None:
    proposal = ConceptProposal(
        label="Search filter",
        data_type="string",
        parents=["Nonexistent thing"],
    )

    resolved, problems = resolve_parents([proposal], SEED_CONCEPTS)
    concepts = proposals_to_concepts(resolved, SEED_CONCEPTS)

    assert concepts[0].parents == ["Concept"]
    assert problems


def test_proposals_without_parents_are_reparented_to_concept() -> None:
    proposal = ConceptProposal(label="Search filter", data_type="string", parents=[])

    resolved, _ = resolve_parents([proposal], SEED_CONCEPTS)
    concepts = proposals_to_concepts(resolved, SEED_CONCEPTS)

    assert concepts[0].parents == ["Concept"]
    _assert_graph_conforms(concepts)


def test_proposals_restating_seed_concepts_are_dropped() -> None:
    proposals = [
        ConceptProposal(label="Temperature", data_type="float"),
        ConceptProposal(label="Wind speed reading", data_type="float"),
    ]

    fresh, dropped = drop_seed_duplicates(proposals, SEED_CONCEPTS)

    assert [proposal.label for proposal in fresh] == ["Wind speed reading"]
    assert dropped == ["Temperature"]


def test_uncovered_field_heuristic_uses_seed_aliases() -> None:
    samples = [_field("temperature_2m"), _field("zwibble_flux")]

    uncovered = uncovered_field_samples(samples, SEED_CONCEPTS)

    names = [sample["field_name"] for sample in uncovered]
    assert "temperature_2m" not in names
    assert "zwibble_flux" in names


def test_merge_never_leaves_duplicate_labels_or_aliases() -> None:
    proposals = [
        ConceptProposal(
            label="Temperature",
            data_type="float",
            unit_family="TemperatureUnit",
            default_unit="Celsius",
        ),
        ConceptProposal(
            label="Air Temperature",
            data_type="float",
            aliases=["temp"],
            unit_family="TemperatureUnit",
            default_unit="Celsius",
        ),
        ConceptProposal(label="Air Temperature", data_type="float"),
    ]

    merged = merge_concepts([*SEED_CONCEPTS, *proposals_to_concepts(proposals)])
    labels = [concept.label for concept in merged]
    aliases = [alias for concept in merged for alias in concept.aliases]

    assert len(labels) == len(set(labels))
    assert len(aliases) == len(set(aliases))

    graph = upper_with_units()
    for triple in concepts_to_graph(merged):
        graph.add(triple)
    result = validate_graph(graph)
    duplicate_messages = [item.message for item in result.violations if "duplicate" in item.message.lower()]
    assert duplicate_messages == []


def test_llm_error_on_every_batch_falls_back_to_seed() -> None:
    llm = FakeLLM([LLMError("provider unavailable")])

    layer = generate_domain_layer(
        [_field("zwibble_flux"), _field("quux_measure")], llm, batch_size=1
    )

    assert layer.source == "seed"
    assert layer.failed_batches >= 2
    assert layer.batches == layer.failed_batches
    _assert_graph_conforms(layer.concepts)
