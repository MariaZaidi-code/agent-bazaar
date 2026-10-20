from __future__ import annotations

from app.evaluation.run_baselines import evaluate


async def test_baselines_tie_on_chains_but_not_fault_recovery() -> None:
    report = await evaluate()
    assert report["suite"] == "baselines"
    assert report["tasks"] == 15
    runners = {row["runner"]: row for row in report["runners"]}
    assert set(runners) == {"full", "b1", "b2"}
    assert all(row["chain_success_rate"] == 1.0 for row in runners.values())
    assert runners["full"]["fault_case"]["recovered"] is True
    assert runners["b1"]["fault_case"]["recovered"] is False
    assert runners["b2"]["fault_case"]["recovered"] is False
    assert report["metrics"]["full_fault_recovery"] == 1.0
    assert report["metrics"]["baseline_fault_recovery"] == 0.0
