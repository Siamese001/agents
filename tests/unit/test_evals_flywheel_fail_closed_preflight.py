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
