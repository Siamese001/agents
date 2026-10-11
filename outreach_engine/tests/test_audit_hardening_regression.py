"""Focused end-to-end regression tests verifying audit remediations for outreach_engine.

Covers:
1. Prevention of silent mission-role overrides (brief role preservation vs explicit override).
2. Adapter ingress role honor in canonical_dispatch.
3. Usable autonomous research disable flag (--no-research).
4. Elimination of stored-verdict replay in outreach_engine eval (live re-evaluation on draft tampering).
5. Elimination of misleading success responses across run, eval, and ingress.
6. Verification of defined logger in managed_research_delegation under error conditions.
7. Stage-level latency measurements presence and precision.
8. Redundant work elimination without weakening quality gates.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateProfileLoader,
    ChannelType,
    RecipientClass,
    TargetOpportunity,
)
from apps_lic.judges.evaluator import ExecutiveOutreachJudgePanel, _RUBRIC_CACHE
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver
from apps_lic.pipeline.mission_loader import MissionLoader
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.runtime.dispatch.canonical_dispatch import run_canonical_apps_lic_spine


def _run_cli(args: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def demo_fixture_path(repo_root: Path) -> Path:
    return repo_root / "outreach_engine" / "data" / "fixtures" / "charles_truist_mission.json"


def test_brief_role_preservation_no_silent_override(repo_root: Path, demo_fixture_path: Path, tmp_path: Path) -> None:
    """Verify loading a brief preserves its specific role title, and that passing explicit --role overrides it only when desired."""
    run_dir = tmp_path / "preserve_role_run"
    res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--brief",
            str(demo_fixture_path),
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert res.returncode == 0, f"Run failed: {res.stderr}"
    data = json.loads(res.stdout)
    assert data["status"] == "PASSED"
    # charles_truist_mission.json specifies "Head of AI Enablement, Truist Care Centers"
    assert "Head of AI Enablement" in data["draft"]["subject"]
    assert "Engineering Leader" not in data["draft"]["subject"]

    # Now verify explicit --role overrides the brief role title intentionally
    override_run_dir = tmp_path / "override_role_run"
    override_res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--brief",
            str(demo_fixture_path),
            "--role",
            "Chief Artificial Intelligence Officer",
            "--artifact-dir",
            str(override_run_dir),
            "--json",
        ],
        repo_root,
    )
    assert override_res.returncode == 0, f"Override run failed: {override_res.stderr}"
    override_data = json.loads(override_res.stdout)
    assert override_data["status"] == "PASSED"
    assert "Chief Artificial Intelligence Officer" in override_data["draft"]["subject"]


def test_canonical_dispatch_respects_target_role(tmp_path: Path) -> None:
    """Verify ingress in canonical_dispatch correctly honors target_role from raw_ingress."""
    ingress_payload = {
        "company": "Apex Dynamics",
        "target_role": "VP of Cognitive Systems",
        "channel": "inmail",
        "manual_brief": "Target Company: Apex Dynamics\nStrategic Priorities:\n- Scaled distributed ML infra",
    }
    result = run_canonical_apps_lic_spine(ingress_payload, artifact_dir=tmp_path / "dispatch_role")
    assert result["x3_code"] == "X3D_ALLOW_FINISH"
    assert result["is_valid"] is True
    # Verify the draft body reflects the custom role
    assert "VP of Cognitive Systems" in result["message"]


def test_research_disable_flag_works(repo_root: Path, tmp_path: Path) -> None:
    """Verify --no-research disables autonomous research resolution and succeeds via fallback without calling external bridges."""
    run_dir = tmp_path / "no_research_run"
    res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--company",
            "Novartis Healthcare",
            "--role",
            "VP of Clinical Platforms",
            "--no-research",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert res.returncode == 0, f"Run with --no-research failed: {res.stderr}"
    data = json.loads(res.stdout)
    assert data["status"] == "PASSED"
    # Under --no-research with company-only, resolution falls back to minimal fallback (source: HERMETIC_FALLBACK or FALLBACK_MINIMAL)
    assert data["resolution_source"] in ("HERMETIC_FALLBACK", "FALLBACK_MINIMAL")


def test_eval_re_evaluates_live_without_stored_verdict_replay(repo_root: Path, tmp_path: Path) -> None:
    """Verify outreach_engine eval re-executes validators and judges; tampering with the draft causes eval to detect violations and return exit code 1."""
    run_dir = tmp_path / "eval_replay_check"
    # Step 1: Run valid demo
    run_res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--demo",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert run_res.returncode == 0
    clean_eval_res = _run_cli(
        [
            "outreach_engine",
            "eval",
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert clean_eval_res.returncode == 0
    clean_data = json.loads(clean_eval_res.stdout)
    assert clean_data["status"] == "PASSED"
    assert clean_data["is_valid"] is True
    assert clean_data["evaluation"]["passed"] is True

    # Step 2: Tamper with outreach_draft.json on disk to introduce hard violations
    draft_file = run_dir / "outreach_draft.json"
    draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
    # Inject subordinate tone, ungrounded compensation claim, and remove question ending
    draft_data["body"] = "Please hire me as soon as possible because I really need the money and want a compensation of $500,000 immediately."
    draft_file.write_text(json.dumps(draft_data, indent=2), encoding="utf-8")

    # Step 3: Run eval again - if it was merely replaying the stored report, it would return 0.
    # Because it evaluates live, it MUST return exit code 1 and flag the violations!
    tampered_eval_res = _run_cli(
        [
            "outreach_engine",
            "eval",
            "--run-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert tampered_eval_res.returncode == 1, "Eval should have returned exit code 1 on tampered draft!"
    tampered_data = json.loads(tampered_eval_res.stdout)
    assert tampered_data["status"] == "FAILED"
    assert tampered_data["is_valid"] is False
    assert len(tampered_data["validation"]["violations"]) > 0


def test_misleading_success_responses_prevented(tmp_path: Path) -> None:
    """Verify that failed validation prevents misleading success rationales in canonical_dispatch."""
    # Create invalid ingress that triggers validation failure (e.g. ungrounded claim and forbidden text)
    orchestrator = OutreachOrchestrator()
    cand = CandidateProfileLoader.load_default()
    opp = TargetOpportunity(
        opportunity_id="opp_block",
        company_name="Block Corp",
        role_title="CTO",
        industry="Tech",
        recipient_name="Lead",
        recipient_title="Lead",
        recipient_class=RecipientClass.HIRING_MANAGER,
    )

    # Validate canonical_dispatch when blocked returns accurate failure rationale
    with mock.patch.object(
        Orchestrator := OutreachOrchestrator,
        "generate_single_draft",
        return_value=(
            mock.MagicMock(body="draft body", draft_id="draft_fail"),
            mock.MagicMock(hard_gate_passed=False, is_valid=False, violations=["Critical spam trigger detected"]),
        ),
    ):
        res = run_canonical_apps_lic_spine({"company": "Block Corp"}, artifact_dir=tmp_path / "dispatch_fail")
        assert res["x3_code"] == "X3D_BLOCK"
        assert res["is_valid"] is False
        assert "Pipeline blocked by validation gates" in res["rationale"]
        assert "Hard validation gates failed" in res["compliance_notes"]
        assert "Pipeline completed with valid grounding" not in res["rationale"]


def test_undefined_logger_remediated(tmp_path: Path) -> None:
    """Verify that managed_research_delegation defines _log and logs warnings on copy failure without raising NameError."""
    import apps_lic.integrations.managed_research_delegation as mrd

    assert hasattr(mrd, "_log")
    assert isinstance(mrd._log, logging.Logger)

    # Simulate copy failure in dispatch_outreach_research_briefing
    req = mrd.RequestForOutreachBriefing(
        request_id="req_01",
        run_id="run_01",
        trace_id="tr_01",
        company_name="Test Company",
        job_title="VP Engineering",
    )
    fake_brief_file = tmp_path / "mock_brief.md"
    fake_brief_file.write_text("# Mock Briefing Content\n", encoding="utf-8")

    fake_result = mrd.ResearchResult(
        run_id="run_01",
        trace_id="tr_01",
        request_id="req_01",
        is_blocked=False,
        block_reason="",
        is_stale=False,
        evidence_items=(),
        confidence_score=0.9,
        brief_sha256="",
        company_brief_text="Valid briefing text",
        strategic_priorities=("Priority 1",),
        fetch_duration_ms=10.0,
        audit_ref="audit_01",
        briefing_artifact_path=str(fake_brief_file),
    )
    fake_bridge = mock.MagicMock()
    fake_bridge.fetch.return_value = fake_result

    with mock.patch.object(mrd._log, "warning") as mock_warn, \
         mock.patch("shutil.copyfile", side_effect=OSError("Simulated copy failure")):
        resp = mrd.dispatch_outreach_research_briefing(
            req,
            bridge=fake_bridge,
            consumer_artifact_dir=tmp_path / "consumer_dir",
        )
        assert isinstance(resp, mrd.OutreachBriefingReady)
        assert mock_warn.called
        assert "Could not copy briefing artifact" in mock_warn.call_args[0][0]


def test_stage_level_latency_measurements_present(repo_root: Path, tmp_path: Path) -> None:
    """Verify stage_latencies_ms is present in run output with all expected stage breakdowns and valid positive durations."""
    run_dir = tmp_path / "latency_check_run"
    res = _run_cli(
        [
            "outreach_engine",
            "run",
            "--demo",
            "--artifact-dir",
            str(run_dir),
            "--json",
        ],
        repo_root,
    )
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert "stage_latencies_ms" in data
    latencies = data["stage_latencies_ms"]

    expected_stages = (
        "briefing_resolution_ms",
        "draft_generation_ms",
        "validation_ms",
        "evaluation_ms",
        "campaign_planning_ms",
        "total_ms",
    )
    for stage in expected_stages:
        assert stage in latencies, f"Missing stage latency metric: {stage}"
        assert isinstance(latencies[stage], (int, float))
        assert latencies[stage] >= 0.0

    # Also verify persisted run_receipt.json contains stage_latencies_ms
    receipt_file = run_dir / "run_receipt.json"
    assert receipt_file.is_file()
    receipt_data = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert "stage_latencies_ms" in receipt_data
    assert receipt_data["status"] == "PASSED"


def test_redundant_work_elimination_and_quality_gates(demo_fixture_path: Path, tmp_path: Path) -> None:
    """Verify briefing resolution is executed only once per run and rubric definitions are memoized without weakening quality gates."""
    orchestrator = OutreachOrchestrator()
    candidate, opportunity = MissionLoader.load_from_file(demo_fixture_path)

    # 1. Verify single briefing resolution
    with mock.patch.object(GovernedBriefingResolver, "resolve", wraps=GovernedBriefingResolver.resolve) as mock_resolve:
        # Resolving once sets sealed_resolution
        resolved_opp = orchestrator.resolve_opportunity_briefing(opportunity, auto_research=True)
        assert resolved_opp.sealed_resolution is not None
        initial_call_count = mock_resolve.call_count

        # Passing resolved_opp to generate_single_draft does not re-invoke resolve()
        draft, val = orchestrator.generate_single_draft(candidate, resolved_opp, ChannelType.LINKEDIN_INMAIL, artifact_dir=tmp_path / "perf1")
        assert mock_resolve.call_count == initial_call_count

        # Passing resolved_opp to generate_full_campaign does not re-invoke resolve()
        seq = orchestrator.generate_full_campaign(candidate, resolved_opp, ChannelType.LINKEDIN_INMAIL, artifact_dir=tmp_path / "perf2")
        assert mock_resolve.call_count == initial_call_count

    # 2. Verify rubric caching
    initial_cache_len = len(_RUBRIC_CACHE)
    panel1 = ExecutiveOutreachJudgePanel()
    count_after_p1 = len(_RUBRIC_CACHE)
    panel2 = ExecutiveOutreachJudgePanel()
    count_after_p2 = len(_RUBRIC_CACHE)
    # The cache length should not increase when instantiated again with same rubric files
    assert count_after_p2 == count_after_p1

    # 3. Verify quality gates remain strict: all 6 lenses are evaluated
    report = panel1.evaluate(draft, candidate, resolved_opp)
    assert report.passed is True
    assert set(report.lens_scores.keys()) == {
        "lens1_altitude",
        "lens2_grounding",
        "lens3_resonance",
        "lens4_cta",
        "lens5_anti_spam",
        "lens6_constraints",
    }
