"""Unmocked E2E closed-loop & fault-injection suite for Wave 4 (eval harness -> flywheel -> auto-apply -> rollback -> self-audits).

Zero unittest.mock, MagicMock, patch, or monkeypatch imports are permitted in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.learning.commit_engine import apply_proposal_atomically
from agents.learning.merkle_seal import verify_merkle_seal
from agents.learning.rollback_manager import evaluate_post_apply_canary_and_seal
from agents.observability.trace_collector import RunTraceCollector, build_run_trace
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.construct_validity import scan_extended_construct_validity
from apps_eval.contracts.digests import sha256_file
from apps_eval.contracts.schemas import EvalCase, ImprovementProposal
from apps_eval.holdout_replay import evaluate_proposal_in_shadow
from apps_eval.longitudinal import (
    LongitudinalEvalEntry,
    LongitudinalEvaluationTracker,
    run_asymmetric_fault_injection_probe,
)
from apps_eval.pareto import ParetoFrontierAnalyzer, ParetoPoint
from apps_eval.triage_promoter import load_holdout_cases
from tools.audit_eval_construct_validity import audit_repository
from tools.audit_multi_ssot_judge_gate_drift import audit_multi_ssot_judge_gate_drift
from tools.run_eval_flywheel_cycle import run_eval_flywheel_cycle
from tools.snapshot_agent_learning_registry import build_learning_registry_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_longitudinal_asymmetric_fault_injection_self_probe_passes() -> None:
    probe = run_asymmetric_fault_injection_probe()
    assert probe["passed"] is True, probe
    assert len(probe["checks"]) == 6


def test_pareto_frontier_dominance_and_zero_baseline_spike_guard() -> None:
    analyzer = ParetoFrontierAnalyzer(
        max_quality_drop_pct=5.0,
        max_latency_spike_pct=25.0,
        max_cost_spike_pct=25.0,
    )
    points = [
        ParetoPoint("cfg-fast", quality_score=92.0, latency_ms=100.0, cost_usd=0.01),
        ParetoPoint("cfg-best", quality_score=97.0, latency_ms=180.0, cost_usd=0.02),
        ParetoPoint("cfg-dominated", quality_score=90.0, latency_ms=250.0, cost_usd=0.05),
    ]
    frontier = {p.config_id: p for p in analyzer.compute_frontier(points)}
    assert frontier["cfg-fast"].is_pareto_optimal is True
    assert frontier["cfg-best"].is_pareto_optimal is True
    assert frontier["cfg-dominated"].is_pareto_optimal is False
    assert "cfg-fast" in frontier["cfg-dominated"].dominated_by

    zero_cost_spike = analyzer.evaluate_regression(
        candidate=ParetoPoint("cand", quality_score=95.0, latency_ms=100.0, cost_usd=0.05),
        baseline=ParetoPoint("base", quality_score=95.0, latency_ms=100.0, cost_usd=0.0),
    )
    assert zero_cost_spike.is_regression is True
    assert any("COST_SPIKE" in r for r in zero_cost_spike.reasons)


def test_extended_construct_validity_catches_planted_anti_gaming_traps(tmp_path: Path) -> None:
    trap_file = tmp_path / "planted_traps.py"
    trap_file.write_text(
        "def evaluate_empty(items, unused_cfg):\n"
        "    if not items:\n"
        "        return True\n"
        "    return len(items) > 0\n\n"
        "def compute_regression_delta(a, b):\n"
        "    return max(0.0, a - b)\n\n"
        "def test_tautology():\n"
        "    x = 1\n"
        "    assert True\n"
        "    assert x == x\n"
        "    returncode = 1\n"
        "    assert returncode in [0, 1]\n"
        "    return 'PASS_WITHOUT_JUDGE'\n",
        encoding="utf-8",
    )
    violations = scan_extended_construct_validity(trap_file)
    codes = {v["code"] for v in violations}
    assert "VACUOUS_ZERO_CASE_PASS" in codes
    assert "IGNORED_EVAL_PARAM" in codes
    assert "CLAMPED_REGRESSION_DELTA" in codes
    assert "TAUTOLOGICAL_CONSTANT_COMPARE" in codes
    assert "TAUTOLOGICAL_SELF_COMPARE" in codes
    assert "VACUOUS_EXIT_CODE_ASSERTION" in codes
    assert "UNWIRED_JUDGE_VACUOUS_PASS" in codes


def test_repo_passes_strict_construct_validity_multi_ssot_drift_and_learning_coverage() -> None:
    cv = audit_repository(REPO_ROOT)
    assert cv["status"] == "PASS", cv["violations"]

    drift = audit_multi_ssot_judge_gate_drift(REPO_ROOT)
    assert drift["status"] == "PASS", drift["violations"]
    assert all(v == "PASS" for v in drift["vectors"].values())

    cov = build_learning_registry_snapshot(REPO_ROOT)
    assert cov["instrumented_seams_count"] == cov["watched_seams_count"], cov


def test_end_to_end_closed_loop_flywheel_apply_canary_rollback_and_drift_exit_code(tmp_path: Path) -> None:
    src_dir = tmp_path / "src_learning"
    out_dir = tmp_path / "sandbox_learning"
    src_dir.mkdir()

    # 1. Emit real PII-containing failing traces + recurring operator corrections into src_dir.
    collector = RunTraceCollector(traces_path=src_dir / "run_traces.jsonl", cursor_path=src_dir / "cursor.json")
    for idx in range(1, 5):
        collector.emit(
            build_run_trace(
                app_id="apps_rg",
                run_id=f"e2e-run-{idx}",
                session_id=f"e2e-sess-{idx}",
                terminal_status="FAIL",
                raw_input={"jd": f"Enterprise AI Director {idx}", "email": f"candidate{idx}@private.test"},
                gate_outcomes={"x2_gates": {"grounding": False}},
                telemetry={"latency_ms": 2000.0, "cost_usd": 0.01},
                finished_at_utc=f"2026-11-21T0{idx}:00:00Z",
            )
        )
    corr_rows = [
        json.dumps(
            {
                "correction_id": f"e2e-corr-{i}",
                "category": "routing",
                "app_id": "agents_core",
                "source_identifier": "threshold_low",
                "corrected_identifier": "threshold_calibrated",
                "operator_id": "operator",
                "session_id": f"e2e-sess-{i}",
                "recorded_at": "2026-11-21T05:00:00Z",
            }
        )
        for i in range(1, 4)
    ]
    (src_dir / "operator_corrections.jsonl").write_text("\n".join(corr_rows) + "\n", encoding="utf-8")

    # 2. Run full sandbox flywheel cycle (healthy longitudinal ledger -> exit 0).
    code, receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src_dir,
        output_root=out_dir,
        sandbox=True,
    )
    assert code == 0, receipt
    assert receipt["marginal_api_cost_usd"] == 0.0
    assert receipt["findings_consolidation"]["total_findings"] >= 2
    assert receipt["golden_promotion"]["total_cases"] >= 2
    assert receipt["synthesized_proposals_count"] >= 1
    assert "private.test" not in (out_dir / "golden_eval_cases.json").read_text(encoding="utf-8")

    # 3. Take synthesized Tier A proposal, run zero-mutation holdout replay, apply atomically, then trigger LP5 rollback.
    tier_a_raw = next(
        p for p in receipt["synthesized_proposals"] if p["autonomy_tier"] == "TIER_A_AUTO_APPLY"
    )
    proposal = ImprovementProposal(**tier_a_raw)

    dataset_digest, holdouts = load_holdout_cases(out_dir / "golden_eval_cases.json")
    assert len(holdouts) >= 1
    # Augment with holdout cases matching routing scenario for replay proof.
    replay_holdouts = [
        EvalCase(
            case_id=f"e2e-holdout-{i}",
            suite_id="agents_core.golden.v1",
            app_id="agents_core",
            split="holdout",
            execution_mode="snapshot",
            source_kind="curated",
            grounding_tier="OFFLINE_BENCHMARK_GROUNDED",
            unlabeled_input={"score": 0.75},
            expected_contract={"reference_label": "PASS"},
        )
        for i in range(5)
    ]
    target_cases = [
        EvalCase(
            case_id=f"e2e-target-{i}",
            suite_id="agents_core.golden.v1",
            app_id="agents_core",
            split="development",
            execution_mode="snapshot",
            source_kind="online_eval_failure",
            grounding_tier="LIVE_CORPUS_GROUNDED",
            unlabeled_input={"score": 0.75},
            expected_contract={"reference_label": "PASS"},
        )
        for i in range(3)
    ]
    verdict = evaluate_proposal_in_shadow(
        proposal=proposal,
        target_cluster_cases=target_cases,
        holdout_cases=replay_holdouts,
        dataset_digest=dataset_digest or "d" * 64,
        candidate_runner=lambda view, val: {
            "label": "PASS" if float(val) > 0.72 else "FAIL",
            "latency_ms": 40.0,
            "cost_usd": 0.0,
        },
    )
    assert verdict.verdict == "PASS", verdict.rejection_reasons

    cfg_copy = tmp_path / "routing_calibration.yaml"
    cfg_copy.write_text("# Live copy\nv12_routing:\n  classifier_surface_threshold: 0.72\n", encoding="utf-8")
    pre_sha = sha256_file(cfg_copy)

    ledger = SqliteLearningLedgerStore(out_dir / "learning_ledger.sqlite")
    try:
        applied = apply_proposal_atomically(
            proposal=proposal,
            holdout_verdict=verdict,
            repo_root=REPO_ROOT,
            ledger_store=ledger,
            rollback_dir=out_dir / "rollbacks",
            target_file_override=cfg_copy,
        )
        assert sha256_file(cfg_copy) != pre_sha

        rb_res = evaluate_post_apply_canary_and_seal(
            receipt=applied,
            canary_metrics={"quality_score": 0.65, "veto_defects": 1, "latency_ms": 100.0},
            baseline_metrics={"quality_score": 0.92},
            ledger_store=ledger,
            seals_dir=out_dir / "seals",
        )
        assert rb_res["status"] == "ROLLED_BACK"
        assert rb_res["rollback"]["exact_pre_apply_sha_match"] is True
        assert sha256_file(cfg_copy) == pre_sha
        assert verify_merkle_seal(rb_res["merkle_seal"]) is True
    finally:
        ledger.close()

    # 4. Inject anchor-peak drift into longitudinal ledger and verify flywheel cycle exits 2 (DRIFT_ALERT).
    tracker = LongitudinalEvaluationTracker(src_dir / "longitudinal_eval_ledger.json")
    for idx, val in enumerate((98.0, 97.0, 94.0)):
        tracker.record_entry(
            LongitudinalEvalEntry(
                run_id=f"drift-run-{idx}",
                timestamp=f"2026-11-2{idx}T00:00:00Z",
                pipeline_version=f"p{idx}",
                rubric_version="rubric.v1",
                benchmark_suite="agents_core.e2e",
                model_id="local-deterministic",
                reasoning_effort="low",
                metrics={"composite": val},
                gates={"g1": True},
            )
        )
    drift_code, drift_receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src_dir,
        output_root=tmp_path / "sandbox_drift",
        sandbox=True,
        active_rubric_version="rubric.v1",
    )
    assert drift_code == 2
    assert len(drift_receipt["drift_alerts"]) >= 1
