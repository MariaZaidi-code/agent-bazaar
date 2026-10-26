from __future__ import annotations

from agent_bazaar_auditor.enums import TrustOutcome
from agent_bazaar_auditor.messages import TrustUpdate
from agent_bazaar_auditor.scheduler import ProbeScheduler
from agent_bazaar_auditor.trust import TrustFeed, TrustLedger


def test_beta_trust_score_and_demotion() -> None:
    ledger = TrustLedger()
    ledger.record("good", TrustOutcome.PROBE_PASS)
    ledger.record("bad", TrustOutcome.PROBE_FAIL)
    assert ledger.score("good") == 2.0 / 3.0
    assert ledger.score("bad") == 1.0 / 3.0
    assert ledger.demoted(0.4) == ["bad"]


def test_trust_feed_updates_ledger_and_summary() -> None:
    ledger = TrustLedger()
    feed = TrustFeed(ledger=ledger)
    feed.send(
        TrustUpdate(
            sender="auditor",
            tool_id="example",
            outcome=TrustOutcome.CONTRADICTION,
            reason="Probe disagreed with the claim.",
            claim_id="claim-1",
        )
    )
    assert feed.summary()["total"] == 1
    assert feed.summary()["tool_ids"] == ["example"]
    assert ledger.score("example") < 0.5


def test_scheduler_moves_to_unstable_interval_and_recovers() -> None:
    now = [1000.0]
    scheduler = ProbeScheduler(
        ["tool"],
        base_interval_seconds=3600.0,
        unstable_interval_seconds=60.0,
        clean_rounds_to_recover=2,
        clock=lambda: now[0],
    )
    entry = scheduler.mark_probed("tool", "probe_pass", now=now[0])
    assert entry.interval_seconds == 3600.0
    entry = scheduler.mark_probed("tool", "drift", now=now[0] + 3600.0)
    assert entry.unstable
    assert entry.interval_seconds == 60.0
    now[0] += 60.0
    scheduler.mark_probed("tool", "probe_pass", now=now[0])
    entry = scheduler.mark_probed("tool", "probe_pass", now=now[0] + 60.0)
    assert not entry.unstable
    assert entry.interval_seconds == 3600.0
