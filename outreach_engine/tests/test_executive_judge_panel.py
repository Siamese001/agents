"""Tests for ExecutiveOutreachJudgePanel and 6-lens evaluation adapted from apps_rg Rubric v3."""

from __future__ import annotations

import pytest

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateFact,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    TargetOpportunity,
)
from apps_lic.judges.evaluator import (
    EvaluationReport,
    ExecutiveOutreachJudgePanel,
    RubricJudgeEvaluator,
)


@pytest.fixture
def candidate_profile() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand-alex",
        full_name="Alex Mercer",
        target_title="VP of Engineering",
        key_competencies=["Enterprise Architecture", "Cloud Migration", "Distributed Systems"],
        verified_facts=[
            CandidateFact(
                fact_id="scale-4b",
                category="scale",
                statement="Scaled payment systems handling $4.2B annual volume at 99.995% SLA.",
            ),
            CandidateFact(
                fact_id="eng-150",
                category="leadership",
                statement="Managed distributed engineering organizations of 150+ engineers.",
            ),
        ],
        executive_summary="Enterprise IT leader specialized in resilient architectures.",
    )


@pytest.fixture
def target_opportunity() -> TargetOpportunity:
    return TargetOpportunity(
        opportunity_id="opp-truist-01",
        company_name="Truist",
        role_title="Head of Enterprise Architecture",
        industry="Financial Services",
        recipient_name="Charles Morris",
        recipient_title="SVP Enterprise Technology",
        recipient_class=RecipientClass.HIRING_EXECUTIVE if hasattr(RecipientClass, "HIRING_EXECUTIVE") else RecipientClass.HIRING_MANAGER,
        strategic_priorities=["Core modernization", "Cloud resilience", "Developer velocity"],
    )


@pytest.fixture
def judge_panel() -> ExecutiveOutreachJudgePanel:
    return ExecutiveOutreachJudgePanel()


def test_judge_panel_all_lenses_pass(candidate_profile, target_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d-pass",
        subject="Truist architecture and core modernization perspectives",
        body=(
            "Charles, following Truist's focus on cloud resilience and core modernization, "
            "I have led architectures scaling $4.2B payment processing with 150+ engineers. "
            "Would you be open to exchanging perspectives on modernizing legacy platforms next week?"
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=["scale-4b", "eng-150"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = judge_panel.evaluate(draft, candidate_profile, target_opportunity)
    assert report.passed is True
    assert report.lens1_altitude_score >= 0.70
    assert report.lens2_grounding_score >= 0.99
    assert report.lens3_resonance_score >= 0.70
    assert report.lens4_cta_score >= 0.70
    assert report.lens5_anti_spam_score >= 0.70
    assert report.lens6_constraints_score >= 0.70
    assert len(report.feedback) == 0


def test_judge_panel_lens1_subordinate_tone_fails(candidate_profile, target_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d-lens1-fail",
        subject="Truist opportunity",
        body=(
            "Charles, I am seeking a role at Truist and please consider my resume. "
            "I would be grateful for any job opening you have. "
            "Could we connect to discuss available roles?"
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=[],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = judge_panel.evaluate(draft, candidate_profile, target_opportunity)
    assert report.passed is False
    assert report.lens1_altitude_score == 0.3
    assert any("Lens 1" in f for f in report.feedback)


def test_judge_panel_lens2_ungrounded_facts_fails(candidate_profile, target_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d-lens2-fail",
        subject="Truist perspectives",
        body=(
            "Charles, regarding Truist's cloud resilience, I personally invented the internet and generated $100B revenue. "
            "Would you have ten minutes to compare notes?"
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=["invented-internet-100b"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = judge_panel.evaluate(draft, candidate_profile, target_opportunity)
    assert report.passed is False
    assert report.lens2_grounding_score == 0.0
    assert any("Lens 2" in f for f in report.feedback)


def test_judge_panel_lens3_lacks_resonance_fails(candidate_profile, target_opportunity, judge_panel):
    draft = OutreachMessageDraft(
        draft_id="d-lens3-fail",
        subject="Generic hello",
        body=(
            "Hello, I have scaled $4.2B in volume and led 150+ engineers. "
            "Would you be interested in having a conversation?"
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=["scale-4b", "eng-150"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = judge_panel.evaluate(draft, candidate_profile, target_opportunity)
    assert report.passed is False
    assert report.lens3_resonance_score == 0.4
    assert any("Lens 3" in f for f in report.feedback)


def test_judge_panel_lens4_missing_question_and_demanding_fails(candidate_profile, target_opportunity, judge_panel):
    draft_no_q = OutreachMessageDraft(
        draft_id="d-lens4-noq",
        subject="Truist core modernization",
        body=(
            "Charles, Truist's cloud resilience priority is exciting. "
            "I scaled $4.2B systems with 150+ engineers. Let's talk soon."
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=["scale-4b", "eng-150"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    report_no_q = judge_panel.evaluate(draft_no_q, candidate_profile, target_opportunity)
    assert report_no_q.passed is False
    assert report_no_q.lens4_cta_score <= 0.4

    draft_demanding = OutreachMessageDraft(
        draft_id="d-lens4-demand",
        subject="Truist core modernization",
        body=(
            "Charles, you must give me a job today at Truist. "
            "Would you like to speak?"
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=[],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    report_demanding = judge_panel.evaluate(draft_demanding, candidate_profile, target_opportunity)
    assert report_demanding.passed is False
    assert report_demanding.lens4_cta_score <= 0.2


def test_judge_panel_lens5_spam_and_em_dash_triggers(candidate_profile, target_opportunity, judge_panel):
    draft_spam = OutreachMessageDraft(
        draft_id="d-lens5-spam",
        subject="Truist core modernization",
        body=(
            "Charles, this is an act now limited time offer to partner with Truist on cloud resilience! "
            "Would you be open to discussing?"
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=[],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    report_spam = judge_panel.evaluate(draft_spam, candidate_profile, target_opportunity)
    assert report_spam.passed is False
    assert report_spam.lens5_anti_spam_score <= 0.2

    draft_em_dash = OutreachMessageDraft(
        draft_id="d-lens5-dash",
        subject="Truist core modernization",
        body=(
            "Charles, Truist's cloud resilience — which is crucial — aligns with my $4.2B scaling. "
            "Could we compare perspectives?"
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=["scale-4b"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    report_dash = judge_panel.evaluate(draft_em_dash, candidate_profile, target_opportunity)
    assert report_dash.lens5_anti_spam_score <= 0.6
    assert any("Lens 5" in f for f in report_dash.feedback)


def test_judge_panel_lens6_channel_length_and_markdown_link(candidate_profile, target_opportunity, judge_panel):
    draft_overlength = OutreachMessageDraft(
        draft_id="d-lens6-len",
        subject="Truist connect",
        body="A" * 305 + "?",
        channel=ChannelType.LINKEDIN_CONNECTION,
        grounded_facts_used=[],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    report_len = judge_panel.evaluate(draft_overlength, candidate_profile, target_opportunity)
    assert report_len.passed is False
    assert report_len.lens6_constraints_score == 0.0

    draft_markdown_link = OutreachMessageDraft(
        draft_id="d-lens6-link",
        subject="Truist connect",
        body=(
            "Charles, check [my profile](https://linkedin.com/in/alex) regarding Truist cloud resilience. "
            "Would you like to connect?"
        ),
        channel=ChannelType.LINKEDIN_INMAIL,
        grounded_facts_used=[],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )
    report_link = judge_panel.evaluate(draft_markdown_link, candidate_profile, target_opportunity)
    assert report_link.lens6_constraints_score <= 0.5


def test_evaluation_report_to_dict_and_alias():
    assert RubricJudgeEvaluator is ExecutiveOutreachJudgePanel

    report = EvaluationReport(
        passed=True,
        lens1_altitude_score=0.9,
        lens2_grounding_score=1.0,
        lens3_resonance_score=0.85,
        lens4_cta_score=0.95,
        lens5_anti_spam_score=0.9,
        lens6_constraints_score=1.0,
        feedback=["Optional note"],
        remediation_hints=["Hint"],
    )
    d = report.to_dict()
    assert d["passed"] is True
    assert d["lens1_altitude_score"] == 0.9
    assert d["lens2_grounding_score"] == 1.0
    assert d["lens3_resonance_score"] == 0.85
    assert d["lens4_cta_score"] == 0.95
    assert d["lens5_anti_spam_score"] == 0.9
    assert d["lens6_constraints_score"] == 1.0
    assert "lens_scores" in d
    assert d["lens_scores"]["lens1_altitude"] == 0.9
