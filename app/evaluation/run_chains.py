from __future__ import annotations

import asyncio
from typing import Any

from app.evaluation.harness import fresh_services, load_dataset, summarize_suite, utc_timestamp, write_report
from app.evaluation.metrics import mean, ratio


async def evaluate() -> dict[str, Any]:
    tasks = load_dataset("chain_tasks.json")
    services = fresh_services()
    rows: list[dict[str, Any]] = []
    expected_total = 0
    expected_found = 0

    for item in tasks:
        result = await services.client.run(item["task"])
        steps = result.plan.steps if result.plan else []
        steps_by_capability: dict[str, list[Any]] = {}
        for step in steps:
            steps_by_capability.setdefault(step.capability, []).append(step)
        missing = []
        for capability, expected_tool in item["expected"].items():
            expected_total += 1
            matching_steps = steps_by_capability.get(capability, [])
            if any(
                step.tool_id == expected_tool and step.status.value in {"completed", "substituted"}
                for step in matching_steps
            ):
                expected_found += 1
            else:
                missing.append(f"{capability}:{expected_tool}")
        trace_events = [event.event_type for event in result.trace]
        rows.append(
            {
                "task_id": item["id"],
                "task": item["task"],
                "status": result.status.value,
                "answer_chars": len(result.answer or ""),
                "steps": [
                    {
                        "capability": step.capability,
                        "tool_id": step.tool_id,
                        "status": step.status.value,
                        "latency_ms": step.latency_ms,
                        "substituted_from": step.substituted_from,
                    }
                    for step in steps
                ],
                "missing": missing,
                "trace_events": len(trace_events),
                "has_completion_event": "task_completed" in trace_events,
                "duration_ms": result.duration_ms,
                "mode": result.mode,
            }
        )
    successful = [row for row in rows if row["status"] == "completed" and not row["missing"]]
    metrics = {
        "success_rate": ratio(len(successful), len(rows)),
        "expected_capability_coverage": ratio(expected_found, expected_total),
        "answer_rate": ratio(sum(1 for row in rows if row["answer_chars"] > 0), len(rows)),
        "trace_coverage": ratio(sum(1 for row in rows if row["trace_events"] > 0), len(rows)),
        "completion_event_rate": ratio(sum(1 for row in rows if row["has_completion_event"]), len(rows)),
        "avg_latency_ms": mean(row["duration_ms"] for row in rows),
        "avg_steps": mean(len(row["steps"]) for row in rows),
    }
    return {
        "suite": "chains",
        "generated_at": utc_timestamp(),
        "mode": "offline",
        "tasks": len(tasks),
        "metrics": metrics,
        "failures": [row for row in rows if row not in successful],
        "rows": rows,
    }


def main() -> dict[str, Any]:
    payload = asyncio.run(evaluate())
    path = write_report("chains", payload)
    print(summarize_suite("chains", payload["metrics"], payload["tasks"]))
    print(f"report: {path}")
    return payload


if __name__ == "__main__":
    main()
