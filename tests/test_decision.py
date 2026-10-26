from __future__ import annotations

import pytest

from agent_bazaar_auditor.decision import decide_label
from agent_bazaar_auditor.enums import ClaimLabel, DocStance, ProbeOutcome


@pytest.mark.parametrize(
    ("doc_stance", "probe_outcome", "expected"),
    [
        (DocStance.CONTRADICTS, ProbeOutcome.AGREES, ClaimLabel.CONTRADICTED),
        (DocStance.CONTRADICTS, ProbeOutcome.PROBE_ERROR, ClaimLabel.CONTRADICTED),
        (DocStance.SUPPORTS, ProbeOutcome.AGREES, ClaimLabel.VERIFIED),
        (DocStance.SUPPORTS, ProbeOutcome.DISAGREES, ClaimLabel.CONTRADICTED),
        (DocStance.SUPPORTS, ProbeOutcome.PROBE_ERROR, ClaimLabel.SUPPORTED),
        (DocStance.SUPPORTS, ProbeOutcome.NOT_PROBEABLE, ClaimLabel.SUPPORTED),
        (DocStance.SILENT, ProbeOutcome.AGREES, ClaimLabel.SUPPORTED),
        (DocStance.SILENT, ProbeOutcome.DISAGREES, ClaimLabel.CONTRADICTED),
        (DocStance.SILENT, ProbeOutcome.PROBE_ERROR, ClaimLabel.UNSUPPORTED),
        (DocStance.SILENT, ProbeOutcome.NOT_PROBED, ClaimLabel.UNSUPPORTED),
    ],
)
def test_four_label_decision_table(doc_stance: DocStance, probe_outcome: ProbeOutcome, expected: ClaimLabel) -> None:
    assert decide_label(doc_stance, probe_outcome) is expected
