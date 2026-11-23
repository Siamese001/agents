"""Unit tests for 2025-2026 statistical calibration (Rogan-Gladen, Lee 2025 dual-uncertainty CI, Arawjo 2026 PPI++, Krippendorff's alpha, IDEJudgeDriftEvaluator, and disjoint multi-judge jury)."""
from __future__ import annotations

from pathlib import Path

import pytest

from apps_eval.graders.judge.external_rubric_store import (
    ExternalHumanLabelRecord,
    load_and_verify_external_rubric,
)
from apps_eval.graders.judge.frontier_calibration_stats import (
    classify_cohort_power,
    compute_krippendorffs_alpha,
    compute_pass_at_k_and_pass_pow_k,
    compute_ppi_calibrated_pass_rate,
    compute_rogan_gladen_prevalence,
    compute_tpr_tnr_balanced_accuracy,
)
from apps_eval.graders.judge.ide_judge_drift_evaluator import (
    IDEJudgeDriftEvaluator,
    save_drift_receipt,
    verify_drift_receipt_digest,
)
from apps_eval.graders.judge.multi_judge_jury import aggregate_disjoint_ide_jury_verdicts


def test_rogan_gladen_dual_uncertainty_ci_and_ppi_plus_plus() -> None:
    human = ["PASS", "PASS", "PASS", "FAIL", "FAIL", "FAIL", "PASS", "FAIL", "PASS", "FAIL"]
    judge = ["PASS", "PASS", "PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL"]
    cm = compute_tpr_tnr_balanced_accuracy(human, judge)
    assert cm["tpr"] == 1.0
    assert cm["tnr"] == 0.8
    assert cm["balanced_accuracy"] == 0.9

    rg = compute_rogan_gladen_prevalence(
        0.6,
        cm["tpr"],
        cm["tnr"],
        human_verdicts=human,
        judge_verdicts=judge,
        unlabeled_eval_n=48,
    )
    assert rg["corrected_pass_rate"] == 0.5
    assert rg["ci_95"][0] <= 0.5 <= rg["ci_95"][1]

    ppi = compute_ppi_calibrated_pass_rate(human, judge, unlabeled_judge_verdicts=["PASS", "FAIL"] * 12)
    assert 0.35 <= ppi["ppi_pass_rate"] <= 0.65
    assert 0.0 <= ppi["lambda_opt"] <= 1.0

    stoch = compute_pass_at_k_and_pass_pow_k([True, True, False, True], k=3)
    assert stoch["pass_at_k"] > stoch["pass_pow_k"]
    assert classify_cohort_power(24) == "UNDERPOWERED_PILOT"
    assert classify_cohort_power(48) == "CALIBRATION_READY"
    assert classify_cohort_power(120) == "FRONTIER_QUALIFIED"


def test_krippendorffs_alpha_handles_sparse_missing_cells() -> None:
    matrix = [
        ["PASS", "FAIL", "PASS", None, "FAIL"],
        ["PASS", "FAIL", "PASS", "PASS", None],
        [None, "FAIL", "PASS", "PASS", "FAIL"],
    ]
    assert compute_krippendorffs_alpha(matrix, level="nominal") == 1.0


def test_ide_judge_drift_evaluator_and_receipt_verification(tmp_path: Path) -> None:
    rubric = load_and_verify_external_rubric()
    rubric_sha = str(rubric["rubric_sha256"])

    human_records: list[ExternalHumanLabelRecord] = []
    verdicts_by_case: dict[str, dict[str, object]] = {}
    for idx in range(1, 13):
        is_pass = idx <= 7
        sha = f"{idx:064x}"
        cid = f"case_{idx:03d}"
        rec = ExternalHumanLabelRecord.from_mapping(
            {
                "case_id": cid,
                "judge_surface": "resume_engine",
                "topic_family": f"topic_{idx:03d}",
                "partition": "final_holdout",
                "artifact_sha256": sha,
                "external_rubric_id": "external_judge_rubric_v1",
                "external_rubric_sha256": rubric_sha,
                "annotator_id": "human-exec-reviewer",
                "graded_at_utc": f"2026-11-23T01:{idx:02d}:00Z",
                "dimension_grades": {
                    "factual_faithfulness": 5 if is_pass else 2,
                    "completeness_and_relevance": 4 if is_pass else 2,
                    "cold_reader_clarity": 4 if is_pass else 3,
                    "actionability_and_proportion": 4 if is_pass else 2,
                },
                "human_verdict": "PASS" if is_pass else "FAIL",
                "failure_tags": [] if is_pass else ["HALLUCINATED_FACT"],
                "critique_rationale": "Grounded answer." if is_pass else "Unsupported claim detected.",
            },
            expected_rubric_sha256=rubric_sha,
        )
        human_records.append(rec)
        verdicts_by_case[cid] = {
            "case_id": cid,
            "artifact_sha256": sha,
            "verdict": "PASS" if is_pass else "FAIL",
            "overall_score": 8.9 if is_pass else 1.8,
            "evaluator_kind": "antigravity_ide_blind_subagent_judge",
            "judge_model_family": "neon",
            "bundle_digest": f"bundle_{idx:058x}",
            "external_http_call_count": 0,
        }

    evaluator = IDEJudgeDriftEvaluator()
    report = evaluator.evaluate(
        human_records,
        verdicts_by_case,
        judge_surface="resume_engine",
        partition="final_holdout",
    )
    assert report.passed is True
    assert report.drift_detected is False
    assert report.cohens_kappa == 1.0
    assert report.failure_tag_detection_recall["HALLUCINATED_FACT"] == 1.0

    receipt_path = save_drift_receipt(report, tmp_path / "drift_receipt.json")
    assert verify_drift_receipt_digest(report.to_dict()) is True
    assert receipt_path.is_file()


def test_disjoint_multi_judge_jury_aggregation_rejects_duplicate_family() -> None:
    sha = "c" * 64
    m_neon = {
        "case_id": "rg_gold_001",
        "artifact_sha256": sha,
        "verdict": "PASS",
        "overall_score": 8.6,
        "evaluator_kind": "antigravity_ide_blind_subagent_judge",
        "judge_model_family": "neon",
        "bundle_digest": "1" * 64,
        "external_http_call_count": 0,
    }
    m_carbon = {
        "case_id": "rg_gold_001",
        "artifact_sha256": sha,
        "verdict": "PASS",
        "overall_score": 8.2,
        "evaluator_kind": "antigravity_ide_blind_subagent_judge",
        "judge_model_family": "carbon",
        "bundle_digest": "2" * 64,
        "external_http_call_count": 0,
    }
    pooled = aggregate_disjoint_ide_jury_verdicts(
        "rg_gold_001",
        [m_neon, m_carbon],
        expected_artifact_sha256=sha,
    )
    assert pooled.verdict == "PASS"
    assert pooled.judge_model_family == "disjoint_jury"
    assert pooled.member_families == ("neon", "carbon")

    with pytest.raises(ValueError, match="duplicate model family"):
        aggregate_disjoint_ide_jury_verdicts("rg_gold_001", [m_neon, m_neon], expected_artifact_sha256=sha)
