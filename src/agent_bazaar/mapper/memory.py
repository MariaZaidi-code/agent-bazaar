"""Correction memory persisted as JSONL for in-context mapping learning."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_bazaar.config import get_settings
from agent_bazaar.protocols import IndexItem


class CorrectionEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_id: str
    field_path: str
    corrected_concept: str
    corrected_unit: str | None = None
    note: str = ""
    submitted_by: str = ""
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: str = "promoted"


def _correction_item(entry: CorrectionEntry) -> IndexItem:
    digest = hashlib.sha1(f"{entry.tool_id}|{entry.field_path}".encode()).hexdigest()[:12]
    return IndexItem(
        id=f"corr-{digest}",
        text=(
            f"{entry.field_path} -> {entry.corrected_concept} "
            f"{entry.corrected_unit or ''} {entry.note}"
        ),
        metadata={
            "tool_id": entry.tool_id,
            "field_path": entry.field_path,
            "concept": entry.corrected_concept,
            "unit": entry.corrected_unit,
        },
    )


class CorrectionMemory:
    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root is not None else get_settings().paths.memory_dir
        self.root = base
        self.path = base / "corrections.jsonl"
        self._entries: list[CorrectionEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                self._entries.append(CorrectionEntry.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError):
                continue

    def _append(self, entry: CorrectionEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    def add(self, entry: CorrectionEntry) -> CorrectionEntry:
        self._entries.append(entry)
        self._append(entry)
        return entry

    def all(self) -> list[CorrectionEntry]:
        return list(self._entries)

    def for_tool(self, tool_id: str) -> list[CorrectionEntry]:
        return [entry for entry in self._entries if entry.tool_id == tool_id]

    def for_field(self, tool_id: str, field_path: str) -> list[CorrectionEntry]:
        return [
            entry
            for entry in self._entries
            if entry.tool_id == tool_id and entry.field_path == field_path
        ]

    def count(self) -> int:
        return len(self._entries)

    def as_index_items(self) -> list[IndexItem]:
        return [_correction_item(entry) for entry in self._entries]
