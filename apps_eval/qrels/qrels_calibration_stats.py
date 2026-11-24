"""Statistical Calibration, Retrieval Metrics & Hash-Bound Kappa Verification (DIE Parity).

Implements:
- Unweighted Cohen's Kappa and Quadratic-Weighted Kappa (`>= 0.80` gate)
- Sparse Krippendorff's Alpha (ordinal/interval handling `None` abstentions)
- One-sided 95% binomial upper error bounds
- Graded NDCG@K (2^rel - 1 over 0..3), MRR@K (rel >= 2), Recall@K
- Deterministic paired-bootstrap 95% CIs and one-sided p-values
- Cryptographic SHA-256 Kappa calibration receipt sealing and fail-closed verification
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any


def calculate_one_sided_upper_error_bound(sample_size: int, confidence: float = 0.95) -> float:
    """One-sided upper error bound for zero observed errors under Binomial distribution."""
    if sample_size <= 0:
        return 1.0
    return round(1.0 - (1.0 - confidence) ** (1.0 / sample_size), 6)


def compute_cohens_kappa(
    ratings_a: Sequence[int],
    ratings_b: Sequence[int],
    labels: tuple[int, ...] = (0, 1, 2, 3),
) -> float:
    """Compute unweighted Cohen's Kappa across multi-class relevance judgments."""
    n = len(ratings_a)
    if n == 0 or n != len(ratings_b):
        return 0.0
    observed = sum(1 for a, b in zip(ratings_a, ratings_b) if int(a) == int(b)) / n
    expected = sum((sum(1 for a in ratings_a if int(a) == k) / n) * (sum(1 for b in ratings_b if int(b) == k) / n) for k in labels)
    if abs(1.0 - expected) < 1e-12:
        return 1.0
    return round((observed - expected) / (1.0 - expected), 4)


def compute_quadratic_weighted_kappa(
    ratings_a: Sequence[int],
    ratings_b: Sequence[int],
    labels: tuple[int, ...] = (0, 1, 2, 3),
) -> float:
    """Compute quadratic-weighted Kappa across 0..3 ordinal relevance grades."""
    n = len(ratings_a)
    if n == 0 or n != len(ratings_b):
        return 0.0
    max_diff_sq = float((max(labels) - min(labels)) ** 2) or 1.0
    obs_dis = sum(((int(a) - int(b)) ** 2) / max_diff_sq for a, b in zip(ratings_a, ratings_b)) / n
    exp_dis = 0.0
    for i in labels:
        pi = sum(1 for a in ratings_a if int(a) == i) / n
        for j in labels:
            pj = sum(1 for b in ratings_b if int(b) == j) / n
            exp_dis += pi * pj * (((i - j) ** 2) / max_diff_sq)
    if exp_dis < 1e-12:
        return 1.0
    return round(1.0 - (obs_dis / exp_dis), 4)


def compute_bootstrap_kappa_ci95(
    ratings_a: Sequence[int],
    ratings_b: Sequence[int],
    *,
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """Compute deterministic 95% non-parametric bootstrap CI for Cohen's Kappa (DIE Parity)."""
    n = len(ratings_a)
    if n == 0 or n != len(ratings_b):
        return 0.0, 0.0
    rng = random.Random(int(seed))
    samples: list[float] = []
    for _ in range(max(100, int(n_boot))):
        idxs = [rng.randrange(n) for _ in range(n)]
        sa = [int(ratings_a[i]) for i in idxs]
        sb = [int(ratings_b[i]) for i in idxs]
        samples.append(compute_cohens_kappa(sa, sb))
    samples.sort()
    lo_idx = max(0, int(0.025 * len(samples)))
    hi_idx = min(len(samples) - 1, int(0.975 * len(samples)))
    return round(samples[lo_idx], 4), round(samples[hi_idx], 4)


def compute_sparse_krippendorffs_alpha(rater_matrix: Sequence[Sequence[float | int | None]]) -> float:
    """Compute interval Krippendorff's Alpha supporting sparse `None` abstentions across >= 2 raters."""
    if not rater_matrix:
        return 0.0
    n_items = len(rater_matrix[0])
    if n_items == 0:
        return 0.0

    item_values: list[list[float]] = []
    all_values: list[float] = []
    for col in range(n_items):
        vals = [float(row[col]) for row in rater_matrix if col < len(row) and row[col] is not None]
        if len(vals) >= 2:
            item_values.append(vals)
            all_values.extend(vals)

    total_n = len(all_values)
    if total_n < 2 or not item_values:
        return 0.0

    # Observed disagreement Do
    do_num = 0.0
    for vals in item_values:
        m_u = len(vals)
        pair_sum = sum((vals[i] - vals[j]) ** 2 for i in range(m_u) for j in range(m_u))
        do_num += pair_sum / (m_u - 1)
    d_obs = do_num / total_n

    # Expected disagreement De
    mean_all = sum(all_values) / total_n
    var_sum = sum((v - mean_all) ** 2 for v in all_values)
    d_exp = (2.0 * var_sum) / (total_n - 1) if total_n > 1 else 0.0
    if d_exp <= 1e-12:
        return 1.0 if d_obs <= 1e-12 else 0.0
    return round(1.0 - (d_obs / d_exp), 4)


def compute_ndcg_at_k(ranked_grades: Sequence[int], *, k: int = 10) -> float:
    """Compute graded NDCG@K using exponential gains (2^rel - 1) over 0..3 grades."""
    if not ranked_grades or k <= 0:
        return 0.0
    top = [int(g) for g in ranked_grades[:k]]
    dcg = sum(((2 ** rel) - 1.0) / math.log2(idx + 2) for idx, rel in enumerate(top))
    ideal = sorted((int(g) for g in ranked_grades), reverse=True)[:k]
    idcg = sum(((2 ** rel) - 1.0) / math.log2(idx + 2) for idx, rel in enumerate(ideal))
    if idcg <= 1e-12:
        return 0.0
    return round(dcg / idcg, 6)


def compute_mrr_at_k(ranked_grades: Sequence[int], *, k: int = 10, relevant_floor: int = 2) -> float:
    """Compute Reciprocal Rank@K using relevant_floor (default Grade >= 2)."""
    for idx, grade in enumerate(ranked_grades[:k], start=1):
        if int(grade) >= relevant_floor:
            return round(1.0 / idx, 6)
    return 0.0


def compute_recall_at_k(ranked_grades: Sequence[int], *, k: int = 10, relevant_floor: int = 2) -> float:
    """Compute Recall@K over all relevant items (grade >= relevant_floor) in the judged pool."""
    total_rel = sum(1 for g in ranked_grades if int(g) >= relevant_floor)
    if total_rel == 0:
        return 0.0
    hits = sum(1 for g in ranked_grades[:k] if int(g) >= relevant_floor)
    return round(hits / total_rel, 6)


def paired_bootstrap_ndcg_ci(
    system_scores: Sequence[float],
    baseline_scores: Sequence[float],
    *,
    n_resamples: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    """Deterministic paired-bootstrap 95% CI and one-sided p-value for (system - baseline)."""
    n = min(len(system_scores), len(baseline_scores))
    if n == 0:
        return {
            "sample_size": 0,
            "mean_diff": 0.0,
            "ci_95_low": 0.0,
            "ci_95_high": 0.0,
            "p_value_one_sided": 1.0,
            "statistically_significant_p05": False,
        }
    diffs = [float(system_scores[i]) - float(baseline_scores[i]) for i in range(n)]
    obs_mean = sum(diffs) / n
    rng = random.Random(int(seed))
    boot_means: list[float] = []
    non_positive = 0
    for _ in range(max(100, int(n_resamples))):
        sample_mean = sum(diffs[rng.randrange(n)] for _ in range(n)) / n
        boot_means.append(sample_mean)
        if sample_mean <= 0.0:
            non_positive += 1
    boot_means.sort()
    lo_idx = int(0.025 * len(boot_means))
    hi_idx = min(len(boot_means) - 1, int(0.975 * len(boot_means)))
    p_val = round(non_positive / len(boot_means), 4)
    return {
        "sample_size": n,
        "mean_diff": round(obs_mean, 4),
        "ci_95_low": round(boot_means[lo_idx], 4),
        "ci_95_high": round(boot_means[hi_idx], 4),
        "p_value_one_sided": p_val,
        "statistically_significant_p05": p_val < 0.05 and obs_mean > 0.0,
    }


def compute_kappa_receipt_hashes(
    evaluated_queries: Sequence[Mapping[str, Any]],
    human_grades: Sequence[int],
    grader_grades: Sequence[int],
    cohens_kappa: float,
    weighted_kappa: float,
) -> tuple[str, str]:
    """Compute deterministic SHA-256 digests binding evaluated queries and anchor calibration."""
    eq_bytes = json.dumps(list(evaluated_queries), sort_keys=True, separators=(",", ":")).encode("utf-8")
    eq_sha = hashlib.sha256(eq_bytes).hexdigest()
    core_payload = {
        "evaluated_queries_sha256": eq_sha,
        "human_gold_grades": [int(x) for x in human_grades],
        "blind_grader_grades": [int(x) for x in grader_grades],
        "cohens_kappa": round(float(cohens_kappa), 4),
        "quadratic_weighted_kappa": round(float(weighted_kappa), 4),
    }
    art_bytes = json.dumps(core_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return eq_sha, hashlib.sha256(art_bytes).hexdigest()


def verify_kappa_calibration_receipt(
    ground_truth_data: Mapping[str, Any],
    *,
    min_anchor_passages: int = 20,
    min_total_human_labels: int = 0,
    kappa_floor: float = 0.80,
    ci95_lower_floor: float = 0.0,
    expected_grader_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify hash-bound Kappa calibration receipt fail-closed against raw evaluated_queries bytes."""
    receipt = ground_truth_data.get("kappa_calibration_receipt")
    if not isinstance(receipt, Mapping):
        return {
            "is_valid": False,
            "reason": "missing_kappa_calibration_receipt",
            "anchor_passages_evaluated": 0,
            "total_human_passage_labels": 0,
            "cohens_kappa": 0.0,
            "quadratic_weighted_kappa": 0.0,
            "kappa_ci95_low": 0.0,
            "kappa_ci95_high": 0.0,
        }
    human = [int(x) for x in receipt.get("human_gold_grades") or []]
    grader = [int(x) for x in receipt.get("blind_grader_grades") or []]
    total_human_labels = int(receipt.get("total_human_passage_labels", len(human)))
    if len(human) < min_anchor_passages or total_human_labels < min_total_human_labels or len(human) != len(grader):
        return {
            "is_valid": False,
            "reason": "insufficient_or_mismatched_anchor_grades",
            "anchor_passages_evaluated": len(human),
            "total_human_passage_labels": total_human_labels,
            "cohens_kappa": 0.0,
            "quadratic_weighted_kappa": 0.0,
            "kappa_ci95_low": 0.0,
            "kappa_ci95_high": 0.0,
        }
    if float(receipt.get("external_api_cost_usd", 0.0)) > 0.0:
        return {
            "is_valid": False,
            "reason": "nonzero_external_api_cost",
            "anchor_passages_evaluated": len(human),
            "total_human_passage_labels": total_human_labels,
            "cohens_kappa": 0.0,
            "quadratic_weighted_kappa": 0.0,
            "kappa_ci95_low": 0.0,
            "kappa_ci95_high": 0.0,
        }
    if expected_grader_sha256 is not None:
        recorded_grader_sha = str(receipt.get("grader_source_sha256") or "")
        if recorded_grader_sha != expected_grader_sha256:
            return {
                "is_valid": False,
                "reason": "grader_source_sha256_mismatch",
                "anchor_passages_evaluated": len(human),
                "total_human_passage_labels": total_human_labels,
                "cohens_kappa": 0.0,
                "quadratic_weighted_kappa": 0.0,
                "kappa_ci95_low": 0.0,
                "kappa_ci95_high": 0.0,
            }
    ck = compute_cohens_kappa(human, grader)
    qwk = compute_quadratic_weighted_kappa(human, grader)
    ci_low, ci_high = compute_bootstrap_kappa_ci95(human, grader, n_boot=500, seed=42)
    eq_sha, expected_art_sha = compute_kappa_receipt_hashes(
        ground_truth_data.get("evaluated_queries") or [],
        human,
        grader,
        ck,
        qwk,
    )
    hashes_match = (
        receipt.get("evaluated_queries_sha256") == eq_sha
        and receipt.get("artifact_sha256") == expected_art_sha
        and abs(float(receipt.get("cohens_kappa", 0.0)) - ck) <= 1e-4
        and abs(float(receipt.get("quadratic_weighted_kappa", 0.0)) - qwk) <= 1e-4
    )
    passed = hashes_match and ck >= kappa_floor and qwk >= kappa_floor and ci_low >= ci95_lower_floor
    return {
        "is_valid": passed,
        "reason": (
            "verified"
            if passed
            else (
                "hash_tamper_detected"
                if not hashes_match
                else (
                    "kappa_below_threshold"
                    if (ck < kappa_floor or qwk < kappa_floor)
                    else "kappa_ci95_below_threshold"
                )
            )
        ),
        "anchor_passages_evaluated": len(human),
        "total_human_passage_labels": total_human_labels,
        "cohens_kappa": ck,
        "quadratic_weighted_kappa": qwk,
        "kappa_ci95_low": ci_low,
        "kappa_ci95_high": ci_high,
        "evaluated_queries_sha256": eq_sha,
        "artifact_sha256": expected_art_sha,
    }


__all__ = [
    "calculate_one_sided_upper_error_bound",
    "compute_bootstrap_kappa_ci95",
    "compute_cohens_kappa",
    "compute_kappa_receipt_hashes",
    "compute_mrr_at_k",
    "compute_ndcg_at_k",
    "compute_quadratic_weighted_kappa",
    "compute_recall_at_k",
    "compute_sparse_krippendorffs_alpha",
    "paired_bootstrap_ndcg_ci",
    "verify_kappa_calibration_receipt",
]
