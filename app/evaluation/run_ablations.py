from __future__ import annotations

import asyncio
from typing import Any

from app.evaluation.harness import fresh_services, load_dataset, summarize_suite, utc_timestamp, write_report
from app.evaluation.metrics import mean, ratio

SELECTED_TASKS = {"c01", "c04", "c05", "c06", "c07", "c08", "c09", "c13"}
FAILURE_TASK = "What is the temperature in Lahore tomorrow?"
CONFIGURATIONS: dict[str, dict[str, bool]] = {
    "full": {},
    "no_ontology": {"use_ontology": False},
    "no_auditor": {"use_auditor": False},
    "no_trust": {"use_trust": False},
    "no_feedback": {"use_feedback": False},
    "no_substitution": {"use_substitution": False},
    "no_circuit_breaker": {"use_circuit_breaker": False},
}


async def run_configuration(name: str, flags: dict[str, bool]) -> dict[str, Any]:
    services = fresh_services(breaker_failure_threshold=1, **flags)
    tasks = [item for item in load_dataset("chain_tasks.json") if item["id"] in SELECTED_TASKS]
    rows = []
    for item in tasks:
        result = await services.client.run(item["task"])
        steps = result.plan.steps if result.plan else []
        completed_tools = {
            step.tool_id
            for step in steps
            if step.status.value in {"completed", "substituted"}
        }
        missing = [tool for tool in item["expected"].values() if tool not in completed_tools]
        rows.append(
            {
                "task_id": item["id"],
                "status": result.status.value,
                "missing": missing,
                "duration_ms": result.duration_ms,
                "success": result.status.value == "completed" and not missing,
            }
        )
    services.reset_demo()
    services.providers.force_failure("open-meteo-forecast", times=1)
    recovery = await services.client.run(FAILURE_TASK)
    recovery_steps = recovery.plan.steps if recovery.plan else []
    weather_step = next(
        (step for step in recovery_steps if step.capability == "GetWeatherForecast"),
        None,
    )
    substituted = bool(
        weather_step
        and weather_step.tool_id == "open-meteo-forecast-backup"
        and weather_step.substituted_from == "open-meteo-forecast"
    )
    recovered = recovery.status.value == "completed" and substituted
    success_count = sum(1 for row in rows if row["success"])
    return {
        "configuration": name,
        "flags": flags,
        "tasks": len(rows),
        "success_rate": ratio(success_count, len(rows)),
        "recovered_from_failure": recovered,
        "substitution_used": substituted,
        "failure_status": recovery.status.value,
        "avg_latency_ms": mean(row["duration_ms"] for row in rows),
        "rows": rows,
    }


async def evaluate() -> dict[str, Any]:
    rows = []
    for name, flags in CONFIGURATIONS.items():
        rows.append(await run_configuration(name, flags))
    metrics = {
        "chain_success_rate": mean(row["success_rate"] for row in rows),
        "recovery_rate": ratio(sum(1 for row in rows if row["recovered_from_failure"]), len(rows)),
        "substitution_rate": ratio(sum(1 for row in rows if row["substitution_used"]), len(rows)),
        "avg_latency_ms": mean(row["avg_latency_ms"] for row in rows),
    }
    return {
        "suite": "ablations",
        "generated_at": utc_timestamp(),
        "mode": "offline",
        "configurations": len(CONFIGURATIONS),
        "selected_chain_tasks": sorted(SELECTED_TASKS),
        "failure_task": FAILURE_TASK,
        "metrics": metrics,
        "rows": rows,
    }


def main() -> dict[str, Any]:
    payload = asyncio.run(evaluate())
    path = write_report("ablations", payload)
    print(summarize_suite("ablations", payload["metrics"], payload["configurations"]))
    print(f"report: {path}")
    return payload


if __name__ == "__main__":
    main()
