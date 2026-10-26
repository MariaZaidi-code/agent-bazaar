from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from ..auditor import Auditor
from ..claims import Claim
from ..config import Settings
from ..mocks.provider import MockProvider
from ..paths import DATA_DIR, OUTPUTS_DIR
from ..probes.models import validate_payload
from ..utils import atomic_write_json, percentage, utc_now
from .metrics import compute_classification_metrics, latency_summary, markdown_confusion, markdown_metrics_table


def _subset_metrics(details: list[dict[str, Any]], predicate) -> dict[str, Any]:
    rows = [row for row in details if predicate(row)]
    return compute_classification_metrics(
        [row["expected_label"] for row in rows],
        [row["predicted_label"] for row in rows],
    )


def _markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Claim Verification Evaluation",
        "",
        f"Generated: {result['generated_at']}",
        "",
        f"Dataset: `{result['dataset']}`",
        "",
        "This evaluation uses the frozen documentation in the dataset, the Auditor evidence judge, deterministic probe checks and the fixed decision table. "
        "Outage items provide probe-error evidence. Seeded claims measure detection ability, not real-world prevalence.",
        "",
        "## Dataset counts",
        "",
        "| Label | Count |",
        "| --- | ---: |",
    ]
    for label, count in result["dataset_counts"].items():
        lines.append(f"| {label} | {count} |")
    lines.extend(
        [
            "",
            "## Overall metrics",
            "",
            markdown_metrics_table(result["metrics"]),
            "",
            "## Confusion matrix",
            "",
            markdown_confusion(result["metrics"]),
            "",
            "## Real and seeded subsets",
            "",
            f"**Real claims:** accuracy {result['subsets']['real']['accuracy']:.3f}, "
            f"macro F1 {result['subsets']['real']['macro_f1']:.3f} ({result['subsets']['real']['total']} items).",
            "",
            f"**Seeded claims:** accuracy {result['subsets']['seeded']['accuracy']:.3f}, "
            f"macro F1 {result['subsets']['seeded']['macro_f1']:.3f} ({result['subsets']['seeded']['total']} items).",
            "",
            "## Probe coverage",
            "",
            f"- Total claims: {result['coverage']['total_claims']}",
            f"- Probeable claims: {result['coverage']['probeable_claims']}",
            f"- Probed claims: {result['coverage']['probed_claims']}",
            f"- Coverage of all claims: {result['coverage']['coverage_percent']:.2f}%",
            f"- Coverage of probeable claims: {result['coverage']['probeable_coverage_percent']:.2f}%",
            f"- Probe sources: {result['coverage']['probe_sources']}",
            "",
            "## Cost",
            "",
            f"- Mean time per claim (probe + assess): {result['cost']['mean_ms']:.3f} ms",
            f"- p95 time per claim: {result['cost']['p95_ms']:.3f} ms",
            f"- Token use in offline mode: {result['cost']['total_tokens']} tokens "
            "(LLM mode records tokens through the cached LLM client).",
            "",
            "## Per-label results",
            "",
        ]
    )
    for label, row in result["metrics"]["per_label"].items():
        lines.append(
            f"- **{label}**: precision {row['precision']:.3f}, recall {row['recall']:.3f}, "
            f"F1 {row['f1']:.3f}, support {row['support']}."
        )
    lines.extend(["", "## Mismatches", ""])
    if result["mismatches"]:
        for item in result["mismatches"]:
            lines.append(
                f"- `{item['id']}` ({item['tool_id']}): expected **{item['expected_label']}**, "
                f"predicted **{item['predicted_label']}** — {item['claim']}"
            )
    else:
        lines.append("No mismatches on this dataset.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The controlled dataset is designed to exercise all four labels, including subtle wrong-unit, wrong-limit, "
            "wrong-type, false-authentication and missing-field claims. A perfect score on this set shows that the "
            "decision procedure matches the curated ground truth; it does not estimate how often providers lie in the wild.",
            "",
        ]
    )
    return "\n".join(lines)


def run_claim_evaluation(
    dataset_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    auditor: Auditor | None = None,
    report_name: str = "claim_evaluation",
) -> dict[str, Any]:
    dataset_path = Path(dataset_path) if dataset_path else DATA_DIR / "seeded_claims.json"
    output_dir = Path(output_dir) if output_dir else OUTPUTS_DIR
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if auditor is None:
        temporary = tempfile.TemporaryDirectory(prefix="agent-bazaar-claim-eval-")
        settings = Settings(
            outputs_dir=Path(temporary.name) / "outputs",
            cache_dir=Path(temporary.name) / "cache",
            live=False,
            drift_mode="rule_only",
        )
        auditor = Auditor(settings=settings, persist=False)
    else:
        temporary = None
    try:
        details: list[dict[str, Any]] = []
        latencies: list[float] = []
        sources: dict[str, int] = {}
        probeable = 0
        probed = 0
        for index, item in enumerate(dataset["items"]):
            tool_id = item["tool_id"]
            tool = auditor.get_tool(tool_id)
            definition = auditor.get_definition(tool_id)
            claim = Claim.from_dict(item["claim"])
            documentation = item.get("documentation")
            behavior = item.get("mock_behavior", "normal")
            options = item.get("mock_options") or {}
            provider = MockProvider(
                tool_id=tool_id,
                definition=definition,
                behavior=behavior,
                options=options,
                seed=1000 + index,
                documentation=tool.documentation,
            )
            auditor.harness.set_provider(tool_id, provider)
            started = time.perf_counter()
            probe = auditor.harness.probe(tool_id)
            validation = validate_payload(definition, probe.payload) if probe.payload is not None else None
            assessment = auditor.assess_claim(
                claim,
                probe=probe,
                validation=validation,
                documentation=documentation,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            auditor.harness.remove_provider(tool_id)
            claim_probeable = claim.probeable and definition.probeable
            probeable += 1 if claim_probeable else 0
            probed += 1 if assessment.probed else 0
            if assessment.probed:
                sources[probe.source.value] = sources.get(probe.source.value, 0) + 1
            expected_label = item["ground_truth_label"]
            predicted_label = assessment.label.value
            latencies.append(elapsed_ms)
            details.append(
                {
                    "id": item["id"],
                    "tool_id": tool_id,
                    "claim_id": claim.id,
                    "claim": claim.text,
                    "focus": item.get("focus", "real"),
                    "seeded": bool(item.get("seeded", False)),
                    "expected_label": expected_label,
                    "predicted_label": predicted_label,
                    "correct": expected_label == predicted_label,
                    "doc_stance": assessment.doc_stance.value,
                    "probe_outcome": assessment.probe_outcome.value,
                    "probe_source": assessment.probe_source,
                    "probe_status_code": assessment.probe_status_code,
                    "probe_checks": assessment.probe_checks,
                    "rationale": assessment.rationale,
                    "elapsed_ms": round(elapsed_ms, 3),
                }
            )
        truth = [row["expected_label"] for row in details]
        predicted = [row["predicted_label"] for row in details]
        metrics = compute_classification_metrics(truth, predicted)
        subsets = {
            "real": _subset_metrics(details, lambda row: not row["seeded"]),
            "seeded": _subset_metrics(details, lambda row: row["seeded"]),
        }
        mismatches = [row for row in details if not row["correct"]]
        result = {
            "schema_version": 1,
            "generated_at": utc_now(),
            "dataset": str(dataset_path),
            "dataset_name": dataset.get("name", ""),
            "dataset_version": dataset.get("version", ""),
            "dataset_notes": dataset.get("notes", []),
            "dataset_counts": dataset.get("counts", {}),
            "metrics": metrics,
            "subsets": subsets,
            "coverage": {
                "total_claims": len(details),
                "probeable_claims": probeable,
                "probed_claims": probed,
                "coverage_percent": percentage(probed, len(details)),
                "probeable_coverage_percent": percentage(probed, probeable),
                "probe_sources": sources,
            },
            "cost": {
                **latency_summary(latencies),
                "total_tokens": 0,
                "llm_mode": "offline-heuristic",
            },
            "mismatches": mismatches,
            "details": details,
        }
        result["artifacts"] = {
            "json": str(reports_dir / f"{report_name}.json"),
            "markdown": str(reports_dir / f"{report_name}.md"),
        }
        atomic_write_json(reports_dir / f"{report_name}.json", result)
        (reports_dir / f"{report_name}.md").write_text(_markdown_report(result), encoding="utf-8")
        return result
    finally:
        if temporary is not None:
            temporary.cleanup()
