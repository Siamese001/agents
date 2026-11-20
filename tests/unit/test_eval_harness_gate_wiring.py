"""Wave 5 verification tests for Tier 2 readiness, CI promotion gate, pre-push, and rubric Pillar 7 wiring."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.validate_eval_rubrics import _validate_eval_harness_flywheel_health, validate_eval_rubrics

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_py(script: str, args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def test_ci_promotion_gate_wrapper_pass_blocked_and_regression(tmp_path: Path) -> None:
    out_dir = tmp_path / "ci_harness"
    report_path = tmp_path / "final_gate_report.json"

    # 1. Clean offline fast-dev run passes (exit 0)
    ok_proc = _run_py(
        "ops_scripts/ci/check_eval_harness_promotion_evidence.py",
        ["--run-offline", "--fast-dev", "--out-dir", str(out_dir), "--out", str(report_path), "--json"],
    )
    assert ok_proc.returncode == 0, f"stderr={ok_proc.stderr}\nstdout={ok_proc.stdout}"
    assert report_path.is_file()
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    assert rep["status"] == "PASS"

    manifest_path = out_dir / "evidence_manifest.json"
    assert manifest_path.is_file()

    # 2. Missing manifest fails closed with exit 1 (BLOCKED)
    missing_proc = _run_py(
        "ops_scripts/ci/check_eval_harness_promotion_evidence.py",
        ["--manifest", str(tmp_path / "nonexistent.json"), "--json"],
    )
    assert missing_proc.returncode == 1
    assert json.loads(missing_proc.stdout)["status"] == "BLOCKED"

    # 3. Injected regression fails closed with exit 2 (REGRESSION)
    mutated = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutated["suite_receipts"]["apps_lic.dev.outreach_message"]["baseline_comparison"]["delta"] = -0.20
    mutated["suite_receipts"]["apps_lic.dev.outreach_message"]["baseline_comparison"]["verdict"] = "regression"
    mutated_path = tmp_path / "regressed_manifest.json"
    mutated_path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
    reg_proc = _run_py(
        "ops_scripts/ci/check_eval_harness_promotion_evidence.py",
        ["--manifest", str(mutated_path), "--fast-dev", "--json"],
    )
    assert reg_proc.returncode == 2
    assert json.loads(reg_proc.stdout)["status"] == "REGRESSION"


def test_verify_main_readiness_wires_stage6_eval_harness_gate() -> None:
    proc = _run_py("tools/verify_main_readiness.py", ["--dry-run"])
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    assert "6. Resume & Outreach Eval Harness & Promotion Gate" in proc.stdout


def test_pre_push_hook_wires_eval_harness_gate() -> None:
    hook_text = (REPO_ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "ops_scripts/ci/check_eval_harness_promotion_evidence.py" in hook_text


def test_validate_eval_rubrics_pillar7_flywheel_health_passes() -> None:
    errs = _validate_eval_harness_flywheel_health(REPO_ROOT)
    assert errs == [], f"Pillar 7 violations: {errs}"
    full = validate_eval_rubrics(REPO_ROOT)
    assert full["is_clean"] is True, f"validate_eval_rubrics failed: {full['violations']}"
