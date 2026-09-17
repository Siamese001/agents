"""End-to-end integration test suite for Executive IT outreach engine hardening."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from apps_lic.domain.models import (
    AudiencePersona,
    ChannelType,
    RecipientClass,
)
from apps_lic.pipeline.mission_loader import MissionLoader
from apps_lic.pipeline.orchestrator import OutreachOrchestrator


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "fixtures"


def test_executive_contact_track_e2e(fixtures_dir: Path, tmp_path: Path):
    charles_brief = fixtures_dir / "charles_truist_mission.json"
    assert charles_brief.is_file()

    candidate, opportunity = MissionLoader.load_from_file(charles_brief)
    orchestrator = OutreachOrchestrator()

    draft, val = orchestrator.generate_single_draft(
        candidate,
        opportunity,
        channel=ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
        artifact_dir=tmp_path,
    )

    assert val.is_valid is True
    assert len(val.violations) == 0
    assert draft.audience_persona == AudiencePersona.EXECUTIVE_CONTACT
    assert draft.body.strip().endswith("?")
    assert "—" not in draft.body
    assert "[" not in draft.body

    # Full executive signature block verification
    assert "Amit Ayer" in draft.signature_block
    assert "Chief Agentic AI Officer" in draft.signature_block
    assert "linkedin.com" in draft.signature_block
    assert "github.com" in draft.signature_block

    # 6-Lens Rubric Judge Panel verification
    report = orchestrator.evaluate_draft(draft, candidate, opportunity, artifact_dir=tmp_path)
    assert report.passed is True
    assert report.lens1_altitude_score >= 0.70
    assert report.lens2_grounding_score >= 0.99
    assert report.lens3_resonance_score >= 0.70
    assert report.lens4_cta_score >= 0.70
    assert report.lens5_anti_spam_score >= 0.70
    assert report.lens6_constraints_score >= 0.70

    # Multi-touch campaign verification
    campaign = orchestrator.generate_full_campaign(
        candidate,
        opportunity,
        channel=ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
        artifact_dir=tmp_path,
    )
    assert len(campaign.touches) == 3
    for touch in campaign.touches:
        assert touch.draft.metadata.get("passed") is True
        assert len(touch.draft.metadata.get("validation_violations", [])) == 0


def test_executive_recruiter_track_e2e(fixtures_dir: Path, tmp_path: Path):
    pascal_brief = fixtures_dir / "truist_pascal_brief.json"
    assert pascal_brief.is_file()

    candidate, opportunity = MissionLoader.load_from_file(pascal_brief)
    orchestrator = OutreachOrchestrator()

    draft, val = orchestrator.generate_single_draft(
        candidate,
        opportunity,
        channel=ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_RECRUITER,
        artifact_dir=tmp_path,
    )

    assert val.is_valid is True
    assert len(val.violations) == 0
    assert draft.audience_persona == AudiencePersona.EXECUTIVE_RECRUITER
    assert draft.body.strip().endswith("?")

    # Recruiter signature block check (clean, scannable)
    assert "Amit Ayer" in draft.signature_block
    assert "linkedin.com" in draft.signature_block

    report = orchestrator.evaluate_draft(draft, candidate, opportunity, artifact_dir=tmp_path)
    assert report.passed is True
    assert report.lens1_altitude_score >= 0.70
    assert report.lens2_grounding_score >= 0.99


def test_cli_end_to_end_workflow(fixtures_dir: Path, tmp_path: Path):
    brief_file = str(fixtures_dir / "charles_truist_mission.json")
    run_dir = tmp_path / "cli_run"

    # 1. Run action with --audience executive and --json
    cmd_run = [
        sys.executable,
        "-m",
        "outreach_engine",
        "run",
        "--brief",
        brief_file,
        "--audience",
        "executive",
        "--artifact-dir",
        str(run_dir),
        "--json",
    ]
    res_run = subprocess.run(cmd_run, capture_output=True, text=True, check=True, timeout=30)
    data_run = json.loads(res_run.stdout)

    assert data_run["status"] == "PASSED"
    assert data_run["audience_persona"] == "executive_contact"
    assert data_run["evaluation"]["passed"] is True
    assert data_run["evaluation"]["lens1_altitude_score"] >= 0.70
    assert len(data_run["campaign_touches"]) == 3

    # 2. Eval action on completed run
    cmd_eval = [
        sys.executable,
        "-m",
        "outreach_engine",
        "eval",
        "--run-dir",
        str(run_dir),
        "--json",
    ]
    res_eval = subprocess.run(cmd_eval, capture_output=True, text=True, check=True, timeout=30)
    data_eval = json.loads(res_eval.stdout)
    assert data_eval["evaluation"]["passed"] is True
    assert "lens_scores" in data_eval["evaluation"]

    # 3. Show action on draft artifact
    cmd_show = [
        sys.executable,
        "-m",
        "outreach_engine",
        "show",
        "--run-dir",
        str(run_dir),
        "--artifact",
        "draft",
    ]
    res_show = subprocess.run(cmd_show, capture_output=True, text=True, check=True, timeout=30)
    assert "Outreach Draft:" in res_show.stdout or "Subject" in res_show.stdout
