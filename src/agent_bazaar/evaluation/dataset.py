"""Labelled field-mapping dataset helpers for offline evaluation."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agent_bazaar.ingestion.models import flatten_fields
from agent_bazaar.kg.loader import load_normalized_specs
from agent_bazaar.messages.schema import FieldSpec


class MappingExample(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    tool_id: str
    field_name: str
    field_type: str = "string"
    field_description: str = ""
    sample_value: Any = None
    gold_concept: str = ""
    gold_unit: str | None = None
    split: Literal["dev", "test", "unlabelled"] = "unlabelled"
    source: str = ""
    prelabel: str = ""
    prelabel_confidence: float | None = None


def load_dataset(path: str | Path) -> list[MappingExample]:
    target = Path(path)
    if not target.exists():
        return []
    examples: list[MappingExample] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        examples.append(MappingExample.model_validate_json(stripped))
    return examples


def save_dataset(examples: list[MappingExample], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [example.model_dump_json() for example in examples]
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


def to_field_spec(example: MappingExample) -> FieldSpec:
    return FieldSpec(
        field_path=example.id,
        name=example.field_name,
        type=example.field_type,
        description=example.field_description,
        sample_value=example.sample_value,
        direction="output",
    )


def _expected_agreement(labels_a: list[str], labels_b: list[str]) -> float:
    n = len(labels_a)
    if n == 0:
        return 0.0
    counts_a = Counter(labels_a)
    counts_b = Counter(labels_b)
    return sum((counts_a[label] / n) * (counts_b[label] / n) for label in counts_a.keys() | counts_b.keys())


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    if len(labels_a) != len(labels_b):
        raise ValueError("label lists must have equal length")
    n = len(labels_a)
    if n == 0:
        return 0.0
    observed = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b) / n
    expected = _expected_agreement(labels_a, labels_b)
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def agreement_report(pairs: list[tuple[str, str]]) -> dict[str, float | int]:
    n = len(pairs)
    if n == 0:
        return {"n": 0, "agreements": 0, "observed": 0.0, "expected": 0.0, "kappa": 0.0}
    labels_a = [pair[0] for pair in pairs]
    labels_b = [pair[1] for pair in pairs]
    agreements = sum(1 for a, b in pairs if a == b)
    observed = agreements / n
    expected = _expected_agreement(labels_a, labels_b)
    if expected >= 1.0:
        kappa = 1.0 if observed >= 1.0 else 0.0
    else:
        kappa = (observed - expected) / (1.0 - expected)
    return {"n": n, "agreements": agreements, "observed": observed, "expected": expected, "kappa": kappa}


def export_unlabelled(specs_dir: str | Path, out_path: str | Path) -> Path:
    examples: list[MappingExample] = []
    for spec in load_normalized_specs(specs_dir):
        for field in flatten_fields(spec):
            parts = [part for part in re.split(r"[./]", field.path) if part]
            field_name = parts[-1] if parts else field.path
            examples.append(
                MappingExample(
                    id=f"{spec.tool_id}:{field.path}",
                    tool_id=spec.tool_id,
                    field_name=field_name,
                    field_type=field.type,
                    field_description=field.description,
                    sample_value=field.sample_value,
                    split="unlabelled",
                    source=spec.source,
                )
            )
    return save_dataset(examples, out_path)


def apply_prelabels(
    examples: list[MappingExample], prelabel_fn: Callable[[MappingExample], str]
) -> list[MappingExample]:
    updated: list[MappingExample] = []
    for example in examples:
        if example.split == "unlabelled":
            updated.append(example.model_copy(update={"prelabel": prelabel_fn(example)}))
        else:
            updated.append(example.model_copy())
    return updated
