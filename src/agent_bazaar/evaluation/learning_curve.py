"""Learning-curve, ablation and drift evaluation helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from agent_bazaar.evaluation.dataset import MappingExample, to_field_spec
from agent_bazaar.evaluation.metrics import AccuracyReport, compute_accuracy, format_markdown_table
from agent_bazaar.messages.schema import CorrectionSubmit, MapRequest, new_message


class LearningCurveResult(BaseModel):
    counts: list[int]
    accuracy: list[float]
    f1: list[float]
    n_evaluated: int


def _local_name(label: str) -> str:
    if "#" in label:
        return label.split("#", 1)[1]
    return label


def _attr(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _mapping_name(mapping: Any) -> str:
    name = _attr(mapping, "name", "")
    if name:
        return str(name)
    path = str(_attr(mapping, "field_path", ""))
    parts = [part for part in path.replace("/", ".").split(".") if part]
    return parts[-1] if parts else path


def run_learning_curve(
    mapper: Any,
    examples: list[MappingExample],
    corrections: list[MappingExample],
    counts: tuple[int, ...] = (0, 5, 10, 20),
    reset: Callable[[], None] | None = None,
    map_batch_size: int = 100,
) -> LearningCurveResult:
    """Measure held-out accuracy after increasing numbers of corrections.

    ``examples`` are the held-out evaluation fields and must not include the
    corrections' own fields; any example whose id matches a correction id is
    excluded so the curve never evaluates a field it has just been taught.
    """
    correction_ids = {correction.id for correction in corrections}
    held_out = [example for example in examples if example.id not in correction_ids]
    field_specs = [to_field_spec(example) for example in held_out]
    gold_labels = [_local_name(example.gold_concept) for example in held_out]
    batch_size = max(1, map_batch_size)
    recorded_counts: list[int] = []
    accuracy: list[float] = []
    f1: list[float] = []
    for count in counts:
        if reset is not None:
            reset()
        for correction in corrections[: max(0, count)]:
            mapper.submit_correction(
                new_message(
                    CorrectionSubmit,
                    tool_id=correction.tool_id or "evaluation",
                    field_path=correction.id,
                    corrected_concept=correction.gold_concept,
                    corrected_unit=correction.gold_unit,
                    note="learning-curve",
                    submitted_by="evaluation",
                )
            )
        mappings: list[Any] = []
        for start in range(0, len(field_specs), batch_size):
            batch = field_specs[start : start + batch_size]
            if not batch:
                continue
            response = mapper.map_fields(new_message(MapRequest, tool_id="evaluation", fields=batch))
            mappings.extend(_attr(response, "mappings", []) or [])
        by_path: dict[str, Any] = {}
        by_name: dict[str, Any] = {}
        for mapping in mappings:
            by_path.setdefault(str(_attr(mapping, "field_path", "")), mapping)
            by_name.setdefault(_mapping_name(mapping), mapping)
        predicted: list[str] = []
        for example in held_out:
            mapping = by_path.get(example.id) or by_name.get(example.field_name)
            concept = _attr(mapping, "concept", "") if mapping is not None else ""
            predicted.append(_local_name(str(concept or "")))
        report = compute_accuracy(predicted, gold_labels)
        recorded_counts.append(count)
        accuracy.append(report.accuracy)
        f1.append(report.macro_f1)
    return LearningCurveResult(
        counts=recorded_counts,
        accuracy=accuracy,
        f1=f1,
        n_evaluated=len(held_out),
    )


def curve_to_markdown(result: LearningCurveResult) -> str:
    rows = [
        [count, f"{accuracy:.3f}", f"{f1:.3f}"]
        for count, accuracy, f1 in zip(result.counts, result.accuracy, result.f1, strict=True)
    ]
    return format_markdown_table(["Corrections", "Accuracy", "Macro F1"], rows)


def ablation_table(results: dict[str, AccuracyReport]) -> str:
    rows = [
        [name, report.n, f"{report.accuracy:.3f}", f"{report.macro_f1:.3f}", f"{report.micro_f1:.3f}"]
        for name, report in results.items()
    ]
    return format_markdown_table(["Variant", "n", "Accuracy", "Macro F1", "Micro F1"], rows)


def drift_accuracy(ground_truth: list[str], remapped: list[str]) -> AccuracyReport:
    return compute_accuracy(remapped, ground_truth)
