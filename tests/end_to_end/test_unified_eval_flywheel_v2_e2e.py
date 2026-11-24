"""Wave 6 E2E test: Closed-loop Evaluation Flywheel v2 end-to-end verification."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

from agents.observability.eval_flywheel import EvalFlywheelEngine
from agents.observability.flywheel_sync_hook import sync_flywheel_after_run
from agents.observability.trace_collector import (
    compute_scenario_fingerprint,
    emit_post_run_trace_safe,
)
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from apps_eval.golden_suite_runner import evaluate_golden_flywheel_suite
from tools.run_eval_flywheel_cycle import run_eval_flywheel_cycle


def _init_e2e_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "e2e_repo"
    repo.mkdir(parents=True, exist_ok=True)
    src_root = Path(".").resolve()

    (repo / "config" / "governance").mkdir(parents=True, exist_ok=True)
    (repo / "config" / "prompt_governance").mkdir(parents=True, exist_ok=True)
    (repo / "data" / "eval" / "triage").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        src_root / "config" / "governance" / "auto_apply_policy.yaml",
        repo / "config" / "governance" / "auto_apply_policy.yaml",
    )
    shutil.copy2(
        src_root / "config" / "routing_calibration.yaml",
        repo / "config" / "routing_calibration.yaml",
    )
    shutil.copy2(
        src_root / "config" / "prompt_governance" / "priors.yaml",
        repo / "config" / "prompt_governance" / "priors.yaml",
    )
    (repo / ".gitignore").write_text(".worktrees/\nartifacts/\n", encoding="utf-8")

    subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, shell=False, timeout=10)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "E2E Operator"], check=True, shell=False, timeout=5)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "e2e@agents.local"], check=True, shell=False, timeout=5)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, shell=False, timeout=10)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "initial commit"], check=True, shell=False, timeout=10)
    return repo


def test_unified_eval_flywheel_v2_closed_loop_e2e(tmp_path: Path) -> None:
    repo = _init_e2e_git_repo(tmp_path)
    rt_root = repo / "artifacts" / "learning"
    traces_file = rt_root / "run_traces.jsonl"

    # 1. Emit 4 failing latency_sla traces (with distinct inputs and efficiency_score=0.41) so dev and holdout splits both populate
    for idx in range(4):
        emit_post_run_trace_safe(
            app_id="apps_rg",
            run_id=f"run-lat-fail-{idx}",
            session_id=f"sess-{idx % 2}",
            terminal_status="PASS",
            raw_input={"company": f"Anthropic_{idx}", "efficiency_score": 0.41},
            gate_outcomes={"x2_gates": {"c0_valid": True}},
            telemetry={"latency_ms": 95000.0},
            traces_path=traces_file,
            repo_root=repo,
        )
    for idx in range(4):
        emit_post_run_trace_safe(
            app_id="apps_rg",
            run_id=f"run-lat-pass-{idx}",
            session_id=f"sess-pass-{idx % 2}",
            terminal_status="PASS",
            raw_input={"company": "Anthropic", "efficiency_score": 0.92},
            gate_outcomes={"x2_gates": {"c0_valid": True}},
            telemetry={"latency_ms": 1200.0},
            traces_path=traces_file,
            repo_root=repo,
        )

    # 2. Fast post-run auto-sync (<1s) drains traces, populates online_eval_ledger, consolidates findings, and promotes golden cases
    sync_res = sync_flywheel_after_run(
        repo_root=repo,
        runtime_root=rt_root,
        force_in_pytest=True,
    )
    assert sync_res is not None
    assert sync_res["elapsed_s"] < 1.0
    assert sync_res["new_traces_drained"] == 8
    assert sync_res["total_findings"] == 1

    # 3. While the finding is OPEN, golden suite runs in shadow mode (passed=True, blocking_total=0)
    g_open = evaluate_golden_flywheel_suite(
        repo_root=repo,
        golden_dataset_path=rt_root / "golden_eval_cases.json",
        queue_snapshot_path=rt_root / "remediation_queue_snapshot.json",
    )
    assert g_open["passed"] is True
    assert g_open["shadow_total"] >= 1
    assert g_open["blocking_total"] == 0

    # 4. Run full flywheel cycle: cluster-routed Tier A proposal (v12_routing.loop_guard_efficiency_threshold)
    #    passes real domain shadow replay, auto-commits via ephemeral worktree onto main, and transitions finding to VERIFIED
    curated_seeds = [
        {
            "case_id": f"seed-hold-{i}",
            "suite_id": "apps_rg.holdout.v1",
            "app_id": "apps_rg",
            "unlabeled_input": {"payload": {"efficiency_score": 0.92}, "pii_redacted": True},
            "expected_contract": {"reference_label": "PASS"},
        }
        for i in range(5)
    ]
    code, receipt = run_eval_flywheel_cycle(
        repo_root=repo,
        source_root=rt_root,
        output_root=rt_root,
        sandbox=False,
        curated_holdout_seeds=curated_seeds,
    )
    assert code == 0
    assert receipt["auto_apply_dispatch"]["auto_applied_count"] == 1
    applied_info = receipt["auto_apply_dispatch"]["auto_applied"][0]
    assert applied_info["target_path"] == "config/routing_calibration.yaml"

    # Working tree on main is clean and threshold was promoted via ephemeral worktree commit
    status_out = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True, shell=False, timeout=5,
    ).stdout.strip()
    assert status_out == ""
    routing_doc = yaml.safe_load((repo / "config" / "routing_calibration.yaml").read_text(encoding="utf-8"))
    assert float(routing_doc["v12_routing"]["loop_guard_efficiency_threshold"]) > 0.40

    # 5. Now that the finding is VERIFIED, its golden cases are promoted to merge-blocking (blocking_total >= 1)
    q = SqliteFindingsQueueStore(rt_root / "remediation_queue.sqlite")
    try:
        findings = q.list_findings()
        assert len(findings) == 1
        assert findings[0].status == "VERIFIED"
    finally:
        q.close()

    g_verified = evaluate_golden_flywheel_suite(
        repo_root=repo,
        golden_dataset_path=rt_root / "golden_eval_cases.json",
        queue_snapshot_path=rt_root / "remediation_queue_snapshot.json",
    )
    assert g_verified["blocking_total"] >= 1
    assert g_verified["passed"] is True

    # 6. Scoped resolution check: a passing Truist run never wipes an open Anthropic triage packet
    fw = EvalFlywheelEngine(
        learning_db_path=rt_root / "feedback_learning.sqlite",
        trajectory_store_path=rt_root / "traj.json",
        calibration_history_path=rt_root / "cal.json",
        graduation_state_path=rt_root / "grad.json",
        triage_root=repo / "data" / "eval" / "triage",
    )
    anth_fp = compute_scenario_fingerprint(app_id="apps_rg", raw_input={"company": "Anthropic"})
    tru_fp = compute_scenario_fingerprint(app_id="apps_rg", raw_input={"company": "Truist"})
    fw.ingest_product_run(
        app_id="apps_rg",
        run_id="anth-fail",
        x3_disposition="X3A_DENY_REROUTE",
        passed=False,
        failure_reasons=["section:headline:x2_block"],
        score=0.0,
        scenario_fingerprint=anth_fp,
    )
    fw.ingest_product_run(
        app_id="apps_rg",
        run_id="tru-pass",
        x3_disposition="X3D_ALLOW_FINISH",
        passed=True,
        score=1.0,
        scenario_fingerprint=tru_fp,
    )
    assert len(fw.list_triage_candidates(app_filter="apps_rg", pending_only=True)) == 1
