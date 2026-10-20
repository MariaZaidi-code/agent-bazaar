from __future__ import annotations

import asyncio
from typing import Any

from app.evaluation.harness import fresh_services, load_dataset, summarize_suite, utc_timestamp, write_report
from app.evaluation.metrics import mean, ratio

FAILURE_TASK = "What is the temperature in Lahore tomorrow?"


async def run_normal_tasks(runner: str) -> dict[str, Any]:
    services = fresh_services()
    tasks = load_dataset("chain_tasks.json")
    rows = []
    expected_total = 0
    expected_found = 0
    for item in tasks:
        expected_total += len(item["expected"])
        if runner == "full":
            result = await services.client.run(item["task"])
            steps = result.plan.steps if result.plan else []
            completed = {
                step.capability: step.tool_id
                for step in steps
                if step.status.value in {"completed", "substituted"}
            }
            status = result.status.value
            duration = result.duration_ms
            answer = result.answer
            selected = {capability: completed.get(capability) for capability in item["expected"]}
        else:
            baseline = services.b1 if runner == "b1" else services.b2
            result = await baseline.run(item["task"])
            subgoal_by_capability = {subgoal.capability: subgoal for subgoal in result.subgoals}
            selected = {}
            for capability in item["expected"]:
                subgoal = subgoal_by_capability.get(capability)
                ranking = result.rankings.get(subgoal.id, []) if subgoal else []
                selected[capability] = ranking[0] if ranking else None
            status = result.status
            duration = result.duration_ms
            answer = result.answer
        matched = 0
        for capability, expected_tool in item["expected"].items():
            if selected.get(capability) == expected_tool:
                matched += 1
        expected_found += matched
        rows.append(
            {
                "task_id": item["id"],
                "task": item["task"],
                "status": status,
                "selected": selected,
                "expected": item["expected"],
                "selected_matches": matched,
                "all_expected_selected": matched == len(item["expected"]),
                "answer_chars": len(answer or ""),
                "duration_ms": duration,
            }
        )
    return {
        "runner": runner,
        "tasks": len(tasks),
        "chain_success_rate": ratio(
            sum(1 for row in rows if row["status"] == "completed"), len(rows)
        ),
        "expected_tool_selection_accuracy": ratio(expected_found, expected_total),
        "answer_rate": ratio(sum(1 for row in rows if row["answer_chars"] > 0), len(rows)),
        "avg_latency_ms": mean(row["duration_ms"] for row in rows),
        "rows": rows,
    }


async def run_fault_case(runner: str) -> dict[str, Any]:
    services = fresh_services(breaker_failure_threshold=1)
    services.providers.force_failure("open-meteo-forecast", times=1)
    if runner == "full":
        result = await services.client.run(FAILURE_TASK)
        steps = result.plan.steps if result.plan else []
        weather = next((step for step in steps if step.capability == "GetWeatherForecast"), None)
        recovered = bool(
            result.status.value == "completed"
            and weather
            and weather.tool_id == "open-meteo-forecast-backup"
        )
        status = result.status.value
        selected = weather.tool_id if weather else None
        answer = result.answer
    else:
        baseline = services.b1 if runner == "b1" else services.b2
        result = await baseline.run(FAILURE_TASK)
        status = result.status
        selected = next(
            (
                step.tool_id
                for step in result.steps
                if step.capability == "GetWeatherForecast"
            ),
            None,
        )
        recovered = status == "completed"
        answer = result.answer
    return {
        "runner": runner,
        "task": FAILURE_TASK,
        "status": status,
        "selected_tool": selected,
        "recovered": recovered,
        "answer_chars": len(answer or ""),
    }


async def evaluate() -> dict[str, Any]:
    rows = []
    for runner in ("full", "b1", "b2"):
        normal = await run_normal_tasks(runner)
        fault = await run_fault_case(runner)
        rows.append({**normal, "fault_case": fault})
    for row in rows:
        row["fault_recovery"] = 1.0 if row["fault_case"]["recovered"] else 0.0
    full = next(row for row in rows if row["runner"] == "full")
    best_baseline = max(
        (row for row in rows if row["runner"] != "full"),
        key=lambda row: (row["chain_success_rate"], row["expected_tool_selection_accuracy"]),
    )
    metrics = {
        "full_chain_success_rate": full["chain_success_rate"],
        "best_baseline_chain_success_rate": best_baseline["chain_success_rate"],
        "chain_success_delta": round(
            full["chain_success_rate"] - best_baseline["chain_success_rate"], 4
        ),
        "full_fault_recovery": full["fault_recovery"],
        "baseline_fault_recovery": mean(row["fault_recovery"] for row in rows if row["runner"] != "full"),
    }
    return {
        "suite": "baselines",
        "generated_at": utc_timestamp(),
        "mode": "offline",
        "tasks": len(load_dataset("chain_tasks.json")),
        "metrics": metrics,
        "runners": rows,
    }


def main() -> dict[str, Any]:
    payload = asyncio.run(evaluate())
    path = write_report("baselines", payload)
    print(
        summarize_suite(
            "baselines",
            {
                "success_rate": payload["metrics"]["full_chain_success_rate"],
            },
            payload["tasks"],
        )
    )
    print(f"report: {path}")
    return payload


if __name__ == "__main__":
    main()
