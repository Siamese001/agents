"""Bounded integration tests for agents e2e --json authoritative lifecycle flows."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.cli import _build_parser, run_e2e
from infrastructure.live_execution import LiveExecutionError


def _setup_stage_mocks(tmp_path: Path):
    """Helper to provision mock handlers that simulate child execution and noisy logs."""
    fake_briefing_path = tmp_path / "research" / "briefing.md"
    fake_briefing_path.parent.mkdir(parents=True, exist_ok=True)
    fake_briefing_path.write_text("# Enterprise Briefing: Anthropic\n- Priority: AI Safety", encoding="utf-8")

    from apps_rg.integrations.managed_research_delegation import ResumeBriefingReady

    mock_ready = ResumeBriefingReady(
        request_id="req-int-123",
        run_id="run-int-123",
        trace_id="tr-int-123",
        briefing_text=fake_briefing_path.read_text(),
        research_run_id="rrun-int-123",
        research_evidence_count=2,
        confidence_score=0.95,
        research_artifact_dir=str(fake_briefing_path.parent),
        result_hash="hash-int-123",
        evidence_lineage=(),
        apps_research_handoff_envelope={},
        dispatch_duration_ms=45.0,
        research_briefing_path=str(fake_briefing_path),
        brief_sha256="sha256:" + hashlib.sha256(fake_briefing_path.read_bytes()).hexdigest(),
    )

    def fake_resume_success(argv):
        print("[CHILD STDOUT: apps_rg] Initializing graph neural tokenizer...")
        print("[CHILD STDOUT: apps_rg] Tailoring executive resume...")
        rdir = tmp_path / "resume"
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "FINAL_RESUME_OUTPUT.txt").write_text("SVP Engineering Tailored Resume Output", encoding="utf-8")
        return 0

    def fake_outreach_success(argv, prog=None):
        print("[CHILD STDOUT: apps_lic] Generating touches 1..3...")
        print("[CHILD STDOUT: apps_lic] Evaluating against candidate manifest...")
        odir = tmp_path / "outreach"
        odir.mkdir(parents=True, exist_ok=True)
        (odir / "campaign_sequence.json").write_text(
            json.dumps({"touches": [{"channel": "inmail", "body": "Executive message"}]}),
            encoding="utf-8",
        )
        return 0

    return mock_ready, fake_resume_success, fake_outreach_success


def test_e2e_json_success_flow(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test full E2E success flow emits exactly one authoritative JSON lifecycle record."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--demo",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    mock_ready, fake_resume, fake_outreach = _setup_stage_mocks(tmp_path)

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach):

        code = run_e2e(args)
        assert code == 0

    captured = capsys.readouterr()
    stdout_raw = captured.out.strip()

    # Verify exactly one parseable JSON payload on stdout
    assert stdout_raw.startswith("{")
    assert stdout_raw.endswith("}")
    data = json.loads(stdout_raw)

    assert data["status"] == "PASSED"
    assert data["workflow_status"] == "COMPLETED"
    assert data["company"] == "Anthropic"
    assert data["failure_reasons"] == []

    # Check stage statuses
    stages = data["stages"]
    assert stages["resume_tailoring"]["status"] == "PASSED"
    assert stages["executive_outreach"]["status"] == "PASSED"
    assert stages["lifecycle_sealing"]["status"] == "PASSED"

    # Check artifact hashes
    hashes = data["artifact_hashes"]
    assert "final_resume" in hashes
    assert "outreach_campaign" in hashes
    resume_file = tmp_path / "resume" / "FINAL_RESUME_OUTPUT.txt"
    campaign_file = tmp_path / "outreach" / "campaign_sequence.json"
    assert hashes["final_resume"] == hashlib.sha256(resume_file.read_bytes()).hexdigest()
    assert hashes["outreach_campaign"] == hashlib.sha256(campaign_file.read_bytes()).hexdigest()

    # Check latency
    assert data["latency"]["total_ms"] > 0.0
    assert "stages_ms" in data["latency"]


def test_e2e_json_blocked_flow(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test blocked/failure flow produces non-zero exit code and structured failure reasons."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--demo",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    def fake_resume_blocked(argv):
        print("[CHILD STDOUT: apps_rg] Policy gatekeeper blocked run!")
        rdir = tmp_path / "resume"
        rdir.mkdir(parents=True, exist_ok=True)
        # Create non-allow x3 receipt
        (rdir / "x3_disposition_receipt.json").write_text(
            json.dumps({"x3_disposition": "X3D_BLOCK_SUBMISSION"}),
            encoding="utf-8",
        )
        (rdir / "FINAL_RESUME_OUTPUT.txt").write_text("Blocked output", encoding="utf-8")
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_blocked):

        code = run_e2e(args)
        assert code != 0

    captured = capsys.readouterr()
    stdout_raw = captured.out.strip()

    assert stdout_raw.startswith("{")
    assert stdout_raw.endswith("}")
    data = json.loads(stdout_raw)

    assert data["status"] in ("FAILED", "BLOCKED")
    assert data["workflow_status"] == "FAILED"
    assert len(data["failure_reasons"]) > 0
    assert any("blocked run" in r.lower() for r in data["failure_reasons"])
    assert data["stages"]["resume_tailoring"]["status"] in ("FAILED", "BLOCKED")


def test_e2e_json_research_enabled_flow(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test --with-research flow executes upstream research and captures brief_sha256."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--with-research",
        "--demo",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    mock_ready, fake_resume, fake_outreach = _setup_stage_mocks(tmp_path)

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.integrations.managed_research_delegation.dispatch_resume_research_briefing", return_value=mock_ready), \
         patch("apps_rg.__main__.main", side_effect=fake_resume), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach):

        code = run_e2e(args)
        assert code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data["status"] == "PASSED"
    assert data["stages"]["company_research"]["status"] == "PASSED"
    assert data["stages"]["company_research"]["brief_sha256"].startswith("sha256:")
    assert "research_briefing" in data["artifact_hashes"]
    briefing_file = tmp_path / "research" / "briefing.md"
    assert data["artifact_hashes"]["research_briefing"] == hashlib.sha256(briefing_file.read_bytes()).hexdigest()


def test_e2e_json_resume_skipped_flow(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test --skip-resume marks resume stage SKIPPED and proceeds with outreach."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--skip-resume",
        "--demo",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    mock_ready, fake_resume, fake_outreach = _setup_stage_mocks(tmp_path)

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach):

        code = run_e2e(args)
        assert code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data["status"] == "PASSED"
    assert data["stages"]["resume_tailoring"]["status"] == "SKIPPED"
    assert data["stages"]["executive_outreach"]["status"] == "PASSED"
    assert "final_resume" not in data["artifact_hashes"]
    assert "outreach_campaign" in data["artifact_hashes"]
    assert data["failure_reasons"] == []


def test_e2e_json_preflight_blocked_flow(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test preflight credential failure emits authoritative lifecycle result and exit code 2."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    with patch("agents.live_preflight.assert_engine_live_preflight", side_effect=LiveExecutionError("Missing live API credentials")):
        code = run_e2e(args)
        assert code == 2

    captured = capsys.readouterr()
    data = json.loads(captured.out.strip())

    assert data["status"] == "BLOCKED"
    assert data["workflow_status"] == "FAILED"
    assert len(data["failure_reasons"]) > 0
    assert "Missing live API credentials" in data["failure_reasons"][0]
    assert data["stages"]["preflight"]["status"] == "FAILED"


def test_e2e_json_child_output_isolation_strict(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Verify child print statements are strictly captured in logs/*.log and never leak to stdout."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--demo",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    mock_ready, fake_resume, fake_outreach = _setup_stage_mocks(tmp_path)

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach):

        code = run_e2e(args)
        assert code == 0

    captured = capsys.readouterr()
    # Confirm child markers are completely absent from stdout
    assert "[CHILD STDOUT: apps_rg]" not in captured.out
    assert "[CHILD STDOUT: apps_lic]" not in captured.out

    # Confirm child markers are present in respective isolated log files
    resume_log = tmp_path / "logs" / "resume_tailoring.log"
    outreach_log = tmp_path / "logs" / "executive_outreach.log"
    assert resume_log.is_file()
    assert "[CHILD STDOUT: apps_rg]" in resume_log.read_text(encoding="utf-8")
    assert outreach_log.is_file()
    assert "[CHILD STDOUT: apps_lic]" in outreach_log.read_text(encoding="utf-8")
