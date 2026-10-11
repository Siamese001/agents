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
    ForbiddenClaimsValidator,
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
        self._forbidden_validator = ForbiddenClaimsValidator()
        self._judge_panel = ExecutiveOutreachJudgePanel()
        from apps_lic.pipeline.compiler import PromptCompiler
        self._compiler = PromptCompiler()

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
        from apps_lic.pipeline.compiler import (
            get_executive_signature_block,
            get_recruiter_signature_block,
        )
        compiler = self._compiler
        raw_hook = opportunity.strategic_priorities[0] if opportunity.strategic_priorities else opportunity.industry
        hook = compiler._format_strategic_hook(raw_hook, company_name=opportunity.company_name)

        if persona == AudiencePersona.EXECUTIVE_RECRUITER:
            t1_body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Targeting {candidate.target_title} leadership opportunities at {opportunity.company_name}.\n"
                f"Track record includes {primary_fact}.\n\n"
                f"Would you be open to a brief conversation regarding current or upcoming mandates?"
            )
            t1_subject = f"{opportunity.company_name} / {opportunity.role_title} perspective"
        else:
            t1_subject, t1_body, _ = compiler.render_draft_message(
                candidate,
                opportunity,
                effective_primary,
                audience_persona=persona,
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
            subject=t1_subject or f"{opportunity.company_name} / {opportunity.role_title} perspective",
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
        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            t2_body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Following up briefly on my note. Recalled our shared work and thought of {opportunity.company_name} given our recent results {secondary_fact}.\n\n"
                f"Open to a 10-minute introductory conversation?"
            )
        elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
            t2_body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Following up briefly on my note. Given our mutual network and {opportunity.company_name}'s priorities, thought of our recent results {secondary_fact}.\n\n"
                f"Open to a 10-minute introductory conversation?"
            )
        else:
            t2_body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Following up briefly on my note. Thought of {opportunity.company_name} given our recent results {secondary_fact}.\n\n"
                f"Open to a 10-minute introductory conversation?"
            )
        t2_draft = OutreachMessageDraft(
            draft_id=f"{sequence_id}_t2",
            channel=ChannelType.FOLLOW_UP,
            subject=f"Re: {t1_draft.subject}",
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
        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            t3_body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"I know how busy things get. If timing is not right at {opportunity.company_name}, no problem at all.\n\n"
                f"Would it be helpful to reconnect next quarter instead?"
            )
        else:
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
        # Authoritative Evaluation of All Touches in a Single Pass
        # -----------------------------------------------------------------
        blocked_summary: List[dict] = []
        for touch in touches:
            d = touch.draft
            verdict = self._judge_panel.evaluate_authoritative(d, candidate, opportunity)
            d.metadata["authoritative_verdict"] = verdict.to_dict()
            d.metadata["validation_violations"] = list(verdict.violations)
            d.metadata["evaluation_report"] = verdict.to_dict()
            d.metadata["passed"] = verdict.passed
            d.metadata["status"] = verdict.status
            d.metadata["failure_reasons"] = list(verdict.failure_reasons)

            if not verdict.passed:
                blocked_summary.append({
                    "touch_number": touch.touch_number,
                    "day_offset": touch.day_offset,
                    "channel": touch.channel.value,
                    "objective": touch.objective,
                    "status": "BLOCKED",
                    "failure_reasons": list(verdict.failure_reasons),
                    "violations": list(verdict.violations),
                })

        seq_status = "PASSED" if not blocked_summary else "BLOCKED"

        return TouchSequence(
            sequence_id=sequence_id,
            candidate_id=candidate.candidate_id,
            opportunity_id=opportunity.opportunity_id,
            touches=touches,
            sealed_resolution=opportunity.sealed_resolution,
            status=seq_status,
            blocked_touches=blocked_summary,
        )
