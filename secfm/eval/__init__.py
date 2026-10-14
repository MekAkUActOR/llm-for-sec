"""评估骨架（docs/01 §5）。"""

from .metrics import (asr, capability_accuracy, expected_calibration_error,
                      over_refusal_rate, pareto_points, policy_compliance_matrix)
from .registry import Suite, run_suite
from .report import render_markdown, to_jsonl
from .schema import DOMAINS, KINDS, EvalItem, ResultRecord, score

__all__ = [
    "KINDS", "DOMAINS", "EvalItem", "ResultRecord", "score",
    "Suite", "run_suite",
    "asr", "over_refusal_rate", "capability_accuracy",
    "expected_calibration_error", "pareto_points", "policy_compliance_matrix",
    "render_markdown", "to_jsonl",
]
