"""Tests for the correction staging queue and its persisted decision log."""

from __future__ import annotations

from pathlib import Path

from agent_bazaar.mapper.memory import CorrectionEntry, CorrectionMemory
from agent_bazaar.mapper.staging import StagingQueue
from agent_bazaar.messages.schema import CorrectionSubmit


def _correction(concept: str = "Temperature", unit: str | None = "Celsius") -> CorrectionSubmit:
    return CorrectionSubmit(
        tool_id="weather",
        field_path="output.temperature_2m",
        corrected_concept=concept,
        corrected_unit=unit,
        note="unit test",
        submitted_by="reviewer",
    )


def _memory_entry(correction: CorrectionSubmit) -> CorrectionEntry:
    return CorrectionEntry(
        tool_id=correction.tool_id,
        field_path=correction.field_path,
        corrected_concept=correction.corrected_concept,
        corrected_unit=correction.corrected_unit,
        note=correction.note,
        submitted_by=correction.submitted_by,
    )


def test_good_correction_is_promoted_and_statistics_count_it(tmp_path: Path) -> None:
    memory = CorrectionMemory(tmp_path / "memory")
    staging = StagingQueue(tmp_path / "staging")

    decision = staging.submit(_correction(), lambda item: [], lambda item: memory.add(_memory_entry(item)))

    assert decision.status == "promoted"
    assert decision.entry is not None
    assert decision.entry.corrected_concept == "Temperature"
    assert memory.count() == 1
    stats = staging.stats()
    assert stats == {"submitted": 1, "promoted": 1, "rejected": 0, "rejected_share": 0.0}


def test_bad_correction_is_rejected_and_not_promoted(tmp_path: Path) -> None:
    memory = CorrectionMemory(tmp_path / "memory")
    staging = StagingQueue(tmp_path / "staging")
    promoted: list[CorrectionSubmit] = []

    def promote(item: CorrectionSubmit) -> CorrectionEntry:
        promoted.append(item)
        return memory.add(_memory_entry(item))

    decision = staging.submit(
        _correction("NoSuchConcept"),
        lambda item: ["concept not found in ontology"],
        promote,
    )

    assert decision.status == "rejected"
    assert "concept not found in ontology" in decision.reason
    assert decision.problems == ["concept not found in ontology"]
    assert promoted == []
    assert memory.count() == 0
    assert staging.stats()["rejected"] == 1
    assert staging.stats()["rejected_share"] == 1.0


def test_rejected_share_math(tmp_path: Path) -> None:
    memory = CorrectionMemory(tmp_path / "memory")
    staging = StagingQueue(tmp_path / "staging")
    check = lambda item: [] if item.corrected_concept == "Temperature" else ["bad concept"]
    promote = lambda item: memory.add(_memory_entry(item))

    staging.submit(_correction(), check, promote)
    for _ in range(3):
        staging.submit(_correction("NoSuchConcept"), check, promote)

    stats = staging.stats()
    assert stats["submitted"] == 4
    assert stats["promoted"] == 1
    assert stats["rejected"] == 3
    assert stats["rejected_share"] == 0.75
    assert memory.count() == 1


def test_decisions_persist_across_queue_instances(tmp_path: Path) -> None:
    memory = CorrectionMemory(tmp_path / "memory")
    staging = StagingQueue(tmp_path / "staging")
    check = lambda item: [] if item.corrected_concept == "Temperature" else ["bad concept"]
    promote = lambda item: memory.add(_memory_entry(item))

    staging.submit(_correction(), check, promote)
    staging.submit(_correction("NoSuchConcept"), check, promote)

    reloaded = StagingQueue(tmp_path / "staging")
    history = reloaded.history()
    assert [decision.status for decision in history] == ["promoted", "rejected"]
    assert reloaded.stats()["submitted"] == 2
    assert reloaded.pending() == []


def test_check_exception_is_held_for_review_without_crash(tmp_path: Path) -> None:
    staging = StagingQueue(tmp_path / "staging")
    promoted: list[CorrectionSubmit] = []

    def check(item: CorrectionSubmit) -> list[str]:
        raise RuntimeError("validator exploded")

    def promote(item: CorrectionSubmit) -> CorrectionEntry:
        promoted.append(item)
        return _memory_entry(item)

    decision = staging.submit(_correction(), check, promote)

    assert decision.status == "pending_review"
    assert "validator exploded" in decision.reason
    assert promoted == []
    assert len(staging.pending()) == 1
    assert staging.history()[-1].status == "pending_review"

    reloaded = StagingQueue(tmp_path / "staging")
    assert len(reloaded.pending()) == 1
    assert reloaded.history()[-1].status == "pending_review"
