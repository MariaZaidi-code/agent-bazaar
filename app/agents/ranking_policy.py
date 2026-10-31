"""Deterministic free-first ranking policy for candidate tools.

Proposal Section 7 requires the ranking arithmetic to be deterministic code, and
FR3/NFR4 require a ranked list with reasons that can be explained from stored
evidence. The policy therefore never calls a language model.

Ordering has two levels:

1. A **tier partition** on the commercial tier, so a free tool is always
   ranked above a paid one. A multiplier cannot express that, so the tier is a
   sort key, not a factor.
2. The **score within a tier**: relevance x trust x quality x rating factor,
   with hard gates for demoted providers, open circuit breakers and
   contradicted claims.

Paid and unknown tools stay visible in the candidate list with an explicit
reason, but they are never executed (proposal NFR1: no paid APIs).
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_TIER_ORDER: tuple[str, ...] = ("free", "freemium", "paid", "unknown")


@dataclass
class CandidateFacts:
    """The stored facts about one candidate that the policy weighs."""

    tool_id: str
    relevance: float = 0.0
    trust: float = 0.5
    pricing_tier: str = "unknown"
    access_requirement: str = "unknown"
    rating_value: float | None = None
    rating_count: int = 0
    doc_quality: float = 0.0
    mapping_coverage: float = 0.0
    chain_fit: float = 0.0
    latency_ms: float | None = None
    freshness_days: float | None = None
    claim_label: str = "unsupported"
    demoted: bool = False
    breaker_open: bool = False
    licence: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class RankingPolicy:
    """Weights and gates of the policy; every value is configurable."""

    pricing_policy: str = "prefer_free"
    tier_order: tuple[str, ...] = DEFAULT_TIER_ORDER
    doc_quality_weight: float = 0.4
    mapping_coverage_weight: float = 0.3
    chain_fit_weight: float = 0.3
    latency_weight: float = 0.0
    freshness_weight: float = 0.0
    latency_normalizer_ms: float = 1000.0
    freshness_half_life_days: float = 30.0
    min_rating_count: int = 3
    rating_floor: float = 0.5
    contradicted_penalty: float = 0.6
    require_known_licence: bool = False


@dataclass
class RankedCandidate:
    tool_id: str
    score: float
    quality: float
    tier: str
    tier_rank: int
    eligible: bool
    executable: bool
    reasons: list[str]


def tier_rank(facts: CandidateFacts, policy: RankingPolicy) -> int:
    """Position of the candidate's tier; lower is better."""
    if policy.pricing_policy == "ignore":
        return 0
    tier = facts.pricing_tier if facts.pricing_tier in policy.tier_order else "unknown"
    return policy.tier_order.index(tier)


def latency_factor(facts: CandidateFacts, policy: RankingPolicy) -> float:
    """Higher is better for low-latency candidates."""
    if facts.latency_ms is None or policy.latency_normalizer_ms <= 0:
        return 1.0
    latency = max(0.0, float(facts.latency_ms))
    return round(1.0 / (1.0 + latency / policy.latency_normalizer_ms), 6)


def freshness_factor(facts: CandidateFacts, policy: RankingPolicy) -> float:
    """Higher is better for recently verified or updated candidates."""
    if facts.freshness_days is None or policy.freshness_half_life_days <= 0:
        return 1.0
    age = max(0.0, float(facts.freshness_days))
    return round(0.5 ** (age / policy.freshness_half_life_days), 6)


def quality_score(facts: CandidateFacts, policy: RankingPolicy) -> float:
    """Weighted documentation, mapping, chain-fit, latency and freshness quality."""
    terms = [
        (policy.doc_quality_weight, max(0.0, min(1.0, facts.doc_quality))),
        (policy.mapping_coverage_weight, max(0.0, min(1.0, facts.mapping_coverage))),
        (policy.chain_fit_weight, max(0.0, min(1.0, facts.chain_fit))),
    ]
    if policy.latency_weight > 0:
        terms.append((policy.latency_weight, latency_factor(facts, policy)))
    if policy.freshness_weight > 0:
        terms.append((policy.freshness_weight, freshness_factor(facts, policy)))
    total = sum(weight * value for weight, value in terms)
    weight_sum = sum(weight for weight, _ in terms)
    if weight_sum <= 0:
        return 0.0
    return round(total / weight_sum, 6)


def rating_factor(facts: CandidateFacts, policy: RankingPolicy) -> float:
    """Shrunk developer rating as a reputation factor.

    Below ``min_rating_count`` the rating is ignored so a single review cannot
    move the ranking.
    """
    if facts.rating_value is None or facts.rating_count < policy.min_rating_count:
        return 1.0
    value = max(0.0, min(1.0, facts.rating_value))
    floor = max(0.0, min(1.0, policy.rating_floor))
    return round(floor + (1.0 - floor) * value, 6)


def is_executable(facts: CandidateFacts, policy: RankingPolicy) -> bool:
    """Only free, keyless tools may be executed."""
    if facts.pricing_tier != "free":
        return False
    if facts.access_requirement != "keyless":
        return False
    if policy.require_known_licence and not facts.licence.strip():
        return False
    return True


def explain(facts: CandidateFacts, policy: RankingPolicy) -> list[str]:
    """Reasons stored with the decision so it can be explained (FR3, NFR4)."""
    reasons: list[str] = []
    tier = facts.pricing_tier
    reasons.append(f"pricing tier {tier}")
    if facts.access_requirement == "keyless":
        reasons.append("no api key required")
    else:
        reasons.append(f"requires {facts.access_requirement.replace('_', ' ')}")
    if facts.rating_value is not None and facts.rating_count >= policy.min_rating_count:
        reasons.append(f"rating {facts.rating_value:.2f} from {facts.rating_count} reviews")
    elif facts.rating_count:
        reasons.append(f"rating not used ({facts.rating_count} review(s) below {policy.min_rating_count})")
    reasons.append(f"doc quality {facts.doc_quality:.2f}")
    reasons.append(f"mapping coverage {facts.mapping_coverage:.2f}")
    reasons.append(f"chain fit {facts.chain_fit:.2f}")
    reasons.append(f"trust {facts.trust:.2f}")
    if facts.claim_label == "contradicted":
        reasons.append("contradicted claim penalty applied")
    if facts.demoted:
        reasons.append("provider demoted by the trust registry")
    if facts.breaker_open:
        reasons.append("circuit breaker open")
    if not is_executable(facts, policy):
        if tier != "free":
            reasons.append(f"not executable: {tier} tier")
        else:
            reasons.append("not executable: requires an api key")
    return reasons


def rank_candidates(
    candidates: list[CandidateFacts], policy: RankingPolicy | None = None
) -> list[RankedCandidate]:
    """Rank candidates free-first and return them with their reasons."""
    policy = policy or RankingPolicy()
    ranked: list[RankedCandidate] = []
    for facts in candidates:
        quality = quality_score(facts, policy)
        score = facts.relevance * facts.trust * quality * rating_factor(facts, policy)
        eligible = True
        if facts.claim_label == "contradicted":
            score *= policy.contradicted_penalty
        if facts.demoted:
            score = 0.0
            eligible = False
        if facts.breaker_open:
            score = 0.0
            eligible = False
        ranked.append(
            RankedCandidate(
                tool_id=facts.tool_id,
                score=round(score, 6),
                quality=quality,
                tier=facts.pricing_tier,
                tier_rank=tier_rank(facts, policy),
                eligible=eligible,
                executable=is_executable(facts, policy),
                reasons=explain(facts, policy),
            )
        )
    ranked.sort(key=lambda item: (item.tier_rank, -item.score, item.tool_id))
    return ranked


def free_first_compliance(
    candidates: list[CandidateFacts], policy: RankingPolicy | None = None
) -> bool:
    """True when the top ranked candidate is free whenever a free candidate exists."""
    policy = policy or RankingPolicy()
    if policy.pricing_policy != "prefer_free":
        return True
    free = [facts for facts in candidates if facts.pricing_tier == "free"]
    if not free:
        return True
    ranked = rank_candidates(candidates, policy)
    if not ranked:
        return True
    return ranked[0].tier == "free"
