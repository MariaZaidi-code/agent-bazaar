from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .enums import TrustOutcome
from .messages import TrustUpdate
from .utils import append_jsonl, atomic_write_json, read_json, utc_now

SUCCESS_OUTCOMES = {
    TrustOutcome.PROBE_PASS,
    TrustOutcome.SCHEMA_VALID,
    TrustOutcome.CALL_SUCCESS,
}

FAILURE_OUTCOMES = {
    TrustOutcome.PROBE_FAIL,
    TrustOutcome.SCHEMA_INVALID,
    TrustOutcome.CALL_FAILURE,
    TrustOutcome.CONTRADICTION,
    TrustOutcome.DRIFT,
}


class TrustRegistry(Protocol):
    def push(self, update: TrustUpdate) -> bool:
        ...


class HttpTrustRegistry:
    def __init__(self, url: str, timeout: float = 5.0) -> None:
        self.url = url
        self.timeout = timeout

    def push(self, update: TrustUpdate) -> bool:
        body = update.to_json().encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "agent-bazaar-auditor/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return False


@dataclass
class ToolTrust:
    tool_id: str
    successes: float = 0.0
    failures: float = 0.0
    observations: int = 0
    last_outcome: str = ""
    updated_at: str = field(default_factory=utc_now)

    @property
    def score(self) -> float:
        return (self.successes + 1.0) / (self.successes + self.failures + 2.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "successes": self.successes,
            "failures": self.failures,
            "observations": self.observations,
            "score": round(self.score, 6),
            "last_outcome": self.last_outcome,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolTrust:
        return cls(
            tool_id=str(data["tool_id"]),
            successes=float(data.get("successes", 0.0)),
            failures=float(data.get("failures", 0.0)),
            observations=int(data.get("observations", 0)),
            last_outcome=str(data.get("last_outcome", "")),
            updated_at=str(data.get("updated_at", utc_now())),
        )


class TrustLedger:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else None
        self.tools: dict[str, ToolTrust] = {}
        self.history: list[dict[str, Any]] = []
        if self.path is not None:
            self.load()

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            data = read_json(self.path)
        except (OSError, ValueError):
            return
        self.tools = {tool_id: ToolTrust.from_dict(record) for tool_id, record in data.get("tools", {}).items()}
        self.history = list(data.get("history", []))

    def save(self) -> None:
        if self.path is None:
            return
        atomic_write_json(
            self.path,
            {
                "schema_version": 1,
                "updated_at": utc_now(),
                "tools": {tool_id: record.to_dict() for tool_id, record in sorted(self.tools.items())},
                "history": self.history[-500:],
            },
        )

    def record(self, tool_id: str, outcome: TrustOutcome, success: bool | None = None, weight: float = 1.0) -> ToolTrust:
        entry = self.tools.setdefault(tool_id, ToolTrust(tool_id=tool_id))
        if success is None:
            if outcome in FAILURE_OUTCOMES:
                success = False
            elif outcome in SUCCESS_OUTCOMES:
                success = True
            else:
                success = True
        if success:
            entry.successes += weight
        else:
            entry.failures += weight
        entry.observations += 1
        entry.last_outcome = outcome.value
        entry.updated_at = utc_now()
        self.history.append(
            {
                "tool_id": tool_id,
                "outcome": outcome.value,
                "success": success,
                "weight": weight,
                "score": round(entry.score, 6),
                "timestamp": entry.updated_at,
            }
        )
        return entry

    def apply(self, update: TrustUpdate) -> ToolTrust:
        outcome = update.outcome
        success: bool | None = None
        weight = 1.0
        if outcome is TrustOutcome.RATING:
            if update.value is None:
                success = True
            else:
                success = update.value >= 0.5
                weight = 1.0
        entry = self.record(update.tool_id, outcome, success=success, weight=weight)
        self.save()
        return entry

    def score(self, tool_id: str) -> float:
        entry = self.tools.get(tool_id)
        return entry.score if entry else 0.5

    def leaderboard(self) -> list[dict[str, Any]]:
        rows = [record.to_dict() for record in self.tools.values()]
        rows.sort(key=lambda row: row["score"], reverse=True)
        return rows

    def demoted(self, threshold: float) -> list[str]:
        return sorted(tool_id for tool_id, entry in self.tools.items() if entry.score < threshold)


class TrustFeed:
    def __init__(
        self,
        log_path: Path | str | None = None,
        registry: TrustRegistry | None = None,
        ledger: TrustLedger | None = None,
    ) -> None:
        self.log_path = Path(log_path) if log_path else None
        self.registry = registry
        self.ledger = ledger
        self.updates: list[TrustUpdate] = []
        self.delivery_failures = 0

    def send(self, update: TrustUpdate) -> bool:
        self.updates.append(update)
        if self.log_path is not None:
            append_jsonl(self.log_path, update.to_dict())
        if self.ledger is not None:
            self.ledger.apply(update)
        delivered = True
        if self.registry is not None:
            delivered = self.registry.push(update)
            if not delivered:
                self.delivery_failures += 1
        return delivered

    def updates_for(self, tool_id: str) -> list[TrustUpdate]:
        return [update for update in self.updates if update.tool_id == tool_id]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for update in self.updates:
            counts[update.outcome.value] = counts.get(update.outcome.value, 0) + 1
        return {
            "total": len(self.updates),
            "by_outcome": counts,
            "delivery_failures": self.delivery_failures,
            "tool_ids": sorted({update.tool_id for update in self.updates}),
        }
