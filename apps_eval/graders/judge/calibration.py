"""Statistical judge calibration (Kappa, Brier, ECE, single-class guard) and position-swap debiasing."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal, Sequence


@dataclass(frozen=True)
class PositionSwapResult:
    pair_id: str
    winner: Literal["A", "B", "INCONCLUSIVE"]
    status: Literal[
        "CONSISTENT_WIN",
        "INCONCLUSIVE_ORDER_BIAS",
        "INCONCLUSIVE_CONFIDENCE_SWING",
        "INCONCLUSIVE_INVALID_WINNER",
        "REJECTED_CONTAMINATED_SELECTION",
    ]
    forward_winner: str
    reverse_winner: str
    confidence_mean: float
    confidence_swing: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PositionSwapDebiaser:
    """Evaluates pairwise candidates in (A, B) and (B, A) order to eliminate position bias."""

    def __init__(self, *, margin_threshold: float = 0.20, max_order_bias_rate: float = 0.05) -> None:
        self.margin_threshold = margin_threshold
        self.max_order_bias_rate = max_order_bias_rate

    def evaluate_pair(
        self,
        *,
        pair_id: str,
        candidate_a: Any,
        candidate_b: Any,
        judge_fn: Callable[[Any, Any], tuple[str, float]],
        contaminated_side: Literal["A", "B"] | None = None,
    ) -> PositionSwapResult:
        fwd_choice, fwd_conf = judge_fn(candidate_a, candidate_b)
        rev_choice, rev_conf = judge_fn(candidate_b, candidate_a)

        fwd_norm = str(fwd_choice or "").strip().upper()
        rev_norm = str(rev_choice or "").strip().upper()
        if fwd_norm not in {"A", "B"} or rev_norm not in {"A", "B"}:
            return PositionSwapResult(
                pair_id=pair_id,
                winner="INCONCLUSIVE",
                status="INCONCLUSIVE_INVALID_WINNER",
                forward_winner=fwd_norm,
                reverse_winner=rev_norm,
                confidence_mean=0.0,
                confidence_swing=1.0,
            )

        # In reverse order (B, A), "A" means candidate_b won and "B" means candidate_a won.
        mapped_rev_winner = "B" if rev_norm == "A" else "A"
        swing = abs(float(fwd_conf) - float(rev_conf))
        conf_mean = round((float(fwd_conf) + float(rev_conf)) / 2.0, 4)

        if fwd_norm != mapped_rev_winner:
            return PositionSwapResult(
                pair_id=pair_id,
                winner="INCONCLUSIVE",
                status="INCONCLUSIVE_ORDER_BIAS",
                forward_winner=fwd_norm,
                reverse_winner=mapped_rev_winner,
                confidence_mean=conf_mean,
                confidence_swing=round(swing, 4),
            )

        if swing > self.margin_threshold:
            return PositionSwapResult(
                pair_id=pair_id,
                winner="INCONCLUSIVE",
                status="INCONCLUSIVE_CONFIDENCE_SWING",
                forward_winner=fwd_norm,
                reverse_winner=mapped_rev_winner,
                confidence_mean=conf_mean,
                confidence_swing=round(swing, 4),
            )

        if contaminated_side is not None and fwd_norm == contaminated_side:
            return PositionSwapResult(
                pair_id=pair_id,
                winner="INCONCLUSIVE",
                status="REJECTED_CONTAMINATED_SELECTION",
                forward_winner=fwd_norm,
                reverse_winner=mapped_rev_winner,
                confidence_mean=conf_mean,
                confidence_swing=round(swing, 4),
            )

        return PositionSwapResult(
            pair_id=pair_id,
            winner=fwd_norm,  # type: ignore[arg-type]
            status="CONSISTENT_WIN",
            forward_winner=fwd_norm,
            reverse_winner=mapped_rev_winner,
            confidence_mean=conf_mean,
            confidence_swing=round(swing, 4),
        )

    def evaluate_batch_gate(self, results: Sequence[PositionSwapResult]) -> tuple[bool, dict[str, Any]]:
        if not results:
            return False, {"reason": "EMPTY_BATCH"}
        total = len(results)
        order_bias_count = sum(1 for r in results if r.status == "INCONCLUSIVE_ORDER_BIAS")
        decoy_count = sum(1 for r in results if r.status == "REJECTED_CONTAMINATED_SELECTION")
        bias_rate = order_bias_count / float(total)
        passed = decoy_count == 0 and bias_rate <= self.max_order_bias_rate
        return passed, {
            "total_pairs": total,
            "order_bias_count": order_bias_count,
            "order_bias_rate": round(bias_rate, 4),
            "decoy_selected_count": decoy_count,
            "passed": passed,
        }


@dataclass(frozen=True)
class CalibrationReport:
    sample_size: int
    cohens_kappa: float
    brier_score: float
    ece: float
    accuracy: float
    recall: float
    single_class_collapse: bool
    passed: bool
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_cohens_kappa(y_true: Sequence[int], y_pred: Sequence[int]) -> float:
    n = len(y_true)
    if n == 0 or n != len(y_pred):
        return 0.0
    agree = sum(1 for a, b in zip(y_true, y_pred) if a == b)
    p_o = agree / float(n)
    labels = sorted(set(y_true) | set(y_pred))
    p_e = 0.0
    for lbl in labels:
        p_t = sum(1 for a in y_true if a == lbl) / float(n)
        p_p = sum(1 for b in y_pred if b == lbl) / float(n)
        p_e += p_t * p_p
    if math.isclose(1.0 - p_e, 0.0):
        return 1.0 if math.isclose(p_o, 1.0) else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def compute_brier_and_ece(
    y_true: Sequence[int],
    probs: Sequence[float],
    *,
    num_bins: int = 10,
) -> tuple[float, float]:
    n = len(y_true)
    if n == 0 or n != len(probs):
        return 1.0, 1.0
    brier = sum((float(p) - float(y)) ** 2 for y, p in zip(y_true, probs)) / float(n)
    ece = 0.0
    for b in range(num_bins):
        low = b / float(num_bins)
        high = (b + 1) / float(num_bins)
        bucket = [
            (float(y), float(p))
            for y, p in zip(y_true, probs)
            if (low <= float(p) < high) or (b == num_bins - 1 and float(p) == 1.0)
        ]
        if not bucket:
            continue
        acc = sum(y for y, _ in bucket) / float(len(bucket))
        conf = sum(p for _, p in bucket) / float(len(bucket))
        ece += (len(bucket) / float(n)) * abs(acc - conf)
    return brier, ece


class JudgeCalibrationRunner:
    """Computes fail-closed judge calibration metrics with single-class collapse protection."""

    def __init__(
        self,
        *,
        min_kappa: float = 0.82,
        max_brier: float = 0.10,
        max_ece: float = 0.15,
        min_accuracy: float = 0.85,
        min_recall: float = 0.85,
    ) -> None:
        self.min_kappa = min_kappa
        self.max_brier = max_brier
        self.max_ece = max_ece
        self.min_accuracy = min_accuracy
        self.min_recall = min_recall

    def evaluate(
        self,
        *,
        ground_truth: Sequence[int],
        predictions: Sequence[int],
        probabilities: Sequence[float],
    ) -> CalibrationReport:
        n = len(ground_truth)
        if n == 0 or n != len(predictions) or n != len(probabilities):
            return CalibrationReport(
                sample_size=n,
                cohens_kappa=0.0,
                brier_score=1.0,
                ece=1.0,
                accuracy=0.0,
                recall=0.0,
                single_class_collapse=True,
                passed=False,
                failure_reasons=["EMPTY_OR_MISMATCHED_CALIBRATION_INPUT"],
            )

        single_class = len(set(ground_truth)) < 2 or len(set(predictions)) < 2
        kappa = compute_cohens_kappa(ground_truth, predictions)
        brier, ece = compute_brier_and_ece(ground_truth, probabilities)
        accuracy = sum(1 for y, p in zip(ground_truth, predictions) if y == p) / float(n)
        positives = sum(1 for y in ground_truth if y == 1)
        tp = sum(1 for y, p in zip(ground_truth, predictions) if y == 1 and p == 1)
        recall = (tp / float(positives)) if positives > 0 else 0.0

        reasons: list[str] = []
        if single_class:
            reasons.append("SINGLE_CLASS_COLLAPSE")
        if kappa < self.min_kappa:
            reasons.append(f"KAPPA_BELOW_FLOOR:{kappa:.4f}<{self.min_kappa:.2f}")
        if brier > self.max_brier:
            reasons.append(f"BRIER_ABOVE_CEILING:{brier:.4f}>{self.max_brier:.2f}")
        if ece > self.max_ece:
            reasons.append(f"ECE_ABOVE_CEILING:{ece:.4f}>{self.max_ece:.2f}")
        if accuracy < self.min_accuracy:
            reasons.append(f"ACCURACY_BELOW_FLOOR:{accuracy:.4f}<{self.min_accuracy:.2f}")
        if recall < self.min_recall:
            reasons.append(f"RECALL_BELOW_FLOOR:{recall:.4f}<{self.min_recall:.2f}")

        return CalibrationReport(
            sample_size=n,
            cohens_kappa=round(kappa, 4),
            brier_score=round(brier, 4),
            ece=round(ece, 4),
            accuracy=round(accuracy, 4),
            recall=round(recall, 4),
            single_class_collapse=single_class,
            passed=len(reasons) == 0,
            failure_reasons=reasons,
        )


def evaluate_cross_family_judge_agreement(
    family_a_labels: Sequence[int],
    family_b_labels: Sequence[int],
    family_a_scores: Sequence[float],
    family_b_scores: Sequence[float],
    *,
    min_kappa: float = 0.82,
    min_agreement_rate: float = 0.85,
    max_mean_divergence: float = 0.35,
) -> dict[str, Any]:
    """Verify inter-family agreement between orthogonal judge families."""
    n = len(family_a_labels)
    if n == 0 or not (n == len(family_b_labels) == len(family_a_scores) == len(family_b_scores)):
        return {"passed": False, "reason": "EMPTY_OR_MISMATCHED_SERIES"}
    kappa = compute_cohens_kappa(family_a_labels, family_b_labels)
    agreement = sum(1 for a, b in zip(family_a_labels, family_b_labels) if a == b) / float(n)
    mean_div = sum(abs(float(a) - float(b)) for a, b in zip(family_a_scores, family_b_scores)) / float(n)
    reasons: list[str] = []
    if kappa < min_kappa:
        reasons.append(f"CROSS_FAMILY_KAPPA_LOW:{kappa:.4f}")
    if agreement < min_agreement_rate:
        reasons.append(f"CROSS_FAMILY_AGREEMENT_LOW:{agreement:.4f}")
    if mean_div > max_mean_divergence:
        reasons.append(f"CROSS_FAMILY_DIVERGENCE_HIGH:{mean_div:.4f}")
    return {
        "sample_size": n,
        "cohens_kappa": round(kappa, 4),
        "agreement_rate": round(agreement, 4),
        "mean_score_divergence": round(mean_div, 4),
        "passed": len(reasons) == 0,
        "failure_reasons": reasons,
    }
