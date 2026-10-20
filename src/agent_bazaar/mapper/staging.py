"""Correction staging queue with validation before promotion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent_bazaar.config import get_settings
from agent_bazaar.mapper.memory import CorrectionEntry
from agent_bazaar.messages.schema import CorrectionSubmit


class StagingDecision(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["promoted", "rejected", "pending_review"]
    reason: str = ""
    entry: CorrectionEntry | None = None
    problems: list[str] = Field(default_factory=list)


class StagingQueue:
    def __init__(self, root: str | Path | None = None) -> None:
        base = Path(root) if root is not None else get_settings().paths.staging_dir
        self.root = base
        self.path = base / "staging.jsonl"
        self._decisions: list[StagingDecision] = []
        self._pending: list[CorrectionSubmit] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                decision = StagingDecision.model_validate(record.get("decision") or {})
                correction = CorrectionSubmit.model_validate(record.get("correction") or {})
            except (json.JSONDecodeError, ValidationError):
                continue
            self._decisions.append(decision)
            if decision.status == "pending_review":
                self._pending.append(correction)

    def _record(self, decision: StagingDecision, correction: CorrectionSubmit) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "decision": decision.model_dump(mode="json"),
            "correction": correction.model_dump(mode="json"),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")

    def submit(
        self,
        correction: CorrectionSubmit,
        check: Callable[[CorrectionSubmit], list[str]],
        promote: Callable[[CorrectionSubmit], CorrectionEntry],
    ) -> StagingDecision:
        try:
            problems = list(check(correction))
        except Exception as error:
            problems = [f"validation check failed: {error}"]
            decision = StagingDecision(
                status="pending_review",
                reason=problems[0],
                problems=problems,
            )
            self._pending.append(correction)
            self._decisions.append(decision)
            self._record(decision, correction)
            return decision

        if problems:
            decision = StagingDecision(
                status="rejected",
                reason="; ".join(problems),
                problems=problems,
            )
            self._decisions.append(decision)
            self._record(decision, correction)
            return decision

        try:
            entry = promote(correction)
        except Exception as error:
            problems = [f"promotion failed: {error}"]
            decision = StagingDecision(
                status="pending_review",
                reason=problems[0],
                problems=problems,
            )
            self._pending.append(correction)
            self._decisions.append(decision)
            self._record(decision, correction)
            return decision

        decision = StagingDecision(status="promoted", entry=entry)
        self._decisions.append(decision)
        self._record(decision, correction)
        return decision

    def stats(self) -> dict[str, float | int]:
        submitted = len(self._decisions)
        promoted = sum(1 for decision in self._decisions if decision.status == "promoted")
        rejected = sum(1 for decision in self._decisions if decision.status == "rejected")
        rejected_share = rejected / submitted if submitted else 0.0
        return {
            "submitted": submitted,
            "promoted": promoted,
            "rejected": rejected,
            "rejected_share": rejected_share,
        }

    def pending(self) -> list[CorrectionSubmit]:
        return list(self._pending)

    def history(self) -> list[StagingDecision]:
        return list(self._decisions)
