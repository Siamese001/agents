"""Wave 4 verification tests for unified `python -m agents eval-flywheel` and `learning` CLI commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_cli(args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def test_apps_eval_direct_cli_guard_remains_intact() -> None:
    proc = _run_cli(["apps_eval"])
    assert proc.returncode == 1
    assert "APPS_RG_CLI_VIOLATION" in proc.stderr


def test_eval_flywheel_cli_run_gate_status_and_learning_commands(tmp_path: Path) -> None:
    out_dir = tmp_path / "ef_out"
    db_path = tmp_path / "fb.sqlite"
    triage_dir = tmp_path / "triage"

    # 1. Run fast-dev offline eval harness + ingest into isolated flywheel stores
    run_proc = _run_cli(
        [
            "agents",
            "eval-flywheel",
            "run",
            "--app",
            "all",
            "--mode",
            "offline",
            "--fast-dev",
            "--out-dir",
            str(out_dir),
            "--learning-db",
            str(db_path),
            "--triage-root",
            str(triage_dir),
            "--json",
        ]
    )
    assert run_proc.returncode == 0, f"stderr={run_proc.stderr}\nstdout={run_proc.stdout}"
    run_data = json.loads(run_proc.stdout)
    assert run_data["status"] == "PASS"
    assert run_data["flywheel_ingested"] is True
    manifest_path = run_data["manifest_path"]
    assert Path(manifest_path).is_file()

    # 2. Gate command passes on sealed manifest
    gate_proc = _run_cli(
        [
            "agents",
            "eval-flywheel",
            "gate",
            "--manifest",
            manifest_path,
            "--no-require-holdout",
            "--no-require-engine-probes",
            "--json",
        ]
    )
    assert gate_proc.returncode == 0, f"stderr={gate_proc.stderr}"
    gate_data = json.loads(gate_proc.stdout)
    assert gate_data["passed"] is True

    # 3. Status command returns combined telemetry
    status_proc = _run_cli(
        [
            "agents",
            "eval-flywheel",
            "status",
            "--manifest",
            manifest_path,
            "--learning-db",
            str(db_path),
            "--triage-root",
            str(triage_dir),
            "--json",
        ]
    )
    assert status_proc.returncode == 0, f"stderr={status_proc.stderr}"
    status_data = json.loads(status_proc.stdout)
    assert status_data["baselines"]["status"] == "PASS"
    assert status_data["latest_promotion_gate"]["status"] == "PASS"

    # 4. Learning triage-list, graduation-status, and drift commands return valid JSON
    triage_proc = _run_cli(
        ["agents", "learning", "triage-list", "--triage-root", str(triage_dir), "--json"]
    )
    assert triage_proc.returncode == 0
    assert "candidates" in json.loads(triage_proc.stdout)

    grad_proc = _run_cli(["agents", "learning", "graduation-status", "--json"])
    assert grad_proc.returncode == 0
    assert "consecutive_target" in json.loads(grad_proc.stdout)

    drift_proc = _run_cli(["agents", "learning", "drift", "--json"])
    assert drift_proc.returncode == 0
    assert "statistical_drift" in json.loads(drift_proc.stdout)
