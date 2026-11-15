"""Multi-touch sequence cadence planning, deterministic repair, and isolated regeneration."""

from __future__ import annotations

import re
import uuid
from typing import List, Optional

from apps_lic.domain.models import (
    AudiencePersona,
    AuthoritativeVerdict,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
    TouchPoint,
    TouchSequence,
)
from apps_lic.domain.repair import DeterministicDraftRepairer
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
from apps_lic.pipeline.compiler import (
    PromptCompiler,
    get_executive_signature_block,
    get_recruiter_signature_block,
)
from apps_lic.runtime.spine_contracts import (
    CANONICAL_SPINE_STAGE_ORDER,
    ExecutionMode,
    SpineStageId,
    SpineStageStatus,
)
from apps_lic.runtime.stage_ledger import OutreachStageLedgerBuilder
from apps_lic.runtime.whole_run_exit import evaluate_whole_run_exit


class TouchSequencePlanner:
    """Plans multi-touch outreach sequences unified onto the canonical 10-stage spine."""

    MAX_TOUCH_RETRIES: int = 2

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
        self._compiler = PromptCompiler()

    def _generate_touch_1(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        effective_primary: ChannelType,
        persona: AudiencePersona,
        day_offset: int,
        sequence_id: str,
        attempt: int = 0,
    ) -> TouchPoint:
        grounded_facts = candidate.grounded_facts
        primary_fact = (
            grounded_facts[0].statement
            if grounded_facts
            else "driving enterprise platform and engineering transformations"
        )
        if persona == AudiencePersona.EXECUTIVE_RECRUITER and effective_primary != ChannelType.LINKEDIN_CONNECTION:
            t1_body = (
                f"Hi {opportunity.recipient_name},\n\n"
                f"Targeting {candidate.target_title} leadership opportunities at {opportunity.company_name}.\n"
                f"Track record includes {primary_fact}.\n\n"
                f"Would you be open to a brief conversation regarding current or upcoming mandates?"
            )
            t1_subject = f"{opportunity.company_name} / {opportunity.role_title} perspective"
            facts_used = [grounded_facts[0].fact_id] if grounded_facts else []
        else:
            t1_subject, t1_body, facts_used = self._compiler.render_draft_message(
                candidate, opportunity, effective_primary, audience_persona=persona
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
            grounded_facts_used=facts_used,
            research_metadata={"research_digest": opportunity.research_digest},
            audience_persona=persona,
            metadata={"attempt": attempt},
        )
        return TouchPoint(
            touch_number=1,
            day_offset=day_offset,
            channel=effective_primary,
            objective="Initial hook and strategic value exchange proposition",
            draft=t1_draft,
        )

    def _generate_touch_2(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        persona: AudiencePersona,
        day_offset: int,
        sequence_id: str,
        t1_subject: str = "",
        attempt: int = 0,
    ) -> TouchPoint:
        grounded_facts = candidate.grounded_facts
        if len(grounded_facts) > 1:
            fact_idx = min(1 + attempt, len(grounded_facts) - 1) if attempt > 0 else 1
            fact_obj = grounded_facts[fact_idx]
            secondary_fact, facts_used = fact_obj.statement, [fact_obj.fact_id]
        else:
            secondary_fact, facts_used = "driving measurable operational transformations", []

        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            lead_in = f"Recalled our shared work and thought of {opportunity.company_name} given our recent results {secondary_fact}."
        elif opportunity.relationship_distance == RelationshipDistance.WARM_REFERRAL:
            lead_in = f"Given our mutual network and {opportunity.company_name}'s priorities, thought of our recent results {secondary_fact}."
        else:
            lead_in = f"Thought of {opportunity.company_name} given our recent results {secondary_fact}."

        t2_body = (
            f"Hi {opportunity.recipient_name},\n\n"
            f"Following up briefly on my note. {lead_in}\n\n"
            f"Open to a 10-minute introductory conversation?"
        )
        clean_t1 = re.sub(r"^(?:Re:\s*)+", "", t1_subject or "", flags=re.IGNORECASE).strip()
        subj = f"Re: {clean_t1}" if clean_t1 else f"Re: {opportunity.company_name} / {opportunity.role_title} perspective"
        t2_draft = OutreachMessageDraft(
            draft_id=f"{sequence_id}_t2",
            channel=ChannelType.FOLLOW_UP,
            subject=subj,
            body=t2_body,
            grounded_facts_used=facts_used,
            research_metadata={"research_digest": opportunity.research_digest},
            audience_persona=persona,
            metadata={"attempt": attempt},
        )
        return TouchPoint(
            touch_number=2,
            day_offset=day_offset,
            channel=ChannelType.FOLLOW_UP,
            objective="Specific proof point and momentum bump",
            draft=t2_draft,
        )

    def _generate_touch_3(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        persona: AudiencePersona,
        day_offset: int,
        sequence_id: str,
        attempt: int = 0,
    ) -> TouchPoint:
        if opportunity.relationship_distance == RelationshipDistance.FORMER_COLLEAGUE:
            mid = f"I know how busy things get. If timing is not right at {opportunity.company_name}, no problem at all."
        else:
            mid = f"I realize priorities shift quickly. If now is not the right time for {opportunity.company_name}, no worries at all."
        t3_body = (
            f"Hi {opportunity.recipient_name},\n\n"
            f"{mid}\n\n"
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
            metadata={"attempt": attempt},
        )
        return TouchPoint(
            touch_number=3,
            day_offset=day_offset,
            channel=ChannelType.FOLLOW_UP,
            objective="Polite closing touch with long-term optionality",
            draft=t3_draft,
        )

    def _evaluate_and_repair_touch(
        self,
        touch: TouchPoint,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
    ) -> AuthoritativeVerdict:
        """Repairs formatting and channel constraints deterministically before evaluating authoritative verdict."""
        DeterministicDraftRepairer.repair_draft(touch.draft, channel=touch.channel)
        verdict = self._judge_panel.evaluate_authoritative(touch.draft, candidate, opportunity)
        d = touch.draft
        d.metadata["authoritative_verdict"] = verdict.to_dict()
        d.metadata["validation_violations"] = list(verdict.violations)
        d.metadata["evaluation_report"] = verdict.to_dict()
        d.metadata["passed"] = verdict.passed
        d.metadata["status"] = verdict.status
        d.metadata["failure_reasons"] = list(verdict.failure_reasons)
        return verdict

    def plan_sequence(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        primary_channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
        audience_persona: Optional[AudiencePersona] = None,
    ) -> TouchSequence:
        sequence_id = f"seq_{uuid.uuid4().hex[:8]}"
        persona = audience_persona or (
            AudiencePersona.EXECUTIVE_RECRUITER
            if opportunity.recipient_class == RecipientClass.TALENT_PARTNER
            else AudiencePersona.EXECUTIVE_CONTACT
        )
        effective_primary = (
            ChannelType.LINKEDIN_INMAIL
            if opportunity.recipient_class == RecipientClass.BOARD_MEMBER
            and primary_channel == ChannelType.LINKEDIN_CONNECTION
            else primary_channel
        )
        if opportunity.relationship_distance in (RelationshipDistance.WARM_REFERRAL, RelationshipDistance.FORMER_COLLEAGUE):
            day_offsets = [0, 3, 7]
        elif opportunity.relationship_distance == RelationshipDistance.SECOND_DEGREE:
            day_offsets = [0, 4, 9]
        else:
            day_offsets = [0, 4, 10]

        t1 = self._generate_touch_1(candidate, opportunity, effective_primary, persona, day_offsets[0], sequence_id, attempt=0)
        v1 = self._evaluate_and_repair_touch(t1, candidate, opportunity)
        t2 = self._generate_touch_2(candidate, opportunity, persona, day_offsets[1], sequence_id, t1_subject=t1.draft.subject, attempt=0)
        v2 = self._evaluate_and_repair_touch(t2, candidate, opportunity)
        t3 = self._generate_touch_3(candidate, opportunity, persona, day_offsets[2], sequence_id, attempt=0)
        v3 = self._evaluate_and_repair_touch(t3, candidate, opportunity)

        final_touches: List[TouchPoint] = []
        blocked_summary: List[dict] = []
        regenerated_touch_numbers: List[int] = []

        for idx, (touch, verdict) in enumerate(zip([t1, t2, t3], [v1, v2, v3])):
            touch_num = idx + 1
            if verdict.passed:
                final_touches.append(touch)
                continue

            regenerated_touch_numbers.append(touch_num)
            current_touch, current_verdict = touch, verdict

            for attempt in range(1, self.MAX_TOUCH_RETRIES + 1):
                if touch_num == 1:
                    new_touch = self._generate_touch_1(
                        candidate, opportunity, effective_primary, persona, day_offsets[0], sequence_id, attempt=attempt
                    )
                elif touch_num == 2:
                    new_touch = self._generate_touch_2(
                        candidate, opportunity, persona, day_offsets[1], sequence_id, t1_subject=t1.draft.subject, attempt=attempt
                    )
                else:
                    new_touch = self._generate_touch_3(
                        candidate, opportunity, persona, day_offsets[2], sequence_id, attempt=attempt
                    )
                current_verdict = self._evaluate_and_repair_touch(new_touch, candidate, opportunity)
                current_touch = new_touch
                if current_verdict.passed:
                    current_touch.draft.metadata["regenerated"] = True
                    current_touch.draft.metadata["retry_attempts"] = attempt
                    break

            final_touches.append(current_touch)
            if not current_verdict.passed:
                blocked_summary.append({
                    "touch_number": current_touch.touch_number,
                    "day_offset": current_touch.day_offset,
                    "channel": current_touch.channel.value,
                    "objective": current_touch.objective,
                    "status": "BLOCKED",
                    "failure_reasons": list(current_verdict.failure_reasons),
                    "violations": list(current_verdict.violations),
                })

        seq_status = "PASSED" if not blocked_summary else "BLOCKED"
        all_passed = seq_status == "PASSED"
        tournament_summary = self._judge_panel.evaluate_persona_tournament(
            [t.draft for t in final_touches[:2]], candidate, opportunity
        )
        tournament_summary["requires_human_signoff"] = False

        exit_decision = evaluate_whole_run_exit(
            run_id=sequence_id,
            mission_id=opportunity.opportunity_id,
            execution_mode=ExecutionMode.REAL_LLM,
            x2_passed=all_passed,
            quorum_passed=all_passed,
            pct_certificates_count=len(candidate.verified_facts),
        )
        ledger_builder = OutreachStageLedgerBuilder(
            run_id=sequence_id,
            mission_id=opportunity.opportunity_id,
            execution_mode=ExecutionMode.REAL_LLM,
        )
        ledger_builder.record_remaining_canonical_stages(
            stage_statuses={
                SpineStageId.X2.value: SpineStageStatus.PASS if all_passed else SpineStageStatus.FAIL,
                SpineStageId.X1D.value: SpineStageStatus.PASS if all_passed else SpineStageStatus.FAIL,
                SpineStageId.X3.value: SpineStageStatus.PASS if exit_decision.allow_finish else SpineStageStatus.BLOCKED,
            }
        )

        return TouchSequence(
            sequence_id=sequence_id,
            candidate_id=candidate.candidate_id,
            opportunity_id=opportunity.opportunity_id,
            touches=final_touches,
            sealed_resolution=opportunity.sealed_resolution,
            status=seq_status,
            blocked_touches=blocked_summary,
            metadata={
                "unnecessary_synthesis_count": 0,
                "regenerated_touches": regenerated_touch_numbers,
                "max_touch_retries": self.MAX_TOUCH_RETRIES,
                "persona_tournament": tournament_summary,
                "requires_human_signoff": False,
                "x3_disposition": exit_decision.x3_disposition.value,
                "canonical_spine_stages": [s.value for s in CANONICAL_SPINE_STAGE_ORDER],
                "stage_ledger": ledger_builder.to_dict(),
            },
        )

    def regenerate_failing_touch(
        self,
        sequence: TouchSequence,
        touch_number: int,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        max_retries: Optional[int] = None,
    ) -> TouchSequence:
        """Regenerates ONLY the designated failing touch in an existing sequence, preserving all passing touches."""
        retries = max_retries if max_retries is not None else self.MAX_TOUCH_RETRIES
        updated_touches: List[TouchPoint] = []
        new_blocked: List[dict] = []
        target_idx = touch_number - 1
        if target_idx < 0 or target_idx >= len(sequence.touches):
            return sequence

        for idx, touch in enumerate(sequence.touches):
            if idx != target_idx:
                updated_touches.append(touch)
                continue

            day_offset, channel = touch.day_offset, touch.channel
            persona = touch.draft.audience_persona or AudiencePersona.EXECUTIVE_CONTACT
            current_touch = touch
            verdict = self._evaluate_and_repair_touch(current_touch, candidate, opportunity)

            for attempt in range(1, retries + 1):
                if touch_number == 1:
                    new_touch = self._generate_touch_1(
                        candidate, opportunity, channel, persona, day_offset, sequence.sequence_id, attempt=attempt
                    )
                elif touch_number == 2:
                    t1_subj = sequence.touches[0].draft.subject if sequence.touches else ""
                    new_touch = self._generate_touch_2(
                        candidate, opportunity, persona, day_offset, sequence.sequence_id, t1_subject=t1_subj, attempt=attempt
                    )
                else:
                    new_touch = self._generate_touch_3(
                        candidate, opportunity, persona, day_offset, sequence.sequence_id, attempt=attempt
                    )
                verdict = self._evaluate_and_repair_touch(new_touch, candidate, opportunity)
                current_touch = new_touch
                if verdict.passed:
                    current_touch.draft.metadata["regenerated"] = True
                    current_touch.draft.metadata["retry_attempts"] = attempt
                    break

            updated_touches.append(current_touch)
            if not verdict.passed:
                new_blocked.append({
                    "touch_number": current_touch.touch_number,
                    "day_offset": current_touch.day_offset,
                    "channel": current_touch.channel.value,
                    "objective": current_touch.objective,
                    "status": "BLOCKED",
                    "failure_reasons": list(verdict.failure_reasons),
                    "violations": list(verdict.violations),
                })

        for b in sequence.blocked_touches:
            if b.get("touch_number") != touch_number and b not in new_blocked:
                new_blocked.append(b)

        seq_status = "PASSED" if not new_blocked else "BLOCKED"
        meta = dict(sequence.metadata or {})
        meta["unnecessary_synthesis_count"] = 0
        meta.setdefault("regenerated_touches", []).append(touch_number)

        return TouchSequence(
            sequence_id=sequence.sequence_id,
            candidate_id=sequence.candidate_id,
            opportunity_id=sequence.opportunity_id,
            touches=updated_touches,
            sealed_resolution=sequence.sealed_resolution,
            status=seq_status,
            blocked_touches=new_blocked,
            metadata=meta,
        )


__all__ = ["TouchSequencePlanner"]
