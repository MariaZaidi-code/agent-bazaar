"""Offline evaluation suite for the free-first ranking policy.

The suite replays a hand-checked dataset of ranking tasks through
:func:`app.agents.ranking_policy.rank_candidates` and reports how well the
policy puts the expected tool first, keeps the commercial tier honest and
keeps the ranked list executable.

Metrics
-------

``mrr``
    Mean reciprocal rank of the expected best tool (the first entry of the
    task's ``expected_order``) in the ranked list.
``ndcg_at_10``
    Normalised discounted cumulative gain at 10 with graded gains: the gain
    of a ranked candidate is ``len(expected_order) - position`` in the
    expected order, so the expected best tool carries the largest gain.
    ``DCG = sum(gain_i / log2(i + 1))`` over the first ten positions and
    ``IDCG`` is the same sum over the expected order itself. Because the
    expected order is a full permutation of the candidates, graded gains are
    what makes the metric sensitive to a wrong order; binary gains would be
    1.0 for every ranking.
``free_first_rate``
    Share of tasks that had at least one free candidate and whose top ranked
    candidate is in the free tier.
``executable_top_rate``
    Share of tasks whose top ranked candidate is executable, that is free
    and keyless under the policy in force.
``tier_separation_accuracy``
    Share of tasks whose ranked list never places a candidate from a lower
    tier above a candidate from a higher tier, using the canonical tier
    order free > freemium > paid > unknown.

Ablations
---------

``full``
    The default policy.
``no_tier``
    ``pricing_policy="ignore"``: the tier stops being a sort key.
``no_quality``
    The documentation, mapping and chain-fit weights are zero.
``no_rating``
    ``min_rating_count`` is raised so the rating factor is always neutral.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import log2
from pathlib import Path
from typing import Any

from app.agents.ranking_policy import (
    DEFAULT_TIER_ORDER,
    CandidateFacts,
    RankingPolicy,
    rank_candidates,
)
from app.evaluation.harness import DATA_DIR, utc_timestamp, write_report
from app.evaluation.metrics import mean, ratio

DEFAULT_DATASET = DATA_DIR / "ranking_tasks.jsonl"
METRIC_KEYS = (
    "mrr",
    "ndcg_at_10",
    "free_first_rate",
    "executable_top_rate",
    "tier_separation_accuracy",
)
ABLATIONS: dict[str, dict[str, Any]] = {
    "full": {},
    "no_tier": {"pricing_policy": "ignore"},
    "no_quality": {
        "doc_quality_weight": 0.0,
        "mapping_coverage_weight": 0.0,
        "chain_fit_weight": 0.0,
    },
    "no_rating": {"min_rating_count": 1_000_000},
}


@dataclass(frozen=True)
class RankedEntry:
    """One candidate as the policy ranked it."""

    tool_id: str
    score: float
    tier: str
    tier_rank: int
    eligible: bool
    executable: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class TaskOutcome:
    """The result of ranking one task with one policy variant."""

    task: str
    capability: str
    expected_order: list[str]
    ranked: list[RankedEntry]
    has_free_candidate: bool
    best_rank: int | None
    reciprocal_rank: float
    ndcg_at_10: float
    free_first: bool
    executable_top: bool
    tier_separation: bool

    @property
    def ranked_order(self) -> list[str]:
        return [entry.tool_id for entry in self.ranked]

    @property
    def top(self) -> RankedEntry | None:
        return self.ranked[0] if self.ranked else None


def reference_tier_rank(tier: str) -> int:
    """Tier position in the canonical order, independent of the policy in force."""
    return DEFAULT_TIER_ORDER.index(tier if tier in DEFAULT_TIER_ORDER else "unknown")


def load_tasks(path: Path) -> list[dict[str, Any]]:
    """Read the JSONL dataset, one task object per line."""
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def candidate_facts(entry: dict[str, Any]) -> CandidateFacts:
    """Build the policy facts for one candidate record."""
    return CandidateFacts(
        tool_id=str(entry["tool_id"]),
        relevance=float(entry["relevance"]),
        trust=float(entry["trust"]),
        pricing_tier=str(entry["pricing_tier"]),
        access_requirement=str(entry["access_requirement"]),
        rating_value=entry["rating_value"],
        rating_count=int(entry["rating_count"]),
        doc_quality=float(entry["doc_quality"]),
        mapping_coverage=float(entry["mapping_coverage"]),
        chain_fit=float(entry["chain_fit"]),
        claim_label=str(entry["claim_label"]),
        demoted=bool(entry["demoted"]),
        breaker_open=bool(entry["breaker_open"]),
        licence=str(entry.get("licence", "")),
    )


def reciprocal_rank_of(ranked_ids: Sequence[str], target: str) -> tuple[int | None, float]:
    """One-based position of the target in the ranked list and its reciprocal."""
    for position, tool_id in enumerate(ranked_ids, start=1):
        if tool_id == target:
            return position, round(1.0 / position, 4)
    return None, 0.0


def ndcg_at_10(ranked_ids: Sequence[str], expected_ids: Sequence[str], k: int = 10) -> float:
    """Normalised DCG with position graded gains over the expected order."""
    if not expected_ids:
        return 0.0
    gains = {tool_id: len(expected_ids) - position for position, tool_id in enumerate(expected_ids)}
    dcg = sum(
        gains.get(tool_id, 0) / log2(position + 1)
        for position, tool_id in enumerate(ranked_ids[:k], start=1)
    )
    ideal = sum(
        (len(expected_ids) - position + 1) / log2(position + 1)
        for position in range(1, min(k, len(expected_ids)) + 1)
    )
    return round(dcg / ideal, 4) if ideal else 0.0


def evaluate_task(task: dict[str, Any], policy: RankingPolicy) -> TaskOutcome:
    """Rank one task with one policy variant and score the outcome."""
    facts = [candidate_facts(entry) for entry in task["candidates"]]
    ranked = rank_candidates(facts, policy)
    entries = [
        RankedEntry(
            tool_id=item.tool_id,
            score=item.score,
            tier=item.tier,
            tier_rank=item.tier_rank,
            eligible=item.eligible,
            executable=item.executable,
            reasons=tuple(item.reasons),
        )
        for item in ranked
    ]
    ranked_ids = [entry.tool_id for entry in entries]
    expected_order = [str(tool_id) for tool_id in task["expected_order"]]
    best_rank, reciprocal = reciprocal_rank_of(ranked_ids, expected_order[0])
    has_free = any(entry["pricing_tier"] == "free" for entry in task["candidates"])
    top = entries[0] if entries else None
    tier_ranks = [reference_tier_rank(entry.tier) for entry in entries]
    return TaskOutcome(
        task=str(task["task"]),
        capability=str(task["capability"]),
        expected_order=expected_order,
        ranked=entries,
        has_free_candidate=has_free,
        best_rank=best_rank,
        reciprocal_rank=reciprocal,
        ndcg_at_10=ndcg_at_10(ranked_ids, expected_order),
        free_first=bool(has_free and top is not None and top.tier == "free"),
        executable_top=bool(top is not None and top.executable),
        tier_separation=all(
            earlier <= later
            for earlier, later in zip(tier_ranks, tier_ranks[1:], strict=False)
        ),
    )


def free_first_rate(outcomes: Sequence[TaskOutcome]) -> float:
    """Share of tasks with a free candidate whose top candidate is free."""
    eligible = [outcome for outcome in outcomes if outcome.has_free_candidate]
    return ratio(sum(1 for outcome in eligible if outcome.free_first), len(eligible))


def executable_top_rate(outcomes: Sequence[TaskOutcome]) -> float:
    """Share of tasks whose top candidate may be executed."""
    return ratio(sum(1 for outcome in outcomes if outcome.executable_top), len(outcomes))


def tier_separation_accuracy(outcomes: Sequence[TaskOutcome]) -> float:
    """Share of tasks whose ranked list never inverts the tier order."""
    return ratio(sum(1 for outcome in outcomes if outcome.tier_separation), len(outcomes))


def summarise(outcomes: Sequence[TaskOutcome]) -> dict[str, float]:
    """The metric table for one policy variant."""
    return {
        "mrr": mean(outcome.reciprocal_rank for outcome in outcomes),
        "ndcg_at_10": mean(outcome.ndcg_at_10 for outcome in outcomes),
        "free_first_rate": free_first_rate(outcomes),
        "executable_top_rate": executable_top_rate(outcomes),
        "tier_separation_accuracy": tier_separation_accuracy(outcomes),
    }


def outcome_row(outcome: TaskOutcome, detail: bool = True) -> dict[str, Any]:
    """Per-task detail for the report; the compact form drops the reasons."""
    row: dict[str, Any] = {
        "task": outcome.task,
        "capability": outcome.capability,
        "expected_order": outcome.expected_order,
        "ranked_order": outcome.ranked_order,
        "best_rank": outcome.best_rank,
        "reciprocal_rank": outcome.reciprocal_rank,
        "ndcg_at_10": outcome.ndcg_at_10,
        "has_free_candidate": outcome.has_free_candidate,
        "free_first": outcome.free_first,
        "executable_top": outcome.executable_top,
        "tier_separation": outcome.tier_separation,
    }
    if not detail:
        return row
    row["ranked"] = [
        {
            "tool_id": entry.tool_id,
            "score": entry.score,
            "tier": entry.tier,
            "tier_rank": entry.tier_rank,
            "eligible": entry.eligible,
            "executable": entry.executable,
            "reasons": list(entry.reasons) if position == 0 else [],
        }
        for position, entry in enumerate(outcome.ranked)
    ]
    return row


def per_capability(outcomes: Sequence[TaskOutcome]) -> dict[str, dict[str, Any]]:
    """Metrics of the full policy broken down by capability."""
    grouped: dict[str, list[TaskOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.capability].append(outcome)
    report: dict[str, dict[str, Any]] = {}
    for capability, rows in sorted(grouped.items()):
        summary = summarise(rows)
        report[capability] = {"tasks": len(rows), **summary}
    return report


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a GitHub flavoured Markdown table."""
    header = "| " + " | ".join(str(item) for item in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(item) for item in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


def run_ablations(
    tasks: Sequence[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[TaskOutcome]]]:
    """Rank every task with every policy variant."""
    results: dict[str, dict[str, Any]] = {}
    outcomes_by_name: dict[str, list[TaskOutcome]] = {}
    for name, overrides in ABLATIONS.items():
        policy = RankingPolicy(**overrides)
        outcomes = [evaluate_task(task, policy) for task in tasks]
        outcomes_by_name[name] = outcomes
        results[name] = {
            "configuration": name,
            "overrides": overrides,
            "metrics": summarise(outcomes),
            "rows": [outcome_row(outcome, detail=name == "full") for outcome in outcomes],
        }
    return results, outcomes_by_name


def evaluate(dataset: Path = DEFAULT_DATASET) -> dict[str, Any]:
    """Run the whole suite and return the report payload."""
    tasks = load_tasks(dataset)
    ablations, outcomes_by_name = run_ablations(tasks)
    full = ablations["full"]
    outcomes = outcomes_by_name["full"]
    policy = RankingPolicy()
    return {
        "suite": "ranking",
        "generated_at": utc_timestamp(),
        "mode": "offline",
        "dataset": str(dataset),
        "tasks": len(tasks),
        "capabilities": len({task["capability"] for task in tasks}),
        "policy": {
            "pricing_policy": policy.pricing_policy,
            "tier_order": list(policy.tier_order),
            "doc_quality_weight": policy.doc_quality_weight,
            "mapping_coverage_weight": policy.mapping_coverage_weight,
            "chain_fit_weight": policy.chain_fit_weight,
            "min_rating_count": policy.min_rating_count,
            "rating_floor": policy.rating_floor,
            "contradicted_penalty": policy.contradicted_penalty,
        },
        "metrics": full["metrics"],
        "metric_table": [
            {"configuration": name, **result["metrics"]} for name, result in ablations.items()
        ],
        "ablations": ablations,
        "per_capability": per_capability(outcomes),
        "failures": [
            row for row in full["rows"] if not row["free_first"] or row["ranked_order"] != row["expected_order"]
        ],
        "rows": full["rows"],
    }


def print_tables(payload: dict[str, Any]) -> None:
    """Print the metric table of the suite and its ablations."""
    print(f"## ranking evaluation ({payload['tasks']} tasks, {payload['capabilities']} capabilities)")
    print()
    print(
        markdown_table(
            ["configuration", *METRIC_KEYS],
            [
                [row["configuration"], *(f"{row[key]:.4f}" for key in METRIC_KEYS)]
                for row in payload["metric_table"]
            ],
        )
    )
    print()
    print("### full policy by capability")
    print()
    print(
        markdown_table(
            ["capability", "tasks", *METRIC_KEYS],
            [
                [capability, row["tasks"], *(f"{row[key]:.4f}" for key in METRIC_KEYS)]
                for capability, row in payload["per_capability"].items()
            ],
        )
    )


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    """Run the suite, write the report and print the metric table."""
    parser = argparse.ArgumentParser(description="Offline ranking evaluation for the free-first policy")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    payload = evaluate(args.dataset)
    if args.out is None:
        path = write_report("ranking", payload)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        path = args.out
    print_tables(payload)
    print()
    print(f"failures: {len(payload['failures'])}")
    print(f"report: {path}")
    return payload


if __name__ == "__main__":
    main()
