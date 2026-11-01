from __future__ import annotations

import pytest

from app.config import Settings
from app.services import AppServices


@pytest.mark.asyncio
async def test_client_records_a_self_reflection_event(services: AppServices) -> None:
    result = await services.client.run("What is the weather in Lahore tomorrow?")

    events = services.traces.events(result.task_id)
    reflection = [event for event in events if event.event_type == "self_reflection"]
    assert reflection, [event.event_type for event in events]
    checks = reflection[-1].data["checks"]
    assert checks["completed_steps"] >= 1
    assert checks["answer_present"] is True
    assert checks["empty_outputs"] == []


def test_reasoning_mode_is_configurable() -> None:
    assert Settings().reasoning_mode == "hybrid"
    assert Settings(reasoning_mode="none").reasoning_mode == "none"
    assert Settings(reasoning_mode="llm").reasoning_mode == "llm"
