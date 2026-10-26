from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

LABELS = ["Verified", "Supported", "Contradicted", "Unsupported"]


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def confusion_matrix(truth: Iterable[str], predicted: Iterable[str], labels: list[str] | None = None) -> dict[str, dict[str, int]]:
    labels = labels or LABELS
    matrix = {label: {inner: 0 for inner in labels} for label in labels}
    for expected, actual in zip(truth, predicted, strict=False):
        if expected not in matrix:
            matrix[expected] = {inner: 0 for inner in labels}
        if actual not in matrix[expected]:
            matrix[expected][actual] = 0
        matrix[expected][actual] += 1
    return matrix


def compute_classification_metrics(
    truth: list[str],
    predicted: list[str],
    labels: list[str] | None = None,
) -> dict[str, Any]:
    labels = labels or LABELS
    if len(truth) != len(predicted):
        raise ValueError("truth and predicted must have the same length")
    matrix = confusion_matrix(truth, predicted, labels)
    per_label: dict[str, dict[str, float]] = {}
    total = len(truth)
    correct = sum(1 for expected, actual in zip(truth, predicted, strict=False) if expected == actual)
    for label in labels:
        true_positive = sum(1 for expected, actual in zip(truth, predicted, strict=False) if expected == label and actual == label)
        false_positive = sum(1 for expected, actual in zip(truth, predicted, strict=False) if expected != label and actual == label)
        false_negative = sum(1 for expected, actual in zip(truth, predicted, strict=False) if expected == label and actual != label)
        support = sum(1 for expected in truth if expected == label)
        precision = _safe_divide(true_positive, true_positive + false_positive)
        recall = _safe_divide(true_positive, true_positive + false_negative)
        f1 = _safe_divide(2.0 * precision * recall, precision + recall)
        per_label[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        }
    macro_f1 = sum(per_label[label]["f1"] for label in labels) / len(labels)
    weighted_f1 = sum(per_label[label]["f1"] * per_label[label]["support"] for label in labels) / max(1, total)
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(_safe_divide(correct, total), 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "per_label": per_label,
        "confusion_matrix": matrix,
        "label_counts": dict(Counter(truth)),
    }


def markdown_metrics_table(metrics: dict[str, Any]) -> str:
    lines = [
        "| Label | Precision | Recall | F1 | Support | TP | FP | FN |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, row in metrics["per_label"].items():
        lines.append(
            f"| {label} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} | "
            f"{row['support']} | {row['true_positive']} | {row['false_positive']} | {row['false_negative']} |"
        )
    lines.append("")
    lines.append(
        f"Accuracy: **{metrics['accuracy']:.3f}** ({metrics['correct']}/{metrics['total']}); "
        f"macro F1: **{metrics['macro_f1']:.3f}**; weighted F1: **{metrics['weighted_f1']:.3f}**."
    )
    return "\n".join(lines)


def markdown_confusion(metrics: dict[str, Any]) -> str:
    labels = list(metrics["confusion_matrix"].keys())
    lines = ["| Expected \\ Predicted | " + " | ".join(labels) + " |", "| --- | " + " | ".join("---:" for _ in labels) + " |"]
    for expected in labels:
        row = metrics["confusion_matrix"][expected]
        lines.append(f"| {expected} | " + " | ".join(str(row.get(actual, 0)) for actual in labels) + " |")
    return "\n".join(lines)


def latency_summary(milliseconds: list[float]) -> dict[str, float]:
    if not milliseconds:
        return {"count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(milliseconds)
    count = len(ordered)
    p50 = ordered[int(0.5 * (count - 1))]
    p95 = ordered[int(0.95 * (count - 1))]
    return {
        "count": count,
        "mean_ms": round(sum(ordered) / count, 3),
        "p50_ms": round(p50, 3),
        "p95_ms": round(p95, 3),
        "max_ms": round(ordered[-1], 3),
    }
