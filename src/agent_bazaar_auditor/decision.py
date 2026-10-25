from __future__ import annotations

from .enums import ClaimLabel, DocStance, ProbeOutcome


def decide_label(doc_stance: DocStance, probe_outcome: ProbeOutcome) -> ClaimLabel:
    if doc_stance is DocStance.CONTRADICTS:
        return ClaimLabel.CONTRADICTED
    if doc_stance is DocStance.SUPPORTS:
        if probe_outcome is ProbeOutcome.AGREES:
            return ClaimLabel.VERIFIED
        if probe_outcome is ProbeOutcome.DISAGREES:
            return ClaimLabel.CONTRADICTED
        return ClaimLabel.SUPPORTED
    if probe_outcome is ProbeOutcome.AGREES:
        return ClaimLabel.SUPPORTED
    if probe_outcome is ProbeOutcome.DISAGREES:
        return ClaimLabel.CONTRADICTED
    return ClaimLabel.UNSUPPORTED


def explain_label(doc_stance: DocStance, probe_outcome: ProbeOutcome, label: ClaimLabel) -> str:
    document_text = {
        DocStance.SUPPORTS: "documentation supports the claim",
        DocStance.CONTRADICTS: "documentation contradicts the claim",
        DocStance.SILENT: "documentation is silent on the claim",
    }[doc_stance]
    probe_text = {
        ProbeOutcome.AGREES: "the probe agrees",
        ProbeOutcome.DISAGREES: "the probe disagrees",
        ProbeOutcome.NOT_PROBEABLE: "the claim cannot be probed",
        ProbeOutcome.NOT_PROBED: "the claim was not probed",
        ProbeOutcome.PROBE_ERROR: "the probe did not produce usable evidence",
    }[probe_outcome]
    return f"{document_text}; {probe_text}; decision table returns {label.value}."
