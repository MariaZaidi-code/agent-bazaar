from __future__ import annotations

from app.evaluation.harness import load_dataset
from app.services import AppServices


def test_matching_dataset_is_complete_and_typed(services: AppServices) -> None:
    tasks = load_dataset("matching_tasks.json")
    assert len(tasks) == 50
    assert len({item["id"] for item in tasks}) == 50
    for item in tasks:
        assert item["expected"]
        for capability, tool_id in item["expected"].items():
            assert capability in services.ontology.capabilities
            assert services.graph.get(tool_id) is not None


def test_chain_dataset_is_complete(services: AppServices) -> None:
    tasks = load_dataset("chain_tasks.json")
    assert len(tasks) == 15
    for item in tasks:
        for capability, tool_id in item["expected"].items():
            assert services.graph.get(tool_id) is not None
            assert services.graph.get(tool_id).capability == capability


def test_substitution_and_trust_scenarios_are_well_formed(services: AppServices) -> None:
    cases = load_dataset("substitution_cases.json")
    assert len(cases) == 7
    for case in cases:
        assert services.graph.get(case["fail_tool"]) is not None
        if case["expected_substitute"]:
            assert services.graph.get(case["expected_substitute"]) is not None

    scenarios = load_dataset("trust_scenarios.json")
    assert len(scenarios) == 6
    for scenario in scenarios:
        assert scenario["operations"]
        assert "expected_demoted" in scenario
