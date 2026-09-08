"""Multi-touch sequence cadence planning."""

from __future__ import annotations

import uuid
from typing import List

from apps_lic.domain.models import (
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    TargetOpportunity,
    TouchPoint,
    TouchSequence,
)


class TouchSequencePlanner:
    """Plans multi-touch outreach sequences with proper spacing and differentiated hooks."""

    def plan_sequence(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        primary_channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
    ) -> TouchSequence:
        sequence_id = f"seq_{uuid.uuid4().hex[:8]}"
        touches: List[TouchPoint] = []

        # Touch 1 (Day 1): Initial Hook & Alignment
        primary_fact = candidate.verified_facts[0].statement if candidate.verified_facts else candidate.executive_summary
        t1_body = (
            f"Hi {opportunity.recipient_name},\n\n"
            f"Noticed {opportunity.company_name}'s focus on {opportunity.strategic_priorities[0] if opportunity.strategic_priorities else opportunity.industry}.\n"
            f"In my work as {candidate.target_title}, {primary_fact}.\n\n"
            f"Would you be open to exchanging brief perspectives next week?"
        )
        t1_draft = OutreachMessageDraft(
            draft_id=f"{sequence_id}_t1",
            channel=primary_channel,
            subject=f"{opportunity.company_name} / {opportunity.role_title} perspective",
            body=t1_body,
            grounded_facts_used=[candidate.verified_facts[0].fact_id] if candidate.verified_facts else [],
        )
        touches.append(
            TouchPoint(
                touch_number=1,
                day_offset=0,
                channel=primary_channel,
                objective="Initial hook and strategic value exchange proposition",
                draft=t1_draft,
            )
        )

        # Touch 2 (Day 4): High-Value Proof Point Follow-Up
        secondary_fact = (
            candidate.verified_facts[1].statement
            if len(candidate.verified_facts) > 1
            else "driving measurable operational transformations"
        )
        t2_body = (
            f"Hi {opportunity.recipient_name},\n\n"
            f"Following up briefly on my note. Thought of {opportunity.company_name} given our recent results {secondary_fact}.\n\n"
            f"Open to a 10-minute introductory conversation?"
        )
        t2_draft = OutreachMessageDraft(
            draft_id=f"{sequence_id}_t2",
            channel=ChannelType.FOLLOW_UP,
            subject=f"Re: {opportunity.company_name} / {opportunity.role_title} perspective",
            body=t2_body,
            grounded_facts_used=[candidate.verified_facts[1].fact_id] if len(candidate.verified_facts) > 1 else [],
        )
        touches.append(
            TouchPoint(
                touch_number=2,
                day_offset=4,
                channel=ChannelType.FOLLOW_UP,
                objective="Specific proof point and momentum bump",
                draft=t2_draft,
            )
        )

        # Touch 3 (Day 10): Graceful Low-Friction Close
        t3_body = (
            f"Hi {opportunity.recipient_name},\n\n"
            f"I realize priorities shift quickly. If now isn't the right time, no worries at all.\n\n"
            f"Would it be helpful to reconnect next quarter instead?"
        )
        t3_draft = OutreachMessageDraft(
            draft_id=f"{sequence_id}_t3",
            channel=ChannelType.FOLLOW_UP,
            subject=f"Checking in: {opportunity.company_name}",
            body=t3_body,
            grounded_facts_used=[],
        )
        touches.append(
            TouchPoint(
                touch_number=3,
                day_offset=10,
                channel=ChannelType.FOLLOW_UP,
                objective="Polite closing touch with long-term optionality",
                draft=t3_draft,
            )
        )

        return TouchSequence(
            sequence_id=sequence_id,
            candidate_id=candidate.candidate_id,
            opportunity_id=opportunity.opportunity_id,
            touches=touches,
        )
