from __future__ import annotations

import json
from pathlib import Path

from agent_bazaar_auditor.evaluation import run_all_evaluations
from agent_bazaar_auditor.paths import DATA_DIR


def test_seeded_dataset_shape() -> None:
    claims = json.loads((DATA_DIR / "seeded_claims.json").read_text(encoding="utf-8"))
    drift = json.loads((DATA_DIR / "drift_scenarios.json").read_text(encoding="utf-8"))
    assert len(claims["items"]) == 60
    assert claims["counts"] == {"Verified": 32, "Supported": 8, "Contradicted": 10, "Unsupported": 10}
    assert len(drift["scenarios"]) == 20
    behaviors = {scenario["behavior"] for scenario in drift["scenarios"]}
    assert {"rename_field", "remove_field", "type_change", "unit_change", "garbage_200", "outage", "flapping", "dishonest"} <= behaviors


def test_full_evaluation_meets_controlled_targets(tmp_path: Path) -> None:
    result = run_all_evaluations(output_dir=tmp_path)
    claims = result["claim_verification"]["metrics"]
    drift = result["drift_detection"]
    trust = result["trust_experiment"]
    assert claims["accuracy"] >= 0.95
    assert claims["macro_f1"] >= 0.95
    assert drift["runs"]["rule_only"]["detected"] < drift["scenario_count"]
    assert drift["runs"]["full"]["detected"] == drift["scenario_count"]
    assert drift["false_alarms"]["full"]["false_alarms"] == 0
    assert trust["bad_demoted"] == trust["bad_providers"]
    assert trust["honest_demoted"] == 0
    summary = tmp_path / "reports" / "evaluation_summary.md"
    assert summary.exists()
    assert "Claim verification" in summary.read_text(encoding="utf-8")
