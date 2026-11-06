from __future__ import annotations

import json
from typing import Any

from app.core.llm import LLMClient

from .claims import Claim, DocumentJudgement
from .enums import DocStance


class LLMClientProtocol:
    """Protocol for LLM clients used by the evidence judge."""

    def complete_json(self, prompt: str) -> dict[str, Any]:
        ...


class LLMValidator:
    """LLM-based evidence judge that evaluates claim verification using an LLM.

    When an LLM is available (configured via LLM settings), this judge
    provides evidence evaluation using an LLM to determine whether
    documentation supports or contradicts a claim, considering probe
    outcomes as additional evidence.

    Falls back gracefully when no LLM is configured.
    """

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm

    def judge_claim(
        self,
        claim_text: str,
        documentation: str,
        probe_outcome: str,
        probe_outcome_details: str | None = None,
    ) -> tuple[str, str, str]:
        """Judge a claim using the LLM.

        Returns (label, rationale, confidence) where:
        - label: one of "Verified", "Supported", "Contradicted", "Unsupported"
        - rationale: human-readable explanation
        - confidence: "high", "medium", or "low"
        """
        if self.llm is None:
            return "Unsupported", "LLM not configured", "low"

        prompt = self._build_prompt(claim_text, documentation, probe_outcome, probe_outcome_details)

        try:
            result = self.llm.complete_json(prompt)
            label = str(result.get("label", "Unsupported")).title()
            rationale = str(result.get("rationale", "No rationale provided"))
            confidence = str(result.get("confidence", "medium")).lower()

            # Validate label
            valid_labels = {"Verified", "Supported", "Contradicted", "Unsupported"}
            if label not in valid_labels:
                label = "Unsupported"

            return label, rationale, confidence

        except Exception as exc:
            return "Unsupported", f"LLM judge error: {exc}", "low"

    def _build_prompt(
        self,
        claim_text: str,
        documentation: str,
        probe_outcome: str,
        probe_outcome_details: str | None,
    ) -> str:
        prompt = f"""You are an expert fact-checker evaluating whether tool documentation is true.

CLAIM: {claim_text}

DOCUMENTATION:
{documentation[:3000]}

PROBE OUTCOME: {probe_outcome}
{f"PROBE DETAILS: {probe_outcome_details}" if probe_outcome_details else ""}

Instructions:
- Determine if the documentation supports, contradicts, or is silent on the claim.
- Consider the probe outcome as additional evidence.
- Return a JSON object with exactly these keys:
  - "label": One of "Verified", "Supported", "Contradicted", "Unsupported"
  - "rationale": A brief explanation of your reasoning
  - "confidence": One of "high", "medium", "low"

Be strict: only mark "Verified" if the documentation explicitly supports the claim and the probe agrees.
Mark "Supported" if documentation supports the claim but probe evidence is limited.
Mark "Contradicted" if documentation contradicts the claim or probe disagrees with documentation.
Mark "Unsupported" if there is insufficient evidence either way.
"""
        return prompt


def llm_judge_claim(
    llm: LLMClient | None,
    claim_text: str,
    documentation: str,
    probe_outcome: str,
    probe_outcome_details: str | None = None,
) -> tuple[str, str, str]:
    """Convenience function to judge a claim using the LLM if available.

    Returns (label, rationale, confidence).
    Falls back to ("Unsupported", "LLM not configured", "low") if no LLM configured.
    """
    if llm is None or not llm.enabled:
        return "Unsupported", "LLM not configured", "low"

    judge = LLMValidationJudge(llm)
    return judge.judge_claim(claim_text, documentation, probe_outcome, probe_outcome_details)


class LLMJudgement:
    """Wrapper that adapts LLMValidationJudge to the EvidenceJudge protocol."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm
        self._judge = LLMValidationJudge(llm)

    def judge(self, claim, chunks: list[str]):
        """Judge a claim using the LLM evidence judge.

        Returns a DocumentJudgement with stance based on LLM evaluation.
        Falls back to SILENT if no LLM is available.
        """
        from .claims import DocumentJudgement
        from .enums import DocStance

        if self.llm is None or not self.llm.enabled:
            return DocumentJudgement(DocStance.SILENT, "LLM not configured", 0.0)

        # Combine all document chunks into documentation text
        documentation = "\n\n".join(chunks) if chunks else ""

        # Use the last probe outcome if available, otherwise unknown
        probe_outcome = "not_probed"
        probe_outcome_details = None

        label, rationale, confidence = self._judge.judge_claim(
            claim_text=claim.text,
            documentation=documentation,
            probe_outcome=probe_outcome,
            probe_outcome_details=probe_outcome_details,
        )

        # Map label to DocStance
        stance_map = {
            "Verified": DocStance.SUPPORTS,
            "Supported": DocStance.SUPPORTS,
            "Contradicted": DocStance.CONTRADICTS,
            "Unsupported": DocStance.SILENT,
        }
        stance = stance_map.get(label, DocStance.SILENT)

        # Confidence to score
        confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
        score = confidence_map.get(confidence, 0.5)

        return DocumentJudgement(
            stance=stance,
            description=f"{rationale} (confidence: {confidence})",
            score=score,
        )