"""Tests for the free-first ranking evaluation suite.

The suite itself lives in :mod:`app.evaluation.run_ranking`; these tests
check the metric arithmetic against hand computed values, the shape of the
hand-checked dataset and the behaviour of the policy ablations.
"""

from __future__ import annotations

import json
from math import log2
from pathlib import Path
from typing import Any

import pytest

from app.agents.ranking_policy import RankingPolicy
from app.evaluation.run_ranking import (
    DEFAULT_DATASET,
    METRIC_KEYS,
    evaluate,
    evaluate_task,
    executable_top_rate,
    free_first_rate,
    load_tasks,
    main,
    ndcg_at_10,
    tier_separation_accuracy,
)

CURATED_CAPABILITIES = (
    "GeocodeLocation",
    "GetWeatherForecast",
    "ConvertCurrency",
    "GetCountryFacts",
    "GetPublicHolidays",
    "SearchResearchPapers",
    "QueryStructuredData",
    "AnswerFromDocument",
)


def candidate(tool_id: str, **overrides: Any) -> dict[str, Any]:
    """A candidate record with neutral values for everything not overridden."""
    entry: dict[str, Any] = {
        "tool_id": tool_id,
        "relevance": 0.9,
        "trust": 0.8,
        "pricing_tier": "free",
        "access_requirement": "keyless",
        "rating_value": 0.8,
        "rating_count": 5,
        "doc_quality": 0.8,
        "mapping_coverage": 1.0,
        "chain_fit": 0.8,
        "claim_label": "supported",
        "demoted": False,
        "breaker_open": False,
        "licence": "MIT",
    }
    entry.update(overrides)
    return entry


def task(
    candidates: list[dict[str, Any]],
    expected_order: list[str],
    capability: str = "GetWeatherForecast",
) -> dict[str, Any]:
    """A ranking task in the shape the dataset uses."""
    return {
        "task": "synthetic ranking task",
        "capability": capability,
        "candidates": candidates,
        "expected_order": expected_order,
        "notes": "synthetic task used by the metric tests",
    }


def test_ndcg_at_10_matches_a_hand_computed_value() -> None:
    ranked = ["x", "y", "z"]
    expected = ["y", "x", "z"]

    dcg = 2 / log2(2) + 3 / log2(3) + 1 / log2(4)
    idcg = 3 / log2(2) + 2 / log2(3) + 1 / log2(4)

    assert ndcg_at_10(ranked, expected) == pytest.approx(dcg / idcg, abs=1e-4)
    assert ndcg_at_10(ranked, expected) == pytest.approx(0.9225, abs=1e-9)


def test_ndcg_at_10_is_one_for_the_expected_order_and_zero_without_overlap() -> None:
    assert ndcg_at_10(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert ndcg_at_10(["a", "b"], ["c", "d"]) == 0.0
    assert ndcg_at_10([], ["a"]) == 0.0
    assert ndcg_at_10(["a", "b"], []) == 0.0


def test_free_first_rate_counts_only_tasks_that_had_a_free_candidate() -> None:
    ignored = RankingPolicy(pricing_policy="ignore")
    paid_on_top = task(
        [
            candidate("paid-tool", pricing_tier="paid", access_requirement="paid_key", relevance=1.0),
            candidate("free-tool", relevance=0.5),
        ],
        ["paid-tool", "free-tool"],
    )
    free_on_top = task(
        [
            candidate("free-tool", relevance=1.0),
            candidate("paid-tool", pricing_tier="paid", access_requirement="paid_key", relevance=0.5),
        ],
        ["free-tool", "paid-tool"],
    )
    no_free_candidate = task(
        [candidate("paid-tool", pricing_tier="paid", access_requirement="paid_key")],
        ["paid-tool"],
    )
    outcomes = [
        evaluate_task(paid_on_top, ignored),
        evaluate_task(free_on_top, ignored),
        evaluate_task(no_free_candidate, ignored),
    ]

    assert outcomes[0].has_free_candidate is True
    assert outcomes[0].free_first is False
    assert outcomes[1].free_first is True
    assert outcomes[2].has_free_candidate is False

    assert free_first_rate(outcomes) == 0.5


def test_tier_separation_accuracy_flags_a_lower_tier_above_a_higher_tier() -> None:
    ignored = RankingPolicy(pricing_policy="ignore")
    inverted = task(
        [
            candidate("paid-tool", pricing_tier="paid", access_requirement="paid_key", relevance=1.0),
            candidate("free-tool", relevance=0.5),
        ],
        ["paid-tool", "free-tool"],
    )
    ordered = task(
        [
            candidate("free-tool", relevance=1.0),
            candidate("paid-tool", pricing_tier="paid", access_requirement="paid_key", relevance=0.5),
        ],
        ["free-tool", "paid-tool"],
    )
    outcomes = [evaluate_task(inverted, ignored), evaluate_task(ordered, ignored)]

    assert outcomes[0].tier_separation is False
    assert outcomes[1].tier_separation is True
    assert tier_separation_accuracy(outcomes) == 0.5


def test_executable_top_rate_requires_a_free_keyless_candidate() -> None:
    keyed = task(
        [
            candidate("keyed-tool", access_requirement="api_key", relevance=1.0),
            candidate("free-tool", relevance=0.5),
        ],
        ["keyed-tool", "free-tool"],
    )
    free = task([candidate("free-tool", relevance=1.0)], ["free-tool"])
    outcomes = [evaluate_task(keyed, RankingPolicy()), evaluate_task(free, RankingPolicy())]

    assert outcomes[0].executable_top is False
    assert outcomes[1].executable_top is True
    assert executable_top_rate(outcomes) == 0.5


def test_ranking_dataset_is_valid_and_covers_the_curated_capabilities() -> None:
    tasks = load_tasks(DEFAULT_DATASET)

    assert len(tasks) >= 40
    assert {item["capability"] for item in tasks} == set(CURATED_CAPABILITIES)

    for item in tasks:
        assert item["task"].strip()
        assert item["notes"].strip()
        assert item["candidates"]
        assert item["expected_order"]
        tool_ids = [entry["tool_id"] for entry in item["candidates"]]
        assert len(set(tool_ids)) == len(tool_ids)
        assert sorted(item["expected_order"]) == sorted(tool_ids)


def test_every_expected_order_is_the_order_the_default_policy_produces() -> None:
    tasks = load_tasks(DEFAULT_DATASET)

    for item in tasks:
        outcome = evaluate_task(item, RankingPolicy())
        assert outcome.ranked_order == item["expected_order"], item["task"]


def test_the_full_policy_keeps_free_candidates_first_more_often_than_the_no_tier_ablation() -> None:
    payload = evaluate(DEFAULT_DATASET)

    full = payload["ablations"]["full"]["metrics"]
    no_tier = payload["ablations"]["no_tier"]["metrics"]

    assert full["free_first_rate"] > no_tier["free_first_rate"]
    assert full["tier_separation_accuracy"] > no_tier["tier_separation_accuracy"]
    assert full["mrr"] > no_tier["mrr"]


def test_run_ranking_writes_a_report_with_the_expected_keys(tmp_path: Path) -> None:
    out = tmp_path / "ranking.json"

    payload = main(["--dataset", str(DEFAULT_DATASET), "--out", str(out)])

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["suite"] == "ranking"
    assert written["mode"] == "offline"
    assert written["tasks"] == len(load_tasks(DEFAULT_DATASET))
    assert set(METRIC_KEYS) <= set(written["metrics"])
    assert {"ablations", "rows", "per_capability", "failures", "metric_table"} <= set(written)
    assert written["rows"]
    assert written["failures"] == []
    assert {row["configuration"] for row in written["metric_table"]} == {
        "full",
        "no_tier",
        "no_quality",
        "no_rating",
    }
    assert payload["metrics"] == written["metrics"]


def test_the_suite_is_deterministic(tmp_path: Path) -> None:
    first = main(["--out", str(tmp_path / "first.json")])
    second = main(["--out", str(tmp_path / "second.json")])

    assert first["metrics"] == second["metrics"]
    assert first["metric_table"] == second["metric_table"]
    assert first["rows"] == second["rows"]
