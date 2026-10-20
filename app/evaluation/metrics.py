from __future__ import annotations

from collections.abc import Iterable


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return round(sum(items) / len(items), 4) if items else 0.0


def ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def reciprocal_rank(rank: int | None) -> float:
    return round(1.0 / rank, 4) if rank else 0.0


def rank_of(items: list[str], target: str) -> int | None:
    try:
        return items.index(target) + 1
    except ValueError:
        return None


def percentage(value: float) -> float:
    return round(value * 100.0, 2)


def distribution(values: Iterable[float]) -> dict[str, float]:
    items = sorted(float(value) for value in values)
    if not items:
        return {"min": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0, "mean": 0.0}
    return {
        "min": round(items[0], 3),
        "p50": round(items[len(items) // 2], 3),
        "p95": round(items[min(len(items) - 1, int(len(items) * 0.95))], 3),
        "max": round(items[-1], 3),
        "mean": mean(items),
    }
