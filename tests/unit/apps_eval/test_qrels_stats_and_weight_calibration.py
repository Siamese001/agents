"""Unit and adversarial tests for Wave 3 QRELS Kappa/Alpha stats, 4-simplex sweep, and coverage auditor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps_eval.qrels.qrels_calibration_stats import (
    calculate_one_sided_upper_error_bound,
    compute_cohens_kappa,
    compute_kappa_receipt_hashes,
    compute_mrr_at_k,
    compute_ndcg_at_k,
    compute_quadratic_weighted_kappa,
    compute_recall_at_k,
    compute_sparse_krippendorffs_alpha,
    paired_bootstrap_ndcg_ci,
    verify_kappa_calibration_receipt,
)
from apps_eval.qrels.weight_calibration import (
    CANONICAL_QRELS_RRF_WEIGHTS,
    calculate_dynamic_query_weights,
    classify_query_intent,
    generate_4_simplex_grid,
    run_holdout_isolated_weight_calibration,
)
from tools.audit_qrels_coverage import audit_qrels_coverage, main as audit_main


def _build_synthetic_benchmark_fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    dev_topics, cal_topics, hold_topics = [], [], []
    dev_qids, cal_qids, hold_qids = [], [], []
    evaluated_queries: list[dict[str, Any]] = []

    for idx in range(50):
        qid = f"q_{idx + 1:02d}"
        tid = f"topic_{idx + 1:02d}"
        is_neg = idx >= 45
        if idx < 20 or idx == 45 or idx == 46:
            part = "dev"
            dev_topics.append(tid)
            dev_qids.append(qid)
        elif idx < 35 or idx == 47:
            part = "calibration"
            cal_topics.append(tid)
            cal_qids.append(qid)
        else:
            part = "final_holdout"
            hold_topics.append(tid)
            hold_qids.append(qid)

        cands = []
        for rank in range(1, 22):
            if is_neg:
                grade = 0
                f_score = 0.010 / rank
            elif rank == 1:
                grade = 3
                f_score = 0.085
            elif rank == 2:
                grade = 2
                f_score = 0.055
            elif rank <= 4:
                grade = 1
                f_score = 0.032 / rank
            else:
                grade = 0
                f_score = 0.020 / rank
            # Make bm25_only rank a distractor above the grade-3 target on holdout so hybrid beats bm25_only
            bm25_r = 4 if (not is_neg and rank == 1) else (1 if (not is_neg and rank == 5) else rank)
            dense_r = 3 if (not is_neg and rank == 1) else (1 if (not is_neg and rank == 6) else rank)
            cands.append(
                {
                    "record_id": f"fact_{idx:02d}_{rank:02d}",
                    "grade": grade,
                    "fused_rank": rank,
                    "fused_score": round(f_score, 6),
                    "dense_rank": dense_r,
                    "sparse_rank": rank,
                    "bm25_rank": bm25_r,
                    "colbert_rank": rank,
                }
            )
        evaluated_queries.append(
            {
                "query_id": qid,
                "query_text": f"How does enterprise workflow {idx + 1} enforce governance?",
                "topic_id": tid,
                "partition": part,
                "answerable": not is_neg,
                "judged_candidates": cands,
            }
        )

    human = [0, 1, 2, 3, 1, 0, 2, 3, 1, 0, 3, 2, 1, 0, 2, 3, 1, 0, 2, 3]
    grader = [0, 1, 2, 3, 1, 0, 2, 3, 1, 0, 3, 2, 1, 0, 2, 3, 1, 0, 2, 2]
    ck = compute_cohens_kappa(human, grader)
    qwk = compute_quadratic_weighted_kappa(human, grader)
    eq_sha, art_sha = compute_kappa_receipt_hashes(evaluated_queries, human, grader, ck, qwk)

    partitions = {
        "schema_version": "2.0.0",
        "topic_assignments": {"dev": dev_topics, "calibration": cal_topics, "final_holdout": hold_topics},
        "query_partitions": {"dev": dev_qids, "calibration": cal_qids, "final_holdout": hold_qids},
    }
    gt = {
        "schema_version": "3.0.0",
        "corpus_digest": "b" * 64,
        "kappa_calibration_receipt": {
            "external_api_cost_usd": 0.0,
            "human_gold_grades": human,
            "blind_grader_grades": grader,
            "cohens_kappa": ck,
            "quadratic_weighted_kappa": qwk,
            "evaluated_queries_sha256": eq_sha,
            "artifact_sha256": art_sha,
        },
        "evaluated_queries": evaluated_queries,
    }
    pool = {"corpus_digest": "b" * 64, "queries": evaluated_queries}
    return partitions, gt, pool


def test_kappa_alpha_metrics_and_bootstrap_ci() -> None:
    human = [0, 1, 2, 3] * 5
    grader = [0, 1, 2, 3] * 4 + [0, 1, 2, 2]
    assert compute_cohens_kappa(human, grader) >= 0.90
    assert compute_quadratic_weighted_kappa(human, grader) >= 0.95

    sparse_matrix = [
        [3, 2, 1, 0, None, 3],
        [3, 2, 1, 0, 2, None],
        [3, 2, None, 0, 2, 3],
    ]
    assert compute_sparse_krippendorffs_alpha(sparse_matrix) >= 0.99
    assert calculate_one_sided_upper_error_bound(60) < 0.05

    assert compute_ndcg_at_k([3, 2, 1, 0], k=10) == 1.0
    assert compute_mrr_at_k([0, 1, 2, 3], k=10) == pytest.approx(1.0 / 3.0, abs=1e-4)
    assert compute_recall_at_k([0, 2, 0, 3], k=2) == 0.5

    ci = paired_bootstrap_ndcg_ci([0.95, 0.92, 0.94, 0.90, 0.96], [0.70, 0.72, 0.68, 0.75, 0.71], seed=42)
    assert ci["mean_diff"] > 0.15
    assert ci["statistically_significant_p05"] is True


def test_simplex_1771_grid_holdout_isolation_and_abstention(tmp_path: Path) -> None:
    grid = generate_4_simplex_grid(step=0.05)
    assert len(grid) == 1771
    assert classify_query_intent("BCBS_239") == "EXACT_KEYWORD"
    assert classify_query_intent("How did the AI platform cut latency?") == "SEMANTIC_NARRATIVE"
    assert sum(calculate_dynamic_query_weights("BCBS_239").values()) == pytest.approx(1.0, abs=1e-3)

    partitions, gt, _ = _build_synthetic_benchmark_fixture()
    out_path = tmp_path / "weights.json"
    res = run_holdout_isolated_weight_calibration(
        gt,
        partitions,
        canonical_weights=CANONICAL_QRELS_RRF_WEIGHTS,
        output_path=out_path,
    )
    assert res["total_configurations_evaluated"] == 1771
    assert res["tuning_holdout_overlap"] == []
    assert res["excluded_holdout_queries_count"] == len(partitions["query_partitions"]["final_holdout"])
    assert res["abstention_calibration"]["false_abstains"] == 0
    assert res["abstention_calibration"]["negative_probe_abstention_rate"] == 1.0
    assert res["final_holdout_evaluation"]["canonical_hybrid"]["mean_ndcg_10"] > res["final_holdout_evaluation"]["bm25_only"]["mean_ndcg_10"]
    assert out_path.is_file()


def test_audit_qrels_coverage_passes_valid_and_fails_closed_on_tamper_or_low_kappa(tmp_path: Path) -> None:
    partitions, gt, pool = _build_synthetic_benchmark_fixture()
    p_path = tmp_path / "partitions.json"
    gt_path = tmp_path / "gt.json"
    pool_path = tmp_path / "pool.json"
    p_path.write_text(json.dumps(partitions), encoding="utf-8")
    gt_path.write_text(json.dumps(gt), encoding="utf-8")
    pool_path.write_text(json.dumps(pool), encoding="utf-8")

    rep = audit_qrels_coverage(p_path, gt_path, pool_path)
    assert rep["gate_status"] == "PASS", rep["failures"]
    assert audit_main(["--partitions", str(p_path), "--ground-truth", str(gt_path), "--pool", str(pool_path)]) == 0

    # Tamper single grade byte -> fail closed (exit 1)
    tampered = json.loads(gt_path.read_text(encoding="utf-8"))
    tampered["evaluated_queries"][0]["judged_candidates"][0]["grade"] = 2
    bad_gt = tmp_path / "bad_gt.json"
    bad_gt.write_text(json.dumps(tampered), encoding="utf-8")
    assert verify_kappa_calibration_receipt(tampered)["reason"] == "hash_tamper_detected"
    assert audit_main(["--partitions", str(p_path), "--ground-truth", str(bad_gt), "--pool", str(pool_path)]) == 1

    # Sub-0.80 kappa -> fail closed
    low_k = json.loads(gt_path.read_text(encoding="utf-8"))
    low_human = [3, 3, 3, 3, 3, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    low_grader = [0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]
    ck = compute_cohens_kappa(low_human, low_grader)
    qwk = compute_quadratic_weighted_kappa(low_human, low_grader)
    eq_sha, art_sha = compute_kappa_receipt_hashes(low_k["evaluated_queries"], low_human, low_grader, ck, qwk)
    low_k["kappa_calibration_receipt"].update(
        {
            "human_gold_grades": low_human,
            "blind_grader_grades": low_grader,
            "cohens_kappa": ck,
            "quadratic_weighted_kappa": qwk,
            "evaluated_queries_sha256": eq_sha,
            "artifact_sha256": art_sha,
        }
    )
    low_gt = tmp_path / "low_k_gt.json"
    low_gt.write_text(json.dumps(low_k), encoding="utf-8")
    assert verify_kappa_calibration_receipt(low_k)["reason"] == "kappa_below_threshold"
    assert audit_main(["--partitions", str(p_path), "--ground-truth", str(low_gt), "--pool", str(pool_path)]) == 1
