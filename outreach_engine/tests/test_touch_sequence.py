"""Unit tests for multi-touch sequence planner."""

from apps_lic.domain.models import (
    AudiencePersona,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.pipeline.touch_sequence import TouchSequencePlanner


def test_touch_sequence_planner_generates_3_touch_cadence(sample_candidate, sample_opportunity):
    planner = TouchSequencePlanner()
    seq = planner.plan_sequence(sample_candidate, sample_opportunity)

    assert len(seq.touches) == 3
    assert seq.touches[0].day_offset == 0
    assert seq.touches[1].day_offset == 4
    assert seq.touches[2].day_offset == 10

    # Ensure Day 1 and Day 4 use grounded facts
    assert len(seq.touches[0].draft.grounded_facts_used) == 1
    assert len(seq.touches[1].draft.grounded_facts_used) == 1

    # Ensure all drafts conclude with questions
    for t in seq.touches:
        assert t.draft.body.strip().endswith("?")
        assert t.draft.metadata.get("passed") is True
        assert len(t.draft.metadata.get("validation_violations", [])) == 0


def test_touch_sequence_cadence_spacing_warm_and_second_degree(sample_candidate):
    planner = TouchSequencePlanner()

    warm_opp = TargetOpportunity(
        opportunity_id="opp_warm",
        company_name="Apex Systems",
        role_title="CTO",
        industry="Fintech",
        recipient_name="Marcus Vance",
        recipient_title="Partner",
        recipient_class=RecipientClass.EXECUTIVE_PEER,
        relationship_distance=RelationshipDistance.WARM_REFERRAL,
        strategic_priorities=["cloud modern banking core"],
    )
    warm_seq = planner.plan_sequence(sample_candidate, warm_opp)
    assert [t.day_offset for t in warm_seq.touches] == [0, 3, 7]

    sec_opp = TargetOpportunity(
        opportunity_id="opp_sec",
        company_name="Apex Systems",
        role_title="CTO",
        industry="Fintech",
        recipient_name="Marcus Vance",
        recipient_title="Partner",
        recipient_class=RecipientClass.EXECUTIVE_PEER,
        relationship_distance=RelationshipDistance.SECOND_DEGREE,
        strategic_priorities=["cloud modern banking core"],
    )
    sec_seq = planner.plan_sequence(sample_candidate, sec_opp)
    assert [t.day_offset for t in sec_seq.touches] == [0, 4, 9]


def test_touch_sequence_board_member_channel_upgrade(sample_candidate):
    planner = TouchSequencePlanner()

    board_opp = TargetOpportunity(
        opportunity_id="opp_board",
        company_name="Apex Systems",
        role_title="Board Director",
        industry="Fintech",
        recipient_name="Sir Arthur",
        recipient_title="Board Member",
        recipient_class=RecipientClass.BOARD_MEMBER,
        strategic_priorities=["governance"],
    )
    seq = planner.plan_sequence(sample_candidate, board_opp, primary_channel=ChannelType.LINKEDIN_CONNECTION)
    assert seq.touches[0].channel == ChannelType.LINKEDIN_INMAIL


def test_touch_sequence_recruiter_persona(sample_candidate, sample_opportunity):
    planner = TouchSequencePlanner()
    seq = planner.plan_sequence(
        sample_candidate,
        sample_opportunity,
        audience_persona=AudiencePersona.EXECUTIVE_RECRUITER,
    )
    assert seq.touches[0].draft.audience_persona == AudiencePersona.EXECUTIVE_RECRUITER
    assert "leadership opportunities at Apex Financial Systems" in seq.touches[0].draft.body
    assert seq.touches[0].draft.metadata.get("passed") is True


def test_touch_sequence_blocks_forbidden_claims(sample_candidate, sample_opportunity):
    planner = TouchSequencePlanner()
    opp_with_forbidden = TargetOpportunity(
        opportunity_id="opp_forbidden",
        company_name="Apex Financial Systems",
        role_title="VP Engineering",
        industry="Fintech",
        recipient_name="Jordan Reed",
        recipient_title="VP Engineering",
        recipient_class=RecipientClass.HIRING_MANAGER,
        strategic_priorities=["Targeting a salary of $350k plus signing bonus"],
    )
    seq = planner.plan_sequence(sample_candidate, opp_with_forbidden)
    # Touch 1 incorporates the hook which contains forbidden compensation
    t1 = seq.touches[0]
    assert t1.draft.metadata.get("passed") is False
    assert any("compensation" in v.lower() for v in t1.draft.metadata.get("validation_violations", []))

