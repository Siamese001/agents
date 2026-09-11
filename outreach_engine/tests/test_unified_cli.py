"""Tests for the single unified CLI entrypoint and canonical engine commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )


def test_agents_cli_help() -> None:
    res = _run_cli(["agents", "--help"])
    assert res.returncode == 0
    assert "resume" in res.stdout
    assert "outreach" in res.stdout
    assert "e2e" in res.stdout


def test_agents_cli_resume_help() -> None:
    res = _run_cli(["agents", "resume", "--help"])
    assert res.returncode == 0
    assert "run" in res.stdout
    assert "eval" in res.stdout
    assert "show" in res.stdout


def test_agents_cli_outreach_help() -> None:
    res = _run_cli(["agents", "outreach", "--help"])
    assert res.returncode == 0
    assert "run" in res.stdout
    assert "eval" in res.stdout
    assert "show" in res.stdout


def test_resume_engine_module_shims() -> None:
    res1 = _run_cli(["resume_engine", "--help"])
    assert res1.returncode == 0
    assert "run" in res1.stdout

    res2 = _run_cli(["resume_graph_engine", "--help"])
    assert res2.returncode == 0
    assert "run" in res2.stdout


def test_outreach_engine_canonical_run_and_inspection(tmp_path: Path) -> None:
    # 1. Test canonical run
    run_dir = tmp_path / "test_run"
    run_res = _run_cli([
        "outreach_engine",
        "run",
        "--demo",
        "--artifact-dir",
        str(run_dir),
        "--json",
    ])
    assert run_res.returncode == 0, f"run failed: {run_res.stderr}"
    data = json.loads(run_res.stdout)
    assert data["status"] == "PASSED"
    assert data["draft"]["subject"] != ""

    # 2. Test canonical show
    show_res = _run_cli([
        "outreach_engine",
        "show",
        "--run-dir",
        str(run_dir),
        "--artifact",
        "draft",
    ])
    assert show_res.returncode == 0
    assert "Subject" in show_res.stdout
    assert "Charles Morris" in show_res.stdout

    # 3. Test canonical eval
    eval_res = _run_cli([
        "outreach_engine",
        "eval",
        "--run-dir",
        str(run_dir),
        "--json",
    ])
    assert eval_res.returncode == 0
    eval_data = json.loads(eval_res.stdout)
    assert eval_data["evaluation"]["passed"] is True


def test_agents_outreach_unified_demo_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "unified_run"
    res = _run_cli([
        "agents",
        "outreach",
        "run",
        "--demo",
        "--artifact-dir",
        str(run_dir),
        "--json",
    ])
    assert res.returncode == 0, f"agents outreach failed: {res.stderr}"
    data = json.loads(res.stdout)
    assert data["status"] == "PASSED"
    assert (run_dir / "outreach_draft.json").is_file()
