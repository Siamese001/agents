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
        rdir = tmp_path / "resume"
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "FINAL_RESUME_OUTPUT.txt").write_text("SVP Engineering Tailored Resume", encoding="utf-8")
        return 0

    captured_outreach_args = []
    def fake_outreach_main(argv, prog=None):
        captured_outreach_args.extend(argv)
        odir = tmp_path / "outreach"
        odir.mkdir(parents=True, exist_ok=True)
        (odir / "campaign.json").write_text('{"campaign_id": "test_campaign"}', encoding="utf-8")
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


def test_e2e_artifact_resolution_run_scoped_isolation(tmp_path):
    """Verify e2e never globs or touches foreign or stale run-proof directories."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    captured_artifact_dir = []

    def fake_resume_main(argv):
        if "--artifact-dir" in argv:
            idx = argv.index("--artifact-dir")
            art_dir = Path(argv[idx + 1])
            captured_artifact_dir.append(art_dir)
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text("ISOLATED_RUN_RESUME_CONTENT", encoding="utf-8")
            (art_dir / "apps_rg_product_authorization_receipt.json").write_text(json.dumps({"authorized": True}), encoding="utf-8")
        return 0

    def fake_outreach_main(argv, prog=None):
        odir = tmp_path / "outreach"
        odir.mkdir(parents=True, exist_ok=True)
        (odir / "campaign.json").write_text(json.dumps({"campaign": "isolated"}), encoding="utf-8")
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach_main):

        code = run_e2e(args)
        assert code == 0

    assert len(captured_artifact_dir) == 1
    scoped_dir = captured_artifact_dir[0]
    assert "full_resume_e2e_" in scoped_dir.name

    dest_resume = tmp_path / "resume" / "FINAL_RESUME_OUTPUT.txt"
    assert dest_resume.is_file()
    assert dest_resume.read_text(encoding="utf-8") == "ISOLATED_RUN_RESUME_CONTENT"

    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary["stages"]["resume_tailoring"]["status"] == "PASSED"
    import hashlib
    expected_sha = hashlib.sha256(b"ISOLATED_RUN_RESUME_CONTENT").hexdigest()
    assert summary["stages"]["resume_tailoring"]["resume_sha256"] == expected_sha


def test_e2e_artifact_resolution_concurrent_runs(tmp_path):
    """Verify concurrent e2e executions run with zero cross-contamination and exact provenance."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    def run_isolated_e2e(sub_dir_name: str, target_company: str) -> tuple[int, Path]:
        run_base = tmp_path / sub_dir_name
        parser = _build_parser()
        args = parser.parse_args([
            "e2e",
            "--company", target_company,
            "--role", "VP AI Engineering",
            "--artifact-dir", str(run_base),
            "--json",
        ])
        code = run_e2e(args)
        return code, run_base

    def fake_resume_main(argv):
        company = "Unknown"
        if "--target-company" in argv:
            company = argv[argv.index("--target-company") + 1]
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            time.sleep(0.02)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text(f"Resume for {company}", encoding="utf-8")
            (art_dir / "apps_rg_product_authorization_receipt.json").write_text(json.dumps({"authorized": True}), encoding="utf-8")
        return 0

    def fake_outreach_main(argv, prog=None):
        company = "Unknown"
        if "--company" in argv:
            company = argv[argv.index("--company") + 1]
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            time.sleep(0.02)
            (art_dir / "campaign.json").write_text(json.dumps({"company": company, "outreach": True}), encoding="utf-8")
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach_main):

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(run_isolated_e2e, "run_alpha", "AlphaCorp")
            fut2 = executor.submit(run_isolated_e2e, "run_beta", "BetaTech")
            res1, path1 = fut1.result(timeout=10.0)
            res2, path2 = fut2.result(timeout=10.0)

    assert res1 == 0
    assert res2 == 0

    resume1 = (path1 / "resume" / "FINAL_RESUME_OUTPUT.txt").read_text(encoding="utf-8")
    resume2 = (path2 / "resume" / "FINAL_RESUME_OUTPUT.txt").read_text(encoding="utf-8")
    assert resume1 == "Resume for AlphaCorp"
    assert resume2 == "Resume for BetaTech"

    campaign1 = json.loads((path1 / "outreach" / "campaign.json").read_text(encoding="utf-8"))
    campaign2 = json.loads((path2 / "outreach" / "campaign.json").read_text(encoding="utf-8"))
    assert campaign1["company"] == "AlphaCorp"
    assert campaign2["company"] == "BetaTech"

    summary1 = json.loads((path1 / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    summary2 = json.loads((path2 / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    assert summary1["stages"]["resume_tailoring"]["resume_sha256"] != summary2["stages"]["resume_tailoring"]["resume_sha256"]
    assert summary1["workflow_status"] == WorkflowStatus.COMPLETED.value
    assert summary2["workflow_status"] == WorkflowStatus.COMPLETED.value


def test_e2e_fails_closed_when_resume_output_missing_despite_zero_exit_code(tmp_path):
    """Verify that if apps_rg returns exit code 0 but writes no output, the stage fails closed."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    outreach_mock = MagicMock()

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", return_value=0), \
         patch("apps_lic.__main__.main", outreach_mock):

        code = run_e2e(args)
        assert code == 1

    outreach_mock.assert_not_called()
    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["resume_tailoring"]["status"] == "FAILED"
    assert "missing" in summary["stages"]["resume_tailoring"]["error"].lower()


def test_e2e_fails_closed_when_resume_receipt_unauthorized(tmp_path):
    """Verify that if apps_rg produces a resume but receipt indicates unauthorized, it fails closed."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    def fake_resume_main(argv):
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text("Unauthorized Resume", encoding="utf-8")
            (art_dir / "apps_rg_product_authorization_receipt.json").write_text(
                json.dumps({"authorized": False, "reason": "Low rubric score"}), encoding="utf-8"
            )
        return 0

    outreach_mock = MagicMock()

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", outreach_mock):

        code = run_e2e(args)
        assert code == 1

    outreach_mock.assert_not_called()
    summary = json.loads((tmp_path / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["resume_tailoring"]["status"] == "FAILED"
    assert "unauthorized" in summary["stages"]["resume_tailoring"]["error"].lower()


def test_e2e_fails_closed_when_outreach_campaign_missing(tmp_path):
    """Verify that if outreach returns 0 but writes no campaign file, stage fails closed."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    def fake_resume_main(argv):
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text("Valid Resume", encoding="utf-8")
            (art_dir / "apps_rg_product_authorization_receipt.json").write_text(json.dumps({"authorized": True}), encoding="utf-8")
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", return_value=0):

        code = run_e2e(args)
        assert code == 1

    summary = json.loads((tmp_path / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["executive_outreach"]["status"] == "FAILED"
    assert "not generated or is empty" in summary["stages"]["executive_outreach"]["error"]


def test_e2e_fails_closed_when_outreach_receipt_unsealed(tmp_path):
    """Verify that if outreach writes a draft but run_receipt marks sealed=False, it fails closed."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    def fake_resume_main(argv):
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text("Valid Resume", encoding="utf-8")
            (art_dir / "apps_rg_product_authorization_receipt.json").write_text(json.dumps({"authorized": True}), encoding="utf-8")
        return 0

    def fake_outreach_main(argv, prog=None):
        odir = tmp_path / "outreach"
        odir.mkdir(parents=True, exist_ok=True)
        (odir / "campaign.json").write_text(json.dumps({"draft": "unapproved"}), encoding="utf-8")
        (odir / "run_receipt.json").write_text(json.dumps({"sealed": False, "overall_passed": False}), encoding="utf-8")
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach_main):

        code = run_e2e(args)
        assert code == 1

    summary = json.loads((tmp_path / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["executive_outreach"]["status"] == "FAILED"
    assert "unsealed" in summary["stages"]["executive_outreach"]["error"].lower()


def test_e2e_stage4_fails_closed_on_missing_required_deliverable(tmp_path):
    """Verify Stage 4 sealing fails closed if a required deliverable is missing before sealing."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    def fake_resume_main(argv):
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text("Valid Resume", encoding="utf-8")
            (art_dir / "apps_rg_product_authorization_receipt.json").write_text(json.dumps({"authorized": True}), encoding="utf-8")
        return 0

    def fake_outreach_mutates_prior_stage(argv, prog=None):
        odir = tmp_path / "outreach"
        odir.mkdir(parents=True, exist_ok=True)
        (odir / "campaign.json").write_text(json.dumps({"campaign": "ok"}), encoding="utf-8")
        # Tamper with Stage 2 deliverable before Stage 4 runs
        (tmp_path / "resume" / "FINAL_RESUME_OUTPUT.txt").unlink()
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach_mutates_prior_stage):

        code = run_e2e(args)
        assert code == 1

    summary = json.loads((tmp_path / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert "final_resume" in summary.get("sealing_error", "")


def test_e2e_fails_closed_when_resume_output_empty(tmp_path):
    """Verify that if apps_rg writes an empty (0-byte) resume file, it fails closed."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    def fake_resume_main(argv):
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text("   \n", encoding="utf-8")
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", return_value=0):

        code = run_e2e(args)
        assert code == 1

    summary = json.loads((tmp_path / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["resume_tailoring"]["status"] == "FAILED"
    assert "empty" in summary["stages"]["resume_tailoring"]["error"].lower()


def test_e2e_fails_closed_when_resume_contains_fallback_marker(tmp_path):
    """Verify that if apps_rg resume contains [NOT_GENERATED_BY_RUN:], it fails closed."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    def fake_resume_main(argv):
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text("Header\n[NOT_GENERATED_BY_RUN: fallback]", encoding="utf-8")
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", return_value=0):

        code = run_e2e(args)
        assert code == 1

    summary = json.loads((tmp_path / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["resume_tailoring"]["status"] == "FAILED"
    assert "fallback marker" in summary["stages"]["resume_tailoring"]["error"]


def test_e2e_fails_closed_when_outreach_output_empty(tmp_path):
    """Verify that if outreach writes a 0-byte campaign file, it fails closed."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--artifact-dir", str(tmp_path),
        "--json",
    ])

    def fake_resume_main(argv):
        if "--artifact-dir" in argv:
            art_dir = Path(argv[argv.index("--artifact-dir") + 1])
            art_dir.mkdir(parents=True, exist_ok=True)
            (art_dir / "FINAL_RESUME_OUTPUT.txt").write_text("Valid Resume", encoding="utf-8")
            (art_dir / "apps_rg_product_authorization_receipt.json").write_text(json.dumps({"authorized": True}), encoding="utf-8")
        return 0

    def fake_outreach_main(argv, prog=None):
        odir = tmp_path / "outreach"
        odir.mkdir(parents=True, exist_ok=True)
        (odir / "campaign.json").write_text("", encoding="utf-8")
        return 0

    with patch("agents.live_preflight.assert_engine_live_preflight"), \
         patch("apps_rg.__main__.main", side_effect=fake_resume_main), \
         patch("apps_lic.__main__.main", side_effect=fake_outreach_main):

        code = run_e2e(args)
        assert code == 1

    summary = json.loads((tmp_path / "e2e_lifecycle_summary.json").read_text(encoding="utf-8"))
    assert summary["workflow_status"] == WorkflowStatus.FAILED.value
    assert summary["stages"]["executive_outreach"]["status"] == "FAILED"
    assert "not generated or is empty" in summary["stages"]["executive_outreach"]["error"]


