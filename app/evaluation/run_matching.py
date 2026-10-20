from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from app.evaluation.harness import fresh_services, load_dataset, summarize_suite, utc_timestamp, write_report
from app.evaluation.metrics import mean, rank_of, ratio, reciprocal_rank


async def evaluate() -> dict[str, Any]:
    tasks = load_dataset("matching_tasks.json")
    services = fresh_services()
    rows: list[dict[str, Any]] = []
    per_capability: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in tasks:
        result = await services.client.run(item["task"])
        candidate_groups = {group.capability: group for group in result.candidate_lists}
        plan_steps = {step.subgoal_id: step for step in (result.plan.steps if result.plan else [])}
        for capability, expected_tool in item["expected"].items():
            group = candidate_groups.get(capability)
            ranked_ids = [candidate.tool.id for candidate in group.candidates] if group else []
            rank = rank_of(ranked_ids, expected_tool)
            selected = None
            if group and group.subgoal_id in plan_steps:
                selected = plan_steps[group.subgoal_id].tool_id
            row = {
                "task_id": item["id"],
                "task": item["task"],
                "capability": capability,
                "expected_tool": expected_tool,
                "task_status": result.status.value,
                "group_found": group is not None,
                "rank": rank,
                "selected_tool": selected,
                "candidate_count": len(ranked_ids),
                "hit_at_k": rank is not None,
                "top1": rank == 1,
                "selected_ok": selected == expected_tool,
            }
            rows.append(row)
            per_capability[capability].append(row)

    total = len(rows)
    group_found = sum(1 for row in rows if row["group_found"])
    hit = sum(1 for row in rows if row["hit_at_k"])
    top1 = sum(1 for row in rows if row["top1"])
    selected = sum(1 for row in rows if row["selected_ok"])
    metrics = {
        "capability_coverage": ratio(group_found, total),
        "hit_at_k": ratio(hit, total),
        "top1_accuracy": ratio(top1, total),
        "mrr": mean(reciprocal_rank(row["rank"]) for row in rows if row["group_found"]),
        "selected_tool_accuracy": ratio(selected, total),
        "task_completion_rate": ratio(
            sum(1 for result in {row["task_id"]: row for row in rows}.values() if result["task_status"] == "completed"),
            len({row["task_id"] for row in rows}),
        ),
        "avg_candidates": mean(row["candidate_count"] for row in rows if row["group_found"]),
    }
    capabilities = {}
    for capability, capability_rows in sorted(per_capability.items()):
        capabilities[capability] = {
            "cases": len(capability_rows),
            "hit_at_k": ratio(sum(1 for row in capability_rows if row["hit_at_k"]), len(capability_rows)),
            "top1_accuracy": ratio(sum(1 for row in capability_rows if row["top1"]), len(capability_rows)),
            "selected_tool_accuracy": ratio(
                sum(1 for row in capability_rows if row["selected_ok"]), len(capability_rows)
            ),
        }
    return {
        "suite": "matching",
        "generated_at": utc_timestamp(),
        "mode": "offline",
        "tasks": len(tasks),
        "expected_links": total,
        "metrics": metrics,
        "per_capability": capabilities,
        "failures": [
            row
            for row in rows
            if not row["hit_at_k"] or not row["selected_ok"] or row["task_status"] != "completed"
        ],
        "rows": rows,
    }


def main() -> dict[str, Any]:
    payload = asyncio.run(evaluate())
    path = write_report("matching", payload)
    print(summarize_suite("matching", payload["metrics"], payload["tasks"]))
    print(f"report: {path}")
    return payload


if __name__ == "__main__":
    main()
