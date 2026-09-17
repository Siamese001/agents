"""Unit tests for the single unified CLI entrypoint into the resume_engine pipeline."""

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


def test_resume_engine_cli_help() -> None:
    res = _run_cli(["resume_engine", "--help"])
    assert res.returncode == 0
    assert "usage: python -m resume_engine" in res.stdout
    assert "run" in res.stdout
    assert "eval" in res.stdout
    assert "show" in res.stdout


def test_resume_engine_run_help() -> None:
    res = _run_cli(["resume_engine", "run", "--help"])
    assert res.returncode == 0
    assert "--json" in res.stdout
    assert "--target-company" in res.stdout
    assert "--target-role" in res.stdout
    assert "--jd" in res.stdout
    assert "--resume" in res.stdout
    assert "--artifact-dir" in res.stdout
    assert "--briefing" in res.stdout


def test_resume_engine_eval_help() -> None:
    res = _run_cli(["resume_engine", "eval", "--help"])
    assert res.returncode == 0
    assert "--run-dir" in res.stdout


def test_resume_engine_show_help() -> None:
    res = _run_cli(["resume_engine", "show", "--help"])
    assert res.returncode == 0
    assert "--run-dir" in res.stdout
    assert "--artifact" in res.stdout
    for artifact_choice in ("resume", "email", "research", "summary", "evaluation"):
        assert artifact_choice in res.stdout


def test_entrypoint_identity_and_parity() -> None:
    # 1. resume_engine
    res_re = _run_cli(["resume_engine", "--help"])
    assert res_re.returncode == 0
    assert "python -m resume_engine" in res_re.stdout

    # 2. apps_rg
    res_rg = _run_cli(["apps_rg", "--help"])
    assert res_rg.returncode == 0
    assert "python -m apps_rg" in res_rg.stdout

    # 3. resume_graph_engine
    res_rge = _run_cli(["resume_graph_engine", "--help"])
    assert res_rge.returncode == 0
    assert "python -m resume_graph_engine" in res_rge.stdout

    # 4. agents resume
    res_ar = _run_cli(["agents", "resume", "--help"])
    assert res_ar.returncode == 0
    assert "python -m agents resume" in res_ar.stdout


def test_resume_engine_preflight_fail_closed_in_production(capsys: pytest.CaptureFixture[str]) -> None:
    from apps_rg.__main__ import main

    with mock.patch("agents.live_preflight._is_test_mode", return_value=False):
        with mock.patch.dict(os.environ, {"APPS_RG_L2_FORCE_STUB": "1"}):
            exit_code = main(["run"])
            assert exit_code == 2
            captured = capsys.readouterr()
            assert "Preflight Credential Failure" in captured.err


def test_resume_engine_json_preflight_failure_output(capsys: pytest.CaptureFixture[str]) -> None:
    from apps_rg.__main__ import main

    with mock.patch("agents.live_preflight._is_test_mode", return_value=False):
        with mock.patch.dict(os.environ, {"APPS_RG_L2_FORCE_STUB": "1"}):
            exit_code = main(["run", "--json"])
            assert exit_code == 2
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["status"] == "FAILED"
            assert "PROHIBITED_MOCK_ENV" in data["error"]


def test_resume_engine_route_hmac_env_injection() -> None:
    from apps_rg.__main__ import main

    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("APPS_RG_ROUTE_HMAC_SECRET", None)
        os.environ.pop("APPS_RG_ROUTE_HMAC_KEY_ID", None)

        # Invoking help parses and sets env
        try:
            main(["--help"])
        except SystemExit:
            pass

        assert os.environ.get("APPS_RG_ROUTE_HMAC_SECRET") == "agents-local-dev-session-secret"
        assert os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID") == "agents-local-dev-key"
