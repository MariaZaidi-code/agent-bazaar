from __future__ import annotations

import asyncio
from typing import Any

from app.evaluation import (
    run_ablations,
    run_baselines,
    run_chains,
    run_matching,
    run_substitution,
    run_trust,
)
from app.evaluation.harness import utc_timestamp, write_report


async def evaluate_all() -> dict[str, Any]:
    suites = {}
    for name, evaluator in (
        ("matching", run_matching.evaluate),
        ("chains", run_chains.evaluate),
        ("baselines", run_baselines.evaluate),
        ("substitution", run_substitution.evaluate),
        ("trust", run_trust.evaluate),
        ("ablations", run_ablations.evaluate),
    ):
        payload = await evaluator() if asyncio.iscoroutinefunction(evaluator) else evaluator()
        suites[name] = payload
        write_report(name, payload)
    summary = {
        "suite": "summary",
        "generated_at": utc_timestamp(),
        "mode": "offline",
        "headline": {
            "matching_mrr": suites["matching"]["metrics"]["mrr"],
            "matching_selected_tool_accuracy": suites["matching"]["metrics"]["selected_tool_accuracy"],
            "chain_success_rate": suites["chains"]["metrics"]["success_rate"],
            "baseline_full_chain_success_rate": suites["baselines"]["metrics"]["full_chain_success_rate"],
            "baseline_best_chain_success_rate": suites["baselines"]["metrics"]["best_baseline_chain_success_rate"],
            "fault_recovery_full": suites["baselines"]["metrics"]["full_fault_recovery"],
            "fault_recovery_baselines": suites["baselines"]["metrics"]["baseline_fault_recovery"],
            "substitution_recovery_accuracy": suites["substitution"]["metrics"]["recovery_accuracy"],
            "trust_pass_rate": suites["trust"]["metrics"]["pass_rate"],
            "ablation_chain_success_rate": suites["ablations"]["metrics"]["chain_success_rate"],
        },
        "suites": suites,
    }
    write_report("summary", summary)
    return summary


def main() -> dict[str, Any]:
    summary = asyncio.run(evaluate_all())
    for name, metrics in summary["headline"].items():
        print(f"{name}: {metrics}")
    print("reports written to reports/*.json")
    return summary


if __name__ == "__main__":
    main()
