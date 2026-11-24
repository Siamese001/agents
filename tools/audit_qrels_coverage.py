#!/usr/bin/env python3
"""Fail-Closed QRELS Coverage, Zero-Leakage, 0-3 Grade & Hash-Bound Kappa Gate (DIE Parity)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.qrels.qrels_calibration_stats import (  # noqa: E402
    calculate_one_sided_upper_error_bound,
    verify_kappa_calibration_receipt,
)
from apps_eval.qrels.trec_pooling import validate_zero_leakage_partitions  # noqa: E402

_SYNTHETIC_PREFIXES = ("expert_pos_", "outside_pool_sample_", "synthetic_stub_")


def _extract_grade(cand: Mapping[str, Any]) -> int:
    if "grade" in cand and cand["grade"] is not None:
        return int(cand["grade"])
    mdl = cand.get("multi_dimensional_label") or {}
    ev = mdl.get("evidence_relevance") or {}
    if "grade" in ev:
        return int(ev["grade"])
    return int(cand.get("relevance_grade", 0))


def _scan_judged_candidates(evaluated_queries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grade_counts: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
    total_candidates = 0
    unanswerable_queries = 0
    has_synthetic_ids = False
    for q in evaluated_queries:
        if not q.get("answerable", True):
            unanswerable_queries += 1
        for c in q.get("judged_candidates") or []:
            total_candidates += 1
            g = _extract_grade(c)
            grade_counts[g] = grade_counts.get(g, 0) + 1
            rec_id = str(c.get("record_id") or "")
            if rec_id.startswith(_SYNTHETIC_PREFIXES):
                has_synthetic_ids = True
    return {
        "total_candidates": total_candidates,
        "unanswerable_queries": unanswerable_queries,
        "grade_counts": grade_counts,
        "has_synthetic_ids": has_synthetic_ids,
    }


def audit_qrels_coverage(
    partitions_path: Path,
    ground_truth_path: Path,
    candidate_pool_path: Path,
    *,
    receipt_output_path: Path | None = None,
    min_total_queries: int = 50,
    min_unanswerable_probes: int = 5,
    min_candidates_judged: int = 1000,
    kappa_floor: float = 0.80,
    min_total_human_labels: int = 0,
    min_holdout_passages: int = 20,
    ci95_lower_floor: float = 0.0,
    expected_grader_sha256: str | None = None,
) -> dict[str, Any]:
    """Audit QRELS family leakage, 0-3 grade distribution, synthetic IDs, and SHA-256 Kappa receipt."""
    partitions_data = json.loads(partitions_path.read_text(encoding="utf-8"))
    gt_data = json.loads(ground_truth_path.read_text(encoding="utf-8"))
    pool_data = json.loads(candidate_pool_path.read_text(encoding="utf-8"))

    leakage = validate_zero_leakage_partitions(partitions_data)
    evaluated_queries = list(gt_data.get("evaluated_queries") or [])
    total_queries = len(evaluated_queries)
    scan = _scan_judged_candidates(evaluated_queries)
    grade_counts = scan["grade_counts"]
    denom = max(scan["total_candidates"], 1)
    kappa_audit = verify_kappa_calibration_receipt(
        gt_data,
        min_anchor_passages=min_holdout_passages,
        min_total_human_labels=min_total_human_labels,
        kappa_floor=kappa_floor,
        ci95_lower_floor=ci95_lower_floor,
        expected_grader_sha256=expected_grader_sha256,
    )

    dev_c = leakage["dev_topics_count"]
    cal_c = leakage["calibration_topics_count"]
    hold_c = leakage["final_holdout_topics_count"]
    dev_ub = calculate_one_sided_upper_error_bound(dev_c, 0.95)
    cal_ub = calculate_one_sided_upper_error_bound(cal_c, 0.95)
    hold_ub = calculate_one_sided_upper_error_bound(hold_c, 0.95)

    failures: list[str] = []
    if leakage["has_leakage"]:
        failures.append("topic_or_query_partition_leakage")
    if scan["has_synthetic_ids"]:
        failures.append("synthetic_record_ids_detected")
    if total_queries < min_total_queries:
        failures.append(f"insufficient_queries:{total_queries}<{min_total_queries}")
    if scan["unanswerable_queries"] < min_unanswerable_probes:
        failures.append(f"insufficient_unanswerable_probes:{scan['unanswerable_queries']}<{min_unanswerable_probes}")
    if scan["total_candidates"] < min_candidates_judged:
        failures.append(f"insufficient_candidates:{scan['total_candidates']}<{min_candidates_judged}")
    if grade_counts.get(3, 0) <= 0:
        failures.append("missing_grade_3_authoritative")
    if grade_counts.get(1, 0) <= 0:
        failures.append("missing_grade_1_marginal")
    if not kappa_audit["is_valid"]:
        failures.append(f"kappa_receipt_invalid:{kappa_audit['reason']}")

    report: dict[str, Any] = {
        "audit_version": "3.0.0",
        "gate_status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "corpus_digest": str(gt_data.get("corpus_digest") or pool_data.get("corpus_digest") or ""),
        "family_leakage_audit": leakage,
        "ground_truth_audit": {
            "total_queries": total_queries,
            "unanswerable_probes": scan["unanswerable_queries"],
            "total_candidates_judged": scan["total_candidates"],
            "has_synthetic_ids": scan["has_synthetic_ids"],
            "grade_distribution": {str(k): v for k, v in grade_counts.items()},
            "authoritative_grade_3_ratio": round(grade_counts.get(3, 0) / denom, 4),
            "relevant_grade_2_plus_ratio": round((grade_counts.get(3, 0) + grade_counts.get(2, 0)) / denom, 4),
            "marginal_grade_1_ratio": round(grade_counts.get(1, 0) / denom, 4),
            "irrelevant_grade_0_ratio": round(grade_counts.get(0, 0) / denom, 4),
        },
        "kappa_calibration_audit": kappa_audit,
        "statistical_uncertainty_quantification": {
            "dev_topic_clusters": dev_c,
            "calibration_topic_clusters": cal_c,
            "final_holdout_topic_clusters": hold_c,
            "dev_one_sided_95_upper_error_bound_pct": round(dev_ub * 100, 2),
            "calibration_one_sided_95_upper_error_bound_pct": round(cal_ub * 100, 2),
            "final_holdout_one_sided_95_upper_error_bound_pct": round(hold_ub * 100, 2),
        },
    }
    if receipt_output_path is not None:
        receipt_output_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit QRELS Coverage, Family Leakage, 0-3 Grades & Kappa Receipt")
    parser.add_argument("--partitions", type=Path, default=REPO_ROOT / "data/qrels/qrels_partitions.v1.json")
    parser.add_argument("--ground-truth", type=Path, default=REPO_ROOT / "data/qrels/qrels_independent_ground_truth.v1.json")
    parser.add_argument("--pool", "--candidate-pool", dest="pool", type=Path, default=REPO_ROOT / "data/qrels/qrels_authentic_candidate_pool.v1.json")
    parser.add_argument("--output", "--receipt", dest="receipt", type=Path, default=None)
    parser.add_argument("--min-queries", type=int, default=50)
    parser.add_argument("--min-candidates", type=int, default=1000)
    parser.add_argument("--strict-200", action="store_true", help="Enforce DIE 200-human-label, 60-holdout, CI95 >= 0.70, and frozen grader SHA-256")
    args = parser.parse_args(argv)
    expected_grader_sha = None
    if args.strict_200:
        from apps_eval.qrels.qrels_blind_grader import compute_grader_source_sha256

        expected_grader_sha = compute_grader_source_sha256()
    report = audit_qrels_coverage(
        args.partitions,
        args.ground_truth,
        args.pool,
        receipt_output_path=args.receipt,
        min_total_queries=args.min_queries,
        min_candidates_judged=args.min_candidates,
        min_total_human_labels=200 if args.strict_200 else 0,
        min_holdout_passages=60 if args.strict_200 else 20,
        ci95_lower_floor=0.70 if args.strict_200 else 0.0,
        expected_grader_sha256=expected_grader_sha,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["gate_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
