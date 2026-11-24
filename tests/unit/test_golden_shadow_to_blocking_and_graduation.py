"""Wave 3 tests: Golden-case shadow-to-blocking promotion and capability graduation bridge."""

from __future__ import annotations

import json
from pathlib import Path

from agents.learning.proposal_generator import synthesize_graduation_proposals
from agents.observability.eval_flywheel import EvalFlywheelEngine
from apps_eval.contracts.schemas import EvalCase
from apps_eval.golden_suite_runner import evaluate_golden_flywheel_suite
from apps_eval.harness_orchestrator import EVIDENCE_MANIFEST_SCHEMA_VERSION
from apps_eval.promotion_gate import verify_promotion_evidence


def _make_base_manifest(golden_receipt: dict) -> dict:
    return {
        "schema_version": EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "generated_at": "2026-11-24T12:00:00Z",
        "app_filter": "apps_lic",
        "fast_dev": True,
        "suite_receipts": {
            "apps_lic.dev.outreach_message": {
                "finding_count": 10,
                "passed_findings": 10,
                "verdict": "pass",
                "suite_passed": True,
                "score": 1.0,
                "baseline_comparison": {"compared": True, "verdict": "pass", "delta": 0.0},
            }
        },
        "l6_shadow_handoff_receipts": {
            "apps_lic.dev.outreach_message": {"present": True, "sha256": "a" * 64}
        },
        "apps_lic_g5_g6_receipt": {
            "status": "PASS",
            "g6": {
                "passed": True,
                "corpus_size": 80,
                "spearman_rho": 0.92,
                "cohens_kappa": 0.88,
                "fpr": 0.0,
                "tpr": 1.0,
            },
            "g5": {"passed": True, "max_std": 0.0},
        },
        "release_gate_receipt": {"status": "pass"},
        "golden_flywheel_receipt": golden_receipt,
    }


def test_open_finding_golden_case_runs_in_shadow_without_blocking_promotion(tmp_path: Path) -> None:
    case = EvalCase(
        case_id="golden-case-open-001",
        suite_id="apps_lic.golden.v1",
        app_id="apps_lic",
        split="development",
        execution_mode="snapshot",
        grounding_tier="LIVE_CORPUS_GROUNDED",
        source_kind="online_eval_failure",
        source_trace_id="trace-open-001",
        unlabeled_input={
            "payload": {"app_id": "apps_lic", "run_id": "run-open-001", "simulated_candidate_pass": False},
            "pii_redacted": True,
        },
        expected_contract={"reference_label": "PASS"},
    )
    golden_path = tmp_path / "golden_eval_cases.json"
    golden_path.write_text(
        json.dumps({"dataset_digest": "d" * 64, "cases": [case.to_dict()]}, indent=2),
        encoding="utf-8",
    )
    snap_path = tmp_path / "remediation_queue_snapshot.json"
    snap_path.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "find-open-001",
                        "status": "OPEN",
                        "sample_trace_ids": ["trace-open-001"],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    rec = evaluate_golden_flywheel_suite(
        repo_root=Path(".").resolve(),
        golden_dataset_path=golden_path,
        queue_snapshot_path=snap_path,
    )
    assert rec["passed"] is True
    assert rec["shadow_total"] == 1
    assert rec["shadow_passed"] == 0
    assert len(rec["shadow_failures"]) == 1
    assert rec["blocking_total"] == 0

    manifest_path = tmp_path / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(_make_base_manifest(rec), indent=2), encoding="utf-8")
    gate_res = verify_promotion_evidence(manifest_path, require_holdout=False, require_engine_probes=False)
    assert gate_res.passed is True
    assert gate_res.exit_code == 0
    assert gate_res.checks["golden_flywheel_blocking"] is True


def test_verified_finding_golden_case_blocks_promotion_on_regression(tmp_path: Path) -> None:
    case = EvalCase(
        case_id="golden-case-ver-001",
        suite_id="apps_lic.golden.v1",
        app_id="apps_lic",
        split="holdout",
        execution_mode="snapshot",
        grounding_tier="LIVE_CORPUS_GROUNDED",
        source_kind="online_eval_failure",
        source_trace_id="trace-ver-001",
        unlabeled_input={
            "payload": {"app_id": "apps_lic", "run_id": "run-ver-001", "regression_injected": True},
            "pii_redacted": True,
        },
        expected_contract={"reference_label": "PASS"},
    )
    golden_path = tmp_path / "golden_eval_cases.json"
    golden_path.write_text(
        json.dumps({"dataset_digest": "e" * 64, "cases": [case.to_dict()]}, indent=2),
        encoding="utf-8",
    )
    snap_path = tmp_path / "remediation_queue_snapshot.json"
    snap_path.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "find-ver-001",
                        "status": "VERIFIED",
                        "sample_trace_ids": ["trace-ver-001"],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    rec = evaluate_golden_flywheel_suite(
        repo_root=Path(".").resolve(),
        golden_dataset_path=golden_path,
        queue_snapshot_path=snap_path,
    )
    assert rec["passed"] is False
    assert rec["status"] == "REGRESSION"
    assert rec["blocking_total"] == 1
    assert len(rec["blocking_failures"]) == 1

    manifest_path = tmp_path / "evidence_manifest.json"
    manifest_path.write_text(json.dumps(_make_base_manifest(rec), indent=2), encoding="utf-8")
    gate_res = verify_promotion_evidence(manifest_path, require_holdout=False, require_engine_probes=False)
    assert gate_res.passed is False
    assert gate_res.status == "REGRESSION"
    assert gate_res.exit_code == 2
    assert gate_res.checks["golden_flywheel_blocking"] is False
    assert any("golden-case-ver-001" in r for r in gate_res.regression_reasons)


def test_capability_graduation_streak_synthesizes_regression_case_pin_proposal(tmp_path: Path) -> None:
    grad_path = tmp_path / "capability_graduation_state.json"
    fw = EvalFlywheelEngine(
        learning_db_path=tmp_path / "fb.sqlite",
        trajectory_store_path=tmp_path / "traj.json",
        calibration_history_path=tmp_path / "cal.json",
        graduation_state_path=grad_path,
        triage_root=tmp_path / "triage",
    )
    for _ in range(10):
        state = fw._update_graduation_streaks({"apps_rg.capability.multi_jd": 1.0})
    assert "apps_rg.capability.multi_jd" in state["graduation_ready_suites"]

    props = synthesize_graduation_proposals(
        repo_root=Path(".").resolve(),
        graduation_state_path=grad_path,
    )
    assert len(props) == 1
    p = props[0]
    assert p.artifact_class == "regression_case_pin"
    assert p.autonomy_tier == "TIER_A_AUTO_APPLY"
    assert p.target_path == "apps_eval/suites/pinned_fix_regressions.json"
    assert p.target_key == "graduated_capability_suites"
    assert "apps_rg.capability.multi_jd" in p.proposed_value_or_patch
    assert p.verify_digest() is True
