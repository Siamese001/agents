"""Judge calibration and evaluation telemetry models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvaluationVerdict(str, Enum):
    """Standardized verdict for judge and evaluation outcomes."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"


@dataclass(frozen=True)
class EvaluationTelemetry:
    """Standardized telemetry record for judge and evaluation decisions."""

    evaluator_id: str
    criterion: str
    score: float
    threshold: float
    verdict: EvaluationVerdict
    confidence: float = 1.0
    reasoning_summary: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize evaluation record to dictionary."""
        return {
            "evaluator_id": self.evaluator_id,
            "criterion": self.criterion,
            "score": round(self.score, 4),
            "threshold": round(self.threshold, 4),
            "verdict": self.verdict.value,
            "confidence": round(self.confidence, 4),
            "reasoning_summary": self.reasoning_summary,
            "latency_ms": round(self.latency_ms, 2),
        }


@dataclass
class CalibrationProfile:
    """Configured baseline thresholds and bounds for judge calibration."""

    criterion_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "groundedness": 0.80,
            "brevity": 0.70,
            "relevance": 0.75,
            "competency_coverage": 0.85,
            "schema_compliance": 1.00,
        }
    )
    min_score: float = 0.0
    max_score: float = 1.0


class JudgeCalibrator:
    """Validates evaluation outputs against frozen calibration bounds and tracks drift."""

    def __init__(self, profile: CalibrationProfile | None = None) -> None:
        self.profile = profile or CalibrationProfile()

    def evaluate_score(
        self,
        evaluator_id: str,
        criterion: str,
        score: float,
        *,
        reasoning: str = "",
        latency_ms: float = 0.0,
        confidence: float = 1.0,
    ) -> EvaluationTelemetry:
        """Evaluate a score against calibrated thresholds, enforcing bounds."""
        clamped_score = max(self.profile.min_score, min(self.profile.max_score, score))
        threshold = self.profile.criterion_thresholds.get(criterion, 0.70)

        if clamped_score >= threshold:
            verdict = EvaluationVerdict.PASS
        elif clamped_score >= threshold - 0.15:
            verdict = EvaluationVerdict.WARN
        else:
            verdict = EvaluationVerdict.FAIL

        return EvaluationTelemetry(
            evaluator_id=evaluator_id,
            criterion=criterion,
            score=clamped_score,
            threshold=threshold,
            verdict=verdict,
            confidence=max(0.0, min(1.0, confidence)),
            reasoning_summary=reasoning,
            latency_ms=max(0.0, latency_ms),
        )

    def audit_evaluations(
        self,
        records: list[EvaluationTelemetry],
    ) -> dict[str, Any]:
        """Produce an aggregated calibration audit report over evaluation records."""
        if not records:
            return {
                "total_records": 0,
                "pass_count": 0,
                "warn_count": 0,
                "fail_count": 0,
                "pass_rate": 0.0,
                "drift_detected": False,
            }

        total = len(records)
        passes = sum(1 for r in records if r.verdict == EvaluationVerdict.PASS)
        warns = sum(1 for r in records if r.verdict == EvaluationVerdict.WARN)
        fails = sum(1 for r in records if r.verdict == EvaluationVerdict.FAIL)
        avg_score = sum(r.score for r in records) / total

        # Drift heuristic: significant skew or failure rate exceeding 40%
        drift_detected = (fails / total) > 0.40

        return {
            "total_records": total,
            "pass_count": passes,
            "warn_count": warns,
            "fail_count": fails,
            "pass_rate": round(passes / total, 4),
            "average_score": round(avg_score, 4),
            "drift_detected": drift_detected,
            "criteria_breakdown": {
                c: {
                    "count": sum(1 for r in records if r.criterion == c),
                    "mean_score": round(
                        sum(r.score for r in records if r.criterion == c)
                        / max(1, sum(1 for r in records if r.criterion == c)),
                        4,
                    ),
                }
                for c in {r.criterion for r in records}
            },
        }


__all__ = [
    "CalibrationProfile",
    "EvaluationTelemetry",
    "EvaluationVerdict",
    "JudgeCalibrator",
]
