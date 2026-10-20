from __future__ import annotations

import asyncio
from typing import Any

from app.evaluation.harness import fresh_services, load_dataset, summarize_suite, utc_timestamp, write_report
from app.evaluation.metrics import mean, ratio


async def evaluate() -> dict[str, Any]:
    cases = load_dataset("substitution_cases.json")
    rows: list[dict[str, Any]] = []
    for case in cases:
        services = fresh_services(breaker_failure_threshold=1)
        scheduled = services.providers.force_failure(case["fail_tool"], times=1)
        try:
            result = await services.client.run(case["task"])
            error = None
        except Exception as exc:
            result = None
            error = str(exc)
        step = None
        if result and result.plan:
            step = next(
                (item for item in result.plan.steps if item.capability == case["expected_capability"]),
                None,
            )
        recovered = bool(result and result.status.value == "completed")
        substitute_used = bool(
            step
            and case["expected_substitute"]
            and step.tool_id == case["expected_substitute"]
            and step.substituted_from == case["fail_tool"]
        )
        substitute_expected = bool(case["expected_recovered"])
        outcome_correct = recovered == substitute_expected
        if substitute_expected:
            outcome_correct = outcome_correct and substitute_used
        events = [event.event_type for event in result.trace] if result else []
        rows.append(
            {
                "case_id": case["id"],
                "task": case["task"],
                "fail_tool": case["fail_tool"],
                "scheduled": scheduled,
                "expected_recovered": case["expected_recovered"],
                "expected_substitute": case["expected_substitute"],
                "actual_status": result.status.value if result else "failed",
                "actual_tool": step.tool_id if step else None,
                "substituted_from": step.substituted_from if step else None,
                "substitute_used": substitute_used,
                "outcome_correct": outcome_correct,
                "trace_has_substitution": "substitution_succeeded" in events,
                "answer": result.answer if result else "",
                "error": error or (step.error if step else None),
                "duration_ms": result.duration_ms if result else 0.0,
            }
        )
    metrics = {
        "recovery_accuracy": ratio(sum(1 for row in rows if row["outcome_correct"]), len(rows)),
        "substitute_accuracy": ratio(sum(1 for row in rows if row["substitute_used"]), len(rows)),
        "unexpected_recovery_rate": ratio(
            sum(
                1
                for row in rows
                if row["actual_status"] == "completed" and not row["expected_recovered"]
            ),
            len(rows),
        ),
        "trace_coverage": ratio(sum(1 for row in rows if row["trace_has_substitution"]), len(rows)),
        "avg_latency_ms": mean(row["duration_ms"] for row in rows),
    }
    return {
        "suite": "substitution",
        "generated_at": utc_timestamp(),
        "mode": "offline",
        "cases": len(cases),
        "metrics": metrics,
        "failures": [row for row in rows if not row["outcome_correct"]],
        "rows": rows,
    }


def main() -> dict[str, Any]:
    payload = asyncio.run(evaluate())
    path = write_report("substitution", payload)
    print(summarize_suite("substitution", payload["metrics"], payload["cases"]))
    print(f"report: {path}")
    return payload


if __name__ == "__main__":
    main()
