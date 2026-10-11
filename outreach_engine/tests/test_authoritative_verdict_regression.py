"""Comprehensive regression tests for all outreach_engine blocked paths, authoritative verdict consolidation, and sealing invariants."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import pytest

from apps_lic.domain.models import (
    AudiencePersona,
    AuthoritativeVerdict,
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


@pytest.fixture
def base_candidate() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand_test_001",
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
        opportunity_id="opp_acme_001",
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


@pytest.fixture
def orchestrator() -> OutreachOrchestrator:
    return OutreachOrchestrator()


# =============================================================================
# 1. Blocked Path: Critical Spam Triggers
# =============================================================================
def test_blocked_path_critical_spam_triggers(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_spam_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Urgent Platform Opportunity",
        body=(
            f"Hi Sarah,\n\n"
            f"Act now for an exclusive invitation to discuss Acme Financial Technologies cloud modern banking core. "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you be open to connecting next week?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert verdict.hard_gate_passed is False
    assert any("spam" in r.lower() or "act now" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 2. Blocked Path: Channel Length Exceeded
# =============================================================================
def test_blocked_path_channel_length_exceeded(base_candidate, base_opportunity, judge_panel):
    long_body = "Hi Sarah, " + ("noticing your cloud modern banking core priorities at Acme Financial Technologies. " * 6) + "Would you be open to connecting?"
    assert len(long_body) > 300

    draft = OutreachMessageDraft(
        draft_id="d_len_01",
        channel=ChannelType.LINKEDIN_CONNECTION,
        subject="",
        body=long_body,
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert verdict.hard_gate_passed is False
    assert any("exceeds channel ceiling" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 3. Blocked Path: Missing Question Ending
# =============================================================================
def test_blocked_path_missing_question_ending(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_noq_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Engineering",
        body=(
            f"Hi Sarah,\n\n"
            f"Following Acme Financial Technologies focus on cloud modern banking core. "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Looking forward to speaking with you soon."
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert any("question" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 4. Blocked Path: Hallucinated / Ungrounded Candidate Facts
# =============================================================================
def test_blocked_path_hallucinated_grounding_facts(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_ground_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Engineering",
        body=(
            f"Hi Sarah,\n\n"
            f"Following Acme Financial Technologies focus on cloud modern banking core. "
            f"I previously ran quantum computing at NASA.\n\n"
            f"Would you be open to a brief conversation?"
        ),
        grounded_facts_used=["fact_quantum_nasa_fabricated"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert any("ungrounded fact" in r.lower() or "grounding" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 5. Blocked Path: Forbidden Em Dash
# =============================================================================
def test_blocked_path_forbidden_em_dash(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_dash_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Alignment",
        body=(
            f"Hi Sarah,\n\n"
            f"Following Acme Financial Technologies—specifically cloud modern banking core. "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you be open to connecting?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert any("em dash" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 6. Blocked Path: Forbidden Markdown Links
# =============================================================================
def test_blocked_path_forbidden_markdown_links(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_link_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Alignment",
        body=(
            f"Hi Sarah,\n\n"
            f"Following Acme Financial Technologies focus on cloud modern banking core. "
            f"Review my work on [LinkedIn Profile](https://linkedin.com/in/alexmorgan). "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you be open to connecting?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert any("markdown link" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 7. Blocked Path: Subordinate Job-Seeker Phrasing
# =============================================================================
def test_blocked_path_subordinate_tone(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_tone_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Alignment",
        body=(
            f"Hi Sarah,\n\n"
            f"I would love to learn more about Acme Financial Technologies and think I'd be a great fit for cloud modern banking core. "
            f"Please give me a shot as VP of Engineering. {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you consider my application?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert any("subordinate" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 8. Blocked Path: Forbidden Compensation Claims
# =============================================================================
def test_blocked_path_forbidden_compensation(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_comp_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Alignment",
        body=(
            f"Hi Sarah,\n\n"
            f"Following Acme Financial Technologies focus on cloud modern banking core. "
            f"My base pay expectations are $350k salary plus equity grant. "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you be open to discussing?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert any("compensation" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 9. Blocked Path: Unverifiable Tenure Claims
# =============================================================================
def test_blocked_path_unverifiable_tenure(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_tenure_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Alignment",
        body=(
            f"Hi Sarah,\n\n"
            f"With over 25 years of experience leading cloud platform transformations for Acme Financial Technologies. "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you be open to connecting?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert any("tenure" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 10. Blocked Path: Policy-Forbidden Claims (Visa, Relocation)
# =============================================================================
def test_blocked_path_policy_forbidden_claims(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_policy_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Alignment",
        body=(
            f"Hi Sarah,\n\n"
            f"I require visa sponsorship and relocation package for Acme Financial Technologies cloud modern banking core. "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you be open to discussing?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert any("policy-forbidden" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 11. Blocked Path: Board Member Altitude Invariant
# =============================================================================
def test_blocked_path_board_member_altitude(base_candidate, judge_panel):
    board_opp = TargetOpportunity(
        opportunity_id="opp_board_001",
        company_name="Apex Global Holdings",
        role_title="Board Director",
        industry="Enterprise",
        recipient_name="Lord Hastings",
        recipient_title="Board Chair",
        recipient_class=RecipientClass.BOARD_MEMBER,
        strategic_priorities=["governance oversight", "fiduciary restructuring"],
    )
    draft = OutreachMessageDraft(
        draft_id="d_board_conn_01",
        channel=ChannelType.LINKEDIN_CONNECTION,
        subject="",
        body=(
            f"Hi Lord Hastings,\n\n"
            f"Noticed Apex Global Holdings focus on governance oversight. "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Open to connecting?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, board_opp)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert verdict.lens_scores["lens1_altitude"] < 0.70
    assert any("board member" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 12. Blocked Path: Missing Briefing Resonance
# =============================================================================
def test_blocked_path_missing_resonance(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_no_res_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Generic Platform Alignment",
        body=(
            f"Hi Sarah,\n\n"
            f"Reaching out to chat about generic software engineering in enterprise technology. "
            f"In my prior work, {base_candidate.verified_facts[0].statement}.\n\n"
            f"Would you be open to exchanging perspectives?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert verdict.lens_scores["lens3_resonance"] < 0.70
    assert any("resonance" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 13. Blocked Path: Demanding / High-Friction Call-to-Action
# =============================================================================
def test_blocked_path_demanding_cta(base_candidate, base_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d_demand_01",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Acme Financial Technologies / Platform Alignment",
        body=(
            f"Hi Sarah,\n\n"
            f"Following Acme Financial Technologies focus on cloud modern banking core. "
            f"As VP of Engineering, {base_candidate.verified_facts[0].statement}.\n\n"
            f"You must give me a job and I need a response today?"
        ),
        grounded_facts_used=["fact_001"],
    )
    verdict = judge_panel.evaluate_authoritative(draft, base_candidate, base_opportunity)
    assert verdict.passed is False
    assert verdict.status == "BLOCKED"
    assert verdict.lens_scores["lens4_cta"] < 0.70
    assert any("call-to-action" in r.lower() or "cta" in r.lower() for r in verdict.failure_reasons)


# =============================================================================
# 14. Campaign Touch Isolation & Preservation: Touch 2 Blocked While 1 & 3 Pass
# =============================================================================
def test_campaign_touch_isolation_and_preservation(base_candidate, orchestrator, tmp_path: Path):
    """Verifies failed touches are NOT sealed/promoted in 'touches', but preserved successful outputs ARE."""
    corrupted_opp = TargetOpportunity(
        opportunity_id="opp_corrupt_t2",
        company_name="Vanguard Platforms",
        role_title="Head of Engineering",
        industry="Financial Services",
        recipient_name="David Miller",
        recipient_title="SVP Engineering",
        recipient_class=RecipientClass.HIRING_MANAGER,
        strategic_priorities=["cloud native banking", "reliable payments"],
    )

    campaign = orchestrator.generate_full_campaign(
        base_candidate,
        corrupted_opp,
        primary_channel=ChannelType.LINKEDIN_INMAIL,
        artifact_dir=tmp_path,
    )

    # Intentionally corrupt Touch 2 with a forbidden compensation claim
    t2 = campaign.touches[1]
    t2.draft.body = "Hi David,\n\nFollowing up on my note. Our comp target is $400k salary plus ote. Open to talking?"
    # Re-evaluate campaign through planner logic
    verdict_t2 = orchestrator.judge.evaluate_authoritative(t2.draft, base_candidate, corrupted_opp)
    assert verdict_t2.passed is False
    t2.draft.metadata["passed"] = False
    t2.draft.metadata["status"] = "BLOCKED"
    t2.draft.metadata["failure_reasons"] = verdict_t2.failure_reasons
    t2.draft.metadata["validation_violations"] = verdict_t2.violations

    # Re-run campaign saving logic
    successful = [t for t in campaign.touches if t.draft.metadata.get("passed", False)]
    blocked = [
        {
            "touch_number": t.touch_number,
            "day_offset": t.day_offset,
            "channel": t.channel.value,
            "objective": t.objective,
            "status": "BLOCKED",
            "failure_reasons": t.draft.metadata.get("failure_reasons", []),
            "violations": t.draft.metadata.get("validation_violations", []),
        }
        for t in campaign.touches
        if not t.draft.metadata.get("passed", False)
    ]
    assert len(successful) == 2  # Touch 1 and Touch 3 preserved!
    assert len(blocked) == 1     # Touch 2 blocked!
    assert blocked[0]["touch_number"] == 2
    assert any("compensation" in r.lower() for r in blocked[0]["failure_reasons"])

    # Simulate orchestrator sealing
    seq_dict = {
        "sequence_id": campaign.sequence_id,
        "status": "BLOCKED",
        "candidate_id": campaign.candidate_id,
        "opportunity_id": campaign.opportunity_id,
        "touch_count": len(successful),
        "total_planned_touches": len(campaign.touches),
        "touches": [
            {
                "touch_number": t.touch_number,
                "day_offset": t.day_offset,
                "channel": t.channel.value,
                "objective": t.objective,
                "subject": t.draft.subject,
                "body": t.draft.body,
                "status": "PASSED",
            }
            for t in successful
        ],
        "blocked_touches": blocked,
    }
    seq_file = tmp_path / "campaign_sequence.json"
    seq_file.write_text(json.dumps(seq_dict, indent=2))

    # Read back and assert invariants
    saved = json.loads(seq_file.read_text())
    assert saved["status"] == "BLOCKED"
    assert saved["touch_count"] == 2
    assert saved["total_planned_touches"] == 3
    # Critical invariant: Touch 2 must NEVER appear in promoted 'touches'
    promoted_numbers = [t["touch_number"] for t in saved["touches"]]
    assert promoted_numbers == [1, 3]
    assert 2 not in promoted_numbers
    # Exact failure reasons preserved in blocked_touches
    assert len(saved["blocked_touches"]) == 1
    assert saved["blocked_touches"][0]["touch_number"] == 2
    assert saved["blocked_touches"][0]["status"] == "BLOCKED"


# =============================================================================
# 15. Blocked Path: Unsealed Draft Artifact Invariant
# =============================================================================
def test_blocked_draft_artifacts_never_sealed(base_candidate, orchestrator, tmp_path: Path):
    """Verifies failed draft never generates outreach_draft.md and records unsealed status in JSON."""
    opp = TargetOpportunity(
        opportunity_id="opp_fail_01",
        company_name="Apex Financial",
        role_title="VP Engineering",
        industry="Finance",
        recipient_name="Marcus Vance",
        recipient_title="CTO",
        strategic_priorities=["Targeting compensation of $450k salary"],  # Corrupted hook
    )

    # Pre-create an old outreach_draft.md to ensure clean removal
    old_md = tmp_path / "outreach_draft.md"
    old_md.write_text("# Stale Draft\n\nStale content")

    draft, verdict = orchestrator.generate_single_draft(
        base_candidate,
        opp,
        channel=ChannelType.LINKEDIN_INMAIL,
        artifact_dir=tmp_path,
    )

    assert verdict.passed is False
    assert verdict.status == "BLOCKED"

    # outreach_draft.md must NOT exist
    assert not old_md.exists(), "Failed draft must remove or never write outreach_draft.md!"

    # outreach_draft.json must exist with BLOCKED and sealed=False
    draft_json_file = tmp_path / "outreach_draft.json"
    assert draft_json_file.is_file()
    draft_data = json.loads(draft_json_file.read_text())
    assert draft_data["status"] == "BLOCKED"
    assert draft_data["sealed"] is False
    assert draft_data["body"] == ""
    assert len(draft_data["failure_reasons"]) > 0

    # validation_report.json must also have synchronized status
    val_file = tmp_path / "validation_report.json"
    assert val_file.is_file()
    val_data = json.loads(val_file.read_text())
    assert val_data["status"] == "BLOCKED"
    assert val_data["is_valid"] is False


# =============================================================================
# 16. CLI Status Synchronization Invariant Across CLI, JSON & Artifacts
# =============================================================================
def test_cli_status_synchronization_on_blocked_run(base_candidate, tmp_path: Path):
    """Verifies CLI exit code 1, JSON status BLOCKED, and disk artifact status BLOCKED on failure."""
    # Write a fixture with a forbidden compensation priority
    corrupt_fixture = tmp_path / "corrupt_mission.json"
    corrupt_fixture.write_text(json.dumps({
        "candidate_name": "Alex Morgan",
        "target_role": "VP Engineering",
        "recipient_company": "NextGen Pay",
        "recipient_name": "Laura Croft",
        "recipient_title": "CTO",
        "strategic_priorities": ["Targeting base pay of $400k salary"],
    }))

    run_dir = tmp_path / "blocked_cli_run"
    cmd = [
        sys.executable,
        "-m",
        "outreach_engine",
        "run",
        "--brief",
        str(corrupt_fixture),
        "--artifact-dir",
        str(run_dir),
        "--json",
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)
    assert res.returncode == 1, f"Blocked run must exit 1, got {res.returncode}. Stderr: {res.stderr}"

    data = json.loads(res.stdout)
    assert data["status"] == "BLOCKED"
    assert data["draft"]["status"] == "BLOCKED"
    assert data["draft"]["sealed"] is False
    assert data["campaign_status"] == "BLOCKED"
    assert len(data["failure_reasons"]) > 0

    # Verify disk artifacts synchronize on BLOCKED
    draft_json = json.loads((run_dir / "outreach_draft.json").read_text())
    assert draft_json["status"] == "BLOCKED"
    assert draft_json["sealed"] is False

    val_json = json.loads((run_dir / "validation_report.json").read_text())
    assert val_json["status"] == "BLOCKED"

    camp_json = json.loads((run_dir / "campaign_sequence.json").read_text())
    assert camp_json["status"] == "BLOCKED"
    # Never promote failed touches
    assert all(t["status"] == "PASSED" for t in camp_json["touches"])
    assert len(camp_json["blocked_touches"]) > 0
