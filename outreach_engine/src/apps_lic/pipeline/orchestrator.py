"""Orchestrator coordinating prompt compilation, draft generation, and validation."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    TargetOpportunity,
    TouchSequence,
    ValidationResult,
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
from apps_lic.judges.evaluator import EvaluationReport, RubricJudgeEvaluator
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver, SealedBriefingResolution
from apps_lic.pipeline.compiler import (
    PromptCompiler,
    get_executive_signature_block,
    get_recruiter_signature_block,
)
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
        self.em_dash_validator = EmDashValidator()
        self.md_link_validator = MarkdownLinkValidator()
        self.tone_validator = SubordinateToneValidator()
        self.judge = RubricJudgeEvaluator()

    def resolve_opportunity_briefing(
        self,
        opportunity: TargetOpportunity,
        *,
        auto_research: bool = True,
        research_bridge: Any | None = None,
        job_description_text: str = "",
        artifact_runs_root: Path | None = None,
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
            artifact_runs_root=artifact_runs_root,
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
        audience_persona: Optional[AudiencePersona] = None,
        auto_research: bool = True,
        research_bridge: Any | None = None,
        job_description_text: str = "",
        artifact_dir: Path | str | None = None,
        trace_id: str = "",
    ) -> tuple[OutreachMessageDraft, ValidationResult]:
        """Generates and validates a single grounded outreach draft with governed briefing."""
        a_dir = Path(artifact_dir) if artifact_dir else None
        artifact_runs_root = (a_dir / "apps_research" / "runs") if a_dir else None

        opp = self.resolve_opportunity_briefing(
            opportunity,
            auto_research=auto_research,
            research_bridge=research_bridge,
            job_description_text=job_description_text,
            artifact_runs_root=artifact_runs_root,
            trace_id=trace_id,
        )

        # Resolve audience persona
        if audience_persona is None:
            if opp.recipient_class == RecipientClass.TALENT_PARTNER:
                persona = AudiencePersona.EXECUTIVE_RECRUITER
            else:
                persona = AudiencePersona.EXECUTIVE_CONTACT
        else:
            persona = audience_persona

        context = self.compiler.assemble_context(candidate, opp, channel, audience_persona=persona)
        subject, body, fact_ids = self.compiler.render_draft_message(candidate, opp, channel, audience_persona=persona)

        signature = ""
        if channel in (ChannelType.LINKEDIN_INMAIL, ChannelType.EMAIL):
            if persona == AudiencePersona.EXECUTIVE_RECRUITER:
                signature = get_recruiter_signature_block(candidate.full_name)
            else:
                signature = get_executive_signature_block(candidate.full_name)

        draft = OutreachMessageDraft(
            draft_id=f"draft_{uuid.uuid4().hex[:8]}",
            channel=channel,
            subject=subject,
            body=body,
            signature_block=signature,
            audience_persona=persona,
            grounded_facts_used=fact_ids,
            research_metadata={
                "resolution_source": opp.sealed_resolution.get("resolution_source") if opp.sealed_resolution else "none",
                "research_digest": opp.research_digest,
                "evidence_count": len(opp.evidence_items),
            },
            metadata={
                "context_keys": list(context.keys()),
                "template_id": context.get("template_id"),
                "audience_persona": persona.value,
            },
        )

        validation = self.validate_draft(draft, candidate)

        if a_dir is not None:
            a_dir.mkdir(parents=True, exist_ok=True)
            draft_dict = {
                "draft_id": draft.draft_id,
                "channel": draft.channel.value,
                "audience_persona": persona.value,
                "subject": draft.subject,
                "body": draft.body,
                "signature_block": draft.signature_block,
                "character_count": draft.character_count,
                "grounded_facts_used": draft.grounded_facts_used,
                "research_metadata": draft.research_metadata,
            }
            (a_dir / "outreach_draft.json").write_text(json.dumps(draft_dict, indent=2) + "\n", encoding="utf-8")
            draft_body_full = f"{draft.body}\n\n{draft.signature_block}" if draft.signature_block else draft.body
            (a_dir / "outreach_draft.md").write_text(
                f"# Outreach Draft: {draft.channel.value.upper()}\n\n"
                f"**Subject**: {draft.subject}\n\n"
                f"```text\n{draft_body_full}\n```\n",
                encoding="utf-8",
            )
            val_dict = {
                "is_valid": validation.is_valid,
                "violations": validation.violations,
                "warnings": validation.warnings,
                "scores": validation.scores,
            }
            (a_dir / "validation_report.json").write_text(json.dumps(val_dict, indent=2) + "\n", encoding="utf-8")

        return draft, validation

    def validate_draft(
        self, draft: OutreachMessageDraft, candidate: CandidateProfile
    ) -> ValidationResult:
        """Runs all 7 validation gates over the draft."""
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

        # 5. Em dashes
        dash_valid, dash_err = self.em_dash_validator.validate(draft.body)
        if not dash_valid and dash_err:
            violations.append(dash_err)

        # 6. Markdown links
        link_valid, link_err = self.md_link_validator.validate(draft.body)
        if not link_valid and link_err:
            violations.append(link_err)

        # 7. Subordinate tone
        tone_valid, tone_viols = self.tone_validator.validate(draft.body)
        violations.extend(tone_viols)

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
                "dash_score": 1.0 if dash_valid else 0.0,
                "link_score": 1.0 if link_valid else 0.0,
                "tone_score": 1.0 if tone_valid else 0.0,
            },
        )

    def evaluate_draft(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        *,
        artifact_dir: Path | str | None = None,
    ) -> EvaluationReport:
        """Evaluates draft against the 4 canonical rubric judges."""
        report = self.judge.evaluate(draft, candidate, opportunity)
        if artifact_dir is not None:
            a_dir = Path(artifact_dir)
            a_dir.mkdir(parents=True, exist_ok=True)
            (a_dir / "evaluation_report.json").write_text(
                json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8"
            )
        return report

    def generate_full_campaign(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        primary_channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
        *,
        audience_persona: Optional[AudiencePersona] = None,
        auto_research: bool = True,
        research_bridge: Any | None = None,
        job_description_text: str = "",
        artifact_dir: Path | str | None = None,
        trace_id: str = "",
    ) -> TouchSequence:
        """Generates a complete validated multi-touch sequence with governed briefing."""
        a_dir = Path(artifact_dir) if artifact_dir else None
        artifact_runs_root = (a_dir / "apps_research" / "runs") if a_dir else None

        opp = self.resolve_opportunity_briefing(
            opportunity,
            auto_research=auto_research,
            research_bridge=research_bridge,
            job_description_text=job_description_text,
            artifact_runs_root=artifact_runs_root,
            trace_id=trace_id,
        )
        sequence = self.sequence_planner.plan_sequence(
            candidate,
            opp,
            primary_channel,
            audience_persona=audience_persona,
        )
        sequence.sealed_resolution = opp.sealed_resolution

        if a_dir is not None:
            a_dir.mkdir(parents=True, exist_ok=True)
            seq_dict = {
                "sequence_id": sequence.sequence_id,
                "candidate_id": sequence.candidate_id,
                "opportunity_id": sequence.opportunity_id,
                "touch_count": len(sequence.touches),
                "touches": [
                    {
                        "touch_number": t.touch_number,
                        "day_offset": t.day_offset,
                        "channel": t.channel.value,
                        "objective": t.objective,
                        "subject": t.draft.subject,
                        "body": t.draft.body,
                    }
                    for t in sequence.touches
                ],
            }
            (a_dir / "campaign_sequence.json").write_text(
                json.dumps(seq_dict, indent=2) + "\n", encoding="utf-8"
            )

        return sequence


__all__ = ["OutreachOrchestrator"]
