"""Adversarial regression test suite verifying fail-closed candidate facts and grounding provenance.

Enforces:
1. Missing provenance on CandidateFact fails closed.
2. Valid fact IDs do NOT excuse unsupported claims or metrics in message body.
3. Undeclared metrics in message body are rejected.
4. Unsupported superlative/invention claims are rejected even when valid fact IDs are present.
5. Opportunity context metrics are properly distinguished from candidate claims.
6. Legitimate facts with verified provenance pass with exemplary scores.
"""

from __future__ import annotations

import pytest

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateFact,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.domain.validators import GroundingValidator
from apps_lic.judges.evaluator import ExecutiveOutreachJudgePanel


@pytest.fixture
def candidate_with_provenance() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand_provenance_test",
        full_name="Alex Mercer",
        target_title="VP of Engineering",
        verified_facts=[
            CandidateFact(
                fact_id="fact_scale_4b",
                category="scale",
                statement="scaled payment systems handling $4.2B annual volume at 99.995% SLA",
                metric="$4.2B / 99.995%",
                source_reference="canonical_platform_profile",
            ),
            CandidateFact(
                fact_id="fact_team_150",
                category="leadership",
                statement="managed distributed engineering organization of 150+ engineers",
                metric="150+",
                source_reference="canonical_care_profile",
            ),
        ],
    )


@pytest.fixture
def opportunity_with_context() -> TargetOpportunity:
    return TargetOpportunity(
        opportunity_id="opp_test_01",
        company_name="Truist",
        role_title="Head of Enterprise Architecture",
        industry="Financial Services",
        recipient_name="Charles Morris",
        recipient_title="SVP Enterprise Technology",
        recipient_class=RecipientClass.HIRING_MANAGER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["managing $50M legacy core banking modernization program", "cloud resilience"],
        briefing_text="Truist is driving a $50M modernization initiative.",
    )


def test_adversarial_missing_provenance_fails_closed():
    """Fail closed when CandidateFact has missing or whitespace source_reference."""
    fact_no_prov = CandidateFact(
        fact_id="fact_unproven",
        category="scale",
        statement="scaled distributed platform to $10B annual volume",
        metric="$10B",
        source_reference=None,
    )
    assert fact_no_prov.has_provenance is False

    fact_empty_prov = CandidateFact(
        fact_id="fact_empty",
        category="scale",
        statement="scaled platform",
        source_reference="   ",
    )
    assert fact_empty_prov.has_provenance is False

    cand = CandidateProfile(
        candidate_id="cand_unproven",
        full_name="Alex Unproven",
        target_title="CTO",
        verified_facts=[fact_no_prov, fact_empty_prov],
    )
    assert len(cand.grounded_facts) == 0

    validator = GroundingValidator()
    # Even if fact_id is in allowed_facts, missing provenance in candidate_facts must fail closed
    valid, viols = validator.validate(
        draft_facts_used=["fact_unproven"],
        allowed_fact_ids={"fact_unproven"},
        candidate_facts=[fact_no_prov],
    )
    assert valid is False
    assert len(viols) >= 1
    assert any("missing provenance" in v.lower() for v in viols)


def test_adversarial_valid_fact_id_with_fabricated_metric_rejected(candidate_with_provenance, opportunity_with_context):
    """A valid fact ID with valid provenance MUST NOT allow unsupported metrics in draft body."""
    panel = ExecutiveOutreachJudgePanel()

    # Draft uses VALID fact ID 'fact_scale_4b' ($4.2B), but fabricates '$100B' in the text
    draft = OutreachMessageDraft(
        draft_id="d_adversarial_fabricated_dollar",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist perspectives",
        body=(
            "Hi Charles,\n\n"
            "Following Truist's cloud resilience mandate. "
            "In my recent work, I scaled platforms to $100B annual volume across enterprise markets.\n\n"
            "Would you be open to exchanging brief perspectives next week?"
        ),
        grounded_facts_used=["fact_scale_4b"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = panel.evaluate(draft, candidate_with_provenance, opportunity_with_context)
    assert report.passed is False
    assert report.lens2_grounding_score == 0.0
    assert any("Unsupported dollar metric claim" in f for f in report.feedback)
    assert any("$100B" in f for f in report.feedback)


def test_adversarial_valid_fact_id_with_fabricated_percentage_rejected(candidate_with_provenance, opportunity_with_context):
    """A valid fact ID MUST NOT allow unsupported percentage claims in draft body."""
    panel = ExecutiveOutreachJudgePanel()

    # Draft uses VALID fact ID 'fact_scale_4b' (which has 99.995%), but fabricates '500%'
    draft = OutreachMessageDraft(
        draft_id="d_adversarial_fabricated_pct",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist perspectives",
        body=(
            "Hi Charles,\n\n"
            "Following Truist's cloud resilience mandate. "
            "In my recent work, I achieved a 500% operational uplift across enterprise systems.\n\n"
            "Would you be open to exchanging brief perspectives next week?"
        ),
        grounded_facts_used=["fact_scale_4b"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = panel.evaluate(draft, candidate_with_provenance, opportunity_with_context)
    assert report.passed is False
    assert report.lens2_grounding_score == 0.0
    assert any("Unsupported percentage metric claim" in f for f in report.feedback)
    assert any("500%" in f for f in report.feedback)


def test_adversarial_body_metric_without_declared_fact_rejected(candidate_with_provenance, opportunity_with_context):
    """Citing factual candidate metrics in body without declaring corresponding grounded fact ID fails closed."""
    panel = ExecutiveOutreachJudgePanel()

    # Body cites $4.2B, but grounded_facts_used is empty
    draft = OutreachMessageDraft(
        draft_id="d_adversarial_undeclared_fact",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist perspectives",
        body=(
            "Hi Charles,\n\n"
            "Following Truist's cloud resilience mandate. "
            "In my recent work, scaled payment systems handling $4.2B annual volume.\n\n"
            "Would you be open to exchanging brief perspectives next week?"
        ),
        grounded_facts_used=[],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = panel.evaluate(draft, candidate_with_provenance, opportunity_with_context)
    assert report.passed is False
    assert report.lens2_grounding_score == 0.0
    assert any("without declaring any grounded fact ID" in f for f in report.feedback)


def test_adversarial_unsupported_superlative_claim_rejected(candidate_with_provenance, opportunity_with_context):
    """Invented accomplishments or invention claims are rejected even with valid fact IDs attached."""
    panel = ExecutiveOutreachJudgePanel()

    draft = OutreachMessageDraft(
        draft_id="d_adversarial_invention",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist cloud resilience",
        body=(
            "Hi Charles,\n\n"
            "Following Truist's cloud resilience mandate. "
            "In my work, I personally invented the internet and scaled payment systems handling $4.2B annual volume.\n\n"
            "Would you be open to exchanging brief perspectives next week?"
        ),
        grounded_facts_used=["fact_scale_4b"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = panel.evaluate(draft, candidate_with_provenance, opportunity_with_context)
    assert report.passed is False
    assert report.lens2_grounding_score == 0.0
    assert any("Unsupported factual assertion" in f for f in report.feedback)


def test_adversarial_opportunity_context_metric_allowed(candidate_with_provenance, opportunity_with_context):
    """Metrics originating from target company strategic priorities do not trigger false positives."""
    panel = ExecutiveOutreachJudgePanel()

    # Body cites $50M (from Truist strategic priorities) and $4.2B (from candidate fact)
    draft = OutreachMessageDraft(
        draft_id="d_grounded_pass",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist architecture and cloud resilience perspectives",
        body=(
            "Charles, following Truist's focus on managing $50M legacy core banking modernization program and cloud resilience, "
            "I wanted to connect. In my recent work, scaled payment systems handling $4.2B annual volume at 99.995% SLA.\n\n"
            "Would you be open to exchanging perspectives next week?"
        ),
        grounded_facts_used=["fact_scale_4b"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = panel.evaluate(draft, candidate_with_provenance, opportunity_with_context)
    assert report.passed is True
    assert report.lens2_grounding_score >= 0.99
    assert report.lens3_resonance_score >= 0.70
    assert len(report.feedback) == 0


def test_adversarial_supported_metrics_and_provenance_pass(candidate_with_provenance, opportunity_with_context):
    """Verified claims with rigorous provenance pass evaluation cleanly."""
    panel = ExecutiveOutreachJudgePanel()

    draft = OutreachMessageDraft(
        draft_id="d_supported_pass",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist / Enterprise Architecture perspectives",
        body=(
            "Hi Charles,\n\n"
            "Following Truist's focus on cloud resilience and core modernization. "
            "In my recent work, managed distributed engineering organization of 150+ engineers.\n\n"
            "Would you be open to a brief conversation next week?"
        ),
        grounded_facts_used=["fact_team_150"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = panel.evaluate(draft, candidate_with_provenance, opportunity_with_context)
    assert report.passed is True
    assert report.lens2_grounding_score >= 0.99
    assert report.score_band in ("ACCEPTABLE", "EXEMPLARY")


def test_adversarial_mismatched_declared_fact_rejected(candidate_with_provenance, opportunity_with_context):
    """When a draft declares fact_team_150 (150+ engineers) but quotes $4.2B, it is rejected for undeclared fact."""
    panel = ExecutiveOutreachJudgePanel()

    draft = OutreachMessageDraft(
        draft_id="d_mismatched_fact",
        channel=ChannelType.LINKEDIN_INMAIL,
        subject="Truist / Enterprise Architecture perspectives",
        body=(
            "Hi Charles,\n\n"
            "Following Truist's focus on cloud resilience and core modernization. "
            "In my recent work, scaled payment systems handling $4.2B annual volume at 99.995% SLA.\n\n"
            "Would you be open to a brief conversation next week?"
        ),
        # Deliberately declaring fact_team_150 instead of fact_scale_4b!
        grounded_facts_used=["fact_team_150"],
        audience_persona=AudiencePersona.EXECUTIVE_CONTACT,
    )

    report = panel.evaluate(draft, candidate_with_provenance, opportunity_with_context)
    assert report.passed is False
    assert report.lens2_grounding_score == 0.0
    assert any("Unsupported dollar metric claim" in f for f in report.feedback)


def test_adversarial_touch_sequence_blocks_unsupported_touch(candidate_with_provenance, opportunity_with_context):
    """Multi-touch sequence planner marks touch failed when ungrounded fact is injected."""
    from apps_lic.pipeline.touch_sequence import TouchSequencePlanner

    planner = TouchSequencePlanner()
    seq = planner.plan_sequence(candidate_with_provenance, opportunity_with_context)
    assert len(seq.touches) == 3
    # Standard touches pass
    assert seq.touches[0].draft.metadata.get("passed") is True
    assert seq.touches[1].draft.metadata.get("passed") is True

    # Corrupt touch 1 with unsupported metric
    seq.touches[0].draft.body += " In addition, achieved $999B in ungrounded volume."
    panel = ExecutiveOutreachJudgePanel()
    corrupted_report = panel.evaluate(seq.touches[0].draft, candidate_with_provenance, opportunity_with_context)
    assert corrupted_report.passed is False
    assert corrupted_report.lens2_grounding_score == 0.0

