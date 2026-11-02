"""Release Policy Service.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Gates final document release based on evaluation verdicts and gate thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from agents.orchestration.services.release_policy import evaluate_score_threshold_reports
from apps_rg.runtime.pipeline.evaluation import EvaluationReport


@dataclass(frozen=True, slots=True)
class ReleaseGateDecision:
    """Decision whether a generated document is certified for release."""

    approved: bool
    rejection_reasons: tuple[str, ...]
    min_score_required: float
    actual_average_score: float


class ReleasePolicy:
    """Policy governing certification of assembled artifacts for release."""

    def __init__(self, min_average_score: float = 0.80, require_all_pass: bool = True) -> None:
        self.min_average_score = min_average_score
        self.require_all_pass = require_all_pass

    def evaluate_release(
        self,
        evaluation_reports: Mapping[str, EvaluationReport],
    ) -> ReleaseGateDecision:
        """Evaluate whether document passes release criteria via shared orchestration evaluator."""
        approved, reasons, avg_score = evaluate_score_threshold_reports(
            evaluation_reports,
            min_average_score=self.min_average_score,
            require_all_pass=self.require_all_pass,
        )
        return ReleaseGateDecision(
            approved=approved,
            rejection_reasons=reasons,
            min_score_required=self.min_average_score,
            actual_average_score=avg_score,
        )
