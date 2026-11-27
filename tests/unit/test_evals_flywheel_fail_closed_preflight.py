"""Counterfactual rigor tests for Agent 5 (Fail-Closed Judge Drift, Flywheel Pending Exit, Grounding Tier & Coverage)."""
from __future__ import annotations

from pathlib import Path

from agents.eval_flywheel_cli import register_eval_flywheel_subparser, run_eval_flywheel
from ops_scripts.run_ide_judge_drift import main as run_ide_judge_drift_main
from tools.audit_eval_construct_validity import audit_repository
from tools.eval_shield_core.domain_eval_checks import (
    check_apps_research_domain,
    check_outreach_engine_domain,
    check_resume_graph_engine_domain,
    verify_unmocked_runtime_environment,
)
from tools.run_eval_flywheel_cycle import run_eval_flywheel_cycle

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ide_judge_drift_require_sealed_receipt_fails_closed_when_unsealed() -> None:
    # Default --check-preflight remains CI-safe (exit 0)
    assert run_ide_judge_drift_main(["--check-preflight"]) == 0
    # Strict --require-sealed-receipt must fail closed (exit 3) when human gold is unsealed
    adj_rg = REPO_ROOT / "data" / "judge_calibration" / "resume_human_adjudicated.v1.json"
    adj_lic = REPO_ROOT / "data" / "judge_calibration" / "outreach_human_adjudicated.v1.json"
    if not (adj_rg.is_file() and adj_lic.is_file()):
        assert run_ide_judge_drift_main(["--check-preflight", "--require-sealed-receipt"]) == 3


def test_flywheel_cycle_fail_on_pending_action_and_construct_validity(tmp_path: Path) -> None:
    assert callable(register_eval_flywheel_subparser)
    assert callable(run_eval_flywheel)
    ok_env, _ = verify_unmocked_runtime_environment()
    assert ok_env is True
    assert callable(check_resume_graph_engine_domain)
    assert callable(check_outreach_engine_domain)
    assert callable(check_apps_research_domain)

    cv = audit_repository(REPO_ROOT)
    assert cv["status"] == "PASS", cv["violations"]
    assert cv["grounding_tiers"]["tools/eval_shield_core/domain_eval_checks.py"] == "LIVE_CORPUS_GROUNDED"

    # Empty sandbox yields 0 pending items -> exit 0 even with fail_on_pending_action=True
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    code, receipt = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src,
        output_root=out,
        sandbox=True,
        fail_on_pending_action=True,
    )
    assert code == 0
    assert receipt["auto_apply_dispatch"]["pending_hitl_count"] == 0


def test_flywheel_sandbox_isolates_custom_source_root_from_repo_triage_and_preserves_canonical(
    tmp_path: Path,
) -> None:
    """Custom source_root must not leak live repo triage packets, while canonical artifacts/learning consolidates them."""
    import json
    import shutil

    fake_repo = tmp_path / "repo"
    (fake_repo / "config" / "governance").mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "config" / "governance" / "auto_apply_policy.yaml",
        fake_repo / "config" / "governance" / "auto_apply_policy.yaml",
    )
    triage_dir = fake_repo / "data" / "eval" / "triage" / "apps_lic"
    triage_dir.mkdir(parents=True)
    (triage_dir / "pending_pkt.json").write_text(
        json.dumps(
            {
                "app_id": "apps_lic",
                "candidate_id": "apps_lic_triage_isolation_01",
                "status": "PENDING_REVIEW",
                "trigger_reason": "IDE_CLI_JUDGE_V3_FAILED",
                "staged_at": "2026-11-27T22:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    isolated_src = tmp_path / "empty_src"
    isolated_src.mkdir()
    code_iso, receipt_iso = run_eval_flywheel_cycle(
        repo_root=fake_repo,
        source_root=isolated_src,
        output_root=tmp_path / "out_iso",
        sandbox=True,
        fail_on_pending_action=True,
    )
    assert code_iso == 0
    assert receipt_iso["findings_consolidation"]["total_findings"] == 0
    assert receipt_iso["auto_apply_dispatch"]["pending_hitl_count"] == 0

    canonical_src = fake_repo / "artifacts" / "learning"
    canonical_src.mkdir(parents=True)
    code_canon, receipt_canon = run_eval_flywheel_cycle(
        repo_root=fake_repo,
        source_root=canonical_src,
        output_root=tmp_path / "out_canon",
        sandbox=True,
        fail_on_pending_action=True,
    )
    assert code_canon == 3
    assert receipt_canon["findings_consolidation"]["total_findings"] == 1
    assert receipt_canon["auto_apply_dispatch"]["pending_hitl_count"] == 1


def test_flywheel_sandbox_preserves_verified_watermarks_and_reopens_post_watermark_regressions(
    tmp_path: Path,
) -> None:
    """Sandbox mode must snapshot source remediation_queue.sqlite so VERIFIED watermarks hold while newer regressions reopen."""
    from agents.observability.trace_collector import RunTraceCollector, build_run_trace
    from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore

    src = tmp_path / "learning"
    src.mkdir(parents=True)
    collector = RunTraceCollector(
        traces_path=src / "run_traces.jsonl",
        cursor_path=src / "run_traces_cursor.json",
    )
    collector.emit(
        build_run_trace(
            app_id="apps_rg",
            run_id="rg-hist-fail-1",
            session_id="sess-1",
            terminal_status="FAIL",
            raw_input={"jd": "Principal AI Architect"},
            gate_outcomes={"x2_gates": {"c0_valid": False}},
            telemetry={"latency_ms": 1200.0, "cost_usd": 0.0},
            finished_at_utc="2026-11-21T10:00:00Z",
        )
    )

    # Initial live consolidation creates OPEN finding, then operator marks it VERIFIED at watermark 2026-11-23T00:00:00Z.
    code_init, _ = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src,
        output_root=src,
        sandbox=False,
        fail_on_pending_action=True,
    )
    assert code_init == 3

    q = SqliteFindingsQueueStore(src / "remediation_queue.sqlite")
    try:
        open_findings = q.list_findings(status="OPEN")
        assert len(open_findings) == 1
        fid = open_findings[0].finding_id
        q.transition_status(
            fid,
            "VERIFIED",
            actor="operator",
            rationale="Verified fixed after consecutive passing runs.",
            now_utc="2026-11-23T00:00:00Z",
        )
    finally:
        q.close()

    # Sandbox preflight must respect the VERIFIED watermark and NOT resurrect the historical Nov 21 failure.
    code_clean, rec_clean = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src,
        output_root=tmp_path / "sandbox_clean",
        sandbox=True,
        fail_on_pending_action=True,
    )
    assert code_clean == 0
    assert rec_clean["auto_apply_dispatch"]["pending_hitl_count"] == 0

    # A NEW failure strictly after the watermark must reopen the finding in sandbox preflight (fail closed -> exit 3).
    collector.emit(
        build_run_trace(
            app_id="apps_rg",
            run_id="rg-post-wm-reg-2",
            session_id="sess-2",
            terminal_status="FAIL",
            raw_input={"jd": "Principal AI Architect"},
            gate_outcomes={"x2_gates": {"c0_valid": False}},
            telemetry={"latency_ms": 1200.0, "cost_usd": 0.0},
            finished_at_utc="2026-11-27T12:00:00Z",
        )
    )
    code_reopen, rec_reopen = run_eval_flywheel_cycle(
        repo_root=REPO_ROOT,
        source_root=src,
        output_root=tmp_path / "sandbox_reopen",
        sandbox=True,
        fail_on_pending_action=True,
    )
    assert code_reopen == 3
    assert rec_reopen["auto_apply_dispatch"]["pending_hitl_count"] == 1
