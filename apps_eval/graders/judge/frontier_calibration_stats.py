"""2025-2026 Frontier Statistical Calibration: Dual-Uncertainty CI, PPI++, Alpha & Power (DIE Parity).

Implements strictly 2025-2026 LLM-as-a-Judge statistical calibration standards:
1. Google Cloud (2025-2026 `evaluate-judge-model`): `TPR`, `TNR`, `FPR`, `FNR`,
   and 2-class balanced accuracy.
2. Lee et al. (arXiv:2511.21140, 2025): Rogan-Gladen prevalence debiasing with
   dual-uncertainty 95% CI accounting for both evaluation and human-calibration sets.
3. Arawjo (`evalstats`, arXiv:2609.35815, 2026): Small-sample (`N < 100`) PPI++
   calibrated pass-rate estimator with variance-optimal power-tuning weight `lambda`.
4. Anthropic (2025-2026 `Demystifying Evals for AI Agents`): Multi-rater Krippendorff's
   alpha (sparse/abstained matrices), failure-tag recall, and `pass@k` / `pass^k`.
"""
from __future__ import annotations

import math
import random
from typing import Any, Mapping, Sequence


def compute_tpr_tnr_balanced_accuracy(
    human_verdicts: Sequence[str],
    judge_verdicts: Sequence[str],
) -> dict[str, Any]:
    """Compute confusion matrix, TPR (sensitivity), TNR (specificity), and balanced accuracy."""
    if len(human_verdicts) != len(judge_verdicts):
        raise ValueError("human_verdicts and judge_verdicts must have equal length.")
    tp = fp = tn = fn = 0
    for hv_raw, jv_raw in zip(human_verdicts, judge_verdicts):
        hv = str(hv_raw).strip().upper()
        jv = str(jv_raw).strip().upper()
        if hv == "PASS" and jv == "PASS":
            tp += 1
        elif hv == "FAIL" and jv == "PASS":
            fp += 1
        elif hv == "FAIL" and jv == "FAIL":
            tn += 1
        elif hv == "PASS" and jv == "FAIL":
            fn += 1
    pos = tp + fn
    neg = tn + fp
    tpr = round(tp / pos, 4) if pos > 0 else 0.0
    tnr = round(tn / neg, 4) if neg > 0 else 0.0
    fpr = round(fp / neg, 4) if neg > 0 else 1.0
    fnr = round(fn / pos, 4) if pos > 0 else 1.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "tpr": tpr,
        "tnr": tnr,
        "fpr": fpr,
        "fnr": fnr,
        "balanced_accuracy": round(0.5 * (tpr + tnr), 4),
    }


def _rogan_gladen_point(q_obs: float, tpr: float, tnr: float) -> tuple[float, bool]:
    denom = tpr + tnr - 1.0
    if denom <= 1e-6:
        return round(max(0.0, min(1.0, q_obs)), 4), True
    return round(max(0.0, min(1.0, (q_obs + tnr - 1.0) / denom)), 4), False


def compute_rogan_gladen_prevalence(
    observed_judge_pass_rate: float,
    tpr: float,
    tnr: float,
    *,
    human_verdicts: Sequence[str] = (),
    judge_verdicts: Sequence[str] = (),
    unlabeled_eval_n: int = 0,
    bootstrap_draws: int = 400,
    seed: int = 42,
) -> dict[str, Any]:
    """Compute Rogan-Gladen debiased prevalence + Lee et al. (2025) dual-uncertainty 95% CI."""
    q_obs = max(0.0, min(1.0, float(observed_judge_pass_rate)))
    point, degenerate = _rogan_gladen_point(q_obs, float(tpr), float(tnr))
    n = len(human_verdicts)
    if n < 2 or n != len(judge_verdicts) or bootstrap_draws <= 0:
        return {"corrected_pass_rate": point, "ci_95": [point, point], "degenerate": degenerate}

    cm_full = compute_tpr_tnr_balanced_accuracy(human_verdicts, judge_verdicts)
    m1 = max(1, cm_full["tp"] + cm_full["fn"])
    m0 = max(1, cm_full["tn"] + cm_full["fp"])
    n_test = max(n, int(unlabeled_eval_n))
    denom = max(1e-6, (cm_full["tpr"] + cm_full["tnr"] - 1.0))
    var_test = (q_obs * (1.0 - q_obs)) / n_test
    var_cal = ((point**2) * cm_full["tpr"] * (1.0 - cm_full["tpr"]) / m1) + (
        ((1.0 - point) ** 2) * cm_full["tnr"] * (1.0 - cm_full["tnr"]) / m0
    )
    se_dual = math.sqrt(max(0.0, (var_test + var_cal) / (denom**2))) if not degenerate else 0.5
    dual_lo = round(max(0.0, point - 1.96 * se_dual), 4)
    dual_hi = round(min(1.0, point + 1.96 * se_dual), 4)

    rng = random.Random(int(seed))
    samples: list[float] = []
    for _ in range(bootstrap_draws):
        idxs = [rng.randrange(n) for _ in range(n)]
        hb = [human_verdicts[i] for i in idxs]
        jb = [judge_verdicts[i] for i in idxs]
        cm = compute_tpr_tnr_balanced_accuracy(hb, jb)
        qb = sum(1 for v in jb if str(v).strip().upper() == "PASS") / n
        est_b, _ = _rogan_gladen_point(qb, cm["tpr"], cm["tnr"])
        samples.append(est_b)
    samples.sort()
    lo_b = round(samples[max(0, int(math.floor(0.025 * (len(samples) - 1))))], 4)
    hi_b = round(samples[min(len(samples) - 1, int(math.ceil(0.975 * (len(samples) - 1))))], 4)
    return {
        "corrected_pass_rate": point,
        "ci_95": [min(lo_b, dual_lo), max(hi_b, dual_hi)],
        "bootstrap_ci_95": [lo_b, hi_b],
        "dual_uncertainty_ci_95": [dual_lo, dual_hi],
        "degenerate": degenerate,
    }


def compute_ppi_calibrated_pass_rate(
    human_verdicts: Sequence[str],
    judge_verdicts: Sequence[str],
    *,
    unlabeled_judge_verdicts: Sequence[str] = (),
) -> dict[str, float]:
    """Compute small-sample PPI++ calibrated pass rate (Arawjo, arXiv:2609.35815, 2026)."""
    if len(human_verdicts) != len(judge_verdicts) or not human_verdicts:
        return {"ppi_pass_rate": 0.0, "lambda_opt": 0.0, "standard_error": 0.0}
    ys = [1.0 if str(v).strip().upper() == "PASS" else 0.0 for v in human_verdicts]
    fs = [1.0 if str(v).strip().upper() == "PASS" else 0.0 for v in judge_verdicts]
    n = len(ys)
    mean_y = sum(ys) / n
    mean_f = sum(fs) / n
    var_f = sum((f - mean_f) ** 2 for f in fs) / n
    cov_yf = sum((y - mean_y) * (f - mean_f) for y, f in zip(ys, fs)) / n
    all_f = fs + [1.0 if str(v).strip().upper() == "PASS" else 0.0 for v in unlabeled_judge_verdicts]
    N_total = len(all_f)
    scale = (N_total / (N_total + n)) if N_total > 0 else 0.0
    lam = max(0.0, min(1.0, (scale * cov_yf / var_f) if var_f > 1e-9 else 0.0))
    mean_f_all = sum(all_f) / N_total
    residuals = [y - lam * f for y, f in zip(ys, fs)]
    mean_res = sum(residuals) / n
    theta = max(0.0, min(1.0, lam * mean_f_all + mean_res))
    var_res = sum((r - mean_res) ** 2 for r in residuals) / max(1, n - 1) if n > 1 else 0.0
    se = math.sqrt((var_res / n) + ((lam**2) * var_f / max(1, N_total)))
    return {"ppi_pass_rate": round(theta, 4), "lambda_opt": round(lam, 4), "standard_error": round(se, 4)}


def compute_pass_at_k_and_pass_pow_k(trial_passes: Sequence[bool], k: int = 3) -> dict[str, float]:
    """Compute Anthropic (2026) stochastic reliability metrics `pass@k` and `pass^k`."""
    if not trial_passes or k < 1:
        return {"pass_at_k": 0.0, "pass_pow_k": 0.0}
    p = sum(1 for x in trial_passes if bool(x)) / len(trial_passes)
    return {
        "pass_at_k": round(1.0 - ((1.0 - p) ** k), 4),
        "pass_pow_k": round(p**k, 4),
    }


def _metric_delta_sq(a: Any, b: Any, level: str) -> float:
    if level == "nominal":
        return 0.0 if a == b else 1.0
    if level in {"ordinal", "interval"}:
        return (float(a) - float(b)) ** 2
    raise ValueError(f"Unsupported Krippendorff level {level!r}; use 'nominal' or 'ordinal'.")


def compute_krippendorffs_alpha(
    reliability_matrix: Sequence[Sequence[Any]],
    *,
    level: str = "nominal",
) -> float:
    """Compute Krippendorff's alpha across raters (rows) x items (cols), tolerating `None`."""
    if len(reliability_matrix) < 2:
        return 0.0
    n_items = len(reliability_matrix[0])
    if n_items == 0 or any(len(row) != n_items for row in reliability_matrix):
        raise ValueError("reliability_matrix rows must be non-empty and uniform width.")
    units = [
        vals
        for col in range(n_items)
        if len(vals := [row[col] for row in reliability_matrix if row[col] is not None]) >= 2
    ]
    all_vals = [v for unit in units for v in unit]
    n_total = len(all_vals)
    if n_total < 2:
        return 0.0
    obs_sum = sum(
        sum(_metric_delta_sq(u[i], u[j], level) for i in range(len(u)) for j in range(len(u)) if i != j)
        / (len(u) - 1)
        for u in units
    )
    d_o = obs_sum / n_total
    exp_sum = sum(
        _metric_delta_sq(all_vals[i], all_vals[j], level)
        for i in range(n_total)
        for j in range(n_total)
        if i != j
    )
    d_e = exp_sum / (n_total * (n_total - 1))
    if d_e <= 1e-12:
        return 1.0 if d_o <= 1e-12 else 0.0
    return round(max(-1.0, min(1.0, 1.0 - (d_o / d_e))), 4)


def classify_cohort_power(evaluated_cases: int) -> str:
    """Classify calibration cohort statistical power per 2025-2026 Google/frontier sizing."""
    n = int(evaluated_cases)
    if n < 30:
        return "UNDERPOWERED_PILOT"
    if n < 100:
        return "CALIBRATION_READY"
    return "FRONTIER_QUALIFIED"


def compute_failure_tag_detection_recall(
    human_records: Sequence[Any],
    judge_verdicts_by_case: Mapping[str, Mapping[str, Any]],
) -> dict[str, float]:
    """Compute per-failure-tag judge recall across human-labeled FAIL records."""
    totals: dict[str, int] = {}
    caught: dict[str, int] = {}
    for rec in human_records:
        if str(getattr(rec, "human_verdict", "")).upper() != "FAIL":
            continue
        tags = tuple(getattr(rec, "failure_tags", ()) or ())
        jv_obj = judge_verdicts_by_case.get(str(rec.case_id)) if tags else None
        if not jv_obj:
            continue
        j_verdict = str(jv_obj.get("verdict") or jv_obj.get("status") or "").strip().upper()
        for tag in tags:
            totals[tag] = totals.get(tag, 0) + 1
            if j_verdict == "FAIL":
                caught[tag] = caught.get(tag, 0) + 1
    return {tag: round(caught.get(tag, 0) / cnt, 4) for tag, cnt in sorted(totals.items()) if cnt > 0}


__all__ = [
    "classify_cohort_power",
    "compute_failure_tag_detection_recall",
    "compute_krippendorffs_alpha",
    "compute_pass_at_k_and_pass_pow_k",
    "compute_ppi_calibrated_pass_rate",
    "compute_rogan_gladen_prevalence",
    "compute_tpr_tnr_balanced_accuracy",
]
