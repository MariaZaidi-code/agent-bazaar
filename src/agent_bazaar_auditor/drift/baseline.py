from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..utils import atomic_write_json, read_json, utc_now


@dataclass
class BaselineRecord:
    tool_id: str
    summary: str
    embedding: list[float]
    embedder_name: str
    dimensions: int
    created_at: str = field(default_factory=utc_now)
    probe_round: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "summary": self.summary,
            "embedding": list(self.embedding),
            "embedder_name": self.embedder_name,
            "dimensions": self.dimensions,
            "created_at": self.created_at,
            "probe_round": self.probe_round,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineRecord:
        return cls(
            tool_id=str(data["tool_id"]),
            summary=str(data.get("summary", "")),
            embedding=[float(value) for value in data.get("embedding", [])],
            embedder_name=str(data.get("embedder_name", "")),
            dimensions=int(data.get("dimensions", 0)),
            created_at=str(data.get("created_at", "")),
            probe_round=int(data.get("probe_round", 0)),
        )


class BaselineStore:
    def __init__(self, path: Path | str = "outputs/baselines.json", persist: bool = True) -> None:
        self.path = Path(path)
        self.persist = persist
        self.records: dict[str, BaselineRecord] = {}
        if self.persist:
            self.load()

    def load(self) -> None:
        if not self.persist or not self.path.exists():
            self.records = {}
            return
        try:
            data = read_json(self.path)
        except (OSError, ValueError):
            self.records = {}
            return
        self.records = {
            tool_id: BaselineRecord.from_dict(record)
            for tool_id, record in data.get("tools", {}).items()
        }

    def save(self) -> None:
        if not self.persist:
            return
        atomic_write_json(
            self.path,
            {
                "schema_version": 1,
                "updated_at": utc_now(),
                "tools": {tool_id: record.to_dict() for tool_id, record in sorted(self.records.items())},
            },
        )

    def get(self, tool_id: str, embedder_name: str | None = None, dimensions: int | None = None) -> BaselineRecord | None:
        record = self.records.get(tool_id)
        if record is None:
            return None
        if embedder_name is not None and record.embedder_name != embedder_name:
            return None
        if dimensions is not None and record.dimensions != dimensions:
            return None
        return record

    def set(self, record: BaselineRecord) -> None:
        self.records[record.tool_id] = record
        self.save()

    def clear(self, tool_id: str) -> None:
        if tool_id in self.records:
            del self.records[tool_id]
            self.save()

    def clear_all(self) -> None:
        self.records.clear()
        self.save()

    def count(self) -> int:
        return len(self.records)
