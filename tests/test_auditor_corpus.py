from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CLAIMS = json.loads((DATA_DIR / "seeded_claims.json").read_text(encoding="utf-8"))
DRIFT = json.loads((DATA_DIR / "drift_scenarios.json").read_text(encoding="utf-8"))
LABELS = {"Verified", "Supported", "Contradicted", "Unsupported"}


@pytest.mark.parametrize(
    "item", CLAIMS["items"], ids=[item["id"] for item in CLAIMS["items"]]
)
def test_every_labelled_claim_is_complete(item: dict) -> None:
    assert item["tool_id"]
    assert item["claim"]["text"].strip()
    assert item["ground_truth_label"] in LABELS
    assert item["rationale"].strip()
    assert item["mock_behavior"]


@pytest.mark.parametrize(
    "scenario", DRIFT["scenarios"], ids=[item["id"] for item in DRIFT["scenarios"]]
)
def test_every_drift_scenario_is_complete(scenario: dict) -> None:
    assert scenario["tool_id"]
    assert scenario["behavior"]
    assert scenario["description"].strip()
    assert scenario["expected_detector"] in {"rule", "embedding", "either"}
    assert scenario["expected_round"] >= 1


def test_auditor_corpus_meets_the_master_plan_targets() -> None:
    assert len(CLAIMS["items"]) >= 100
    assert len(DRIFT["scenarios"]) >= 40
    assert sum(CLAIMS["counts"].values()) == len(CLAIMS["items"])
    assert set(CLAIMS["counts"]) == LABELS
