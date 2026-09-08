"""Orchestrator coordinating prompt compilation, draft generation, and validation."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

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
from apps_lic.judges.evaluator import EvaluationReport, RubricJudgeEvaluator
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver, SealedBriefingResolution
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
        self.judge = RubricJudgeEvaluator()

    def resolve_opportunity_briefing(
        self,
        opportunity: TargetOpportunity,
        *,
        auto_research: bool = True,
        research_bridge: Any | None = None,
        job_description_text: str = "",
        trace_id: str = "",
    ) -> TargetOpportunity:
        """Resolves target briefing via GovernedBriefingResolver if not already sealed."""
        if opportunity.sealed_resolution is not None:
            return opportunity

        resolution: SealedBriefingResolution = GovernedBriefingResolver.resolve(
            company_name=opportunity.company_name,
            target_role=opportunity.role_title,
            manual_brief_or_fixture=opportunity.briefing_text,
            strategic_priorities=opportunity.strategic_priorities,
            job_description_text=job_description_text,
            auto_research=auto_research,
            research_bridge=research_bridge,
            trace_id=trace_id,
        )

        priorities = list(opportunity.strategic_priorities)
        if not priorities and resolution.strategic_priorities:
            priorities = list(resolution.strategic_priorities)

        return TargetOpportunity(
            opportunity_id=opportunity.opportunity_id,
            company_name=opportunity.company_name,
            role_title=opportunity.role_title,
            industry=opportunity.industry,
            recipient_name=opportunity.recipient_name,
            recipient_title=opportunity.recipient_title,
            recipient_class=opportunity.recipient_class,
            relationship_distance=opportunity.relationship_distance,
            strategic_priorities=priorities,
            briefing_text=resolution.briefing_text,
            research_digest=resolution.digest,
            evidence_items=list(resolution.metadata.get("evidence_items", [])),
            sealed_resolution=resolution.to_dict(),
        )

    def generate_single_draft(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
        *,
        auto_research: bool = True,
        research_bridge: Any | None = None,
        job_description_text: str = "",
        trace_id: str = "",
    ) -> tuple[OutreachMessageDraft, ValidationResult]:
        """Generates and validates a single grounded outreach draft with governed briefing."""
        opp = self.resolve_opportunity_briefing(
            opportunity,
            auto_research=auto_research,
            research_bridge=research_bridge,
            job_description_text=job_description_text,
            trace_id=trace_id,
        )

        context = self.compiler.assemble_context(candidate, opp, channel)
        subject, body, fact_ids = self.compiler.render_draft_message(candidate, opp, channel)

        draft = OutreachMessageDraft(
            draft_id=f"draft_{uuid.uuid4().hex[:8]}",
            channel=channel,
            subject=subject,
            body=body,
            grounded_facts_used=fact_ids,
            research_metadata={
                "resolution_source": opp.sealed_resolution.get("resolution_source") if opp.sealed_resolution else "none",
                "research_digest": opp.research_digest,
                "evidence_count": len(opp.evidence_items),
            },
            metadata={"context_keys": list(context.keys()), "template_id": context.get("template_id")},
        )

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

    def evaluate_draft(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
    ) -> EvaluationReport:
        """Evaluates draft against the 4 canonical rubric judges."""
        return self.judge.evaluate(draft, candidate, opportunity)

    def generate_full_campaign(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        primary_channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
        *,
        auto_research: bool = True,
        research_bridge: Any | None = None,
        job_description_text: str = "",
        trace_id: str = "",
    ) -> TouchSequence:
        """Generates a complete validated multi-touch sequence with governed briefing."""
        opp = self.resolve_opportunity_briefing(
            opportunity,
            auto_research=auto_research,
            research_bridge=research_bridge,
            job_description_text=job_description_text,
            trace_id=trace_id,
        )
        sequence = self.sequence_planner.plan_sequence(candidate, opp, primary_channel)
        sequence.sealed_resolution = opp.sealed_resolution
        return sequence
