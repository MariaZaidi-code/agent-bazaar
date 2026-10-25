from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ..auditor import Auditor
from ..config import Settings
from ..enums import ClaimLabel, TrustOutcome
from ..messages import TrustUpdate
from ..mocks.provider import MockProvider
from ..paths import OUTPUTS_DIR
from ..probes.models import validate_payload
from ..trust import TrustFeed, TrustLedger
from ..utils import atomic_write_json, utc_now

PROVIDERS = [
    {
        "provider_id": "frankfurter-honest",
        "tool_id": "frankfurter",
        "behavior": "normal",
        "options": {},
        "malicious": False,
        "claim_index": 0,
    },
    {
        "provider_id": "nominatim-honest",
        "tool_id": "nominatim",
        "behavior": "normal",
        "options": {},
        "malicious": False,
        "claim_index": 0,
    },
    {
        "provider_id": "restcountries-honest",
        "tool_id": "rest-countries",
        "behavior": "normal",
        "options": {},
        "malicious": False,
        "claim_index": 0,
    },
    {
        "provider_id": "nager-honest",
        "tool_id": "nager-date",
        "behavior": "normal",
        "options": {},
        "malicious": False,
        "claim_index": 0,
    },
    {
        "provider_id": "dogceo-honest",
        "tool_id": "dog-ceo",
        "behavior": "normal",
        "options": {},
        "malicious": False,
        "claim_index": 0,
    },
    {
        "provider_id": "openmeteo-dishonest",
        "tool_id": "open-meteo",
        "behavior": "dishonest",
        "options": {
            "field_path": "current.temperature_2m",
            "unit_path": "current_units.temperature_2m",
            "from_unit": "celsius",
            "to_unit": "fahrenheit",
        },
        "malicious": True,
        "claim_index": 0,
    },
    {
        "provider_id": "ipify-outage",
        "tool_id": "ipify",
        "behavior": "outage",
        "options": {},
        "malicious": True,
        "claim_index": 0,
    },
    {
        "provider_id": "joke-flapping",
        "tool_id": "joke-api",
        "behavior": "flapping",
        "options": {"fail_on_calls": [2, 3, 4, 6, 7, 8, 10]},
        "malicious": True,
        "claim_index": 0,
    },
    {
        "provider_id": "catfact-typechange",
        "tool_id": "cat-fact",
        "behavior": "type_change",
        "options": {"field_path": "length", "replacement": "unknown"},
        "malicious": True,
        "claim_index": 1,
    },
    {
        "provider_id": "usgs-removefield",
        "tool_id": "usgs-earthquake",
        "behavior": "remove_field",
        "options": {"field_path": "properties.mag"},
        "malicious": True,
        "claim_index": 1,
    },
]


def _round_outcome(auditor: Auditor, provider: MockProvider, claim, definition) -> tuple[TrustOutcome, str, str]:
    probe = auditor.harness.probe(provider.tool_id, force_live=True)
    if not probe.ok:
        return TrustOutcome.PROBE_FAIL, probe.error or f"HTTP {probe.status_code}", "probe_failure"
    validation = validate_payload(definition, probe.payload) if probe.payload is not None else None
    assessment = auditor.assess_claim(claim, probe=probe, validation=validation)
    if validation is not None and not validation.ok:
        return TrustOutcome.SCHEMA_INVALID, "Schema validation failed.", assessment.label.value
    if assessment.label is ClaimLabel.CONTRADICTED:
        return TrustOutcome.CONTRADICTION, assessment.rationale, assessment.label.value
    if assessment.label is ClaimLabel.UNSUPPORTED:
        return TrustOutcome.PROBE_FAIL, assessment.rationale, assessment.label.value
    return TrustOutcome.PROBE_PASS, assessment.rationale, assessment.label.value


def _markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Trust and Dishonest-Provider Experiment",
        "",
        f"Generated: {result['generated_at']}",
        "",
        f"Rounds: {result['rounds']}; demotion threshold: {result['demotion_threshold']:.2f}.",
        "",
        "The Auditor pushes probe outcomes to a local Beta-style trust ledger using the formula "
        "`(successes + 1) / (successes + failures + 2)`. In production the ledger is Rameen's passive trust registry; "
        "this experiment uses the same TrustUpdate contract.",
        "",
        "## Detection summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Honest providers | {result['honest_providers']} |",
        f"| Malicious/unreliable providers | {result['bad_providers']} |",
        f"| Bad providers demoted | {result['bad_demoted']} |",
        f"| Honest providers incorrectly demoted | {result['honest_demoted']} |",
        f"| Detection precision | {result['detection_precision']:.3f} |",
        f"| Detection recall | {result['detection_recall']:.3f} |",
        f"| Mean rounds until demotion (bad) | {result['mean_rounds_bad']:.2f} |",
        "",
        "## Provider trajectories",
        "",
        "| Provider | Tool | Class | Demoted | Round | Final trust |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for row in result["providers"]:
        provider_class = "bad" if row["malicious"] else "honest"
        lines.append(
            f"| {row['provider_id']} | {row['tool_id']} | {provider_class} | "
            f"{'yes' if row['demoted'] else 'no'} | {row['demotion_round'] or '-'} | {row['final_trust']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The controlled providers make ground truth explicit. Outage, schema corruption and dishonest unit changes "
            "are demoted after repeated failed evidence; honest providers remain trusted. This measures the Auditor's "
            "TrustUpdate feed, not the Client's ranking or substitution policy, which belongs to Rameen's component.",
            "",
            "A limitation is that the local Beta ledger treats one trust outcome per probe round in this experiment. "
            "The production registry may apply different weights to probe, schema, contradiction and rating outcomes.",
            "",
        ]
    )
    return "\n".join(lines)


def run_trust_evaluation(
    output_dir: Path | str | None = None,
    rounds: int = 8,
    demotion_threshold: float = 0.4,
) -> dict[str, Any]:
    output_dir = Path(output_dir) if output_dir else OUTPUTS_DIR
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agent-bazaar-trust-eval-") as temporary:
        base = Path(temporary)
        settings = Settings(
            outputs_dir=base / "outputs",
            cache_dir=base / "cache",
            live=False,
            drift_mode="rule_only",
        )
        auditor = Auditor(settings=settings, persist=False)
        ledger = TrustLedger()
        feed = TrustFeed(ledger=ledger)
        provider_results: list[dict[str, Any]] = []
        for index, spec in enumerate(PROVIDERS):
            tool_id = spec["tool_id"]
            definition = auditor.get_definition(tool_id)
            tool = auditor.get_tool(tool_id)
            claim = tool.claims[spec["claim_index"]]
            provider = MockProvider(
                tool_id=tool_id,
                definition=definition,
                behavior=spec["behavior"],
                options=spec["options"],
                seed=7000 + index,
            )
            auditor.harness.set_provider(tool_id, provider)
            trajectory: list[dict[str, Any]] = []
            demotion_round: int | None = None
            for round_number in range(1, rounds + 1):
                outcome, reason, label = _round_outcome(auditor, provider, claim, definition)
                update = TrustUpdate(
                    sender="auditor",
                    correlation_id=spec["provider_id"],
                    tool_id=spec["provider_id"],
                    outcome=outcome,
                    reason=reason,
                    claim_id=claim.id,
                    value=1.0 if outcome is TrustOutcome.PROBE_PASS else 0.0,
                )
                feed.send(update)
                score = ledger.score(spec["provider_id"])
                trajectory.append(
                    {
                        "round": round_number,
                        "outcome": outcome.value,
                        "claim_label": label,
                        "score": round(score, 6),
                    }
                )
                if demotion_round is None and score < demotion_threshold:
                    demotion_round = round_number
            auditor.harness.remove_provider(tool_id)
            provider_results.append(
                {
                    "provider_id": spec["provider_id"],
                    "tool_id": tool_id,
                    "behavior": spec["behavior"],
                    "malicious": bool(spec["malicious"]),
                    "demoted": demotion_round is not None,
                    "demotion_round": demotion_round,
                    "final_trust": round(ledger.score(spec["provider_id"]), 6),
                    "trajectory": trajectory,
                }
            )
        honest = [row for row in provider_results if not row["malicious"]]
        bad = [row for row in provider_results if row["malicious"]]
        demoted = [row for row in provider_results if row["demoted"]]
        bad_demoted = [row for row in bad if row["demoted"]]
        honest_demoted = [row for row in honest if row["demoted"]]
        precision = len(bad_demoted) / max(1, len(demoted))
        recall = len(bad_demoted) / max(1, len(bad))
        mean_rounds = sum(row["demotion_round"] for row in bad_demoted if row["demotion_round"]) / max(1, len(bad_demoted))
        result = {
            "schema_version": 1,
            "generated_at": utc_now(),
            "rounds": rounds,
            "demotion_threshold": demotion_threshold,
            "honest_providers": len(honest),
            "bad_providers": len(bad),
            "bad_demoted": len(bad_demoted),
            "honest_demoted": len(honest_demoted),
            "detection_precision": round(precision, 4),
            "detection_recall": round(recall, 4),
            "mean_rounds_bad": round(mean_rounds, 4),
            "trust_formula": "(successes + 1) / (successes + failures + 2)",
            "feed_summary": feed.summary(),
            "providers": provider_results,
            "artifacts": {
                "json": str(reports_dir / "trust_evaluation.json"),
                "markdown": str(reports_dir / "trust_evaluation.md"),
            },
        }
        atomic_write_json(reports_dir / "trust_evaluation.json", result)
        (reports_dir / "trust_evaluation.md").write_text(_markdown_report(result), encoding="utf-8")
        return result
