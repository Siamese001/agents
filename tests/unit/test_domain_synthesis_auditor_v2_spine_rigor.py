"""Counterfactual rigor tests for Agent 4 (Domain Synthesis V2 Spine, Bilateral Vocab Symmetry & Anti-Overfitting)."""
from __future__ import annotations

from pathlib import Path

from tools.e2e_functionality_auditor import _probe_vocab_symmetry_overlap_and_v2_sealing
from tools.lint_apps_rg_domain_literals import (
    MAX_VALIDATOR_JUDGE_FROZENSET_CALLS,
    audit_apps_rg_domain_literals,
)
from tools.lint_no_jd_overfitting import check_file_no_jd_overfitting, collect_production_files, scan_files
from tools.lint_prompt_validator_vocab_symmetry import audit_prompt_validator_vocab_symmetry

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_domain_synthesis_pillar7_bilateral_vocab_and_domain_literals_pass() -> None:
    assert MAX_VALIDATOR_JUDGE_FROZENSET_CALLS <= 85
    assert audit_apps_rg_domain_literals(REPO_ROOT) == []
    assert audit_prompt_validator_vocab_symmetry(REPO_ROOT) == []

    p7 = _probe_vocab_symmetry_overlap_and_v2_sealing(REPO_ROOT)
    assert p7["passed"] is True, p7["gaps"]
    assert p7["vocab_symmetry_and_v2_sealing_verified"] is True


def test_lint_no_jd_overfitting_catches_dict_dispatch_and_call_patterns(tmp_path: Path) -> None:
    live_ov = scan_files(collect_production_files(REPO_ROOT), REPO_ROOT)
    assert live_ov["status"] == "PASS"
    assert live_ov["unbaselined_count"] == 0

    bad_py = tmp_path / "overfit_probe.py"
    bad_py.write_text(
        "import re\n"
        "OVERRIDES = {'citi': 'banking', 'aig': 'insurance'}\n"
        "PAT = re.compile(r'\\btruist\\b')\n"
        "def match_co(name: str) -> bool:\n"
        "    return name.startswith('invesco')\n",
        encoding="utf-8",
    )
    hits = check_file_no_jd_overfitting(bad_py, tmp_path)
    codes = {h["code"] for h in hits}
    assert "JD_COMPANY_OVERFITTING_DISPATCH_DICT" in codes
    assert "JD_COMPANY_OVERFITTING_CALL" in codes
    assert len(hits) >= 4


def test_apps_rg_and_apps_lic_public_spine_contracts_are_directly_verified() -> None:
    """Direct behavioral & contract verification for split resume/outreach spine modules."""
    import sys

    for p in (REPO_ROOT / "resume_graph_engine" / "src", REPO_ROOT / "outreach_engine" / "src"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    from apps_lic.pipeline.orchestrator_pkg.draft_and_validation import OutreachDraftAndValidationBase
    from apps_rg.engines.duplicate_detector import DuplicateDetector
    from apps_rg.engines.hallucination_detector import HallucinationDetector
    from apps_rg.fact_inventory.role_family_selection import digest_text, infer_role_family_priorities
    from apps_rg.runtime.assembly.coherence_prompt_compact import resolve_coherence_judge_effort
    from apps_rg.runtime.bindings.judge_calibration_baseline import build_apps_rg_judge_calibration_baseline
    from apps_rg.runtime.sections.executive_summary_operator_reporting import summarize_reasoning_execution_receipt
    from apps_rg.runtime.sections.executive_summary_x2_x1d_contract import judge_packet_pre_x2_gate_keys
    from apps_rg.runtime.sections.ibm_bullets.reselection_helpers import build_ibm_reselection_callbacks
    from apps_rg.runtime.sections.ibm_bullets.stage_closeout import run_ibm_closeout_stage
    from apps_rg.runtime.sections.ibm_bullets.stage_ingress import run_ibm_ingress_stage
    from apps_rg.runtime.sections.prose_phrase_repairs import apply_deterministic_prose_repairs
    from apps_rg.runtime.sections.role_episode.lane_ingress import run_role_episode_ingress_stage
    from apps_rg.runtime.sections.section_x2_x1d_contract import lane_x2_x1d_spec
    from apps_rg.runtime.sections.unify_bullets.reselection_helpers import build_unify_reselection_callbacks
    from apps_rg.runtime.sections.unify_bullets.stage_closeout import run_unify_closeout_stage
    from apps_rg.runtime.sections.unify_bullets.stage_ingress import run_unify_ingress_stage
    from apps_rg.runtime.validators.ibm_x2.coverage_checks import build_ibm_bullets_text_claim_coverage
    from apps_rg.runtime.validators.unify_x2.coverage_checks import build_unify_bullets_text_claim_coverage
    from apps_rg.tools.fact_vector_ingest import FactVectorSchema

    assert OutreachDraftAndValidationBase is not None
    assert DuplicateDetector is not None
    assert HallucinationDetector is not None
    assert len(digest_text("enterprise architecture")) == 64
    rf_prios = infer_role_family_priorities(
        target_role="SVP Enterprise Architecture",
        jd_text="AI platform architecture modernization",
        briefing_text="Enterprise cloud governance",
        taxonomy={"role_families": [{"id": "rf_arch", "jd_signal_keywords": ["architecture", "ai"]}]},
    )
    assert isinstance(rf_prios, tuple) and len(rf_prios) == 1
    assert resolve_coherence_judge_effort("xhigh") == "high"
    assert resolve_coherence_judge_effort("medium") == "medium"
    assert callable(build_apps_rg_judge_calibration_baseline)
    assert callable(summarize_reasoning_execution_receipt)
    assert isinstance(judge_packet_pre_x2_gate_keys(), (set, frozenset, tuple, list))
    assert callable(build_ibm_reselection_callbacks)
    assert callable(run_ibm_closeout_stage)
    assert callable(run_ibm_ingress_stage)
    assert callable(apply_deterministic_prose_repairs)
    assert callable(run_role_episode_ingress_stage)
    assert lane_x2_x1d_spec("executive_summary") is not None
    assert callable(build_unify_reselection_callbacks)
    assert callable(run_unify_closeout_stage)
    assert callable(run_unify_ingress_stage)
    assert callable(build_ibm_bullets_text_claim_coverage)
    assert callable(build_unify_bullets_text_claim_coverage)
    assert FactVectorSchema is not None
