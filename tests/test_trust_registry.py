from __future__ import annotations

from pathlib import Path

import pytest

from app.core.trust_registry import TrustRegistry


@pytest.fixture
def registry(tmp_path: Path) -> TrustRegistry:
    return TrustRegistry(tmp_path / "trust.db", demotion_threshold=0.4, min_evidence=3)


def test_default_prior(registry: TrustRegistry) -> None:
    state = registry.get("example")
    assert state["score"] == 0.5
    assert state["evidence"] == 0
    assert state["demoted"] is False


def test_successes_raise_score_and_history(registry: TrustRegistry) -> None:
    for index in range(4):
        state = registry.record_call("example", True, f"call {index}")
    assert state["score"] > 0.5
    assert state["successes"] == 4
    assert state["calls"] == 4
    history = registry.history("example")
    assert len(history) == 4
    assert history[0]["signal"] == "call"
    assert registry.replay("example")["matches"] is True


def test_failures_demote(registry: TrustRegistry) -> None:
    for _ in range(3):
        state = registry.record_call("bad", False, "provider outage")
    assert state["score"] < 0.4
    assert state["demoted"] is True
    assert registry.is_demoted("bad") is True


def test_signal_weights_and_rating(registry: TrustRegistry) -> None:
    state = registry.record_rating("rated", 0.9, "developer rating")
    assert state["ratings_count"] == 1
    assert state["ratings_sum"] == pytest.approx(0.9)
    assert state["score"] > 0.5


def test_contradiction_is_recorded(registry: TrustRegistry) -> None:
    state = registry.record_contradiction("drifted", "unit mismatch")
    assert state["contradictions"] == 1
    assert state["failures"] == 2.0
    assert state["score"] < 0.5


def test_reset_clears_state_and_history(registry: TrustRegistry) -> None:
    registry.record_call("example", True, "ok")
    registry.reset()
    assert registry.all() == []
    assert registry.history("example") == []
