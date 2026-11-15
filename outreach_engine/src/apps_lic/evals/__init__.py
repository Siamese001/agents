"""G5 Repeatability and G6 Meta-Evaluation harnesses for outreach_engine (apps_lic)."""

from __future__ import annotations

from apps_lic.evals.meta_eval import (
    G6MetaEvalReport,
    G6_MAX_CLEAN_FPR,
    G6_MIN_COHENS_KAPPA,
    G6_MIN_DEFECT_TPR,
    G6_MIN_SPEARMAN_RHO,
    PLANTED_DEFECT_CLASSES,
    PlantDefectCase,
    compute_cohens_kappa,
    compute_spearman_rho,
    detect_planted_defects,
    evaluate_g6_meta_calibration,
)
from apps_lic.evals.repeatability import (
    DEFAULT_HOLDOUT_CORPUS_PATH,
    G5ItemRepeatability,
    G5RepeatabilityReport,
    G5_MAX_SCORE_STD_CEILING,
    G5_MIN_REPEATED_RUNS,
    detect_item_defect_classes,
    evaluate_g5_repeatability,
    load_outreach_holdout_corpus,
    score_holdout_item_deterministic,
)

__all__ = [
    "DEFAULT_HOLDOUT_CORPUS_PATH",
    "G5ItemRepeatability",
    "G5RepeatabilityReport",
    "G5_MAX_SCORE_STD_CEILING",
    "G5_MIN_REPEATED_RUNS",
    "G6MetaEvalReport",
    "G6_MAX_CLEAN_FPR",
    "G6_MIN_COHENS_KAPPA",
    "G6_MIN_DEFECT_TPR",
    "G6_MIN_SPEARMAN_RHO",
    "PLANTED_DEFECT_CLASSES",
    "PlantDefectCase",
    "compute_cohens_kappa",
    "compute_spearman_rho",
    "detect_item_defect_classes",
    "detect_planted_defects",
    "evaluate_g5_repeatability",
    "evaluate_g6_meta_calibration",
    "load_outreach_holdout_corpus",
    "score_holdout_item_deterministic",
]
