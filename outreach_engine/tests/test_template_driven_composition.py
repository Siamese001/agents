"""Golden-output test suite proving template-driven, evidence-bound composition across all dimensions."""

from __future__ import annotations

import time
import pytest

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateFact,
    CandidateProfile,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.judges.evaluator import ExecutiveOutreachJudgePanel
from apps_lic.pipeline.compiler import (
    PromptCompiler,
    get_executive_signature_block,
    get_recruiter_signature_block,
)
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.pipeline.touch_sequence import TouchSequencePlanner


@pytest.fixture
def golden_candidate() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand_golden_01",
        full_name="Elena Rostova",
        target_title="Chief Technology Officer",
        current_title="VP of Platform Engineering",
        executive_summary="Enterprise technology leader specializing in modern distributed architecture and high-velocity engineering.",
        verified_facts=[
            CandidateFact(
                fact_id="fact_cloud_scale",
                category="scale",
                statement="scaled distributed cloud platform to 12M active users across 3 continents",
                metric="12M users",
                source_reference="resume:elena_rostova:cloud_architecture",
            ),
            CandidateFact(
                fact_id="fact_efficiency",
                category="efficiency",
                statement="reduced annual infrastructure operational spend by 38% through Kubernetes containerization",
                metric="38%",
                source_reference="resume:elena_rostova:k8s_efficiency",
            ),
        ],
        linkedin_url="https://linkedin.com/in/elena-rostova",
        github_url="https://github.com/erostova",
        phone="+1-415-555-0199",
    )


@pytest.fixture
def golden_opportunity_builder():
    def _builder(
        recipient_class: RecipientClass = RecipientClass.EXECUTIVE_PEER,
        relationship_distance: RelationshipDistance = RelationshipDistance.COLD,
        company_name: str = "Vanguard Cloud Systems",
        role_title: str = "Chief Technology Officer",
        recipient_name: str = "David Sterling",
        strategic_priorities: list[str] | None = None,
    ) -> TargetOpportunity:
        return TargetOpportunity(
            opportunity_id=f"opp_{recipient_class.value}_{relationship_distance.value}",
            company_name=company_name,
            role_title=role_title,
            industry="Enterprise Cloud & SaaS",
            recipient_name=recipient_name,
            recipient_title="Managing Director",
            recipient_class=recipient_class,
            relationship_distance=relationship_distance,
            strategic_priorities=strategic_priorities or [
                "multi-region cloud infrastructure transformation",
                "zero-trust security compliance",
            ],
            briefing_text="Vanguard is expanding its enterprise SaaS footprint with high availability multi-region infrastructure.",
        )

    return _builder


# =============================================================================
# 1. Persona Differentiation: Executive vs Recruiter
# =============================================================================

def test_persona_differentiation_executive_vs_recruiter(golden_candidate, golden_opportunity_builder):
    compiler = PromptCompiler()
    opp = golden_opportunity_builder()

    # Executive draft
    subj_exec, body_exec, facts_exec = compiler.render_draft_message(
        golden_candidate,
        opp,
        ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    # Recruiter draft
    subj_rec, body_rec, facts_rec = compiler.render_draft_message(
        golden_candidate,
        opp,
        ChannelType.LINKEDIN_INMAIL,
        audience_persona=AudiencePersona.EXECUTIVE_RECRUITER,
    )

    # Assert meaningful distinction
    assert subj_exec != subj_rec
    assert body_exec != body_rec

    # Executive contract verification (exec_positioning.yaml)
    assert "Executive Alignment" in subj_exec
    assert "I have been following" in body_exec
    assert "Happy to share our operational playbook" in body_exec  # Reciprocity offer
    assert "brief conversation next week?" in body_exec  # Respectful ask
    assert "fact_cloud_scale" in facts_exec

    # Recruiter contract verification (compact_recruiter_arc.yaml)
    assert f"{golden_candidate.full_name} ->" in subj_rec
    assert "Reaching out regarding" in body_rec
    assert "connecting on this role?" in body_rec
    # Recruiter drafts must be max 2 paragraphs
    paragraphs_rec = [p for p in body_rec.split("\n\n") if p.strip()]
    # Including greeting paragraph ("Hi ..."), body has at most 3 blocks total, with 2 content blocks
    assert len(paragraphs_rec) <= 3
    # Reciprocity is omitted from recruiter drafts to keep them compact
    assert "playbook" not in body_rec


# =============================================================================
# 2. Relationship Distance Differentiation: Cold vs Warm vs Colleague vs 2nd
# =============================================================================

def test_relationship_distance_differentiation(golden_candidate, golden_opportunity_builder):
    compiler = PromptCompiler()

    distances = [
        RelationshipDistance.COLD,
        RelationshipDistance.SECOND_DEGREE,
        RelationshipDistance.WARM_REFERRAL,
        RelationshipDistance.FORMER_COLLEAGUE,
    ]

    drafts: dict[RelationshipDistance, tuple[str, str]] = {}
    for dist in distances:
        opp = golden_opportunity_builder(relationship_distance=dist)
        subj, body, _ = compiler.render_draft_message(
            golden_candidate, opp, ChannelType.LINKEDIN_INMAIL, audience_persona=AudiencePersona.EXECUTIVE_CONTACT
        )
        drafts[dist] = (subj, body)

    # Verify all 4 are pairwise distinct
    bodies = [d[1] for d in drafts.values()]
    assert len(set(bodies)) == 4, "All relationship distance bodies must be distinct"

    # Specific relationship markers
    assert "I have been following" in drafts[RelationshipDistance.COLD][1]
    assert "shared network, following" in drafts[RelationshipDistance.SECOND_DEGREE][1]
    assert "recommendations from our shared network" in drafts[RelationshipDistance.WARM_REFERRAL][1]
    assert "Great to see your continued momentum" in drafts[RelationshipDistance.FORMER_COLLEAGUE][1]
    assert "Catching up /" in drafts[RelationshipDistance.FORMER_COLLEAGUE][0]
    assert "catching up for a brief conversation" in drafts[RelationshipDistance.FORMER_COLLEAGUE][1]


# =============================================================================
# 3. Channel Differentiation: InMail vs Connection vs Email vs Follow-Up
# =============================================================================

def test_channel_differentiation_and_connection_note_ceiling(golden_candidate, golden_opportunity_builder):
    compiler = PromptCompiler()
    opp = golden_opportunity_builder()

    # Connection note
    subj_conn, body_conn, _ = compiler.render_draft_message(
        golden_candidate, opp, ChannelType.LINKEDIN_CONNECTION
    )
    assert subj_conn == "", "LinkedIn connection note must have empty subject"
    assert len(body_conn) <= 300, f"Connection note length ({len(body_conn)}) exceeds 300 chars"
    assert body_conn.strip().endswith("?")
    assert "Open to exchanging perspectives?" in body_conn

    # Email
    subj_email, body_email, _ = compiler.render_draft_message(
        golden_candidate, opp, ChannelType.EMAIL, audience_persona=AudiencePersona.EXECUTIVE_CONTACT
    )
    assert "Strategic Alignment" in subj_email
    assert len(body_email) > len(body_conn)

    # InMail
    subj_inmail, body_inmail, _ = compiler.render_draft_message(
        golden_candidate, opp, ChannelType.LINKEDIN_INMAIL, audience_persona=AudiencePersona.EXECUTIVE_CONTACT
    )
    assert "Executive Alignment" in subj_inmail

    # Follow-Up via Sequence Planner
    planner = TouchSequencePlanner()
    seq = planner.plan_sequence(golden_candidate, opp)
    t2 = seq.touches[1]
    assert t2.draft.channel == ChannelType.FOLLOW_UP
    assert t2.draft.subject.startswith("Re:")
    assert "Following up briefly" in t2.draft.body


# =============================================================================
# 4. Recipient Class Altitude: Board Member vs Executive Peer vs Hiring Manager
# =============================================================================

def test_recipient_class_altitude_differentiation(golden_candidate, golden_opportunity_builder):
    compiler = PromptCompiler()

    opp_board = golden_opportunity_builder(recipient_class=RecipientClass.BOARD_MEMBER)
    opp_peer = golden_opportunity_builder(recipient_class=RecipientClass.EXECUTIVE_PEER)
    opp_mgr = golden_opportunity_builder(recipient_class=RecipientClass.HIRING_MANAGER)

    subj_board, body_board, _ = compiler.render_draft_message(golden_candidate, opp_board, ChannelType.LINKEDIN_INMAIL)
    subj_peer, body_peer, _ = compiler.render_draft_message(golden_candidate, opp_peer, ChannelType.LINKEDIN_INMAIL)
    subj_mgr, body_mgr, _ = compiler.render_draft_message(golden_candidate, opp_mgr, ChannelType.LINKEDIN_INMAIL)

    # Assert distinct subject lines and bodies
    assert "Board & Governance Alignment" in subj_board
    assert "Executive Alignment" in subj_peer

    # Board member has high-altitude governance vocabulary
    assert "governance focus" in body_board
    assert "governance benchmarks" in body_board
    assert "high-level conversation" in body_board

    # Hiring manager has operational scaling vocabulary
    assert "operational scaling framework" in body_mgr

    # Peer has peer-to-peer exchange
    assert "operational playbook and architectural benchmarks" in body_peer


# =============================================================================
# 5. Evidence Grounding & Zero Hallucination
# =============================================================================

def test_evidence_grounding_and_fact_binding(golden_candidate, golden_opportunity_builder):
    compiler = PromptCompiler()
    opp = golden_opportunity_builder()

    _, body, fact_ids = compiler.render_draft_message(
        golden_candidate, opp, ChannelType.LINKEDIN_INMAIL
    )

    # Assert fact_cloud_scale is bound
    assert "fact_cloud_scale" in fact_ids
    # Assert actual metric from fact is woven into the text
    assert "12M active users" in body
    # Assert no hallucinated facts or claims outside verified facts
    assert "38%" not in body  # secondary fact not used in Touch 1


# =============================================================================
# 6. Multi-Touch Sequence Progressive Arc
# =============================================================================

def test_multi_touch_progressive_arc(golden_candidate, golden_opportunity_builder):
    planner = TouchSequencePlanner()
    opp = golden_opportunity_builder()

    seq = planner.plan_sequence(golden_candidate, opp)
    assert len(seq.touches) == 3

    t1, t2, t3 = seq.touches

    # Touch 1: Uses primary fact (scale) + strategic mandate
    assert "fact_cloud_scale" in t1.draft.grounded_facts_used
    assert "12M active users" in t1.draft.body

    # Touch 2: Uses secondary fact (efficiency)
    assert "fact_efficiency" in t2.draft.grounded_facts_used
    assert "reduced annual infrastructure operational spend by 38%" in t2.draft.body

    # Touch 3: Polite close with zero unsupported claims
    assert len(t3.draft.grounded_facts_used) == 0
    assert "reconnect next quarter instead?" in t3.draft.body

    # Verify all touches pass domain gates
    for t in seq.touches:
        assert t.draft.metadata.get("passed") is True
        assert len(t.draft.metadata.get("validation_violations", [])) == 0


# =============================================================================
# 7. Six-Lens Rubric Judge Panel Evaluation
# =============================================================================

def test_rubric_judge_panel_scores_exemplary_on_golden_drafts(golden_candidate, golden_opportunity_builder):
    orchestrator = OutreachOrchestrator()
    judge = ExecutiveOutreachJudgePanel()

    opp_exec = golden_opportunity_builder(recipient_class=RecipientClass.EXECUTIVE_PEER)
    draft_exec, val_exec = orchestrator.generate_single_draft(
        golden_candidate, opp_exec, ChannelType.LINKEDIN_INMAIL, audience_persona=AudiencePersona.EXECUTIVE_CONTACT
    )

    assert val_exec.is_valid is True
    report_exec = judge.evaluate(draft_exec, golden_candidate, opp_exec)

    assert report_exec.passed is True
    assert report_exec.composite_score >= 0.85
    assert report_exec.lens1_altitude_score >= 0.70
    assert report_exec.lens2_grounding_score >= 0.99
    assert report_exec.lens3_resonance_score >= 0.70
    assert report_exec.lens4_cta_score >= 0.70
    assert report_exec.lens5_anti_spam_score >= 0.70
    assert report_exec.lens6_constraints_score >= 0.70

    # Ensure zero forbidden typography
    assert "—" not in draft_exec.body
    assert "\u2014" not in draft_exec.body
    assert "[" not in draft_exec.body


# =============================================================================
# 8. Deterministic Speed & Zero LLM Overhead
# =============================================================================

def test_deterministic_speed_sub_millisecond_drafting(golden_candidate, golden_opportunity_builder):
    compiler = PromptCompiler()
    opp = golden_opportunity_builder()

    start = time.perf_counter()
    for _ in range(100):
        compiler.render_draft_message(golden_candidate, opp, ChannelType.LINKEDIN_INMAIL)
    elapsed_ms = (time.perf_counter() - start) * 1000

    # 100 runs must complete in under 50ms (average < 0.5ms per draft)
    assert elapsed_ms < 50, f"100 drafts took {elapsed_ms:.2f}ms, expected < 50ms"
