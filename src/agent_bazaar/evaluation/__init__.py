"""Evaluation harness for field mapping quality, learning and cost."""

from agent_bazaar.evaluation.dataset import (
    MappingExample,
    agreement_report,
    apply_prelabels,
    cohen_kappa,
    export_unlabelled,
    load_dataset,
    save_dataset,
    to_field_spec,
)
from agent_bazaar.evaluation.learning_curve import (
    LearningCurveResult,
    ablation_table,
    curve_to_markdown,
    drift_accuracy,
    run_learning_curve,
)
from agent_bazaar.evaluation.metrics import (
    AccuracyReport,
    compute_accuracy,
    confusion_pairs,
    domain_of_concept,
    format_markdown_table,
    latency_stats,
    normalize_label,
    surface_accuracy_by_group,
    token_stats,
)

__all__ = [
    "AccuracyReport",
    "LearningCurveResult",
    "MappingExample",
    "ablation_table",
    "agreement_report",
    "apply_prelabels",
    "cohen_kappa",
    "compute_accuracy",
    "confusion_pairs",
    "curve_to_markdown",
    "domain_of_concept",
    "drift_accuracy",
    "export_unlabelled",
    "format_markdown_table",
    "latency_stats",
    "load_dataset",
    "normalize_label",
    "run_learning_curve",
    "save_dataset",
    "surface_accuracy_by_group",
    "to_field_spec",
    "token_stats",
]
