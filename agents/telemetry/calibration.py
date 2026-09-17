"""Judge calibration, evaluation telemetry models, and statistical drift detection.

Part of Sovereign Agentic Platform System Learning Rigor (Wave 2).
Provides empirical statistical calibration:
1. Rolling window EWMA score tracking and variance analysis.
2. Z-score anomaly and distribution drift detection.
3. Multi-judge inter-rater reliability and Cohen's Kappa concordance metrics.
4. Backward-compatible threshold evaluation and aggregated auditing.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Sequence


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


class StatisticalDriftDetector:
    """Tracks empirical score distributions per criterion using rolling window statistics and EWMA."""

    def __init__(self, window_size: int = 100, alpha: float = 0.20) -> None:
        self.window_size = max(10, window_size)
        self.alpha = max(0.01, min(0.99, alpha))
        self._history: dict[str, deque[float]] = {}
        self._ewma: dict[str, float] = {}

    def record(self, criterion: str, score: float) -> None:
        """Record an observed score and update EWMA and rolling history."""
        if criterion not in self._history:
            self._history[criterion] = deque(maxlen=self.window_size)
            self._ewma[criterion] = score
        else:
            prev = self._ewma[criterion]
            self._ewma[criterion] = (self.alpha * score) + ((1.0 - self.alpha) * prev)

        self._history[criterion].append(score)

    def get_stats(self, criterion: str) -> dict[str, Any]:
        """Calculate statistical distribution metrics for a criterion."""
        window = self._history.get(criterion)
        if not window:
            return {
                "count": 0,
                "mean": 0.0,
                "std_dev": 0.0,
                "ewma": 0.0,
                "min": 0.0,
                "max": 0.0,
            }

        count = len(window)
        mean = sum(window) / count
        variance = sum((x - mean) ** 2 for x in window) / max(1, count - 1) if count > 1 else 0.0
        std_dev = math.sqrt(variance)

        return {
            "count": count,
            "mean": round(mean, 4),
            "std_dev": round(std_dev, 4),
            "ewma": round(self._ewma.get(criterion, mean), 4),
            "min": round(min(window), 4),
            "max": round(max(window), 4),
        }

    def compute_z_score(self, criterion: str, current_score: float) -> float:
        """Compute the z-score of a given score against the historical distribution."""
        stats = self.get_stats(criterion)
        std_dev = stats["std_dev"]
        if stats["count"] < 3 or std_dev < 1e-6:
            return 0.0
        return round((current_score - stats["mean"]) / std_dev, 4)

    def detect_drift(
        self,
        criterion: str,
        baseline_threshold: float,
        *,
        z_threshold: float = 2.0,
    ) -> dict[str, Any]:
        """Evaluate whether a criterion exhibits significant statistical drift."""
        stats = self.get_stats(criterion)
        if stats["count"] < 5:
            return {
                "drift_detected": False,
                "reason": "Insufficient samples for statistical drift detection.",
                "z_score": 0.0,
                "stats": stats,
            }

        ewma = stats["ewma"]
        std_dev = stats["std_dev"]
        z_score = (ewma - baseline_threshold) / max(std_dev, 0.05)

        # Drift triggered if EWMA drops below baseline by z_threshold std deviations or drops into WARN territory
        drift_detected = (
            z_score < -z_threshold
            or abs(z_score) > (z_threshold * 1.5)
            or ewma < (baseline_threshold - 0.15)
        )
        reason = "Within normal statistical variation."
        if drift_detected:
            if ewma < (baseline_threshold - 0.15) or z_score < -z_threshold:
                reason = f"Severe score deflation detected: EWMA {ewma:.3f} is below baseline {baseline_threshold:.3f} (z-score: {z_score:.2f})."
            else:
                reason = f"Significant score distribution anomaly: z-score {z_score:.2f} exceeds threshold {z_threshold:.2f}."

        return {
            "drift_detected": drift_detected,
            "z_score": round(z_score, 4),
            "reason": reason,
            "stats": stats,
        }


def calculate_inter_rater_concordance(
    evaluator_a_records: Sequence[EvaluationTelemetry],
    evaluator_b_records: Sequence[EvaluationTelemetry],
) -> dict[str, Any]:
    """Calculate Cohen's Kappa inter-rater agreement between two evaluation streams."""
    # Match records by (criterion, index)
    paired: list[tuple[EvaluationVerdict, EvaluationVerdict]] = []
    min_len = min(len(evaluator_a_records), len(evaluator_b_records))
    for i in range(min_len):
        ra = evaluator_a_records[i]
        rb = evaluator_b_records[i]
        if ra.criterion == rb.criterion:
            paired.append((ra.verdict, rb.verdict))

    if not paired:
        return {
            "paired_count": 0,
            "observed_agreement": 0.0,
            "expected_chance_agreement": 0.0,
            "cohens_kappa": 1.0,
            "agreement_strength": "NONE",
        }

    total = len(paired)
    matching = sum(1 for a, b in paired if a == b)
    p_observed = matching / total

    verdicts = (EvaluationVerdict.PASS, EvaluationVerdict.WARN, EvaluationVerdict.FAIL)
    a_dist = {v: sum(1 for a, _ in paired if a == v) / total for v in verdicts}
    b_dist = {v: sum(1 for _, b in paired if b == v) / total for v in verdicts}

    p_expected = sum(a_dist[v] * b_dist[v] for v in verdicts)

    if 1.0 - p_expected < 1e-9:
        kappa = 1.0
    else:
        kappa = (p_observed - p_expected) / (1.0 - p_expected)

    # Landis & Koch (1977) scale
    if kappa >= 0.81:
        strength = "ALMOST_PERFECT"
    elif kappa >= 0.61:
        strength = "SUBSTANTIAL"
    elif kappa >= 0.41:
        strength = "MODERATE"
    elif kappa >= 0.21:
        strength = "FAIR"
    elif kappa >= 0.0:
        strength = "SLIGHT"
    else:
        strength = "POOR"

    return {
        "paired_count": total,
        "observed_agreement": round(p_observed, 4),
        "expected_chance_agreement": round(p_expected, 4),
        "cohens_kappa": round(max(-1.0, min(1.0, kappa)), 4),
        "agreement_strength": strength,
    }


class JudgeCalibrator:
    """Validates evaluation outputs against frozen calibration bounds and tracks statistical drift."""

    def __init__(
        self,
        profile: CalibrationProfile | None = None,
        drift_detector: StatisticalDriftDetector | None = None,
    ) -> None:
        self.profile = profile or CalibrationProfile()
        self.drift_detector = drift_detector or StatisticalDriftDetector()

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
        """Evaluate a score against calibrated thresholds, enforcing bounds and updating drift detector."""
        clamped_score = max(self.profile.min_score, min(self.profile.max_score, score))
        threshold = self.profile.criterion_thresholds.get(criterion, 0.70)

        # Track score in statistical drift detector
        self.drift_detector.record(criterion, clamped_score)

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
                "average_score": 0.0,
                "drift_detected": False,
                "criteria_breakdown": {},
            }

        total = len(records)
        passes = sum(1 for r in records if r.verdict == EvaluationVerdict.PASS)
        warns = sum(1 for r in records if r.verdict == EvaluationVerdict.WARN)
        fails = sum(1 for r in records if r.verdict == EvaluationVerdict.FAIL)
        avg_score = sum(r.score for r in records) / total

        # Check legacy drift heuristic
        legacy_drift = (fails / total) > 0.40

        # Check statistical drift for each criterion
        criteria_breakdown: dict[str, Any] = {}
        any_stat_drift = False
        for c in {r.criterion for r in records}:
            c_records = [r for r in records if r.criterion == c]
            c_mean = sum(r.score for r in c_records) / len(c_records)
            thresh = self.profile.criterion_thresholds.get(c, 0.70)
            drift_res = self.drift_detector.detect_drift(c, thresh)
            if drift_res["drift_detected"]:
                any_stat_drift = True

            criteria_breakdown[c] = {
                "count": len(c_records),
                "mean_score": round(c_mean, 4),
                "threshold": thresh,
                "drift_detected": drift_res["drift_detected"],
                "z_score": drift_res["z_score"],
            }

        return {
            "total_records": total,
            "pass_count": passes,
            "warn_count": warns,
            "fail_count": fails,
            "pass_rate": round(passes / total, 4),
            "average_score": round(avg_score, 4),
            "drift_detected": legacy_drift or any_stat_drift,
            "statistical_drift_detected": any_stat_drift,
            "criteria_breakdown": criteria_breakdown,
        }

    def audit_evaluations_statistical(
        self,
        records: list[EvaluationTelemetry],
    ) -> dict[str, Any]:
        """Produce rich empirical statistical drift audit report."""
        base_audit = self.audit_evaluations(records)
        stats_summary: dict[str, Any] = {}
        for c in {r.criterion for r in records}:
            thresh = self.profile.criterion_thresholds.get(c, 0.70)
            stats_summary[c] = self.drift_detector.detect_drift(c, thresh)

        base_audit["detailed_statistical_drift"] = stats_summary
        return base_audit


__all__ = [
    "CalibrationProfile",
    "EvaluationTelemetry",
    "EvaluationVerdict",
    "JudgeCalibrator",
    "StatisticalDriftDetector",
    "calculate_inter_rater_concordance",
]
