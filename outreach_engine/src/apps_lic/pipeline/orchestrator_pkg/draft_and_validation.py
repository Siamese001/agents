"""Briefing resolution, single-draft generation, and 10-gate validation for OutreachOrchestrator."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, List, Optional

from apps_lic.domain.models import (
    AudiencePersona,
    AuthoritativeVerdict,
    CandidateProfile,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    TargetOpportunity,
    ValidationResult,
)
from apps_lic.domain.validators import (
    ChannelLengthValidator,
    EmDashValidator,
    ForbiddenClaimsValidator,
    GroundingValidator,
    MarkdownLinkValidator,
    OutboundPrivacyValidator,
    QuestionEndingValidator,
    SpamTriggerValidator,
    SubordinateToneValidator,
    UnsupportedPersonalizationValidator,
)
from apps_lic.judges.evaluator import EvaluationReport, RubricJudgeEvaluator
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver, SealedBriefingResolution
from apps_lic.pipeline.compiler import (
    PromptCompiler,
    get_executive_signature_block,
    get_recruiter_signature_block,
)
from apps_lic.pipeline.touch_sequence import TouchSequencePlanner
from apps_lic.runtime.run_bundle_index import execute_canonical_10_stage_spine
from apps_lic.runtime.spine_contracts import CANONICAL_SPINE_STAGE_ORDER
from apps_lic.runtime.whole_run_exit import evaluate_whole_run_exit


class OutreachDraftAndValidationBase:
    """Base orchestrator implementing briefing resolution, draft generation, and validation."""

    def __init__(self, *, offline_smoke: bool = False) -> None:
        self.offline_smoke = bool(offline_smoke)
        self.compiler = PromptCompiler()
        self.sequence_planner = TouchSequencePlanner()
        self.spam_validator = SpamTriggerValidator()
        self.length_validator = ChannelLengthValidator()
        self.question_validator = QuestionEndingValidator()
        self.grounding_validator = GroundingValidator()
        self.em_dash_validator = EmDashValidator()
        self.md_link_validator = MarkdownLinkValidator()
        self.tone_validator = SubordinateToneValidator()
        self.forbidden_validator = ForbiddenClaimsValidator()
        self.unsupported_personalization_validator = UnsupportedPersonalizationValidator()
        self.privacy_validator = OutboundPrivacyValidator()
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
        force_fresh: bool = False,
    ) -> TargetOpportunity:
        """Resolves target briefing via GovernedBriefingResolver if not already sealed."""
        if not force_fresh and opportunity.sealed_resolution is not None:
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
            force_fresh=force_fresh,
        )

        priorities = list(opportunity.strategic_priorities) or list(resolution.strategic_priorities or [])
        ev_items = list(opportunity.evidence_items) or list(resolution.metadata.get("evidence_items", []))
        if not ev_items and resolution.is_verified and priorities:
            ev_items = list(priorities)

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
            evidence_items=ev_items,
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
        force_fresh: bool = False,
    ) -> tuple[OutreachMessageDraft, AuthoritativeVerdict]:
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
            force_fresh=force_fresh,
        )

        upgraded_from: str | None = None
        if opp.recipient_class == RecipientClass.BOARD_MEMBER and channel == ChannelType.LINKEDIN_CONNECTION:
            upgraded_from = channel.value
            channel = ChannelType.LINKEDIN_INMAIL

        if audience_persona is None:
            persona = (
                AudiencePersona.EXECUTIVE_RECRUITER
                if opp.recipient_class == RecipientClass.TALENT_PARTNER
                else AudiencePersona.EXECUTIVE_CONTACT
            )
        else:
            persona = audience_persona

        context = self.compiler.assemble_context(candidate, opp, channel, audience_persona=persona)
        subject, body, fact_ids = self.compiler.render_draft_message(candidate, opp, channel, audience_persona=persona)

        signature = ""
        if channel in (ChannelType.LINKEDIN_INMAIL, ChannelType.EMAIL):
            signature = (
                get_recruiter_signature_block(candidate)
                if persona == AudiencePersona.EXECUTIVE_RECRUITER
                else get_executive_signature_block(candidate)
            )

        sealed_ev_count = int((opp.sealed_resolution or {}).get("evidence_count", 0))
        res_meta: dict[str, Any] = {
            "resolution_source": opp.sealed_resolution.get("resolution_source") if opp.sealed_resolution else "none",
            "research_digest": opp.research_digest,
            "evidence_count": max(len(opp.evidence_items), sealed_ev_count),
        }
        if upgraded_from is not None:
            res_meta["channel_upgraded_from"] = upgraded_from

        draft = OutreachMessageDraft(
            draft_id=f"draft_{uuid.uuid4().hex[:8]}",
            channel=channel,
            subject=subject,
            body=body,
            signature_block=signature,
            audience_persona=persona,
            grounded_facts_used=fact_ids,
            research_metadata=res_meta,
            metadata={
                "context_keys": list(context.keys()),
                "template_id": context.get("template_id"),
                "audience_persona": persona.value,
            },
        )

        from apps_lic.domain.repair import DeterministicDraftRepairer
        DeterministicDraftRepairer.repair_draft(draft, channel=channel)

        verdict = self.evaluate_authoritative_draft(draft, candidate, opp, artifact_dir=a_dir)
        exit_decision = evaluate_whole_run_exit(
            run_id=draft.draft_id,
            mission_id=opp.opportunity_id,
            x2_passed=bool(verdict.hard_gate_passed),
            quorum_passed=bool(verdict.passed),
            pct_certificates_count=len(draft.grounded_facts_used),
        )
        draft.metadata["passed"] = verdict.passed
        draft.metadata["status"] = verdict.status
        draft.metadata["violations"] = verdict.violations
        draft.metadata["failure_reasons"] = verdict.failure_reasons
        draft.metadata["x3_disposition"] = exit_decision.x3_disposition.value
        draft.metadata["canonical_spine_stages"] = [s.value for s in CANONICAL_SPINE_STAGE_ORDER]

        if a_dir is not None:
            a_dir.mkdir(parents=True, exist_ok=True)
            draft_dict = {
                "draft_id": draft.draft_id,
                "status": verdict.status,
                "is_valid": verdict.passed,
                "sealed": verdict.passed,
                "x3_disposition": exit_decision.x3_disposition.value,
                "violations": verdict.violations,
                "failure_reasons": verdict.failure_reasons,
                "channel": draft.channel.value,
                "audience_persona": persona.value,
                "subject": draft.subject,
                "body": draft.body if verdict.passed else "",
                "signature_block": draft.signature_block if verdict.passed else "",
                "character_count": draft.character_count,
                "grounded_facts_used": draft.grounded_facts_used,
                "research_metadata": draft.research_metadata,
            }
            (a_dir / "outreach_draft.json").write_text(json.dumps(draft_dict, indent=2) + "\n", encoding="utf-8")

            draft_md_file = a_dir / "outreach_draft.md"
            if verdict.passed:
                draft_body_full = f"{draft.body}\n\n{draft.signature_block}" if draft.signature_block else draft.body
                draft_md_file.write_text(
                    f"# Outreach Draft: {draft.channel.value.upper()}\n\n"
                    f"**Subject**: {draft.subject}\n\n"
                    f"```text\n{draft_body_full}\n```\n",
                    encoding="utf-8",
                )
            elif draft_md_file.is_file():
                draft_md_file.unlink()

            val_dict = {
                "status": verdict.status,
                "is_valid": verdict.passed,
                "hard_gate_passed": verdict.hard_gate_passed,
                "judge_passed": verdict.judge_passed,
                "violations": verdict.violations,
                "warnings": verdict.warnings,
                "failure_reasons": verdict.failure_reasons,
                "scores": verdict.scores,
            }
            (a_dir / "validation_report.json").write_text(json.dumps(val_dict, indent=2) + "\n", encoding="utf-8")

            manifest = {
                "run_id": getattr(opp, "opportunity_id", "opp_01"),
                "candidate": {
                    "candidate_id": candidate.candidate_id,
                    "full_name": candidate.full_name,
                    "target_title": candidate.target_title,
                    "current_title": candidate.current_title,
                    "executive_summary": candidate.executive_summary,
                    "key_competencies": list(candidate.key_competencies),
                    "linkedin_url": candidate.linkedin_url,
                    "phone": candidate.phone,
                    "verified_facts": [
                        {
                            "fact_id": f.fact_id,
                            "category": f.category,
                            "statement": f.statement,
                            "metric": f.metric,
                            "source_reference": getattr(f, "source_reference", None),
                        }
                        for f in candidate.verified_facts
                    ],
                },
                "opportunity": {
                    "opportunity_id": opp.opportunity_id,
                    "company_name": opp.company_name,
                    "role_title": opp.role_title,
                    "industry": opp.industry,
                    "recipient_name": opp.recipient_name,
                    "recipient_title": opp.recipient_title,
                    "recipient_class": opp.recipient_class.value if hasattr(opp.recipient_class, "value") else str(opp.recipient_class),
                    "relationship_distance": opp.relationship_distance.value if hasattr(opp.relationship_distance, "value") else str(opp.relationship_distance),
                    "strategic_priorities": list(opp.strategic_priorities),
                    "briefing_text": opp.briefing_text,
                    "research_digest": opp.research_digest,
                    "evidence_items": list(opp.evidence_items),
                    "sealed_resolution": opp.sealed_resolution,
                },
                "channel": channel.value if hasattr(channel, "value") else str(channel),
                "audience_persona": persona.value if hasattr(persona, "value") else str(persona),
                "grounded_facts_used": list(draft.grounded_facts_used),
                "artifact_dir": str(a_dir.resolve()),
                "completed_stages": (
                    ["briefing_resolution", "draft_generation", "authoritative_evaluation"]
                    if verdict.passed
                    else ["briefing_resolution", "draft_generation"]
                ),
            }
            (a_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            execute_canonical_10_stage_spine(
                a_dir,
                run_id=draft.draft_id,
                mission_id=opp.opportunity_id,
                x2_passed=bool(verdict.hard_gate_passed),
                quorum_passed=bool(verdict.passed),
                pct_certificates_count=len(draft.grounded_facts_used),
            )

        return draft, verdict

    def resume_or_patch_run(self, run_dir: Path | str) -> dict[str, Any]:
        """Rebind saved run_manifest.json paths to run_dir and reuse passing stage checkpoints."""
        r_dir = Path(run_dir).resolve()
        manifest_path = r_dir / "run_manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Missing run_manifest.json in {r_dir}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifact_dir"] = str(r_dir)
        reused_stages: list[str] = list(manifest.get("completed_stages", []))
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return {
            "status": "RESUMED",
            "run_dir": str(r_dir),
            "reused_stages": reused_stages,
        }

    def validate_draft(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: Optional[TargetOpportunity] = None,
    ) -> ValidationResult:
        """Runs all 10 validation gates over the draft."""
        violations: List[str] = []
        warnings: List[str] = []

        spam_valid, spam_viol, spam_warn = self.spam_validator.validate(draft.body)
        violations.extend(spam_viol)
        warnings.extend(spam_warn)

        len_valid, len_err = self.length_validator.validate(draft.channel, draft.body)
        if not len_valid and len_err:
            violations.append(len_err)

        q_valid, q_err = self.question_validator.validate(draft.body)
        if not q_valid and q_err:
            violations.append(q_err)

        allowed_facts = {
            f.fact_id
            for f in candidate.verified_facts
            if getattr(f, "has_provenance", False) or bool(getattr(f, "source_reference", None) and str(getattr(f, "source_reference")).strip())
        }
        opp_context = ""
        if opportunity:
            opp_context = f"{' '.join(opportunity.strategic_priorities)} {opportunity.briefing_text} {opportunity.company_name}"
        g_valid, g_viol = self.grounding_validator.validate(
            draft.grounded_facts_used,
            allowed_facts,
            body=draft.body,
            candidate_facts=candidate.verified_facts,
            opportunity_context=opp_context,
        )
        violations.extend(g_viol)

        dash_valid, dash_err = self.em_dash_validator.validate(draft.body)
        if not dash_valid and dash_err:
            violations.append(dash_err)

        link_valid, link_err = self.md_link_validator.validate(draft.body)
        if not link_valid and link_err:
            violations.append(link_err)

        tone_valid, tone_viols = self.tone_validator.validate(draft.body)
        violations.extend(tone_viols)

        fc_valid, fc_viols = self.forbidden_validator.validate(
            draft.body, candidate.verified_facts, opportunity_context=opp_context
        )
        violations.extend(fc_viols)

        up_valid, up_viols = self.unsupported_personalization_validator.validate(
            draft.body, opportunity
        )
        violations.extend(up_viols)

        priv_valid, priv_viols = self.privacy_validator.validate(draft.body)
        violations.extend(priv_viols)

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
                "forbidden_claims_score": 1.0 if fc_valid else 0.0,
                "privacy_score": 1.0 if priv_valid else 0.0,
                "unsupported_personalization_score": 1.0 if up_valid else 0.0,
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
        """Evaluates draft against the canonical rubric judges."""
        report = self.judge.evaluate(draft, candidate, opportunity)
        if artifact_dir is not None:
            a_dir = Path(artifact_dir)
            a_dir.mkdir(parents=True, exist_ok=True)
            (a_dir / "evaluation_report.json").write_text(
                json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8"
            )
        return report

    def evaluate_authoritative_draft(
        self,
        draft: OutreachMessageDraft,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        *,
        artifact_dir: Path | str | None = None,
    ) -> AuthoritativeVerdict:
        """Evaluates draft with single-pass consolidated authoritative verdict plus optional IDE CLI Judge v3."""
        from dataclasses import replace as dc_replace
        from apps_lic.judges.ide_cli_judge import resolve_lic_judge_transport

        verdict = self.judge.evaluate_authoritative(draft, candidate, opportunity)
        ide_cli_payload: dict[str, Any] | None = None
        if verdict.hard_gate_passed and not self.offline_smoke and resolve_lic_judge_transport() == "ide_cli":
            ide_cli_payload = dict(self.judge.evaluate_ide_cli(draft, candidate, opportunity))
            draft.metadata["ide_cli_judge"] = ide_cli_payload
            if not bool(ide_cli_payload.get("passed", False)):
                ide_sub = ide_cli_payload.get("ide_cli_judge") or {}
                ide_viols = list(ide_sub.get("violations") or ()) if isinstance(ide_sub, dict) else []
                verdict = dc_replace(
                    verdict,
                    passed=False,
                    judge_passed=False,
                    status="BLOCKED",
                    violations=[*verdict.violations, *ide_viols],
                    failure_reasons=[*verdict.failure_reasons, "IDE_CLI_JUDGE_V3_FAILED"],
                )
        if artifact_dir is not None:
            a_dir = Path(artifact_dir)
            a_dir.mkdir(parents=True, exist_ok=True)
            report_dict = self.judge.report_from_verdict(verdict).to_dict()
            if ide_cli_payload is not None:
                report_dict["ide_cli_judge"] = ide_cli_payload
            (a_dir / "evaluation_report.json").write_text(
                json.dumps(report_dict, indent=2) + "\n",
                encoding="utf-8",
            )
        return verdict


__all__ = ["OutreachDraftAndValidationBase"]
