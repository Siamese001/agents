"""Unit tests for the single unified CLI entrypoint into the outreach_engine pipeline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_outreach_engine_cli_help() -> None:
    res = _run_cli(["outreach_engine", "--help"])
    assert res.returncode == 0
    assert "usage: python -m outreach_engine" in res.stdout
    assert "run" in res.stdout
    assert "eval" in res.stdout
    assert "show" in res.stdout


def test_outreach_engine_run_help() -> None:
    res = _run_cli(["outreach_engine", "run", "--help"])
    assert res.returncode == 0
    assert "--json" in res.stdout
    assert "--brief" in res.stdout
    assert "--company" in res.stdout
    assert "--role" in res.stdout
    assert "--channel" in res.stdout
    assert "--audience" in res.stdout
    assert "--artifact-dir" in res.stdout
    assert "--demo" in res.stdout


def test_outreach_engine_eval_help() -> None:
    res = _run_cli(["outreach_engine", "eval", "--help"])
    assert res.returncode == 0
    assert "--run-dir" in res.stdout
    assert "--json" in res.stdout


def test_outreach_engine_show_help() -> None:
    res = _run_cli(["outreach_engine", "show", "--help"])
    assert res.returncode == 0
    assert "--run-dir" in res.stdout
    assert "--artifact" in res.stdout
    for artifact_choice in ("draft", "campaign", "evaluation", "validation", "research"):
        assert artifact_choice in res.stdout



def test_entrypoint_identity_and_parity() -> None:
    # 1. outreach_engine
    res_oe = _run_cli(["outreach_engine", "--help"])
    assert res_oe.returncode == 0
    assert "python -m outreach_engine" in res_oe.stdout

    # 2. apps_lic
    res_lic = _run_cli(["apps_lic", "--help"])
    assert res_lic.returncode == 0
    assert "python -m apps_lic" in res_lic.stdout

    # 3. agents outreach
    res_ao = _run_cli(["agents", "outreach", "--help"])
    assert res_ao.returncode == 0
    assert "python -m agents outreach" in res_ao.stdout


def test_outreach_engine_preflight_fail_closed_in_production(capsys: pytest.CaptureFixture[str]) -> None:
    from apps_lic.__main__ import main

    with mock.patch("agents.live_preflight._is_test_mode", return_value=False):
        with mock.patch.dict(os.environ, {"APPS_RG_L2_FORCE_STUB": "1"}):
            exit_code = main(["run"])
            assert exit_code == 2
            captured = capsys.readouterr()
            assert "Preflight Credential Failure" in captured.err


def test_outreach_engine_json_preflight_failure_output(capsys: pytest.CaptureFixture[str]) -> None:
    from apps_lic.__main__ import main

    with mock.patch("agents.live_preflight._is_test_mode", return_value=False):
        with mock.patch.dict(os.environ, {"APPS_RG_L2_FORCE_STUB": "1"}):
            exit_code = main(["run", "--json"])
            assert exit_code == 2
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["status"] == "FAILED"
            assert "PROHIBITED_MOCK_ENV" in data["error"]


def test_outreach_engine_canonical_demo_run_and_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "outreach_demo_run"
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
    assert (run_dir / "outreach_draft.json").is_file()
    assert (run_dir / "evaluation_report.json").is_file()
    assert (run_dir / "campaign_sequence.json").is_file()

