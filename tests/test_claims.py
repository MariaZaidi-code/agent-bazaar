from __future__ import annotations

from agent_bazaar_auditor.claims import Claim, HeuristicEvidenceJudge
from agent_bazaar_auditor.enums import ClaimLabel, ClaimType, DocStance, ProbeOutcome, ProbeSource
from agent_bazaar_auditor.probes.definitions import build_probe_definitions
from agent_bazaar_auditor.probes.models import MISSING, ProbeResult, evaluate_claim, resolve_path


def _claim(**overrides) -> Claim:
    values = {
        "id": "claim-1",
        "tool_id": "example",
        "text": "Returns a temperature in Celsius.",
        "claim_type": ClaimType.UNIT,
        "field_path": "current.temperature_2m",
        "expected_type": "number",
        "expected_unit": "celsius",
        "probeable": True,
    }
    values.update(overrides)
    return Claim(**values)


def test_resolve_path_traverses_nested_arrays() -> None:
    payload = {"feed": {"entry": [{"title": "A", "summary": "B"}]}}
    assert resolve_path(payload, "feed.entry.title") == "A"
    assert resolve_path({"features": [{"properties": {"mag": 4.5}}]}, "properties.mag") == 4.5


def test_resolve_path_returns_missing_for_unknown() -> None:
    assert resolve_path({"a": 1}, "missing.path") is MISSING


def test_evaluate_claim_agrees_on_unit() -> None:
    definition = build_probe_definitions()["open-meteo"]
    probe = ProbeResult(
        tool_id="open-meteo",
        ok=True,
        status_code=200,
        payload=definition.fixture,
        source=ProbeSource.FIXTURE,
    )
    check = evaluate_claim(_claim(), probe, definition)
    assert check.outcome is ProbeOutcome.AGREES


def test_evaluate_claim_disagrees_when_unit_changes() -> None:
    definition = build_probe_definitions()["open-meteo"]
    payload = {
        **definition.fixture,
        "current": {**definition.fixture["current"], "temperature_2m": 77.0},
        "current_units": {**definition.fixture["current_units"], "temperature_2m": "\u00b0F"},
    }
    probe = ProbeResult(tool_id="open-meteo", ok=True, status_code=200, payload=payload, source=ProbeSource.FIXTURE)
    check = evaluate_claim(_claim(), probe, definition)
    assert check.outcome is ProbeOutcome.DISAGREES
    assert check.field_path == "current.temperature_2m"


def test_heuristic_judge_reads_auth_claims() -> None:
    claim = _claim(
        text="An API key is required.",
        claim_type=ClaimType.AUTHENTICATION,
        field_path=None,
        expected_type="boolean",
        expected_unit=None,
        metadata={"expects_key": True},
    )
    judgement = HeuristicEvidenceJudge().judge(
        claim,
        ["An API key is required for every request."],
    )
    assert judgement.stance is DocStance.SUPPORTS


def test_claim_ground_truth_and_roundtrip() -> None:
    claim = _claim(ground_truth_label=ClaimLabel.VERIFIED)
    restored = Claim.from_dict(claim.to_dict())
    assert restored.ground_truth_label is ClaimLabel.VERIFIED
    assert restored.expected_unit == "celsius"
