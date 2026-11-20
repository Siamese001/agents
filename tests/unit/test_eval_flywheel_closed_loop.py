"""Wave 3 closed-loop tests for EvalFlywheelEngine, FeedbackController hints, drift, and ADR-040 triage."""

from __future__ import annotations

import json
from pathlib import Path

from agents.observability.eval_flywheel import (
    GRADUATION_CONSECUTIVE_PASS_TARGET,
    EvalFlywheelEngine,
)
from agents.orchestration.failure_taxonomy import FailureKind
from agents.orchestration.feedback_controller import ControllerAction, FeedbackController
from agents.orchestration.learning_store import FeedbackLearningStore
from apps_eval.triage_promoter import promote_staged_triage_packet


def _sample_manifest(*, failing: bool = False, kappa: float = 1.0, rho: float = 1.0) -> dict:
    return {
        "schema_version": "apps_eval.unified_evidence_manifest.v1",
        "generated_at": "2026-11-20T12:10:00Z",
        "app_filter": "all",
        "suite_receipts": {
            "apps_rg.dev.resume_generation": {
                "app_id": "apps_rg",
                "record_id": "rg_rec_fail" if failing else "rg_rec_pass",
                "finding_count": 55,
                "passed_findings": 50 if failing else 55,
                "score": 0.05 if failing else 0.107914,
                "verdict": "fail",
                "suite_passed": not failing,
                "baseline_comparison": {
                    "compared": True,
                    "delta": -0.057914 if failing else 0.0,
                    "verdict": "regression" if failing else "pass",
                },
                "regression_flywheel": {
                    "failure_mode_counts": {"grounding.ungrounded_claim": 5} if failing else {},
                },
            },
            "apps_lic.dev.outreach_message": {
                "app_id": "apps_lic",
                "record_id": "lic_rec_pass",
                "finding_count": 66,
                "passed_findings": 66,
                "score": 1.0,
                "verdict": "pass",
                "suite_passed": True,
                "baseline_comparison": {"compared": True, "delta": 0.0, "verdict": "pass"},
                "regression_flywheel": {"failure_mode_counts": {}},
            },
        },
        "apps_lic_g5_g6_receipt": {
            "status": "PASS" if kappa >= 0.65 and rho >= 0.70 else "FAIL",
            "g6": {
                "passed": kappa >= 0.65 and rho >= 0.70,
                "corpus_size": 80,
                "spearman_rho": rho,
                "cohens_kappa": kappa,
                "fpr": 0.0,
                "tpr": 1.0,
                "violations": [] if kappa >= 0.65 else ["Cohen's kappa dropped below 0.65"],
            },
            "g5": {"passed": True, "item_count": 80, "max_std": 0.002, "violations": []},
        },
        "apps_rg_e2e_receipt": {"status": "PASS"},
    }


def test_closed_loop_harvest_hint_resolution_trajectory_drift_and_human_triage(tmp_path: Path) -> None:
    db_path = tmp_path / "feedback_learning.sqlite"
    traj_path = tmp_path / "trajectories.json"
    cal_path = tmp_path / "calibration.json"
    grad_path = tmp_path / "graduation.json"
    triage_dir = tmp_path / "triage"

    engine = EvalFlywheelEngine(
        learning_db_path=db_path,
        trajectory_store_path=traj_path,
        calibration_history_path=cal_path,
        graduation_state_path=grad_path,
        triage_root=triage_dir,
    )

    # 1. Failing eval harvests failure signature + stages ADR-040 triage packet (never mutates fixtures)
    r_fail = engine.ingest_manifest(_sample_manifest(failing=True))
    assert r_fail["status"] == "INGESTED"
    assert len(r_fail["harvested_failures"]) >= 1
    assert len(r_fail["staged_triage_candidates"]) >= 1
    assert r_fail["feedback_summary"]["total_failure_signatures"] >= 1
    assert r_fail["trajectory_summary"]["total_golden_trajectories"] >= 1  # apps_lic passed

    pending = engine.list_triage_candidates(app_filter="apps_rg", pending_only=True)
    assert len(pending) == 1
    pkt_path = Path(pending[0]["_path"])
    assert pkt_path.is_file()

    # 2. FeedbackController retrieves harvested repair hint on subsequent runtime failure
    fb_store = FeedbackLearningStore(db_path)
    try:
        ctrl = FeedbackController(learning_store=fb_store)
        decision = ctrl.evaluate_result(
            validation_passed=False,
            errors=["grounding.ungrounded_claim"],
            failure_kind=FailureKind.FACTUAL_CONFLICT,
            run_id="live_rg_retry_1",
        )
        assert decision.action == ControllerAction.REQUEST_SEMANTIC_REVISION
        assert "C0 evidence" in decision.repair_hint or "grounding" in decision.repair_hint.lower()
    finally:
        fb_store.close()

    # 3. Subsequent passing eval auto-records resolution + mines apps_rg golden trajectory
    r_pass = engine.ingest_manifest(_sample_manifest(failing=False))
    assert len(r_pass["recorded_resolutions"]) >= 1
    assert r_pass["trajectory_summary"]["categories"].get("apps_rg", 0) >= 1
    assert r_pass["trajectory_summary"]["categories"].get("apps_lic", 0) >= 1
    assert engine.get_calibration_status()["status"] == "CALIBRATED"

    # 4. Injected calibration collapse triggers JudgeCalibrator drift alert
    r_drift = engine.ingest_manifest(_sample_manifest(failing=False, kappa=0.40, rho=0.50))
    assert len(r_drift["calibration_alerts"]) >= 2
    assert engine.get_calibration_status()["status"] == "DRIFT_ALERT"

    # 5. Human-gated ADR-040 promotion materializes compliant fixture into isolated temp root
    temp_fixtures = tmp_path / "promoted_fixtures" / "dev" / "apps_rg"
    temp_suites = tmp_path / "suites.yaml"
    temp_suites.write_text(
        json.dumps({"suites": {"apps_rg.dev.resume_generation": {"scenarios": []}}}, indent=2),
        encoding="utf-8",
    )
    promo = promote_staged_triage_packet(
        pkt_path,
        target_split="dev",
        reviewer="amit",
        fixtures_base_dir=temp_fixtures,
        suites_registry_path=temp_suites,
    )
    assert promo["status"] == "PROMOTED"
    assert promo["registered"] is True
    assert (Path(promo["target_dir"]) / "scenario.yaml").is_file()
    assert (Path(promo["target_dir"]) / "snapshots" / "app_output_snapshot.json").is_file()
    assert engine.list_triage_candidates(app_filter="apps_rg", pending_only=True) == []

    # 6. Capability-to-regression graduation streak hits ready after N=10 consecutive passes
    for _ in range(GRADUATION_CONSECUTIVE_PASS_TARGET):
        engine.ingest_manifest(_sample_manifest(failing=False))
    grad = engine.get_graduation_status()
    assert "apps_rg.dev.resume_generation" in grad["graduation_ready_suites"]
    assert "apps_lic.dev.outreach_message" in grad["graduation_ready_suites"]
