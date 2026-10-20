"""Tool quality profiles: commercial, access, reputation and documentation facts.

The profile is a *fact bundle*, not a ranking. The Client decides how to weigh
it; the knowledge layer only stores it and exposes it (work plan Section 5.2).

Executable means: free tier, no key required and a known licence. Paid and
unknown tools stay visible in candidate lists but are never executed, which
keeps the project free of paid APIs (proposal NFR1).
"""

from __future__ import annotations

import json
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from agent_bazaar.models import ToolQualityProfile
from agent_bazaar.ontology.ns import AB, tool_iri

PRIOR_MEAN = 0.5
PRIOR_WEIGHT = 2.0

EXECUTABLE_TIERS = frozenset({"free"})
EXECUTABLE_ACCESS = frozenset({"keyless"})


def shrunk_rating(
    rating_sum: float,
    rating_count: int,
    *,
    prior_mean: float = PRIOR_MEAN,
    prior_weight: float = PRIOR_WEIGHT,
) -> tuple[float, float]:
    """Shrink a rating aggregate towards the prior and return (value, confidence).

    Mirrors the Beta-style prior used by the trust registry so a single rating
    cannot move the ranking.
    """
    count = max(0, int(rating_count))
    if count == 0:
        return prior_mean, 0.0
    value = (float(rating_sum) + prior_mean * prior_weight) / (count + prior_weight)
    confidence = count / (count + prior_weight)
    return round(min(1.0, max(0.0, value)), 4), round(min(1.0, confidence), 4)


def is_executable(
    pricing_tier: str,
    access_requirement: str,
    licence: str = "",
    *,
    require_known_licence: bool = False,
) -> bool:
    """A tool is executable when it is free and keyless.

    A known licence is only required when the caller asks for it, so the rule
    matches the Client policy default (``require_known_licence=False``).
    """
    if pricing_tier not in EXECUTABLE_TIERS or access_requirement not in EXECUTABLE_ACCESS:
        return False
    if require_known_licence and not licence.strip():
        return False
    return True


def offering_iri(tool_id: str) -> URIRef:
    return AB[f"offering-{tool_id}"]


def _literal(graph: Graph, subject: URIRef, predicate: URIRef, default: str = "") -> str:
    value = graph.value(subject, predicate)
    return str(value) if value is not None else default


def _decimal(graph: Graph, subject: URIRef, predicate: URIRef) -> float | None:
    value = graph.value(subject, predicate)
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _integer(graph: Graph, subject: URIRef, predicate: URIRef, default: int = 0) -> int:
    value = graph.value(subject, predicate)
    if value is None:
        return default
    try:
        return int(float(str(value)))
    except ValueError:
        return default


def _json(graph: Graph, subject: URIRef, predicate: URIRef) -> dict[str, Any]:
    raw = _literal(graph, subject, predicate)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def mapping_coverage(graph: Graph, tool_id: str) -> float:
    """Share of the tool's mappings that the Mapper typed successfully."""
    tool = tool_iri(tool_id)
    mappings = list(graph.subjects(AB.tool, tool))
    if not mappings:
        return 0.0
    mapped = 0
    confidence_total = 0.0
    for mapping in mappings:
        status = _literal(graph, mapping, AB.status, "mapped")
        if status in ("mapped", "repaired", "drift_remapped"):
            mapped += 1
        confidence = _decimal(graph, mapping, AB.confidence)
        if confidence is not None:
            confidence_total += confidence
    coverage = mapped / len(mappings)
    mean_confidence = confidence_total / len(mappings) if mappings else 0.0
    return round(coverage * (0.5 + 0.5 * min(1.0, mean_confidence)), 4)


def build_profile(graph: Graph, tool_id: str) -> ToolQualityProfile:
    """Assemble the quality profile of a tool from the knowledge graph."""
    tool = tool_iri(tool_id)
    offering = graph.value(tool, AB.hasOffering)
    if offering is None:
        offering = offering_iri(tool_id)
    pricing_tier = _literal(graph, offering, AB.pricingTier, "unknown") or "unknown"
    access = _literal(graph, offering, AB.accessRequirement, "unknown") or "unknown"
    licence = _literal(graph, offering, AB.licence)
    rating_value = _decimal(graph, offering, AB.ratingValue)
    rating_count = _integer(graph, offering, AB.ratingCount)
    sub_scores = _json(graph, offering, AB.docSubScores)
    provenance = _json(graph, offering, AB.provenance)
    stored_coverage = _decimal(graph, offering, AB.mappingCoverage)
    return ToolQualityProfile(
        tool_id=tool_id,
        pricing_tier=pricing_tier,
        access_requirement=access,
        price_amount=_decimal(graph, offering, AB.priceAmount),
        price_currency=_literal(graph, offering, AB.priceCurrency),
        rate_limit_policy=_literal(graph, offering, AB.rateLimit),
        probe_budget_per_minute=(
            _integer(graph, offering, AB.probeBudgetPerMinute)
            if graph.value(offering, AB.probeBudgetPerMinute) is not None
            else None
        ),
        rating_value=rating_value,
        rating_count=rating_count,
        rating_confidence=round(rating_count / (rating_count + PRIOR_WEIGHT), 4) if rating_count else 0.0,
        doc_quality=_decimal(graph, offering, AB.docQuality) or 0.0,
        doc_sub_scores={str(key): float(value) for key, value in sub_scores.items()},
        mapping_coverage=(
            stored_coverage if stored_coverage is not None else mapping_coverage(graph, tool_id)
        ),
        licence=licence,
        terms_url=_literal(graph, offering, AB.termsUrl),
        is_executable=is_executable(pricing_tier, access, licence),
        tier_evidence=[item for item in _literal(graph, offering, AB.tierEvidence).split(" | ") if item],
        access_evidence=[item for item in _literal(graph, offering, AB.accessEvidence).split(" | ") if item],
        provenance=provenance,
    )


def offering_triples(
    graph: Graph,
    tool_id: str,
    *,
    pricing_tier: str = "unknown",
    access_requirement: str = "unknown",
    price_amount: float | None = None,
    price_currency: str = "",
    rate_limit_policy: str = "",
    probe_budget_per_minute: int | None = None,
    rating_value: float | None = None,
    rating_count: int = 0,
    rating_source: str = "",
    doc_quality: float = 0.0,
    doc_sub_scores: dict[str, float] | None = None,
    mapping_coverage_value: float | None = None,
    licence: str = "",
    terms_url: str = "",
    tier_evidence: list[str] | None = None,
    access_evidence: list[str] | None = None,
    provenance: dict[str, Any] | None = None,
    last_seen: str | None = None,
) -> URIRef:
    """Write the offering facts of a tool into a graph and return the offering IRI."""
    tool = tool_iri(tool_id)
    offering = offering_iri(tool_id)
    graph.add((tool, RDF.type, AB.Tool))
    graph.add((tool, AB.hasOffering, offering))
    graph.add((offering, RDF.type, AB.Offering))
    graph.add((offering, AB.pricingTier, Literal(pricing_tier)))
    graph.add((offering, AB.accessRequirement, Literal(access_requirement)))
    if price_amount is not None:
        graph.add((offering, AB.priceAmount, Literal(str(price_amount), datatype=XSD.decimal)))
    if price_currency:
        graph.add((offering, AB.priceCurrency, Literal(price_currency)))
    if rate_limit_policy:
        graph.add((offering, AB.rateLimit, Literal(rate_limit_policy)))
    if probe_budget_per_minute:
        graph.add(
            (offering, AB.probeBudgetPerMinute, Literal(int(probe_budget_per_minute), datatype=XSD.integer))
        )
    if rating_value is not None:
        graph.add((offering, AB.ratingValue, Literal(str(rating_value), datatype=XSD.decimal)))
        graph.add((offering, AB.ratingCount, Literal(int(rating_count), datatype=XSD.integer)))
        if rating_source:
            graph.add((offering, AB.ratingSource, Literal(rating_source)))
    if doc_quality:
        graph.add((offering, AB.docQuality, Literal(str(doc_quality), datatype=XSD.decimal)))
    if doc_sub_scores:
        graph.add((offering, AB.docSubScores, Literal(json.dumps(doc_sub_scores, sort_keys=True))))
    if mapping_coverage_value is not None:
        graph.add(
            (offering, AB.mappingCoverage, Literal(str(mapping_coverage_value), datatype=XSD.decimal))
        )
    if licence:
        graph.add((offering, AB.licence, Literal(licence)))
    if terms_url:
        graph.add((offering, AB.termsUrl, Literal(terms_url)))
    if tier_evidence:
        graph.add((offering, AB.tierEvidence, Literal(" | ".join(tier_evidence))))
    if access_evidence:
        graph.add((offering, AB.accessEvidence, Literal(" | ".join(access_evidence))))
    if provenance:
        graph.add((offering, AB.provenance, Literal(json.dumps(provenance, sort_keys=True, default=str))))
    if last_seen:
        graph.add((offering, AB.lastSeen, Literal(last_seen, datatype=XSD.dateTime)))
    return offering
