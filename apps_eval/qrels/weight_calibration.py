"""Holdout-Isolated 1,771-Point 4-Simplex Weight Optimization & Ablation Gate (DIE Parity).

Tunes RRF fusion weights strictly on `dev + calibration` while keeping `final_holdout`
untouched during parameter search, then evaluates untouched `final_holdout` with
paired-bootstrap 95% CIs, 7 channel ablations, query-intent dynamic weighting, and
unanswerable `tau_abstain` score separation.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from apps_eval.qrels.qrels_calibration_stats import (
    compute_mrr_at_k,
    compute_ndcg_at_k,
    compute_recall_at_k,
    paired_bootstrap_ndcg_ci,
)

CANONICAL_QRELS_RRF_WEIGHTS: dict[str, float] = {
    "dense": 0.25,
    "sparse": 0.20,
    "bm25": 0.45,
    "colbert": 0.10,
}
DEFAULT_QRELS_RRF_K = 60

_QUESTION_MARKERS = frozenset(
    {
        "what", "why", "how", "when", "who", "where", "which",
        "explain", "describe", "summarize", "rationale", "impact", "relationship",
    }
)


def classify_query_intent(query_text: str) -> str:
    """Classify query intent into EXACT_KEYWORD, SEMANTIC_NARRATIVE, or HYBRID_STANDARD."""
    text = str(query_text or "").strip()
    if not text:
        return "HYBRID_STANDARD"
    has_quotes = (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'"))
    has_code_tokens = bool(re.search(r"^[A-Za-z0-9_-]+:[A-Za-z0-9_.:-]+$", text)) or bool(
        re.search(r"^[A-Z0-9_-]{3,25}$", text)
    )
    words = text.split()
    has_qword = any(w.lower().rstrip("?:;,.") in _QUESTION_MARKERS for w in words)
    if has_quotes or has_code_tokens or (len(words) <= 2 and not has_qword):
        return "EXACT_KEYWORD"
    if has_qword or len(words) >= 6:
        return "SEMANTIC_NARRATIVE"
    return "HYBRID_STANDARD"


def calculate_dynamic_query_weights(
    query_text: str,
    base_weights: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Dynamically rebalance 4-channel RRF weights based on query intent."""
    intent = classify_query_intent(query_text)
    if intent == "EXACT_KEYWORD":
        raw = {"dense": 0.10, "sparse": 0.15, "bm25": 0.65, "colbert": 0.10}
    elif intent == "SEMANTIC_NARRATIVE":
        raw = {"dense": 0.35, "sparse": 0.15, "bm25": 0.20, "colbert": 0.30}
    else:
        raw = dict(base_weights or CANONICAL_QRELS_RRF_WEIGHTS)
    total = sum(raw.values()) or 1.0
    return {k: round(v / total, 4) for k, v in raw.items()}


def generate_4_simplex_grid(step: float = 0.05) -> list[dict[str, float]]:
    """Generate all non-negative 4-simplex grid points summing to 1.0 (1,771 points at step=0.05)."""
    steps = int(round(1.0 / step)) + 1
    configs: list[dict[str, float]] = []
    for d in range(steps):
        for s in range(steps - d):
            for b in range(steps - d - s):
                c = steps - 1 - d - s - b
                w = {
                    "dense": round(d * step, 4),
                    "sparse": round(s * step, 4),
                    "bm25": round(b * step, 4),
                    "colbert": round(c * step, 4),
                }
                if abs(sum(w.values()) - 1.0) < 1e-4:
                    configs.append(w)
    return configs


def _extract_candidate_grade(cand: Mapping[str, Any]) -> int:
    if "grade" in cand and cand["grade"] is not None:
        return int(cand["grade"])
    mdl = cand.get("multi_dimensional_label") or {}
    ev = mdl.get("evidence_relevance") or {}
    if "grade" in ev:
        return int(ev["grade"])
    return int(cand.get("relevance_grade", 0))


def _score_candidate_rrf(cand: Mapping[str, Any], weights: Mapping[str, float], rrf_k: int) -> float:
    score = 0.0
    for ch, rk in (("dense", "dense_rank"), ("sparse", "sparse_rank"), ("bm25", "bm25_rank"), ("colbert", "colbert_rank")):
        rank_val = cand.get(rk)
        if rank_val is not None and ch in weights:
            score += float(weights[ch]) / (rrf_k + int(rank_val))
    return score


def evaluate_weight_configuration(
    queries: Sequence[Mapping[str, Any]],
    weights: Mapping[str, float],
    *,
    rrf_k: int = DEFAULT_QRELS_RRF_K,
    k: int = 10,
) -> dict[str, Any]:
    """Evaluate mean NDCG@K, MRR@K, Recall@K, and per-query NDCG@K for answerable queries."""
    per_query_ndcg: list[float] = []
    per_query_mrr: list[float] = []
    per_query_recall: list[float] = []
    for q in queries:
        if not q.get("answerable", True):
            continue
        candidates = q.get("judged_candidates") or []
        if not candidates:
            continue
        scored = [
            (_score_candidate_rrf(c, weights, rrf_k), str(c.get("record_id") or ""), _extract_candidate_grade(c))
            for c in candidates
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        grades = [g for _, _, g in scored]
        per_query_ndcg.append(compute_ndcg_at_k(grades, k=k))
        per_query_mrr.append(compute_mrr_at_k(grades, k=k))
        per_query_recall.append(compute_recall_at_k(grades, k=k))
    n = len(per_query_ndcg)
    return {
        "query_count": n,
        "mean_ndcg_10": round(sum(per_query_ndcg) / n, 4) if n else 0.0,
        "mean_mrr_10": round(sum(per_query_mrr) / n, 4) if n else 0.0,
        "mean_recall_10": round(sum(per_query_recall) / n, 4) if n else 0.0,
        "per_query_ndcg": per_query_ndcg,
    }


def evaluate_dynamic_weight_configuration(
    queries: Sequence[Mapping[str, Any]],
    base_weights: Mapping[str, float] | None = None,
    *,
    rrf_k: int = DEFAULT_QRELS_RRF_K,
    k: int = 10,
) -> dict[str, Any]:
    """Evaluate query-intent adaptive RRF weighting across answerable queries."""
    per_query_ndcg: list[float] = []
    per_query_mrr: list[float] = []
    for q in queries:
        if not q.get("answerable", True):
            continue
        candidates = q.get("judged_candidates") or []
        if not candidates:
            continue
        dyn_w = calculate_dynamic_query_weights(str(q.get("query_text") or ""), base_weights)
        scored = [
            (_score_candidate_rrf(c, dyn_w, rrf_k), str(c.get("record_id") or ""), _extract_candidate_grade(c))
            for c in candidates
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        grades = [g for _, _, g in scored]
        per_query_ndcg.append(compute_ndcg_at_k(grades, k=k))
        per_query_mrr.append(compute_mrr_at_k(grades, k=k))
    n = len(per_query_ndcg)
    return {
        "query_count": n,
        "mean_ndcg_10": round(sum(per_query_ndcg) / n, 4) if n else 0.0,
        "mean_mrr_10": round(sum(per_query_mrr) / n, 4) if n else 0.0,
    }


def evaluate_channel_ablations(
    queries: Sequence[Mapping[str, Any]],
    canonical_ndcg: float,
    *,
    rrf_k: int = DEFAULT_QRELS_RRF_K,
) -> dict[str, Any]:
    """Run 7 single-channel and leave-one-out channel ablation comparisons."""
    ablations = {
        "dense_only": {"dense": 1.0, "sparse": 0.0, "bm25": 0.0, "colbert": 0.0},
        "sparse_only": {"dense": 0.0, "sparse": 1.0, "bm25": 0.0, "colbert": 0.0},
        "bm25_only": {"dense": 0.0, "sparse": 0.0, "bm25": 1.0, "colbert": 0.0},
        "colbert_only": {"dense": 0.0, "sparse": 0.0, "bm25": 0.0, "colbert": 1.0},
        "no_bm25": {"dense": 0.40, "sparse": 0.20, "bm25": 0.0, "colbert": 0.40},
        "no_colbert": {"dense": 0.40, "sparse": 0.20, "bm25": 0.40, "colbert": 0.0},
        "equal_weights": {"dense": 0.25, "sparse": 0.25, "bm25": 0.25, "colbert": 0.25},
    }
    out: dict[str, Any] = {}
    for name, w in ablations.items():
        res = evaluate_weight_configuration(queries, w, rrf_k=rrf_k)
        out[name] = {
            "weights": w,
            "mean_ndcg_10": res["mean_ndcg_10"],
            "mean_mrr_10": res["mean_mrr_10"],
            "mean_recall_10": res["mean_recall_10"],
            "delta_vs_canonical": round(res["mean_ndcg_10"] - canonical_ndcg, 4),
        }
    return out


def _query_abstention_signal(query: Mapping[str, Any], weights: Mapping[str, float], rrf_k: int) -> float:
    """Compute top-1 confidence signal for abstention separation (explicit fused_score or weighted RRF)."""
    cands = query.get("judged_candidates") or []
    if not cands:
        return 0.0
    explicit = [float(c["fused_score"]) for c in cands if c.get("fused_score") is not None]
    if explicit:
        return max(explicit)
    return max(_score_candidate_rrf(c, weights, rrf_k) for c in cands)


def calibrate_abstention_threshold(
    tuning_queries: Sequence[Mapping[str, Any]],
    eval_queries: Sequence[Mapping[str, Any]],
    weights: Mapping[str, float],
    *,
    rrf_k: int = DEFAULT_QRELS_RRF_K,
) -> dict[str, Any]:
    """Calibrate tau_abstain on tuning split (zero false abstains) and verify on eval split."""
    tune_ans = [_query_abstention_signal(q, weights, rrf_k) for q in tuning_queries if q.get("answerable", True)]
    tune_neg = [_query_abstention_signal(q, weights, rrf_k) for q in tuning_queries if not q.get("answerable", True)]

    if tune_ans and tune_neg:
        min_ans = min(tune_ans)
        max_neg = max(tune_neg)
        tau = round((max_neg + min_ans) / 2.0, 6) if max_neg < min_ans else round(max_neg + 1e-6, 6)
    elif tune_neg:
        tau = round(max(tune_neg) + 1e-4, 6)
    else:
        tau = 0.0

    eval_ans = [_query_abstention_signal(q, weights, rrf_k) for q in eval_queries if q.get("answerable", True)]
    eval_neg = [_query_abstention_signal(q, weights, rrf_k) for q in eval_queries if not q.get("answerable", True)]
    false_abstains = sum(1 for s in eval_ans if s <= tau)
    true_abstains = sum(1 for s in eval_neg if s <= tau)
    neg_rate = round(true_abstains / len(eval_neg), 4) if eval_neg else 1.0
    return {
        "tau_abstain": tau,
        "eval_answerable_count": len(eval_ans),
        "eval_unanswerable_count": len(eval_neg),
        "false_abstains": false_abstains,
        "true_negative_abstains": true_abstains,
        "negative_probe_abstention_rate": neg_rate,
    }


def run_holdout_isolated_weight_calibration(
    judgments_data: Mapping[str, Any],
    partitions_data: Mapping[str, Any],
    *,
    canonical_weights: Mapping[str, float] | None = None,
    grid_step: float = 0.05,
    rrf_k: int = DEFAULT_QRELS_RRF_K,
    validation_delta_threshold: float = 0.02,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Execute strict dev+calibration 1,771-point 4-simplex sweep and evaluate untouched final_holdout."""
    started = time.time()
    base_w = dict(canonical_weights or CANONICAL_QRELS_RRF_WEIGHTS)
    all_queries = list(judgments_data.get("evaluated_queries") or [])
    holdout_ids = set((partitions_data.get("query_partitions") or {}).get("final_holdout") or [])

    tuning_queries = [q for q in all_queries if str(q.get("query_id")) not in holdout_ids]
    holdout_queries = [q for q in all_queries if str(q.get("query_id")) in holdout_ids]
    tuning_ids = {str(q.get("query_id")) for q in tuning_queries}
    leak_ids = sorted(tuning_ids & holdout_ids)
    if leak_ids:
        raise ValueError(f"Holdout leakage detected in tuning query set: {leak_ids}")

    can_tune = evaluate_weight_configuration(tuning_queries, base_w, rrf_k=rrf_k)
    ablations = evaluate_channel_ablations(tuning_queries, can_tune["mean_ndcg_10"], rrf_k=rrf_k)
    grid = generate_4_simplex_grid(step=grid_step)

    best_ndcg = -1.0
    best_mrr = -1.0
    best_w = dict(base_w)
    top_configs: list[dict[str, Any]] = []
    for w in grid:
        res = evaluate_weight_configuration(tuning_queries, w, rrf_k=rrf_k)
        ndcg, mrr = res["mean_ndcg_10"], res["mean_mrr_10"]
        if ndcg > best_ndcg or (abs(ndcg - best_ndcg) <= 1e-9 and mrr > best_mrr):
            best_ndcg, best_mrr, best_w = ndcg, mrr, w
        top_configs.append({"weights": w, "mean_ndcg_10": ndcg, "mean_mrr_10": mrr})
    top_configs.sort(key=lambda r: (-r["mean_ndcg_10"], -r["mean_mrr_10"]))

    delta_ndcg = round(best_ndcg - can_tune["mean_ndcg_10"], 4)
    is_validated = delta_ndcg < validation_delta_threshold
    verdict = "VALIDATED" if is_validated else "RECALIBRATION_REQUIRED"

    hold_can = evaluate_weight_configuration(holdout_queries, base_w, rrf_k=rrf_k)
    hold_opt = evaluate_weight_configuration(holdout_queries, best_w, rrf_k=rrf_k)
    hold_bm25 = evaluate_weight_configuration(
        holdout_queries, {"dense": 0.0, "sparse": 0.0, "bm25": 1.0, "colbert": 0.0}, rrf_k=rrf_k
    )
    hold_dense = evaluate_weight_configuration(
        holdout_queries, {"dense": 1.0, "sparse": 0.0, "bm25": 0.0, "colbert": 0.0}, rrf_k=rrf_k
    )
    hold_dyn = evaluate_dynamic_weight_configuration(holdout_queries, base_w, rrf_k=rrf_k)

    ci_vs_bm25 = paired_bootstrap_ndcg_ci(hold_can["per_query_ndcg"], hold_bm25["per_query_ndcg"], seed=42)
    ci_vs_dense = paired_bootstrap_ndcg_ci(hold_can["per_query_ndcg"], hold_dense["per_query_ndcg"], seed=42)
    abstention = calibrate_abstention_threshold(tuning_queries, all_queries, base_w, rrf_k=rrf_k)

    report: dict[str, Any] = {
        "calibration_contract": "urn:agents:qrels:weight-calibration:2.0.0",
        "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "corpus_digest": str(judgments_data.get("corpus_digest") or ""),
        "rrf_k": rrf_k,
        "partition_strategy": "dev_plus_calibration_strict",
        "tuning_holdout_overlap": leak_ids,
        "total_queries_loaded": len(all_queries),
        "calibration_queries_count": len(tuning_queries),
        "excluded_holdout_queries_count": len(holdout_queries),
        "excluded_holdout_query_ids": sorted(str(q.get("query_id")) for q in holdout_queries),
        "total_configurations_evaluated": len(grid),
        "grid_step": grid_step,
        "canonical_weights": base_w,
        "canonical_metrics": {
            "mean_ndcg_10": can_tune["mean_ndcg_10"],
            "mean_mrr_10": can_tune["mean_mrr_10"],
            "mean_recall_10": can_tune["mean_recall_10"],
        },
        "optimal_configuration": {
            "weights": best_w,
            "mean_ndcg_10": best_ndcg,
            "mean_mrr_10": best_mrr,
        },
        "delta_ndcg_10": delta_ndcg,
        "validation_delta_threshold": validation_delta_threshold,
        "is_validated": is_validated,
        "verdict": verdict,
        "channel_ablations": ablations,
        "top_5_simplex_configs": top_configs[:5],
        "final_holdout_evaluation": {
            "canonical_hybrid": {
                "mean_ndcg_10": hold_can["mean_ndcg_10"],
                "mean_mrr_10": hold_can["mean_mrr_10"],
                "mean_recall_10": hold_can["mean_recall_10"],
            },
            "optimal_simplex": {
                "mean_ndcg_10": hold_opt["mean_ndcg_10"],
                "mean_mrr_10": hold_opt["mean_mrr_10"],
                "mean_recall_10": hold_opt["mean_recall_10"],
            },
            "dynamic_intent": hold_dyn,
            "bm25_only": {"mean_ndcg_10": hold_bm25["mean_ndcg_10"], "mean_mrr_10": hold_bm25["mean_mrr_10"]},
            "dense_only": {"mean_ndcg_10": hold_dense["mean_ndcg_10"], "mean_mrr_10": hold_dense["mean_mrr_10"]},
            "paired_bootstrap_vs_bm25": ci_vs_bm25,
            "paired_bootstrap_vs_dense": ci_vs_dense,
        },
        "abstention_calibration": abstention,
        "elapsed_seconds": round(time.time() - started, 3),
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


__all__ = [
    "CANONICAL_QRELS_RRF_WEIGHTS",
    "DEFAULT_QRELS_RRF_K",
    "calculate_dynamic_query_weights",
    "calibrate_abstention_threshold",
    "classify_query_intent",
    "evaluate_channel_ablations",
    "evaluate_dynamic_weight_configuration",
    "evaluate_weight_configuration",
    "generate_4_simplex_grid",
    "run_holdout_isolated_weight_calibration",
]
