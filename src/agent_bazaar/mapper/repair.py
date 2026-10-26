"""Bounded repair loop driven by concrete validation messages."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from agent_bazaar.messages.schema import FieldMapping, FieldSpec, RepairRequest


class RepairOutcome(BaseModel):
    model_config = ConfigDict(extra="allow")

    mapping: FieldMapping | None = None
    attempts: int = 0
    problems: list[str] = Field(default_factory=list)
    messages: list[RepairRequest] = Field(default_factory=list)


class RepairLoop:
    def __init__(self, max_attempts: int) -> None:
        self.max_attempts = max(1, int(max_attempts))

    def run(
        self,
        field: FieldSpec,
        rejected: FieldMapping,
        violations: list[str],
        propose_fn: Callable[[FieldSpec, str], FieldMapping | None],
        validate_fn: Callable[[FieldMapping], list[str]],
    ) -> RepairOutcome:
        problems = list(violations)
        message = "; ".join(problems)
        attempts = 1
        messages = [
            RepairRequest(
                tool_id="",
                field_path=field.field_path,
                violation_message=message,
                rejected_mapping=rejected,
                attempt=attempts,
            )
        ]
        while attempts < self.max_attempts:
            attempts += 1
            candidate = propose_fn(field, message)
            if candidate is None:
                break
            confidence = min(1.0, max(0.0, float(candidate.confidence)))
            if confidence != candidate.confidence:
                candidate = candidate.model_copy(update={"confidence": confidence})
            problems = list(validate_fn(candidate))
            messages.append(
                RepairRequest(
                    tool_id="",
                    field_path=field.field_path,
                    violation_message=message,
                    rejected_mapping=candidate,
                    attempt=attempts,
                )
            )
            if not problems:
                return RepairOutcome(
                    mapping=candidate,
                    attempts=attempts,
                    problems=[],
                    messages=messages,
                )
            message = "; ".join(problems)
        return RepairOutcome(
            mapping=None,
            attempts=attempts,
            problems=problems,
            messages=messages,
        )
