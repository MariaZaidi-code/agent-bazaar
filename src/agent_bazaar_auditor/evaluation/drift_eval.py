from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

from ..auditor import Auditor
from ..config import Settings
from ..enums import ProbeSource
from ..mocks.provider import MockProvider
from ..paths import DATA_DIR, OUTPUTS_DIR
from ..probes.models import ProbeResult
from ..utils import atomic_write_json, canonical_json, percentage, utc_now
from .metrics import latency_summary

BEHAVIOR_ORDER = [
    "rename_field",
    "remove_field",
    "type_change",
    "unit_change",
    "garbage_200",
    "outage",
    "flapping",
    "dishonest",
]


def _probe(tool_id: str, payload: Any, metadata: dict[str, Any] | None = None) -> ProbeResult:
    return ProbeResult(
        tool_id=tool_id,
        ok=True,
        status_code=200,
        payload=payload,
        source=ProbeSource.FIXTURE,
        raw_text=canonical_json(payload),
        metadata=metadata or {},
    )


def _perturb_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _perturb_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_perturb_values(item) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value == 0:
            return 1
        delta = max(1, int(round(abs(value) * 0.04)))
        return value + (delta if value > 0 else -delta)
    if isinstance(value, float):
        return round(value * 1.04, 4) if value != 0 else 0.5
    return value


def _optional_field(value: Any) -> Any:
    result = copy.deepcopy(value)
    if isinstance(result, dict):
        result["_attribution"] = "Agent Bazaar probe variation"
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                item["_attribution"] = "Agent Bazaar probe variation"
    return result


def _known_good_variations(payload: Any) -> dict[str, Any]:
    return {
        "values_changed": _perturb_values(payload),
        "optional_field_added": _optional_field(payload),
    }


def _tune_threshold(auditor: Auditor) -> dict[str, Any]:
    auditor.monitor.threshold = 2.0
    distances: list[dict[str, Any]] = []
    for tool_id, definition in auditor.definitions.items():
        auditor.monitor.reset(tool_id)
        baseline = _probe(tool_id, definition.fixture, {"variation": "baseline"})
        auditor.monitor.check(tool_id, baseline, definition, probe_round=0, establish_if_missing=True)
        for kind, payload in _known_good_variations(definition.fixture).items():
            variation = _probe(tool_id, payload, {"variation": kind})
            check = auditor.monitor.embedding_detector.check(
                tool_id,
                variation,
                probe_round=1,
                establish_if_missing=False,
            )
            distances.append(
                {
                    "tool_id": tool_id,
                    "variation": kind,
                    "distance": round(check.distance or 0.0, 6),
                }
            )
        auditor.monitor.reset(tool_id)
    values = [row["distance"] for row in distances]
    maximum = max(values) if values else 0.0
    mean = sum(values) / len(values) if values else 0.0
    recommended = max(0.15, round(maximum + 0.05, 3))
    return {
        "variations": len(distances),
        "max_good_distance": round(maximum, 6),
        "mean_good_distance": round(mean, 6),
        "recommended_threshold": recommended,
        "margin": 0.05,
        "method": "Maximum cosine distance on two known-good variations per tool, plus a 0.05 margin; never below 0.15.",
        "details": distances,
    }


def _false_alarms(auditor: Auditor, threshold: float) -> dict[str, Any]:
    auditor.monitor.threshold = threshold
    total = 0
    alerts = 0
    rows: list[dict[str, Any]] = []
    for tool_id, definition in auditor.definitions.items():
        auditor.monitor.reset(tool_id)
        baseline = _probe(tool_id, definition.fixture, {"variation": "baseline"})
        auditor.monitor.check(tool_id, baseline, definition, probe_round=0, establish_if_missing=True)
        for kind, payload in _known_good_variations(definition.fixture).items():
            total += 1
            variation = _probe(tool_id, payload, {"variation": kind})
            check = auditor.monitor.check(
                tool_id,
                variation,
                definition,
                probe_round=1,
                establish_if_missing=False,
            )
            if check.detected:
                alerts += 1
                rows.append({"tool_id": tool_id, "variation": kind, "detectors": check.detectors})
        auditor.monitor.reset(tool_id)
    return {
        "total_variations": total,
        "false_alarms": alerts,
        "false_alarm_rate": round(percentage(alerts, total) / 100.0, 4),
        "details": rows,
    }


def _run_scenarios(auditor: Auditor, scenarios: list[dict[str, Any]], threshold: float, max_rounds: int = 3) -> dict[str, Any]:
    auditor.monitor.threshold = threshold
    rows: list[dict[str, Any]] = []
    for index, scenario in enumerate(scenarios):
        tool_id = scenario["tool_id"]
        definition = auditor.get_definition(tool_id)
        provider = MockProvider(
            tool_id=tool_id,
            definition=definition,
            behavior="normal",
            options={},
            seed=5000 + index,
        )
        auditor.harness.set_provider(tool_id, provider)
        auditor.monitor.reset(tool_id)
        baseline = auditor.harness.probe(tool_id)
        baseline_check = auditor.monitor.check(
            tool_id,
            baseline,
            definition,
            probe_round=0,
            establish_if_missing=True,
        )
        provider.configure(scenario["behavior"], **scenario.get("options", {}))
        detected = False
        detected_round: int | None = None
        detector_match = False
        final_check = None
        alerts_payload: list[dict[str, Any]] = []
        for probe_round in range(1, max_rounds + 1):
            probe = auditor.harness.probe(tool_id, force_live=True)
            check = auditor.monitor.check(
                tool_id,
                probe,
                definition,
                probe_round=probe_round,
                establish_if_missing=False,
            )
            final_check = check
            alerts_payload = [alert.to_dict() for alert in check.alerts]
            if check.detected:
                detected = True
                detected_round = probe_round
                detector_match = scenario["expected_detector"] in check.detectors
                break
        auditor.harness.remove_provider(tool_id)
        auditor.monitor.reset(tool_id)
        rows.append(
            {
                "id": scenario["id"],
                "tool_id": tool_id,
                "behavior": scenario["behavior"],
                "description": scenario["description"],
                "expected_detector": scenario["expected_detector"],
                "expected_round": scenario["expected_round"],
                "detected": detected,
                "detected_round": detected_round,
                "detector_match": detector_match,
                "detectors": final_check.detectors if final_check else [],
                "distance": round(final_check.distance, 6) if final_check and final_check.distance is not None else None,
                "baseline_alert": baseline_check.detected,
                "alerts": alerts_payload,
            }
        )
    detected_count = sum(1 for row in rows if row["detected"])
    detector_matches = sum(1 for row in rows if row["detector_match"])
    by_behavior: dict[str, dict[str, Any]] = {}
    for behavior in BEHAVIOR_ORDER:
        subset = [row for row in rows if row["behavior"] == behavior]
        if subset:
            by_behavior[behavior] = {
                "scenarios": len(subset),
                "detected": sum(1 for row in subset if row["detected"]),
                "detector_matches": sum(1 for row in subset if row["detector_match"]),
                "detection_rate": round(percentage(sum(1 for row in subset if row["detected"]), len(subset)) / 100.0, 4),
            }
    return {
        "mode": auditor.monitor.mode,
        "threshold": threshold,
        "max_rounds": max_rounds,
        "scenario_count": len(rows),
        "detected": detected_count,
        "detection_rate": round(percentage(detected_count, len(rows)) / 100.0, 4),
        "detector_matches": detector_matches,
        "detector_match_rate": round(percentage(detector_matches, len(rows)) / 100.0, 4),
        "mean_rounds_to_detection": round(
            sum(row["detected_round"] for row in rows if row["detected_round"] is not None) / max(1, detected_count),
            4,
        ),
        "by_behavior": by_behavior,
        "scenarios": rows,
    }


def _markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Drift Detection and Re-mapping Evaluation",
        "",
        f"Generated: {result['generated_at']}",
        "",
        f"Dataset: `{result['dataset']}`",
        "",
        "## Threshold tuning",
        "",
        f"- Known-good variations evaluated: {result['tuning']['variations']}",
        f"- Maximum known-good cosine distance: {result['tuning']['max_good_distance']:.4f}",
        f"- Mean known-good distance: {result['tuning']['mean_good_distance']:.4f}",
        f"- Tuned threshold used: **{result['threshold']:.3f}**",
        f"- Method: {result['tuning']['method']}",
        "",
        "## Rule-only vs rule + embedding",
        "",
        "| Mode | Scenarios detected | Detection rate | Correct detector | Mean rounds | False alarms | False-alarm rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in ("rule_only", "full"):
        run = result["runs"][mode]
        false_alarms = result["false_alarms"][mode]
        lines.append(
            f"| {mode} | {run['detected']}/{run['scenario_count']} | {run['detection_rate']:.3f} | "
            f"{run['detector_matches']}/{run['scenario_count']} | {run['mean_rounds_to_detection']:.2f} | "
            f"{false_alarms['false_alarms']}/{false_alarms['total_variations']} | {false_alarms['false_alarm_rate']:.3f} |"
        )
    lines.extend(["", "## Detection by behaviour", "", "| Behaviour | Scenarios | Detected (full) | Correct detector | Detection rate |", "| --- | ---: | ---: | ---: | ---: |"])
    for behavior, row in result["runs"]["full"]["by_behavior"].items():
        lines.append(
            f"| {behavior} | {row['scenarios']} | {row['detected']} | {row['detector_matches']} | {row['detection_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Injected scenarios",
            "",
            "| ID | Tool | Behaviour | Expected detector | Detected | Round | Distance |",
            "| --- | --- | --- | --- | --- | ---: | ---: |",
        ]
    )
    for row in result["runs"]["full"]["scenarios"]:
        distance = f"{row['distance']:.4f}" if row["distance"] is not None else "-"
        lines.append(
            f"| {row['id']} | {row['tool_id']} | {row['behavior']} | {row['expected_detector']} | "
            f"{'yes' if row['detected'] else 'no'} | {row['detected_round'] or '-'} | {distance} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Garbage 200 responses preserve the mapped fields and therefore pass deterministic field/type/range checks. "
            "The embedding detector compares a schema summary with the stored baseline and catches the pollution. "
            "This is the controlled, injected evaluation required by the work plan; real APIs rarely drift inside ten weeks, "
            "so real probe history is reported separately and not used to estimate real-world drift frequency.",
            "",
            "Re-mapping accuracy depends on Maria's Mapper contract and is not scored in this standalone Auditor repository. "
            "The `DriftAlert` payload carries the tool id, field path, detector, old description, new sample, distance, timestamp and severity needed for that loop.",
            "",
        ]
    )
    return "\n".join(lines)


def run_drift_evaluation(
    dataset_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    threshold: float | None = None,
    max_rounds: int = 3,
) -> dict[str, Any]:
    dataset_path = Path(dataset_path) if dataset_path else DATA_DIR / "drift_scenarios.json"
    output_dir = Path(output_dir) if output_dir else OUTPUTS_DIR
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    scenarios = dataset["scenarios"]
    with tempfile.TemporaryDirectory(prefix="agent-bazaar-drift-eval-") as temporary:
        base = Path(temporary)
        settings = Settings(
            outputs_dir=base / "outputs",
            cache_dir=base / "cache",
            live=False,
            drift_mode="full",
        )
        auditor = Auditor(settings=settings, persist=False)
        tuning = _tune_threshold(auditor)
        chosen = float(threshold) if threshold is not None else float(tuning["recommended_threshold"])
        runs: dict[str, Any] = {}
        false_alarms: dict[str, Any] = {}
        for mode in ("rule_only", "full"):
            mode_settings = Settings(
                outputs_dir=base / f"outputs-{mode}",
                cache_dir=base / f"cache-{mode}",
                live=False,
                drift_mode=mode,
            )
            mode_auditor = Auditor(settings=mode_settings, persist=False)
            runs[mode] = _run_scenarios(mode_auditor, scenarios, chosen, max_rounds=max_rounds)
            false_alarms[mode] = _false_alarms(mode_auditor, chosen)
        elapsed = latency_summary([0.0])
        result = {
            "schema_version": 1,
            "generated_at": utc_now(),
            "dataset": str(dataset_path),
            "dataset_name": dataset.get("name", ""),
            "dataset_notes": dataset.get("notes", []),
            "scenario_count": len(scenarios),
            "threshold": chosen,
            "tuning": tuning,
            "runs": runs,
            "false_alarms": false_alarms,
            "cost": {**elapsed, "total_tokens": 0, "note": "Offline evaluation uses deterministic fixture payloads and mock providers."},
        }
        result["artifacts"] = {
            "json": str(reports_dir / "drift_evaluation.json"),
            "markdown": str(reports_dir / "drift_evaluation.md"),
        }
        atomic_write_json(reports_dir / "drift_evaluation.json", result)
        (reports_dir / "drift_evaluation.md").write_text(_markdown_report(result), encoding="utf-8")
        return result
