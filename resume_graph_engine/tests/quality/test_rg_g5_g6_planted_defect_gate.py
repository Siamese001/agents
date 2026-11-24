"""Wave 1 verification and counterfactual fault-injection tests for the 96-item Resume G5/G6 Planted-Defect Gate."""

from __future__ import annotations

from pathlib import Path

from apps_rg.evals.planted_defect_gate import (
    DEFAULT_RG_HOLDOUT_CORPUS_PATH,
    RG_PLANTED_DEFECT_CLASSES,
    build_default_rg_planted_defect_corpus,
    compute_cohens_kappa,
    compute_spearman_rho,
    detect_resume_defect_classes,
    ensure_rg_holdout_corpus_file,
    evaluate_rg_g5_repeatability,
    evaluate_rg_g6_planted_defects,
    load_rg_holdout_corpus,
    score_rg_holdout_item_deterministic,
)


def test_rg_planted_defect_corpus_has_96_stratified_items_across_6_jds_and_8_classes() -> None:
    path = ensure_rg_holdout_corpus_file()
    assert path == DEFAULT_RG_HOLDOUT_CORPUS_PATH
    assert path.is_file()

    rows = load_rg_holdout_corpus(path)
    assert len(rows) == 96
    clean = [r for r in rows if not r["is_defective"]]
    defective = [r for r in rows if r["is_defective"]]
    assert len(clean) == 48
    assert len(defective) == 48

    jds = {r["target_jd_key"] for r in rows}
    assert jds == {"anthropic", "truist", "citi", "brown_and_brown", "neo4j", "invesco"}

    for cls_name in RG_PLANTED_DEFECT_CLASSES:
        cls_rows = [r for r in defective if r["planted_defect_class"] == cls_name]
        assert len(cls_rows) == 6, f"Expected 6 cases for {cls_name}, got {len(cls_rows)}"


def test_rg_g6_planted_defects_passes_with_zero_fpr_and_100_percent_tpr() -> None:
    report = evaluate_rg_g6_planted_defects()
    assert report.passed is True, f"G6 failed: {report.violations}"
    assert report.status == "PASS"
    assert report.corpus_size == 96
    assert report.clean_item_count == 48
    assert report.defective_item_count == 48
    assert report.fpr == 0.0
    assert report.tpr == 1.0
    assert report.cohens_kappa == 1.0
    assert report.spearman_rho >= 0.75
    for cls_name in RG_PLANTED_DEFECT_CLASSES:
        assert report.per_defect_class_tpr[cls_name] == 1.0


def test_rg_detector_is_strictly_blind_to_ground_truth_labels() -> None:
    rows = build_default_rg_planted_defect_corpus()
    clean_sample = dict(next(r for r in rows if not r["is_defective"]))
    defect_sample = dict(next(r for r in rows if r["is_defective"]))
    expected_cls = defect_sample["planted_defect_class"]

    # Poison labels on clean sample -> detector must still report zero defects
    clean_sample["is_defective"] = True
    clean_sample["planted_defect_class"] = "repeated_signature_term_or_metric"
    clean_sample["gold_pass_label"] = False
    assert detect_resume_defect_classes(clean_sample) == ()
    _, clean_pass, _ = score_rg_holdout_item_deterministic(clean_sample)
    assert clean_pass is True

    # Strip labels on defective sample -> detector must still catch exact defect class
    defect_sample["is_defective"] = False
    defect_sample["planted_defect_class"] = None
    defect_sample["gold_pass_label"] = True
    detected = detect_resume_defect_classes(defect_sample)
    assert expected_cls in detected
    _, def_pass, _ = score_rg_holdout_item_deterministic(defect_sample)
    assert def_pass is False


def test_rg_g6_fails_closed_when_any_single_defect_detector_is_disabled() -> None:
    for cls_name in RG_PLANTED_DEFECT_CLASSES:
        fault_report = evaluate_rg_g6_planted_defects(disabled_detectors=(cls_name,))
        assert fault_report.passed is False, f"Disabling {cls_name} did not fail G6!"
        assert fault_report.per_defect_class_tpr[cls_name] == 0.0
        assert any(cls_name in v for v in fault_report.violations)


def test_rg_g5_repeatability_passes_with_zero_variance() -> None:
    g5 = evaluate_rg_g5_repeatability(k_runs=3)
    assert g5.passed is True, f"G5 failed: {g5.violations}"
    assert g5.status == "PASS"
    assert g5.item_count == 96
    assert g5.max_std == 0.0
    assert g5.mean_std == 0.0
    assert compute_cohens_kappa([True, False, True], [True, False, True]) == 1.0
    assert compute_spearman_rho([0.1, 0.5, 0.9], [0.2, 0.6, 0.95]) == 1.0
