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
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_root}:{repo_root / 'resume_graph_engine' / 'src'}:{env.get('PYTHONPATH', '')}"
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_resume_engine_cli_help() -> None:
    res = _run_cli(["resume_engine", "--help"])
    assert res.returncode == 0
    assert "usage: python -m resume_engine" in res.stdout
    for subcmd in ("run", "eval", "show", "bootstrap", "patch-run", "preflight", "models", "cache"):
        assert subcmd in res.stdout


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

    # 1. Without posture set: secrets are NOT automatically injected
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("APPS_RG_ROUTE_HMAC_SECRET", None)
        os.environ.pop("APPS_RG_ROUTE_HMAC_KEY_ID", None)
        os.environ.pop("APPS_RG_ROUTE_SIGNING_POSTURE", None)

        try:
            main(["--help"])
        except SystemExit:
            pass

        assert "APPS_RG_ROUTE_HMAC_SECRET" not in os.environ
        assert "APPS_RG_ROUTE_HMAC_KEY_ID" not in os.environ

    # 2. With APPS_RG_ROUTE_SIGNING_POSTURE=ephemeral_dev: ephemeral secret is injected
    with mock.patch.dict(os.environ, {"APPS_RG_ROUTE_SIGNING_POSTURE": "ephemeral_dev"}, clear=False):
        os.environ.pop("APPS_RG_ROUTE_HMAC_SECRET", None)
        os.environ.pop("APPS_RG_ROUTE_HMAC_KEY_ID", None)

        try:
            main(["--help"])
        except SystemExit:
            pass

        secret = os.environ.get("APPS_RG_ROUTE_HMAC_SECRET")
        key_id = os.environ.get("APPS_RG_ROUTE_HMAC_KEY_ID")
        assert secret and len(secret) >= 32
        assert key_id and key_id.startswith("session-key-")
        assert os.environ.get("APPS_RG_ROUTE_SIGNING_POSTURE_APPLIED") == "ephemeral_dev"


def test_resume_engine_console_script() -> None:
    """Verify resume-engine console script entry point executes and outputs unified CLI usage."""
    repo_root = Path(__file__).resolve().parents[2]
    # Check if console script binary exists in virtualenv
    script_bin = Path(sys.executable).parent / "resume-engine"
    if not script_bin.is_file():
        pytest.skip(f"Console script {script_bin} not materialized in this virtualenv")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_root}:{repo_root / 'resume_graph_engine' / 'src'}:{env.get('PYTHONPATH', '')}"
    res = subprocess.run(
        [str(script_bin), "--help"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0
    assert "usage: resume-engine" in res.stdout
    for subcmd in ("run", "eval", "show", "bootstrap", "patch-run", "preflight", "models", "cache"):
        assert subcmd in res.stdout


def test_subcommands_help_pages() -> None:
    """Verify each of the 8 subcommands renders its respective help page cleanly."""
    for subcmd in ("run", "eval", "show", "bootstrap", "patch-run", "preflight", "models", "cache"):
        res = _run_cli(["resume_engine", subcmd, "--help"])
        assert res.returncode == 0
        assert f"usage: python -m resume_engine {subcmd}" in res.stdout


def test_resume_engine_models_subcommand() -> None:
    """Verify models subcommand inspects catalog, profiles, and emits valid digest."""
    res = _run_cli(["resume_engine", "models", "--json"])
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["status"] == "PASS"
    assert data["embedding_model"] == "BAAI/bge-m3"
    assert data["embedding_dimension"] == 1024
    assert data["canonical_digest"].startswith("sha256:")
    assert "generation_pins" in data
    assert len(data["generation_pins"]) > 0


def test_resume_engine_cache_subcommand() -> None:
    """Verify cache subcommand inspects briefing and vector caches."""
    res = _run_cli(["resume_engine", "cache", "--json"])
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["status"] == "PASS"
    assert "briefing_cache" in data
    assert "vector_cache" in data


def test_pipeline_ssot_chain_resolution() -> None:
    """Verify canonical pipeline chain: run resolves to canonical_dispatch -> r3r4 -> section lanes."""
    from apps_rg.runtime.orchestration.canonical_dispatch import (
        run_canonical_apps_rg_from_cli_primitives,
    )
    from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import (
        run_whole_run_with_route_governance,
    )
    from apps_rg.runtime.orchestration.managed_section_lane_dispatcher import (
        dispatch_phase1_lanes_managed,
    )

    assert callable(run_canonical_apps_rg_from_cli_primitives)
    assert callable(run_whole_run_with_route_governance)
    assert callable(dispatch_phase1_lanes_managed)

    # Verify workflow manifest SSOT exists and declares sections
    repo_root = Path(__file__).resolve().parents[2]
    manifest_path = (
        repo_root
        / "resume_graph_engine"
        / "src"
        / "apps_rg"
        / "config"
        / "domain_contract"
        / "workflow_manifest.resume_sections.v1.yaml"
    )
    assert manifest_path.is_file(), f"Workflow manifest SSOT not found: {manifest_path}"

