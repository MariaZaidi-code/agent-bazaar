from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .enums import ClaimLabel, ClaimType, DocStance
from .utils import normalize_text, stable_id, tokenize, utc_now

UNIT_ALIASES = {
    "c": "celsius",
    "°c": "celsius",
    "celsius": "celsius",
    "f": "fahrenheit",
    "°f": "fahrenheit",
    "fahrenheit": "fahrenheit",
    "kelvin": "kelvin",
    "usd": "usd",
    "dollar": "usd",
    "dollars": "usd",
    "pkr": "pkr",
    "rupee": "pkr",
    "rupees": "pkr",
    "km": "km",
    "kilometre": "km",
    "kilometer": "km",
    "m": "m",
    "meter": "m",
    "metre": "m",
    "second": "seconds",
    "seconds": "seconds",
    "minute": "minutes",
    "minutes": "minutes",
}

KNOWN_UNITS = {"celsius", "fahrenheit", "kelvin", "usd", "pkr", "km", "m", "seconds", "minutes"}


@dataclass
class Claim:
    id: str
    tool_id: str
    text: str
    claim_type: ClaimType
    field_path: str | None = None
    expected_type: str | None = None
    expected_unit: str | None = None
    expected_min: float | None = None
    expected_max: float | None = None
    expected_limit: int | None = None
    probeable: bool = False
    source_text: str = ""
    ground_truth_label: ClaimLabel | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_id": self.tool_id,
            "text": self.text,
            "claim_type": self.claim_type.value,
            "field_path": self.field_path,
            "expected_type": self.expected_type,
            "expected_unit": self.expected_unit,
            "expected_min": self.expected_min,
            "expected_max": self.expected_max,
            "expected_limit": self.expected_limit,
            "probeable": self.probeable,
            "source_text": self.source_text,
            "ground_truth_label": self.ground_truth_label.value if self.ground_truth_label else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Claim:
        return cls(
            id=data["id"],
            tool_id=data["tool_id"],
            text=data["text"],
            claim_type=ClaimType(data["claim_type"]),
            field_path=data.get("field_path"),
            expected_type=data.get("expected_type"),
            expected_unit=data.get("expected_unit"),
            expected_min=data.get("expected_min"),
            expected_max=data.get("expected_max"),
            expected_limit=data.get("expected_limit"),
            probeable=bool(data.get("probeable", False)),
            source_text=data.get("source_text", ""),
            ground_truth_label=ClaimLabel(data["ground_truth_label"]) if data.get("ground_truth_label") else None,
            metadata=dict(data.get("metadata", {})),
        )

    @property
    def key(self) -> str:
        return f"{self.tool_id}:{self.id}"


@dataclass
class Evidence:
    id: str
    claim_id: str
    kind: str
    source: str
    summary: str
    quote: str = ""
    doc_stance: DocStance | None = None
    probe_outcome: str | None = None
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "kind": self.kind,
            "source": self.source,
            "summary": self.summary,
            "quote": self.quote,
            "doc_stance": self.doc_stance.value if self.doc_stance else None,
            "probe_outcome": self.probe_outcome,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass
class DocumentJudgement:
    stance: DocStance
    quote: str
    score: float
    chunk_index: int = -1
    evidence: Evidence | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stance": self.stance.value,
            "quote": self.quote,
            "score": self.score,
            "chunk_index": self.chunk_index,
        }


def _extract_unit(text: str) -> str | None:
    lowered = text.lower()
    for alias, unit in sorted(UNIT_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = rf"(?<![\w]){re.escape(alias)}(?![\w])"
        if re.search(pattern, lowered):
            return unit
    return None


def _extract_field(text: str) -> str | None:
    backtick = re.search(r"`([a-zA-Z_][\w.]*)`", text)
    if backtick:
        return backtick.group(1)
    field = re.search(r"\bfield\s+([a-zA-Z_][\w.]*)", text, re.IGNORECASE)
    if field:
        return field.group(1)
    dotted = re.search(r"\b([a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*)\b", text)
    if dotted:
        return dotted.group()
    return None


def _extract_limit(text: str) -> int | None:
    patterns = [
        r"up to\s+(\d+)",
        r"maximum of\s+(\d+)",
        r"maximum\s+(\d+)",
        r"limit of\s+(\d+)",
        r"at most\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _unit_type(unit: str | None) -> str | None:
    if unit in {"celsius", "fahrenheit", "kelvin"}:
        return "number"
    if unit in {"usd", "pkr"}:
        return "number"
    return None


TYPE_HINTS = {
    "array": ("array", "arrays", "list", "lists", "json array"),
    "object": ("object", "objects", "json object", "dictionary", "map"),
    "number": ("number", "numbers", "numeric", "integer", "integers", "float", "decimal"),
    "string": ("string", "strings", "text"),
    "boolean": ("boolean", "booleans", "bool"),
}


def _field_mentioned(chunk: str, field_path: str | None) -> bool:
    if not field_path:
        return False
    leaf = field_path.split(".")[-1]
    for name in {field_path, leaf}:
        if re.search(rf"(?<![\w.]){re.escape(name)}(?![\w])", chunk):
            return True
    return False


def _hints_in_chunk(chunk: str) -> set[str]:
    lowered = chunk.lower()
    present: set[str] = set()
    for expected_type, hints in TYPE_HINTS.items():
        if any(re.search(rf"(?<![\w]){re.escape(hint)}(?![\w])", lowered) for hint in hints):
            present.add(expected_type)
    return present


class ClaimExtractor(Protocol):
    def extract(self, tool_id: str, chunks: list[str]) -> list[Claim]:
        ...


class HeuristicClaimExtractor:
    def extract(self, tool_id: str, chunks: list[str]) -> list[Claim]:
        claims: list[Claim] = []
        seen: set[str] = set()
        for chunk in chunks:
            sentences = re.split(r"(?<=[.!?])\s+", chunk.strip())
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                lowered = normalize_text(sentence)
                if "no api key" in lowered or "no key" in lowered or "keyless" in lowered:
                    created = self._make(
                        tool_id,
                        sentence,
                        ClaimType.AUTHENTICATION,
                        probeable=True,
                        expected_type="boolean",
                        metadata={"expects_key": False},
                    )
                elif "requires" in lowered and "key" in lowered:
                    created = self._make(
                        tool_id,
                        sentence,
                        ClaimType.AUTHENTICATION,
                        probeable=True,
                        expected_type="boolean",
                        metadata={"expects_key": True},
                    )
                else:
                    unit = _extract_unit(sentence)
                    field_path = _extract_field(sentence)
                    limit = _extract_limit(sentence)
                    if unit and field_path:
                        claim_type = ClaimType.UNIT if "degrees" in lowered or "unit" in lowered else ClaimType.OUTPUT_FIELD
                        created = self._make(
                            tool_id,
                            sentence,
                            claim_type,
                            field_path=field_path,
                            expected_type=_unit_type(unit) or "number",
                            expected_unit=unit,
                            probeable=True,
                        )
                    elif limit and ("day" in lowered or "result" in lowered or "forecast" in lowered):
                        created = self._make(
                            tool_id,
                            sentence,
                            ClaimType.LIMIT,
                            expected_type="number",
                            expected_limit=limit,
                            probeable=True,
                        )
                    elif any(word in lowered for word in ("always available", "uptime", "real-time", "real time")):
                        created = self._make(
                            tool_id,
                            sentence,
                            ClaimType.AVAILABILITY,
                            probeable=False,
                        )
                    elif field_path:
                        created = self._make(
                            tool_id,
                            sentence,
                            ClaimType.OUTPUT_FIELD,
                            field_path=field_path,
                            expected_type="present",
                            probeable=True,
                        )
                    else:
                        created = None
                if created and created.text.lower() not in seen:
                    seen.add(created.text.lower())
                    claims.append(created)
        return claims

    def _make(
        self,
        tool_id: str,
        sentence: str,
        claim_type: ClaimType,
        **kwargs: Any,
    ) -> Claim:
        return Claim(
            id=stable_id(tool_id, claim_type.value, sentence),
            tool_id=tool_id,
            text=sentence,
            claim_type=claim_type,
            source_text=sentence,
            **kwargs,
        )


class LLMClaimExtractor:
    def __init__(self, llm) -> None:
        self.llm = llm

    def extract(self, tool_id: str, chunks: list[str]) -> list[Claim]:
        prompt = (
            "Extract discrete testable claims from the documentation below. "
            "Return only JSON with a list named claims. Each item must contain text, "
            "claim_type (output_field, unit, authentication, limit, availability, behaviour), "
            "field_path, expected_unit, expected_type, expected_limit and probeable. "
            "Documentation:\n" + "\n".join(chunks)
        )
        payload = self.llm.complete_json(prompt)
        claims: list[Claim] = []
        for item in payload.get("claims", []):
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            claims.append(
                Claim(
                    id=stable_id(tool_id, "llm", text),
                    tool_id=tool_id,
                    text=text,
                    claim_type=ClaimType(item.get("claim_type", "behaviour")),
                    field_path=item.get("field_path"),
                    expected_type=item.get("expected_type"),
                    expected_unit=item.get("expected_unit"),
                    expected_limit=item.get("expected_limit"),
                    probeable=bool(item.get("probeable", False)),
                    source_text=text,
                    metadata={"extractor": "llm"},
                )
            )
        return claims


class EvidenceJudge(Protocol):
    def judge(self, claim: Claim, chunks: list[str]) -> DocumentJudgement:
        ...


class HeuristicEvidenceJudge:
    def judge(self, claim: Claim, chunks: list[str]) -> DocumentJudgement:
        if not chunks:
            return DocumentJudgement(DocStance.SILENT, "", 0.0)
        best = DocumentJudgement(DocStance.SILENT, "", 0.0)
        for index, chunk in enumerate(chunks):
            judgement = self._judge_chunk(claim, chunk, index)
            if judgement.score > best.score:
                best = judgement
        best.evidence = Evidence(
            id=stable_id(claim.id, "document", best.chunk_index),
            claim_id=claim.id,
            kind="document",
            source=f"{claim.tool_id}:documentation[{best.chunk_index}]",
            summary=f"Document evidence {best.stance.value}",
            quote=best.quote,
            doc_stance=best.stance,
        )
        return best

    def _judge_chunk(self, claim: Claim, chunk: str, index: int) -> DocumentJudgement:
        sentences = re.split(r"(?<=[.!?])\s+", chunk.strip())
        best_sentence = ""
        best_score = 0.0
        for sentence in sentences:
            overlap = len(tokenize(claim.text) & tokenize(sentence)) / max(1, len(tokenize(claim.text)))
            if overlap > best_score:
                best_score = overlap
                best_sentence = sentence.strip()
        lowered_chunk = normalize_text(chunk)
        if claim.claim_type is ClaimType.AUTHENTICATION:
            wants_no_key = not claim.metadata.get("expects_key", False)
            says_no_key = any(
                cue in lowered_chunk
                for cue in ("no api key", "no key", "keyless", "without an api key", "does not require a key")
            )
            says_key = bool(re.search(r"\b(api\s*key|key)\b", lowered_chunk)) and bool(
                re.search(r"\b(requir|need|mandat)", lowered_chunk)
            )
            if says_no_key and wants_no_key:
                return DocumentJudgement(DocStance.SUPPORTS, best_sentence, 0.95, index)
            if says_key and wants_no_key:
                return DocumentJudgement(DocStance.CONTRADICTS, best_sentence, 0.95, index)
            if says_key and not wants_no_key:
                return DocumentJudgement(DocStance.SUPPORTS, best_sentence, 0.95, index)
            if says_no_key and not wants_no_key:
                return DocumentJudgement(DocStance.CONTRADICTS, best_sentence, 0.95, index)
            return DocumentJudgement(DocStance.SILENT, best_sentence, best_score, index)
        if claim.claim_type in {ClaimType.UNIT, ClaimType.OUTPUT_FIELD} and claim.expected_unit:
            doc_unit = _extract_unit(chunk)
            if doc_unit and claim.expected_unit:
                if doc_unit == claim.expected_unit:
                    return DocumentJudgement(DocStance.SUPPORTS, best_sentence, 0.9, index)
                if doc_unit in KNOWN_UNITS and claim.expected_unit in KNOWN_UNITS:
                    return DocumentJudgement(DocStance.CONTRADICTS, best_sentence, 0.9, index)
        if claim.claim_type is ClaimType.LIMIT and claim.expected_limit is not None:
            doc_limit = _extract_limit(chunk)
            if doc_limit is not None:
                if doc_limit == claim.expected_limit:
                    return DocumentJudgement(DocStance.SUPPORTS, best_sentence, 0.9, index)
                return DocumentJudgement(DocStance.CONTRADICTS, best_sentence, 0.9, index)
        if claim.field_path and _field_mentioned(chunk, claim.field_path):
            hints = _hints_in_chunk(chunk)
            expected_type = (claim.expected_type or "").lower()
            if expected_type in {"present", "any"}:
                return DocumentJudgement(DocStance.SUPPORTS, best_sentence, 0.9, index)
            if expected_type in hints:
                return DocumentJudgement(DocStance.SUPPORTS, best_sentence, 0.9, index)
            if expected_type == "string" and not hints:
                return DocumentJudgement(DocStance.SUPPORTS, best_sentence, 0.75, index)
        negation = any(cue in lowered_chunk for cue in (" does not ", " cannot ", " not available", " no longer ", " never "))
        if best_score >= 0.5 and not negation:
            return DocumentJudgement(DocStance.SUPPORTS, best_sentence, best_score, index)
        if best_score >= 0.3 and negation:
            return DocumentJudgement(DocStance.CONTRADICTS, best_sentence, best_score, index)
        return DocumentJudgement(DocStance.SILENT, best_sentence, best_score, index)


class LLMEvidenceJudge:
    def __init__(self, llm) -> None:
        self.llm = llm

    def judge(self, claim: Claim, chunks: list[str]) -> DocumentJudgement:
        if not chunks:
            return DocumentJudgement(DocStance.SILENT, "", 0.0)
        prompt = (
            "Read the documentation passages and judge the claim. Return only JSON with fields "
            "stance (supports, contradicts or silent), quote (an exact supporting or contradicting passage, "
            "or an empty string), and rationale. Do not use outside knowledge.\n\n"
            f"Claim: {claim.text}\nClaim type: {claim.claim_type.value}\n"
            f"Expected unit: {claim.expected_unit}\nExpected limit: {claim.expected_limit}\n\n"
            "Documentation passages:\n" + "\n---\n".join(chunks)
        )
        payload = self.llm.complete_json(prompt)
        stance = DocStance(str(payload.get("stance", "silent")).lower())
        quote = str(payload.get("quote", "")).strip()
        evidence = Evidence(
            id=stable_id(claim.id, "llm-document"),
            claim_id=claim.id,
            kind="document",
            source=f"{claim.tool_id}:llm-documentation-judgement",
            summary=str(payload.get("rationale", f"LLM judged documentation {stance.value}")),
            quote=quote,
            doc_stance=stance,
            metadata={"judge": "llm"},
        )
        return DocumentJudgement(stance, quote, 0.99 if stance is not DocStance.SILENT else 0.0, 0, evidence)


class ScriptedEvidenceJudge:
    def __init__(self, stances: dict[str, DocStance] | None = None) -> None:
        self.stances = stances or {}

    def judge(self, claim: Claim, chunks: list[str]) -> DocumentJudgement:
        stance = self.stances.get(claim.id)
        if stance is None:
            stance = DocStance(claim.metadata.get("scripted_doc_stance", "silent"))
        quote = claim.metadata.get("scripted_quote", claim.source_text)
        evidence = Evidence(
            id=stable_id(claim.id, "scripted-document"),
            claim_id=claim.id,
            kind="document",
            source=f"{claim.tool_id}:seeded-documentation",
            summary=f"Seeded document evidence {stance.value}",
            quote=quote,
            doc_stance=stance,
        )
        return DocumentJudgement(stance, quote, 0.99 if stance is not DocStance.SILENT else 0.0, 0, evidence)
