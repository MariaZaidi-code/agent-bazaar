from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import atomic_write_json, read_json, utc_now

UNSTABLE_OUTCOMES = {
    "drift",
    "contradicted",
    "probe_fail",
    "probe_error",
    "schema_invalid",
    "call_failure",
    "flapping",
    "outage",
    "failure",
}


@dataclass
class ScheduleEntry:
    tool_id: str
    base_interval_seconds: float
    unstable_interval_seconds: float
    interval_seconds: float
    next_due_epoch: float
    unstable: bool = False
    clean_rounds: int = 0
    rounds: int = 0
    last_outcome: str = ""
    last_probe_at: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "base_interval_seconds": self.base_interval_seconds,
            "unstable_interval_seconds": self.unstable_interval_seconds,
            "interval_seconds": self.interval_seconds,
            "next_due_epoch": self.next_due_epoch,
            "unstable": self.unstable,
            "clean_rounds": self.clean_rounds,
            "rounds": self.rounds,
            "last_outcome": self.last_outcome,
            "last_probe_at": self.last_probe_at,
            "history": list(self.history[-25:]),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduleEntry:
        return cls(
            tool_id=str(data["tool_id"]),
            base_interval_seconds=float(data["base_interval_seconds"]),
            unstable_interval_seconds=float(data["unstable_interval_seconds"]),
            interval_seconds=float(data["interval_seconds"]),
            next_due_epoch=float(data["next_due_epoch"]),
            unstable=bool(data.get("unstable", False)),
            clean_rounds=int(data.get("clean_rounds", 0)),
            rounds=int(data.get("rounds", 0)),
            last_outcome=str(data.get("last_outcome", "")),
            last_probe_at=str(data.get("last_probe_at", "")),
            history=list(data.get("history", [])),
        )


class ProbeScheduler:
    def __init__(
        self,
        tool_ids: list[str],
        base_interval_seconds: float = 3600.0,
        unstable_interval_seconds: float = 300.0,
        clean_rounds_to_recover: int = 3,
        clock: Callable[[], float] = time.time,
        path: Path | str | None = None,
    ) -> None:
        self.clock = clock
        self.clean_rounds_to_recover = clean_rounds_to_recover
        self.path = Path(path) if path else None
        self.entries: dict[str, ScheduleEntry] = {}
        for tool_id in tool_ids:
            self.register(tool_id, base_interval_seconds, unstable_interval_seconds)
        if self.path is not None and self.path.exists():
            self.load()

    def register(
        self,
        tool_id: str,
        base_interval_seconds: float = 3600.0,
        unstable_interval_seconds: float = 300.0,
    ) -> ScheduleEntry:
        if base_interval_seconds <= 0 or unstable_interval_seconds <= 0:
            raise ValueError("scheduler intervals must be positive")
        if unstable_interval_seconds > base_interval_seconds:
            unstable_interval_seconds = base_interval_seconds
        entry = ScheduleEntry(
            tool_id=tool_id,
            base_interval_seconds=float(base_interval_seconds),
            unstable_interval_seconds=float(unstable_interval_seconds),
            interval_seconds=float(base_interval_seconds),
            next_due_epoch=self.clock(),
        )
        self.entries[tool_id] = entry
        return entry

    def now(self) -> float:
        return float(self.clock())

    def due(self, now: float | None = None) -> list[str]:
        current = self.now() if now is None else now
        return sorted(tool_id for tool_id, entry in self.entries.items() if entry.next_due_epoch <= current)

    def trigger(self, tool_id: str, now: float | None = None) -> ScheduleEntry:
        entry = self.entries[tool_id]
        entry.next_due_epoch = self.now() if now is None else now
        self.save()
        return entry

    def trigger_all(self, now: float | None = None) -> None:
        for tool_id in self.entries:
            self.trigger(tool_id, now=now)

    def mark_probed(
        self,
        tool_id: str,
        outcome: str = "probe_pass",
        unstable: bool | None = None,
        now: float | None = None,
    ) -> ScheduleEntry:
        entry = self.entries[tool_id]
        current = self.now() if now is None else now
        entry.rounds += 1
        entry.last_outcome = outcome
        entry.last_probe_at = utc_now()
        if unstable is None:
            unstable = outcome.lower() in UNSTABLE_OUTCOMES
        if unstable:
            entry.unstable = True
            entry.clean_rounds = 0
        elif entry.unstable:
            entry.clean_rounds += 1
            if entry.clean_rounds >= self.clean_rounds_to_recover:
                entry.unstable = False
                entry.clean_rounds = 0
        entry.interval_seconds = entry.unstable_interval_seconds if entry.unstable else entry.base_interval_seconds
        entry.next_due_epoch = current + entry.interval_seconds
        entry.history.append(
            {
                "round": entry.rounds,
                "outcome": outcome,
                "unstable": entry.unstable,
                "interval_seconds": entry.interval_seconds,
                "next_due_epoch": entry.next_due_epoch,
                "timestamp": entry.last_probe_at,
            }
        )
        self.save()
        return entry

    def apply_feedback(self, tool_id: str, outcome: str, now: float | None = None) -> ScheduleEntry:
        return self.mark_probed(tool_id, outcome=outcome, now=now)

    def run_due(
        self,
        runner: Callable[[str], Any],
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for tool_id in self.due(now=now):
            outcome = runner(tool_id)
            if isinstance(outcome, tuple):
                outcome_text, unstable = outcome
            else:
                outcome_text, unstable = str(outcome), None
            entry = self.mark_probed(tool_id, outcome=outcome_text, unstable=unstable, now=now)
            results.append({"tool_id": tool_id, "outcome": outcome_text, "entry": entry.to_dict()})
        return results

    def seconds_until_next(self, now: float | None = None) -> float:
        current = self.now() if now is None else now
        if not self.entries:
            return 0.0
        return max(0.0, min(entry.next_due_epoch for entry in self.entries.values()) - current)

    def status(self) -> list[dict[str, Any]]:
        rows = [entry.to_dict() for entry in self.entries.values()]
        rows.sort(key=lambda row: row["next_due_epoch"])
        return rows

    def save(self) -> None:
        if self.path is None:
            return
        atomic_write_json(
            self.path,
            {
                "schema_version": 1,
                "saved_at": utc_now(),
                "entries": {tool_id: entry.to_dict() for tool_id, entry in sorted(self.entries.items())},
            },
        )

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            data = read_json(self.path)
        except (OSError, ValueError):
            return
        loaded = {
            tool_id: ScheduleEntry.from_dict(entry)
            for tool_id, entry in data.get("entries", {}).items()
        }
        for tool_id, entry in loaded.items():
            if tool_id in self.entries:
                entry.base_interval_seconds = self.entries[tool_id].base_interval_seconds
                entry.unstable_interval_seconds = self.entries[tool_id].unstable_interval_seconds
            self.entries[tool_id] = entry
