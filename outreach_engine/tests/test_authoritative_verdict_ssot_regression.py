"""Focused regressions for AuthoritativeVerdict.passed SSOT unification across outreach_engine.

Covers:
1. Judge-only failure (hard gates pass, rubric judge fails -> blocked at all layers).
2. Hard-gate failure (hard gates fail -> blocked at all layers).
3. Successful E2E completion (hard gates and judge pass -> sealed at all layers).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock
import pytest

from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.judges.evaluator import ExecutiveOutreachJudgePanel
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.runtime.dispatch.canonical_dispatch import run_canonical_apps_lic_spine


@pytest.fixture
def base_candidate() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand_ssot_001",
        full_name="Alex Morgan",
        target_title="VP of Engineering",
        current_title="VP of Engineering",
        executive_summary="Experienced engineering leader scaling cloud platforms.",
        verified_facts=[
            CandidateFact(
                fact_id="fact_001",
                category="scale",
                statement="scaled engineering team from 20 to 120 while maintaining 99.99% uptime",
                metric="99.99%",
                source_reference="resume:alex_morgan:scale_history",
            ),
            CandidateFact(
                fact_id="fact_002",
                category="revenue",
                statement="reduced annual cloud infrastructure spend by $3.2M across multi-region AWS",
                metric="$3.2M",
                source_reference="resume:alex_morgan:cost_optimization",
            ),
        ],
        key_competencies=["Distributed Systems", "Cloud Migration"],
        linkedin_url="https://linkedin.com/in/alexmorgan",
        phone="+1-555-0199",
    )


@pytest.fixture
def base_opportunity() -> TargetOpportunity:
    return TargetOpportunity(
        opportunity_id="opp_acme_ssot",
        company_name="Acme Financial Technologies",
        role_title="Head of Platform Engineering",
        industry="Financial Services",
        recipient_name="Sarah Connor",
        recipient_title="Chief Technology Officer",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["cloud modern banking core", "zero-downtime payments architecture"],
    )


@pytest.fixture
def judge_panel() -> ExecutiveOutreachJudgePanel:
    return ExecutiveOutreachJudgePanel()


def test_judge_only_failure_blocked_at_all_layers(base_candidate, base_opportunity, judge_panel, tmp_path: Path):
    """Verifies that when hard validation gates pass but the judge rubric fails (e.g. Lens 3 resonance),
    AuthoritativeVerdict.passed is False, EvaluationReport.passed is False, canonical_dispatch emits
    X3D_BLOCK, artifacts remain unsealed, and draft body is suppressed."""
    draft = OutreachMessageDraft(
        draft_id="d_judge_fail_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Platform leadership perspective",
        body=(
            f"Hi Sarah,\n\n"
            f"In my previous role, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Open to a brief conversation regarding upcoming platform mandates?"
        ),
        grounded_facts_used=["fact_001"],
    )

    # 1. Authoritative Verdict: hard gates pass, judge fails
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.hard_gate_passed is True
    assert verdict.judge_passed is False
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert verdict.is_valid is False
    assert any("Resonance" in r for r in verdict.failure_reasons)

    # 2. EvaluationReport synchronization: passed mirrors verdict.passed
    eval_report = judge_panel.evaluate(draft, base_candidate, base_opportunity)
    assert eval_report.passed is False
    assert eval_report.status == "BLOCKED"
    assert eval_report.hard_gate_passed is True
    assert eval_report.judge_passed is False

    # 3. Canonical dispatch X3 disposition: X3D_BLOCK and empty message
    with mock.patch.object(
        OutreachOrchestrator,
        "generate_single_draft",
        return_value=(draft, verdict),
    ):
        dispatch_out = run_canonical_apps_lic_spine(
            {"company": base_opportunity.company_name},
            artifact_dir=tmp_path / "dispatch_judge_fail",
        )
        assert dispatch_out["x3_code"] == "X3D_BLOCK"
        assert dispatch_out["is_valid"] is False
        assert dispatch_out["message"] == ""
        assert "blocked by judge gates" in dispatch_out["rationale"]

    # 4. Orchestrator draft persistence: unsealed artifacts
    orchestrator = OutreachOrchestrator()
    artifact_dir = tmp_path / "orchestrator_judge_fail"
    with mock.patch.object(
        orchestrator.compiler,
        "render_draft_message",
        return_value=(draft.subject, draft.body, draft.grounded_facts_used),
    ):
        odraft, overd = orchestrator.generate_single_draft(
            base_candidate,
            base_opportunity,
            ChannelType.LINKEDIN_INMAIL,
            artifact_dir=artifact_dir,
        )
        assert overd.passed is False
        assert overd.status == "BLOCKED"
        assert not (artifact_dir / "outreach_draft.md").exists()
        draft_json = json.loads((artifact_dir / "outreach_draft.json").read_text())
        assert draft_json["sealed"] is False
        assert draft_json["status"] == "BLOCKED"
        assert draft_json["body"] == ""


def test_hard_gate_failure_blocked_at_all_layers(base_candidate, base_opportunity, judge_panel, tmp_path: Path):
    """Verifies that when hard validation gates fail, AuthoritativeVerdict.passed is False,
    EvaluationReport.passed is False, canonical_dispatch emits X3D_BLOCK, artifacts remain unsealed,
    and draft body is suppressed."""
    draft = OutreachMessageDraft(
        draft_id="d_hard_fail_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Role",
        body=(
            f"Hi Sarah,\n\n"
            f"Targeting a role at Acme Financial Technologies. My compensation requirement is $450k salary. "
            f"Previously {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you be open to connecting?"
        ),
        grounded_facts_used=["fact_001"],
    )

    # 1. Authoritative Verdict: hard gates fail
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.hard_gate_passed is False
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert verdict.is_valid is False
    assert len(verdict.violations) > 0

    # 2. EvaluationReport synchronization
    eval_report = judge_panel.evaluate(draft, base_candidate, base_opportunity)
    assert eval_report.passed is False
    assert eval_report.status == "BLOCKED"
    assert eval_report.hard_gate_passed is False

    # 3. Canonical dispatch X3 disposition
    with mock.patch.object(
        OutreachOrchestrator,
        "generate_single_draft",
        return_value=(draft, verdict),
    ):
        dispatch_out = run_canonical_apps_lic_spine(
            {"company": base_opportunity.company_name},
            artifact_dir=tmp_path / "dispatch_hard_fail",
        )
        assert dispatch_out["x3_code"] == "X3D_BLOCK"
        assert dispatch_out["is_valid"] is False
        assert dispatch_out["message"] == ""
        assert "blocked by validation gates" in dispatch_out["rationale"]

    # 4. Orchestrator draft persistence: unsealed artifacts
    orchestrator = OutreachOrchestrator()
    artifact_dir = tmp_path / "orchestrator_hard_fail"
    with mock.patch.object(
        orchestrator.compiler,
        "render_draft_message",
        return_value=(draft.subject, draft.body, draft.grounded_facts_used),
    ):
        odraft, overd = orchestrator.generate_single_draft(
            base_candidate,
            base_opportunity,
            ChannelType.LINKEDIN_INMAIL,
            artifact_dir=artifact_dir,
        )
        assert overd.passed is False
        assert overd.status == "BLOCKED"
        assert not (artifact_dir / "outreach_draft.md").exists()
        draft_json = json.loads((artifact_dir / "outreach_draft.json").read_text())
        assert draft_json["sealed"] is False
        assert draft_json["status"] == "BLOCKED"
        assert draft_json["body"] == ""


def test_successful_e2e_completion_sealed_at_all_layers(base_candidate, base_opportunity, judge_panel, tmp_path: Path):
    """Verifies that when all hard validation gates and judge rubric lenses pass,
    AuthoritativeVerdict.passed is True, EvaluationReport.passed is True, canonical_dispatch emits
    X3D_ALLOW_FINISH, artifacts are fully sealed on disk, and campaign touches are promoted."""
    orchestrator = OutreachOrchestrator()
    artifact_dir = tmp_path / "e2e_success_run"

    # 1. Generate single draft
    draft, verdict = orchestrator.generate_single_draft(
        base_candidate,
        base_opportunity,
        ChannelType.LINKEDIN_INMAIL,
        artifact_dir=artifact_dir,
    )
    assert verdict.hard_gate_passed is True
    assert verdict.judge_passed is True
    assert verdict.passed is True
    assert verdict.status == "PASSED"
    assert verdict.is_valid is True
    assert len(verdict.violations) == 0

    # 2. EvaluationReport synchronization
    eval_report = judge_panel.report_from_verdict(verdict)
    assert eval_report.passed is True
    assert eval_report.status == "PASSED"
    assert eval_report.hard_gate_passed is True
    assert eval_report.judge_passed is True

    # 3. Canonical dispatch X3 disposition
    dispatch_out = run_canonical_apps_lic_spine(
        {
            "company": base_opportunity.company_name,
            "target_role": base_opportunity.role_title,
            "channel": "inmail",
            "manual_brief": f"Target Company: {base_opportunity.company_name}\nStrategic Priorities:\n- {base_opportunity.strategic_priorities[0]}",
        },
        artifact_dir=tmp_path / "dispatch_success",
    )
    assert dispatch_out["x3_code"] == "X3D_ALLOW_FINISH"
    assert dispatch_out["is_valid"] is True
    assert len(dispatch_out["message"]) > 0
    assert "completed with valid grounding" in dispatch_out["rationale"]

    # 4. Verified sealed artifacts on disk
    draft_json = json.loads((artifact_dir / "outreach_draft.json").read_text())
    assert draft_json["sealed"] is True
    assert draft_json["status"] == "PASSED"
    assert len(draft_json["body"]) > 0

    draft_md = artifact_dir / "outreach_draft.md"
    assert draft_md.is_file()
    assert len(draft_md.read_text()) > 0

    val_json = json.loads((artifact_dir / "validation_report.json").read_text())
    assert val_json["status"] == "PASSED"
    assert val_json["is_valid"] is True

    eval_json = json.loads((artifact_dir / "evaluation_report.json").read_text())
    assert eval_json["status"] == "PASSED"
    assert eval_json["passed"] is True

    # 5. Full campaign sealing
    campaign_dir = tmp_path / "campaign_success"
    sequence = orchestrator.generate_full_campaign(
        base_candidate,
        base_opportunity,
        ChannelType.LINKEDIN_INMAIL,
        artifact_dir=campaign_dir,
    )
    assert sequence.status == "PASSED"
    camp_json = json.loads((campaign_dir / "campaign_sequence.json").read_text())
    assert camp_json["status"] == "PASSED"
    assert camp_json["all_passed"] is True
    assert camp_json["sealed"] is True
    assert len(camp_json["touches"]) > 0
    assert len(camp_json["blocked_touches"]) == 0


def test_canonical_dispatch_rejects_hard_gate_passed_alone(tmp_path: Path):
    """Verifies that hard_gate_passed=True alone never authorizes completion in canonical_dispatch."""
    mock_draft = mock.MagicMock(body="Hello world, this is a draft", draft_id="d_mock_01")
    mock_val = mock.NonCallableMagicMock(spec=["hard_gate_passed", "is_valid", "violations", "failure_reasons"])
    mock_val.hard_gate_passed = True
    mock_val.is_valid = True
    mock_val.violations = []
    mock_val.failure_reasons = []

    with mock.patch.object(
        OutreachOrchestrator,
        "generate_single_draft",
        return_value=(mock_draft, mock_val),
    ):
        res = run_canonical_apps_lic_spine({"company": "Test Corp"}, artifact_dir=tmp_path / "dispatch_mock_hard_only")
        assert res["x3_code"] == "X3D_BLOCK"
        assert res["is_valid"] is False
        assert res["message"] == ""
        assert "blocked by judge gates" in res["rationale"]
        assert "Authoritative rubric judge failure" in res["failure_reasons"]


def test_canonical_dispatch_judge_only_failure_suppresses_content_and_preserves_diagnostics(tmp_path: Path):
    """Verifies that judge-only failures in canonical_dispatch suppress draft content and preserve diagnostic reasons."""
    from apps_lic.domain.models import AuthoritativeVerdict

    draft = OutreachMessageDraft(
        draft_id="d_judge_fail_suppress",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Strategic partnership inquiry",
        body="Hi Sarah, would love to connect and discuss platform modernization initiatives.",
        grounded_facts_used=[],
    )
    verdict = AuthoritativeVerdict(
        passed=False,
        status="BLOCKED",
        composite_score=0.45,
        score_band="FAIL",
        hard_gate_passed=True,
        judge_passed=False,
        violations=[],
        failure_reasons=["Lens 3 (Resonance) score 0.40 below threshold 0.70", "Missing peer-level positioning"],
        feedback=["Elevate strategic altitude and tailor to executive priorities."],
    )

    with mock.patch.object(
        OutreachOrchestrator,
        "generate_single_draft",
        return_value=(draft, verdict),
    ):
        res = run_canonical_apps_lic_spine({"company": "Acme Corp"}, artifact_dir=tmp_path / "dispatch_judge_suppress")
        assert res["x3_code"] == "X3D_BLOCK"
        assert res["is_valid"] is False
        assert res["message"] == ""
        assert "blocked by judge gates" in res["rationale"]
        assert "Lens 3 (Resonance)" in res["rationale"]
        assert "Authoritative judge gates failed" in res["compliance_notes"]
        assert res["failure_reasons"] == ["Lens 3 (Resonance) score 0.40 below threshold 0.70", "Missing peer-level positioning"]


def test_canonical_dispatch_judge_only_failure_feedback_fallback(tmp_path: Path):
    """Verifies that judge diagnostic feedback is preserved when failure_reasons is empty."""
    from apps_lic.domain.models import AuthoritativeVerdict

    draft = OutreachMessageDraft(
        draft_id="d_judge_fb_fallback",
        channel=ChannelType.EMAIL,
        subject="Platform scaling insights",
        body="Hi Alex, reaching out regarding distributed architecture challenges.",
        grounded_facts_used=[],
    )
    verdict = AuthoritativeVerdict(
        passed=False,
        status="BLOCKED",
        composite_score=0.55,
        score_band="FAIL",
        hard_gate_passed=True,
        judge_passed=False,
        violations=[],
        failure_reasons=[],
        feedback=["Executive peer resonance insufficient for C-suite recipient."],
    )

    with mock.patch.object(
        OutreachOrchestrator,
        "generate_single_draft",
        return_value=(draft, verdict),
    ):
        res = run_canonical_apps_lic_spine({"company": "Acme Corp"}, artifact_dir=tmp_path / "dispatch_fb_fallback")
        assert res["x3_code"] == "X3D_BLOCK"
        assert res["is_valid"] is False
        assert res["message"] == ""
        assert res["failure_reasons"] == ["Executive peer resonance insufficient for C-suite recipient."]
        assert "Executive peer resonance insufficient" in res["rationale"]
        assert "Authoritative judge gates failed" in res["compliance_notes"]


def test_canonical_dispatch_legacy_validation_result_rejected(tmp_path: Path):
    """Verifies that a ValidationResult alone never authorizes completion."""
    from apps_lic.domain.models import ValidationResult

    draft = OutreachMessageDraft(
        draft_id="d_val_result_test",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Valid syntax message",
        body="Valid message body with all hard constraints passing.",
        grounded_facts_used=[],
    )
    val_result = ValidationResult(
        is_valid=True,
        hard_gate_passed=True,
        violations=[],
        warnings=[],
    )

    with mock.patch.object(
        OutreachOrchestrator,
        "generate_single_draft",
        return_value=(draft, val_result),
    ):
        res = run_canonical_apps_lic_spine({"company": "Acme Corp"}, artifact_dir=tmp_path / "dispatch_val_result")
        assert res["x3_code"] == "X3D_BLOCK"
        assert res["is_valid"] is False
        assert res["message"] == ""
        assert "blocked by judge gates" in res["rationale"]
        assert "Authoritative rubric judge failure" in res["failure_reasons"]

