"""Multi-touch sequence cadence planning and validation."""

from __future__ import annotations

import uuid
from typing import List, Optional

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
    TouchPoint,
    TouchSequence,
)
from apps_lic.domain.validators import (
    ChannelLengthValidator,
    EmDashValidator,
    GroundingValidator,
    MarkdownLinkValidator,
    QuestionEndingValidator,
    SpamTriggerValidator,
    SubordinateToneValidator,
)
from apps_lic.judges.evaluator import ExecutiveOutreachJudgePanel


class TouchSequencePlanner:
    """Plans multi-touch outreach sequences with proper spacing, differentiated hooks, and validation."""

    def __init__(self) -> None:
        self._spam_validator = SpamTriggerValidator()
        self._length_validator = ChannelLengthValidator()
        self._question_validator = QuestionEndingValidator()
        self._grounding_validator = GroundingValidator()
        self._dash_validator = EmDashValidator()
        self._link_validator = MarkdownLinkValidator()
        self._tone_validator = SubordinateToneValidator()
        self._judge_panel = ExecutiveOutreachJudgePanel()

    def plan_sequence(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        primary_channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
        audience_persona: Optional[AudiencePersona] = None,
    ) -> TouchSequence:
        sequence_id = f"seq_{uuid.uuid4().hex[:8]}"
        touches: List[TouchPoint] = []

        # 1. Resolve audience persona
        if audience_persona is None:
            if opportunity.recipient_class == RecipientClass.TALENT_PARTNER:
                persona = AudiencePersona.EXECUTIVE_RECRUITER
            else:
                persona = AudiencePersona.EXECUTIVE_CONTACT
        else:
            persona = audience_persona

        # 2. Adjust primary channel for executive altitude / board tier
        effective_primary = primary_channel
        if opportunity.recipient_class == RecipientClass.BOARD_MEMBER and primary_channel == ChannelType.LINKEDIN_CONNECTION:
            effective_primary = ChannelType.LINKEDIN_INMAIL

        # 3. Dynamic cadence spacing based on RelationshipDistance
        if opportunity.relationship_distance in (RelationshipDistance.WARM_REFERRAL, RelationshipDistance.FORMER_COLLEAGUE):
            day_offsets = [0, 3, 7]
        elif opportunity.relationship_distance == RelationshipDistance.SECOND_DEGREE:
            day_offsets = [0, 4, 9]
        else:
            # COLD or default cadence
            day_offsets = [0, 4, 10]

        # -----------------------------------------------------------------
        # Touch 1 (Day 1 / Offset 0): Initial Hook & Alignment
        # -----------------------------------------------------------------
        primary_fact = candidate.verified_facts[0].statement if candidate.verified_facts else candidate.executive_summary
        hook = opportunity.strategic_priorities[0] if opportunity.strategic_priorities else opportunity.industry

        if persona == AudiencePersona.EXECUTIVE_RECRUITER:
            t1_body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Targeting {candidate.target_title} leadership opportunities at {opportunity.company_name}.\n"
                f"Track record includes {primary_fact}.\n\n"
                f"Would you be open to a brief conversation regarding current or upcoming mandates?"
            )
        else:
            t1_body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Noticed {opportunity.company_name}'s focus on {hook}.\n"
                f"In my work as {candidate.target_title}, {primary_fact}.\n\n"
                f"Would you be open to exchanging brief perspectives next week?"
            )

        from apps_lic.pipeline.compiler import (
            get_executive_signature_block,
            get_recruiter_signature_block,
        )

        sig_block = ""
        if effective_primary in (ChannelType.LINKEDIN_INMAIL, ChannelType.EMAIL):
            sig_block = (
                get_recruiter_signature_block(candidate)
                if persona == AudiencePersona.EXECUTIVE_RECRUITER
                else get_executive_signature_block(candidate)
            )

        t1_draft = OutreachMessageDraft(
            draft_id=f"{sequence_id}_t1",
            channel=effective_primary,
            subject=f"{opportunity.company_name} / {opportunity.role_title} perspective",
            body=t1_body,
            signature_block=sig_block,
            grounded_facts_used=[candidate.verified_facts[0].fact_id] if candidate.verified_facts else [],
            research_metadata={"research_digest": opportunity.research_digest},
            audience_persona=persona,
        )
        touches.append(
            TouchPoint(
                touch_number=1,
                day_offset=day_offsets[0],
                channel=effective_primary,
                objective="Initial hook and strategic value exchange proposition",
                draft=t1_draft,
            )
        )

        # -----------------------------------------------------------------
        # Touch 2 (Offset 1): High-Value Proof Point Follow-Up
        # -----------------------------------------------------------------
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
            research_metadata={"research_digest": opportunity.research_digest},
            audience_persona=persona,
        )
        touches.append(
            TouchPoint(
                touch_number=2,
                day_offset=day_offsets[1],
                channel=ChannelType.FOLLOW_UP,
                objective="Specific proof point and momentum bump",
                draft=t2_draft,
            )
        )

        # -----------------------------------------------------------------
        # Touch 3 (Offset 2): Graceful Low-Friction Close
        # -----------------------------------------------------------------
        t3_body = (
            f"Hi {opportunity.recipient_name},\n\n"
            f"I realize priorities shift quickly. If now is not the right time for {opportunity.company_name}, no worries at all.\n\n"
            f"Would it be helpful to reconnect next quarter instead?"
        )
        t3_draft = OutreachMessageDraft(
            draft_id=f"{sequence_id}_t3",
            channel=ChannelType.FOLLOW_UP,
            subject=f"Checking in: {opportunity.company_name}",
            body=t3_body,
            grounded_facts_used=[],
            research_metadata={"research_digest": opportunity.research_digest},
            audience_persona=persona,
        )
        touches.append(
            TouchPoint(
                touch_number=3,
                day_offset=day_offsets[2],
                channel=ChannelType.FOLLOW_UP,
                objective="Polite closing touch with long-term optionality",
                draft=t3_draft,
            )
        )

        # -----------------------------------------------------------------
        # Validate and Evaluate All Touches through Domain & Rubric Gates
        # -----------------------------------------------------------------
        allowed_facts = {f.fact_id for f in candidate.verified_facts}
        for touch in touches:
            d = touch.draft
            # 1. Validation gates
            spam_valid, spam_viols, spam_warns = self._spam_validator.validate(d.body)
            len_valid, len_err = self._length_validator.validate(d.channel, d.body)
            q_valid, q_err = self._question_validator.validate(d.body)
            g_valid, g_viols = self._grounding_validator.validate(d.grounded_facts_used, allowed_facts)
            dash_valid, dash_err = self._dash_validator.validate(d.body)
            link_valid, link_err = self._link_validator.validate(d.body)
            tone_valid, tone_viols = self._tone_validator.validate(d.body)

            all_viols: List[str] = list(spam_viols)
            if len_err:
                all_viols.append(len_err)
            if q_err:
                all_viols.append(q_err)
            all_viols.extend(g_viols)
            if dash_err:
                all_viols.append(dash_err)
            if link_err:
                all_viols.append(link_err)
            all_viols.extend(tone_viols)

            # 2. Evaluation panel
            eval_report = self._judge_panel.evaluate(d, candidate, opportunity)

            d.metadata["validation_violations"] = all_viols
            d.metadata["evaluation_report"] = eval_report.to_dict()
            d.metadata["passed"] = (len(all_viols) == 0) and eval_report.passed

        return TouchSequence(
            sequence_id=sequence_id,
            candidate_id=candidate.candidate_id,
            opportunity_id=opportunity.opportunity_id,
            touches=touches,
            sealed_resolution=opportunity.sealed_resolution,
        )
