"""Tests for the mapping evaluation harness."""

from __future__ import annotations

from typing import Any

import pytest

from agent_bazaar.evaluation.dataset import (
    MappingExample,
    agreement_report,
    apply_prelabels,
    cohen_kappa,
    export_unlabelled,
    load_dataset,
    save_dataset,
    to_field_spec,
)
from agent_bazaar.evaluation.learning_curve import (
    ablation_table,
    curve_to_markdown,
    drift_accuracy,
    run_learning_curve,
)
from agent_bazaar.evaluation.metrics import (
    compute_accuracy,
    confusion_pairs,
    domain_of_concept,
    latency_stats,
    surface_accuracy_by_group,
    token_stats,
)
from agent_bazaar.ingestion.models import EndpointInfo, FieldInfo, NormalizedSpec
from agent_bazaar.messages.schema import FieldMapping, MapResult, new_message
from agent_bazaar.protocols import MapperService

EVAL_TARGETS = {
    f"field_{index}": f"http://example.org/ontology#Concept{index}" for index in range(10)
}


class FakeMapper:
    def __init__(self) -> None:
        self.learned: set[str] = set()
        self.reset_calls = 0
        self.submitted: list[str] = []

    def map_fields(self, request: Any) -> Any:
        mappings: list[FieldMapping] = []
        for spec in request.fields:
            target = EVAL_TARGETS.get(spec.name, "")
            concept = target if target in self.learned else ""
            mappings.append(FieldMapping(field_path=spec.field_path, concept=concept))
        return new_message(MapResult, tool_id=request.tool_id, mappings=mappings)

    def submit_correction(self, correction: Any) -> dict[str, str]:
        self.learned.add(correction.corrected_concept)
        self.submitted.append(correction.field_path)
        return {"status": "promoted"}

    def handle_drift_alert(self, alert: Any) -> dict[str, str]:
        return {"status": "acknowledged"}

    def reindex(self) -> None:
        return None

    def reset(self) -> None:
        self.learned.clear()
        self.reset_calls += 1


def test_accuracy_hand_computed() -> None:
    predicted = ["geo:latitude", "geo:city", "weather:temperature", ""]
    gold = ["geo:latitude", "geo:city", "geo:city", "weather:temperature"]
    report = compute_accuracy(predicted, gold)
    assert report.n == 4
    assert report.correct == 2
    assert report.accuracy == 0.5
    assert report.macro_precision == 0.5
    assert report.macro_recall == 0.375
    assert report.macro_f1 == pytest.approx(0.41666666666666663)
    assert report.micro_precision == 0.5
    assert report.micro_recall == 0.5
    assert report.micro_f1 == 0.5
    assert report.labels == ["geo:city", "geo:latitude", "unmapped", "weather:temperature"]


def test_micro_and_macro_differ_when_class_sizes_differ() -> None:
    predicted = ["a", "a", "b"]
    gold = ["a", "b", "c"]
    report = compute_accuracy(predicted, gold)
    assert report.accuracy == pytest.approx(1 / 3)
    assert report.micro_f1 == pytest.approx(1 / 3)
    assert report.macro_f1 == pytest.approx(2 / 9)
    assert report.micro_f1 != report.macro_f1


def test_accuracy_normalizes_unmapped_variants() -> None:
    report = compute_accuracy(["UNMAPPED", " unmapped ", ""], ["", "unmapped", "UnMapped"])
    assert report.accuracy == 1.0
    assert report.labels == ["unmapped"]


def test_confusion_pairs_sorted_and_normalized() -> None:
    predicted = ["geo:latitude", "geo:city", "weather:temperature", "", "UNMAPPED", "b"]
    gold = ["geo:latitude", "geo:city", "geo:city", "weather:temperature", "", "a"]
    pairs = confusion_pairs(predicted, gold)
    assert pairs == [
        ("b", "a", 1),
        ("unmapped", "weather:temperature", 1),
        ("weather:temperature", "geo:city", 1),
    ]


def test_latency_and_token_stats() -> None:
    assert latency_stats([10, 20, 30, 40]) == {
        "count": 4,
        "mean": 25.0,
        "median": 25.0,
        "p95": 40.0,
        "max": 40.0,
    }
    assert latency_stats([]) == {"count": 0, "mean": 0.0, "median": 0.0, "p95": 0.0, "max": 0.0}
    stats = token_stats(100, 50, 5)
    assert stats["total_tokens"] == 150
    assert stats["avg_prompt_tokens"] == 20.0
    assert stats["avg_completion_tokens"] == 10.0
    assert stats["avg_total_tokens"] == 30.0
    empty = token_stats(0, 0, 0)
    assert empty["total_tokens"] == 0
    assert empty["avg_total_tokens"] == 0.0


def test_surface_accuracy_by_group() -> None:
    predicted = ["a", "b", "a", "c"]
    gold = ["a", "b", "b", "c"]
    grouped = surface_accuracy_by_group(predicted, gold, ["geo", "geo", "weather", "weather"])
    assert set(grouped) == {"geo", "weather"}
    assert grouped["geo"].accuracy == 1.0
    assert grouped["weather"].accuracy == 0.5


def test_domain_of_concept() -> None:
    assert domain_of_concept("http://example.org/geo#latitude") == "geo"
    assert domain_of_concept("http://example.org/weather#temperature_2m") == "weather"
    assert domain_of_concept("ex:exchange_rate") == "currency"
    assert domain_of_concept("http://example.org/reference#population") == "reference"
    assert domain_of_concept("ex:timeZone") == "geo"
    assert domain_of_concept("ex:mystery") == "other"


def test_cohen_kappa_perfect_agreement() -> None:
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert cohen_kappa(["a", "a", "a"], ["a", "a", "a"]) == 1.0


def test_cohen_kappa_zero_agreement_balanced_marginals() -> None:
    kappa = cohen_kappa(["a", "b", "a", "b"], ["b", "a", "b", "a"])
    assert kappa < 0.1
    assert kappa == pytest.approx(-1.0)


def test_cohen_kappa_empty() -> None:
    assert cohen_kappa([], []) == 0.0
    assert agreement_report([]) == {
        "n": 0,
        "agreements": 0,
        "observed": 0.0,
        "expected": 0.0,
        "kappa": 0.0,
    }


def test_agreement_report() -> None:
    report = agreement_report([("a", "a"), ("b", "b"), ("a", "b"), ("b", "a")])
    assert report["n"] == 4
    assert report["agreements"] == 2
    assert report["observed"] == 0.5
    assert report["expected"] == 0.5
    assert report["kappa"] == pytest.approx(0.0)


def test_dataset_jsonl_roundtrip(tmp_path: Any) -> None:
    examples = [
        MappingExample(
            id="weather:temperature_2m",
            tool_id="weather",
            field_name="temperature_2m",
            field_type="float",
            field_description="Air temperature",
            sample_value=21.5,
            gold_concept="http://example.org/ontology#Temperature",
            gold_unit="degC",
            split="test",
            source="openapi",
            prelabel="ex:Temperature",
            prelabel_confidence=0.8,
        ),
        MappingExample(
            id="geo:latitude",
            tool_id="geo",
            field_name="latitude",
            field_type="float",
            sample_value=48.1,
            split="dev",
        ),
    ]
    path = tmp_path / "nested" / "dataset.jsonl"
    saved = save_dataset(examples, path)
    assert saved == path
    path.write_text("\n" + path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    assert load_dataset(path) == examples


def test_to_field_spec() -> None:
    example = MappingExample(
        id="weather:temperature_2m",
        tool_id="weather",
        field_name="temperature_2m",
        field_type="float",
        field_description="Air temperature",
        sample_value=21.5,
    )
    spec = to_field_spec(example)
    assert spec.field_path == example.id
    assert spec.name == example.field_name
    assert spec.type == example.field_type
    assert spec.description == example.field_description
    assert spec.sample_value == example.sample_value
    assert spec.direction == "output"


def test_export_unlabelled(tmp_path: Any) -> None:
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    spec = NormalizedSpec(
        tool_id="weather_api",
        source="openapi",
        spec_format="openapi_json",
        endpoints=[
            EndpointInfo(
                path="/v1/weather",
                method="GET",
                response_fields=[
                    FieldInfo(
                        path="temperature_2m",
                        name="temperature_2m",
                        type="float",
                        description="Air temperature",
                    )
                ],
            ),
            EndpointInfo(
                path="/v1/geo",
                method="GET",
                response_fields=[
                    FieldInfo(
                        path="latitude",
                        name="latitude",
                        type="float",
                        description="Latitude",
                    )
                ],
            ),
        ],
    )
    (specs_dir / "weather.json").write_text(spec.model_dump_json(), encoding="utf-8")
    out_path = tmp_path / "unlabelled.jsonl"
    result = export_unlabelled(specs_dir, out_path)
    assert result == out_path
    examples = load_dataset(out_path)
    assert len(examples) == 2
    assert {example.id for example in examples} == {
        "weather_api:output.get:/v1/weather.temperature_2m",
        "weather_api:output.get:/v1/geo.latitude",
    }
    assert {example.field_name for example in examples} == {"temperature_2m", "latitude"}
    assert all(example.split == "unlabelled" for example in examples)
    assert all(example.tool_id == "weather_api" for example in examples)
    assert all(example.source == "openapi" for example in examples)


def test_apply_prelabels_only_touches_unlabelled() -> None:
    examples = [
        MappingExample(id="u1", tool_id="t", field_name="f1", split="unlabelled"),
        MappingExample(
            id="g1",
            tool_id="t",
            field_name="f2",
            split="test",
            gold_concept="ex:Gold",
            prelabel="ex:Existing",
        ),
    ]
    calls: list[str] = []

    def prelabel_fn(example: MappingExample) -> str:
        calls.append(example.id)
        return "ex:Suggested"

    updated = apply_prelabels(examples, prelabel_fn)
    assert calls == ["u1"]
    assert updated[0].prelabel == "ex:Suggested"
    assert updated[0].gold_concept == ""
    assert updated[1].prelabel == "ex:Existing"
    assert updated[1].gold_concept == "ex:Gold"
    assert examples[0].prelabel == ""


def test_learning_curve_grows_with_corrections() -> None:
    mapper = FakeMapper()
    assert isinstance(mapper, MapperService)
    examples = [
        MappingExample(
            id=f"eval:{index}",
            tool_id="eval",
            field_name=f"field_{index}",
            gold_concept=f"http://example.org/ontology#Concept{index}",
            split="test",
        )
        for index in range(10)
    ]
    corrections = [
        MappingExample(
            id=f"teacher:{index}",
            tool_id="teacher",
            field_name=f"teacher_field_{index}",
            gold_concept=f"http://example.org/ontology#Concept{index}",
            split="dev",
        )
        for index in range(25)
    ]
    result = run_learning_curve(
        mapper,
        examples,
        corrections,
        counts=(0, 5, 10, 20),
        reset=mapper.reset,
        map_batch_size=4,
    )
    assert result.counts == [0, 5, 10, 20]
    assert result.n_evaluated == 10
    assert len(result.accuracy) == 4
    assert len(result.f1) == 4
    assert result.accuracy[0] == 0.0
    assert result.accuracy[-1] >= result.accuracy[0]
    assert result.accuracy[-1] == 1.0
    assert mapper.reset_calls == len(result.counts)
    table = curve_to_markdown(result)
    assert "Corrections" in table
    assert "| 0 |" in table
    assert "| 20 |" in table


def test_learning_curve_excludes_correction_fields() -> None:
    examples = [
        MappingExample(
            id=f"eval:{index}",
            tool_id="eval",
            field_name=f"field_{index}",
            gold_concept=f"http://example.org/ontology#Concept{index}",
            split="test",
        )
        for index in range(10)
    ]
    corrections = [
        MappingExample(
            id="eval:0",
            tool_id="eval",
            field_name="field_0",
            gold_concept="http://example.org/ontology#Concept0",
        )
    ]
    result = run_learning_curve(FakeMapper(), examples, corrections, counts=(0,))
    assert result.n_evaluated == 9


def test_ablation_table_markdown_shape() -> None:
    full = compute_accuracy(["a", "b"], ["a", "b"])
    ablated = compute_accuracy(["a", ""], ["a", "b"])
    table = ablation_table({"full": full, "no-ontology": ablated})
    lines = table.splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("| Variant | n | Accuracy | Macro F1 | Micro F1 |")
    assert lines[1] == "| --- | --- | --- | --- | --- |"
    assert "no-ontology" in table
    assert lines[2].startswith("| full | 2 |")


def test_drift_accuracy_normalizes_unmapped() -> None:
    report = drift_accuracy(["a", "b", "c"], ["a", "UNMAPPED", "c"])
    assert report.accuracy == pytest.approx(2 / 3)
