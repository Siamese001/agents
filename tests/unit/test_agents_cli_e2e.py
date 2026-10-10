"""Unit tests for agents e2e unified CLI orchestration, handoffs, and sealing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.cli import _build_parser, run_e2e
from agents.orchestration.primitives import WorkflowStatus


def test_cli_parser_e2e_flags():
    parser = _build_parser()
    args = parser.parse_args(["e2e", "--with-research", "--demo", "--json"])
    assert args.engine == "e2e"
    assert args.with_research is True
    assert args.demo is True
    assert args.json is True


def test_e2e_orchestrator_stage_continuity_and_provenance(tmp_path):
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--with-research",
        "--demo",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    fake_briefing_path = tmp_path / "research" / "briefing.md"
    fake_briefing_path.parent.mkdir(parents=True, exist_ok=True)
    fake_briefing_path.write_text("# Enterprise Briefing: Anthropic\n- Priority: AI Safety", encoding="utf-8")

    fake_resume_path = tmp_path / "resume" / "FINAL_RESUME_OUTPUT.txt"
    fake_resume_path.parent.mkdir(parents=True, exist_ok=True)
    fake_resume_path.write_text("Executive Resume Content", encoding="utf-8")

    fake_campaign_path = tmp_path / "outreach" / "campaign.json"
    fake_campaign_path.parent.mkdir(parents=True, exist_ok=True)
    fake_campaign_path.write_text(json.dumps({"touches": [{"channel": "inmail"}]}), encoding="utf-8")

    from apps_rg.integrations.managed_research_delegation import ResumeBriefingReady

    mock_ready = ResumeBriefingReady(
        request_id="req-123",
        run_id="run-123",
        trace_id="tr-123",
        briefing_text=fake_briefing_path.read_text(),
        research_run_id="rrun-123",
        research_evidence_count=3,
        confidence_score=0.92,
        research_artifact_dir=str(fake_briefing_path.parent),
        result_hash="hash-123",
        evidence_lineage=(),
        apps_research_handoff_envelope={},
        dispatch_duration_ms=50.0,
        research_briefing_path=str(fake_briefing_path),
        brief_sha256="sha256:abc123brief",
    )

    captured_resume_args = []
    def fake_resume_main(argv):
        captured_resume_args.extend(argv)
        # write file in mock runtime proofs if needed
        return 0

    captured_outreach_args = []
    def fake_outreach_main(argv, prog=None):
        captured_outreach_args.extend(argv)
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.integrations.managed_research_delegation.dispatch_resume_research_briefing", return_value=mock_ready), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach_main):

        code = run_e2e(args)
        assert code == 0

    # Verify briefing was handed off to resume engine
    assert "--briefing" in captured_resume_args
    brief_idx = captured_resume_args.index("--briefing")
    assert captured_resume_args[brief_idx + 1] == str(tmp_path / "research" / "briefing.md")

    # Verify briefing was handed off to outreach engine
    assert "--brief" in captured_outreach_args
    obrief_idx = captured_outreach_args.index("--brief")
    assert captured_outreach_args[obrief_idx + 1] == str(tmp_path / "research" / "briefing.md")

    # Verify Stage 4 sealing manifest
    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text())
    assert summary["workflow_status"] == WorkflowStatus.COMPLETED.value
    assert summary["stages"]["company_research"]["status"] == "PASSED"
    assert summary["stages"]["resume_tailoring"]["status"] == "PASSED"
    assert summary["stages"]["executive_outreach"]["status"] == "PASSED"
    assert "artifact_proofs" in summary
    assert "research_briefing" in summary["artifact_proofs"]
    assert "final_resume" in summary["artifact_proofs"]
    assert "outreach_campaign" in summary["artifact_proofs"]


def test_e2e_orchestrator_fails_closed_on_stage_failure(tmp_path):
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--with-research",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    from apps_rg.integrations.managed_research_delegation import ResearchDispatchFailure

    mock_fail = ResearchDispatchFailure(
        request_id="req-fail",
        run_id="run-fail",
        trace_id="tr-fail",
        r5_reason_code="APPS_RESEARCH_FAILED",
        detail="Simulated provider failure",
        dispatch_duration_ms=10.0,
    )

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.integrations.managed_research_delegation.dispatch_resume_research_briefing", return_value=mock_fail):

        code = run_e2e(args)
        assert code == 1

    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text())
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["company_research"]["status"] == "FAILED"


def test_e2e_orchestrator_fails_closed_on_resume_failure(tmp_path):
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--with-research",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    fake_briefing = tmp_path / "research" / "briefing.md"
    fake_briefing.parent.mkdir(parents=True, exist_ok=True)
    fake_briefing.write_text("# Briefing\n- Strategic focus", encoding="utf-8")

    from apps_rg.integrations.managed_research_delegation import ResumeBriefingReady

    mock_ready = ResumeBriefingReady(
        request_id="req-123",
        run_id="run-123",
        trace_id="tr-123",
        briefing_text=fake_briefing.read_text(),
        research_run_id="rrun-123",
        research_evidence_count=1,
        confidence_score=0.90,
        research_artifact_dir=str(fake_briefing.parent),
        result_hash="hash-123",
        evidence_lineage=(),
        apps_research_handoff_envelope={},
        dispatch_duration_ms=10.0,
        research_briefing_path=str(fake_briefing),
        brief_sha256="sha256:abc",
    )

    outreach_mock = MagicMock()

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.integrations.managed_research_delegation.dispatch_resume_research_briefing", return_value=mock_ready), \
         patch("apps_rg.__main__.main", return_value=1), \
         patch("apps_lic.__main__.main", outreach_mock):

        code = run_e2e(args)
        assert code == 1

    # Outreach should NOT have been called due to fail-closed dependency
    outreach_mock.assert_not_called()

    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text())
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["resume_tailoring"]["status"] == "FAILED"


def test_e2e_orchestrator_fails_closed_on_outreach_failure(tmp_path):
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--with-research",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    fake_briefing = tmp_path / "research" / "briefing.md"
    fake_briefing.parent.mkdir(parents=True, exist_ok=True)
    fake_briefing.write_text("# Briefing\n- Strategic focus", encoding="utf-8")

    fake_resume = tmp_path / "resume" / "FINAL_RESUME_OUTPUT.txt"
    fake_resume.parent.mkdir(parents=True, exist_ok=True)
    fake_resume.write_text("Resume Content", encoding="utf-8")

    from apps_rg.integrations.managed_research_delegation import ResumeBriefingReady

    mock_ready = ResumeBriefingReady(
        request_id="req-123",
        run_id="run-123",
        trace_id="tr-123",
        briefing_text=fake_briefing.read_text(),
        research_run_id="rrun-123",
        research_evidence_count=1,
        confidence_score=0.90,
        research_artifact_dir=str(fake_briefing.parent),
        result_hash="hash-123",
        evidence_lineage=(),
        apps_research_handoff_envelope={},
        dispatch_duration_ms=10.0,
        research_briefing_path=str(fake_briefing),
        brief_sha256="sha256:abc",
    )

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.integrations.managed_research_delegation.dispatch_resume_research_briefing", return_value=mock_ready), \
         patch("apps_rg.__main__.main", return_value=0), \
         patch("apps_lic.__main__.main", return_value=2):

        code = run_e2e(args)
        assert code == 1

    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text())
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["executive_outreach"]["status"] == "FAILED"
