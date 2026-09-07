"""Orchestrator coordinating prompt compilation, draft generation, and validation."""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from apps_lic.domain.models import (
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    TargetOpportunity,
    TouchSequence,
    ValidationResult,
)
from apps_lic.domain.validators import (
    ChannelLengthValidator,
    GroundingValidator,
    QuestionEndingValidator,
    SpamTriggerValidator,
)
from apps_lic.pipeline.compiler import PromptCompiler
from apps_lic.pipeline.touch_sequence import TouchSequencePlanner


class OutreachOrchestrator:
    """Bounded, decoupled orchestrator executing the 4-stage outreach pipeline."""

    def __init__(self) -> None:
        self.compiler = PromptCompiler()
        self.sequence_planner = TouchSequencePlanner()
        self.spam_validator = SpamTriggerValidator()
        self.length_validator = ChannelLengthValidator()
        self.question_validator = QuestionEndingValidator()
        self.grounding_validator = GroundingValidator()

    def generate_single_draft(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
    ) -> tuple[OutreachMessageDraft, ValidationResult]:
        """Generates and validates a single grounded outreach draft."""
        context = self.compiler.assemble_context(candidate, opportunity, channel)
        
        # Assemble message body
        lead_fact = candidate.verified_facts[0] if candidate.verified_facts else None
        fact_statement = lead_fact.statement if lead_fact else candidate.executive_summary
        fact_ids = [lead_fact.fact_id] if lead_fact else []

        subject = f"{opportunity.company_name} / {opportunity.role_title} - Strategic Alignment"
        body = (
            f"Hi {opportunity.recipient_name},\n\n"
            f"I have been following {opportunity.company_name}'s work in {opportunity.industry}. "
            f"In my recent work as {candidate.target_title}, {fact_statement}.\n\n"
            f"Given your focus, would you be open to a brief conversation next week?"
        )

        draft = OutreachMessageDraft(
            draft_id=f"draft_{uuid.uuid4().hex[:8]}",
            channel=channel,
            subject=subject,
            body=body,
            grounded_facts_used=fact_ids,
            metadata={"context_keys": list(context.keys())},
        )

        # Run multi-gate validation
        validation = self.validate_draft(draft, candidate)
        return draft, validation

    def validate_draft(
        self, draft: OutreachMessageDraft, candidate: CandidateProfile
    ) -> ValidationResult:
        """Runs all 4 validation gates over the draft."""
        violations: List[str] = []
        warnings: List[str] = []

        # 1. Spam triggers
        spam_valid, spam_viol, spam_warn = self.spam_validator.validate(draft.body)
        violations.extend(spam_viol)
        warnings.extend(spam_warn)

        # 2. Channel length
        len_valid, len_err = self.length_validator.validate(draft.channel, draft.body)
        if not len_valid and len_err:
            violations.append(len_err)

        # 3. Question ending
        q_valid, q_err = self.question_validator.validate(draft.body)
        if not q_valid and q_err:
            violations.append(q_err)

        # 4. Grounding
        allowed_facts = {f.fact_id for f in candidate.verified_facts}
        g_valid, g_viol = self.grounding_validator.validate(
            draft.grounded_facts_used, allowed_facts
        )
        violations.extend(g_viol)

        hard_passed = len(violations) == 0
        return ValidationResult(
            is_valid=hard_passed,
            hard_gate_passed=hard_passed,
            violations=violations,
            warnings=warnings,
            scores={
                "spam_score": 1.0 if spam_valid else 0.0,
                "length_score": 1.0 if len_valid else 0.0,
                "question_score": 1.0 if q_valid else 0.0,
                "grounding_score": 1.0 if g_valid else 0.0,
            },
        )

    def generate_full_campaign(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        primary_channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
    ) -> TouchSequence:
        """Generates a complete validated multi-touch sequence."""
        return self.sequence_planner.plan_sequence(candidate, opportunity, primary_channel)
