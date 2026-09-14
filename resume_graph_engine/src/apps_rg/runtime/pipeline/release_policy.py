"""Release Policy Service.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Gates final document release based on evaluation verdicts and gate thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

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
        """Evaluate whether document passes release criteria."""
        reasons: list[str] = []
        if not evaluation_reports:
            return ReleaseGateDecision(
                approved=False,
                rejection_reasons=("No evaluation reports provided.",),
                min_score_required=self.min_average_score,
                actual_average_score=0.0,
            )

        scores = [r.score for r in evaluation_reports.values()]
        avg_score = sum(scores) / len(scores)

        if avg_score < self.min_average_score:
            reasons.append(
                f"Average quality score {avg_score:.2f} is below release threshold {self.min_average_score:.2f}."
            )

        if self.require_all_pass:
            for sec_id, report in evaluation_reports.items():
                if not report.passed:
                    reasons.append(f"Section '{sec_id}' failed quality evaluation: {', '.join(report.violations)}.")

        return ReleaseGateDecision(
            approved=len(reasons) == 0,
            rejection_reasons=tuple(reasons),
            min_score_required=self.min_average_score,
            actual_average_score=avg_score,
        )
