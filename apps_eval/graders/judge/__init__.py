"""Tier-1 deterministic pre-judge, Tier-2 fail-closed blind LLM judge protocol, multi-lens panel, and calibration."""

from __future__ import annotations

from apps_eval.graders.judge.blind_protocol import (
    FORBIDDEN_DETERMINISTIC_PRIMING_KEYS,
    NON_LLM_EVALUATOR_KINDS,
    SYNTHETIC_MODEL_TOKENS,
    BlindJudgeBundle,
    build_fail_closed_missing_verdict_receipt,
    build_sealed_blind_judge_bundle,
    infer_provider_family,
    is_borderline_judge_result,
    is_synthetic_model_id,
    load_approved_judge_families,
    resolve_orthogonal_judge_family,
    validate_blind_judge_verdict_provenance,
)
from apps_eval.graders.judge.calibration import (
    CalibrationReport,
    JudgeCalibrationRunner,
    PositionSwapDebiaser,
    PositionSwapResult,
    compute_brier_and_ece,
    compute_cohens_kappa,
    evaluate_cross_family_judge_agreement,
)
from apps_eval.graders.judge.drift_monitor import (
    IDE_JUDGE_DRIFT_RECEIPT_SCHEMA_VERSION,
    ModelDriftEvaluation,
    evaluate_full_drift_suite,
    evaluate_model_drift,
    extract_active_ide_judge_bases,
    extract_active_ide_judge_pins,
    verify_ide_judge_drift_receipt,
)
from apps_eval.graders.judge.gold_corpus import (
    BlindGradingPacket,
    BlindReviewPrompt,
    GoldCandidateRecord,
    build_blind_grading_packet,
    export_blind_review_sheet_csv,
    import_blind_review_sheet_csv,
    load_external_stakeholder_rubric,
    load_gold_candidates_jsonl,
)
from apps_eval.graders.judge.human_provenance import (
    HumanGradeEntry,
    append_human_grade_entry,
    detect_synthetic_human_label_csv,
    unseal_and_adjudicate_human_gold,
    verify_human_label_ledger,
)
from apps_eval.graders.judge.panel import (
    LensSpec,
    LensVerdict,
    MultiLensPanelVerdict,
    evaluate_multi_lens_panel,
)
from apps_eval.graders.judge.pre_judge import (
    Tier1GateReceipt,
    run_tier1_deterministic_pre_judge,
)

__all__ = [
    "BlindJudgeBundle",
    "CalibrationReport",
    "FORBIDDEN_DETERMINISTIC_PRIMING_KEYS",
    "JudgeCalibrationRunner",
    "LensSpec",
    "LensVerdict",
    "MultiLensPanelVerdict",
    "NON_LLM_EVALUATOR_KINDS",
    "PositionSwapDebiaser",
    "PositionSwapResult",
    "SYNTHETIC_MODEL_TOKENS",
    "Tier1GateReceipt",
    "build_fail_closed_missing_verdict_receipt",
    "build_sealed_blind_judge_bundle",
    "compute_brier_and_ece",
    "compute_cohens_kappa",
    "evaluate_cross_family_judge_agreement",
    "evaluate_multi_lens_panel",
    "infer_provider_family",
    "is_borderline_judge_result",
    "is_synthetic_model_id",
    "load_approved_judge_families",
    "resolve_orthogonal_judge_family",
    "run_tier1_deterministic_pre_judge",
    "validate_blind_judge_verdict_provenance",
]
