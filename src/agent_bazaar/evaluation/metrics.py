"""Accuracy, agreement-group and cost metrics for mapping evaluation."""

from __future__ import annotations

import math
import re
import statistics
from collections import Counter
from typing import Any

from pydantic import BaseModel

_UNMAPPED = "unmapped"


class AccuracyReport(BaseModel):
    n: int
    correct: int
    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    labels: list[str]


def normalize_label(label: str) -> str:
    cleaned = (label or "").strip()
    if cleaned.lower() in {"", _UNMAPPED}:
        return _UNMAPPED
    return cleaned


def compute_accuracy(predicted: list[str], gold: list[str]) -> AccuracyReport:
    if len(predicted) != len(gold):
        raise ValueError("predicted and gold must have equal length")
    normalized_predicted = [normalize_label(label) for label in predicted]
    normalized_gold = [normalize_label(label) for label in gold]
    n = len(normalized_gold)
    if n == 0:
        return AccuracyReport(
            n=0,
            correct=0,
            accuracy=0.0,
            macro_precision=0.0,
            macro_recall=0.0,
            macro_f1=0.0,
            micro_precision=0.0,
            micro_recall=0.0,
            micro_f1=0.0,
            labels=[],
        )
    correct = sum(1 for p, g in zip(normalized_predicted, normalized_gold) if p == g)
    labels = sorted(set(normalized_predicted) | set(normalized_gold))
    precisions: list[float] = []
    recalls: list[float] = []
    f1_scores: list[float] = []
    for label in labels:
        true_positives = sum(
            1 for p, g in zip(normalized_predicted, normalized_gold) if p == label and g == label
        )
        predicted_count = sum(1 for p in normalized_predicted if p == label)
        gold_count = sum(1 for g in normalized_gold if g == label)
        precision = true_positives / predicted_count if predicted_count else 0.0
        recall = true_positives / gold_count if gold_count else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        precisions.append(precision)
        recalls.append(recall)
        f1_scores.append(f1)
    accuracy = correct / n
    return AccuracyReport(
        n=n,
        correct=correct,
        accuracy=accuracy,
        macro_precision=sum(precisions) / len(labels),
        macro_recall=sum(recalls) / len(labels),
        macro_f1=sum(f1_scores) / len(labels),
        micro_precision=accuracy,
        micro_recall=accuracy,
        micro_f1=accuracy,
        labels=labels,
    )


def confusion_pairs(predicted: list[str], gold: list[str]) -> list[tuple[str, str, int]]:
    if len(predicted) != len(gold):
        raise ValueError("predicted and gold must have equal length")
    counts: Counter[tuple[str, str]] = Counter()
    for prediction, target in zip(predicted, gold):
        normalized_prediction = normalize_label(prediction)
        normalized_gold = normalize_label(target)
        if normalized_prediction != normalized_gold:
            counts[(normalized_prediction, normalized_gold)] += 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    return [(prediction, target, count) for (prediction, target), count in ordered]


def latency_stats(values_ms: list[float]) -> dict[str, float | int]:
    if not values_ms:
        return {"count": 0, "mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(values_ms)
    count = len(ordered)
    index = max(0, math.ceil(0.95 * count) - 1)
    return {
        "count": count,
        "mean": sum(ordered) / count,
        "median": float(statistics.median(ordered)),
        "p95": float(ordered[index]),
        "max": float(ordered[-1]),
    }


def token_stats(prompt_tokens: int, completion_tokens: int, calls: int) -> dict[str, float | int]:
    total = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total,
        "calls": calls,
        "avg_prompt_tokens": prompt_tokens / calls if calls > 0 else 0.0,
        "avg_completion_tokens": completion_tokens / calls if calls > 0 else 0.0,
        "avg_total_tokens": total / calls if calls > 0 else 0.0,
    }


def surface_accuracy_by_group(
    predicted: list[str], gold: list[str], groups: list[str]
) -> dict[str, AccuracyReport]:
    if not (len(predicted) == len(gold) == len(groups)):
        raise ValueError("predicted, gold and groups must have equal length")
    grouped: dict[str, list[tuple[str, str]]] = {}
    for prediction, target, group in zip(predicted, gold, groups):
        grouped.setdefault(group, []).append((prediction, target))
    return {
        group: compute_accuracy([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        for group, pairs in sorted(grouped.items())
    }


def format_markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    header = "| " + " | ".join(str(item) for item in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(item) for item in row) + " |" for row in rows]
    return "\n".join([header, separator, *body])


_DOMAIN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "geo",
        (
            "position",
            "latitude",
            "longitude",
            "city",
            "country",
            "address",
            "region",
            "postal",
            "place",
            "timezone",
            "elevation",
        ),
    ),
    (
        "weather",
        (
            "temperature",
            "weather",
            "wind",
            "humidity",
            "precip",
            "pressure",
            "cloud",
            "uv",
            "visibility",
            "forecast",
            "dew",
            "sunrise",
            "sunset",
        ),
    ),
    (
        "currency",
        (
            "currency",
            "exchange",
            "rate",
            "money",
            "amount",
            "base",
            "quote",
        ),
    ),
    (
        "reference",
        (
            "holiday",
            "population",
            "area",
            "language",
            "capital",
            "date",
            "time",
            "name",
            "description",
            "identifier",
            "count",
            "rank",
            "rating",
            "url",
            "email",
            "phone",
            "boolean",
        ),
    ),
)


def _local_tokens(concept: str) -> list[str]:
    local = re.split(r"[#/:]", concept or "")[-1]
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", local)
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", spaced) if token]


def domain_of_concept(concept: str) -> str:
    tokens = _local_tokens(concept)
    compact = "".join(tokens)
    for domain, keywords in _DOMAIN_KEYWORDS:
        for keyword in keywords:
            if any(
                token == keyword or (len(keyword) >= 5 and token.startswith(keyword))
                for token in tokens
            ):
                return domain
            if len(keyword) >= 5 and keyword in compact:
                return domain
    return "other"
