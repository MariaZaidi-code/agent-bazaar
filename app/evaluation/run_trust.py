from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.core.trust_registry import TrustRegistry
from app.evaluation.harness import load_dataset, summarize_suite, utc_timestamp, write_report
from app.evaluation.metrics import ratio


def evaluate() -> dict[str, Any]:
    scenarios = load_dataset("trust_scenarios.json")
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        root = Path(tempfile.mkdtemp(prefix="agent-bazaar-trust-"))
        registry = TrustRegistry(
            root / "trust.db",
            demotion_threshold=0.4,
            min_evidence=3,
        )
        provider_id = scenario["id"]
        for operation in scenario["operations"]:
            registry.update(
                provider_id,
                operation["signal"],
                success=bool(operation["success"]),
                weight=operation.get("weight"),
                reason=operation.get("reason", ""),
                source="evaluation",
            )
        state = registry.get(provider_id)
        replay = registry.replay(provider_id)
        checks = {
            "demotion": state["demoted"] is scenario["expected_demoted"],
            "min_score": state["score"] >= scenario.get("min_score", 0.0),
            "max_score": state["score"] <= scenario.get("max_score", 1.0),
            "replay_matches": replay["matches"],
        }
        rows.append(
            {
                "scenario": scenario["id"],
                "name": scenario["name"],
                "operations": len(scenario["operations"]),
                "score": state["score"],
                "demoted": state["demoted"],
                "contradictions": state["contradictions"],
                "expected_demoted": scenario["expected_demoted"],
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    passed = sum(1 for row in rows if row["passed"])
    metrics = {
        "pass_rate": ratio(passed, len(rows)),
        "demotion_accuracy": ratio(
            sum(1 for row in rows if row["checks"]["demotion"]), len(rows)
        ),
        "replay_consistency": ratio(
            sum(1 for row in rows if row["checks"]["replay_matches"]), len(rows)
        ),
    }
    return {
        "suite": "trust",
        "generated_at": utc_timestamp(),
        "mode": "offline",
        "scenarios": len(scenarios),
        "metrics": metrics,
        "failures": [row for row in rows if not row["passed"]],
        "rows": rows,
    }


def main() -> dict[str, Any]:
    payload = evaluate()
    path = write_report("trust", payload)
    print(summarize_suite("trust", payload["metrics"], payload["scenarios"]))
    print(f"report: {path}")
    return payload


if __name__ == "__main__":
    main()
