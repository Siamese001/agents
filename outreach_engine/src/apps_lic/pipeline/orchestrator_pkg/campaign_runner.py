"""Campaign sequence generation and continuity gating for OutreachOrchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateProfile,
    ChannelType,
    TargetOpportunity,
    TouchSequence,
)
from apps_lic.pipeline.orchestrator_pkg.draft_and_validation import OutreachDraftAndValidationBase
from apps_lic.runtime.final_outreach_outputs import export_final_outreach_bundle
from apps_lic.runtime.run_bundle_index import execute_canonical_10_stage_spine
from apps_lic.runtime.spine_contracts import CANONICAL_SPINE_STAGE_ORDER
from apps_lic.runtime.whole_run_exit import evaluate_whole_run_exit


class OutreachOrchestrator(OutreachDraftAndValidationBase):
    """Bounded, decoupled orchestrator executing the canonical 10-stage outreach pipeline."""

    def generate_full_campaign(
        self,
        candidate: CandidateProfile,
        opportunity: TargetOpportunity,
        primary_channel: ChannelType = ChannelType.LINKEDIN_INMAIL,
        *,
        channel: ChannelType | None = None,
        audience_persona: Optional[AudiencePersona] = None,
        auto_research: bool = True,
        research_bridge: Any | None = None,
        job_description_text: str = "",
        artifact_dir: Path | str | None = None,
        trace_id: str = "",
        force_fresh: bool = False,
    ) -> TouchSequence:
        """Generates a complete validated multi-touch sequence with governed briefing."""
        effective_channel = channel if channel is not None else primary_channel
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
        sequence = self.sequence_planner.plan_sequence(
            candidate,
            opp,
            effective_channel,
            audience_persona=audience_persona,
        )
        sequence.sealed_resolution = opp.sealed_resolution

        t1_passed = bool(sequence.touches and sequence.touches[0].draft.metadata.get("passed", False))
        successful_touches = []
        blocked_touches = []

        if not t1_passed and sequence.touches:
            for idx, t in enumerate(sequence.touches):
                ch_v = t.channel.value if hasattr(t.channel, "value") else str(t.channel)
                if idx == 0:
                    reasons = t.draft.metadata.get("failure_reasons", [])
                    violations = t.draft.metadata.get("validation_violations", [])
                else:
                    reasons = ["Sequential touch continuity failure: Touch 1 was blocked"]
                    violations = ["touch_1_dependency_blocked"]
                blocked_touches.append({
                    "touch_number": t.touch_number,
                    "day_offset": t.day_offset,
                    "channel": ch_v,
                    "objective": t.objective,
                    "status": "BLOCKED",
                    "failure_reasons": list(reasons),
                    "violations": list(violations),
                })
        else:
            for t in sequence.touches:
                ch_v = t.channel.value if hasattr(t.channel, "value") else str(t.channel)
                if t.draft.metadata.get("passed", False):
                    successful_touches.append(t)
                else:
                    blocked_touches.append({
                        "touch_number": t.touch_number,
                        "day_offset": t.day_offset,
                        "channel": ch_v,
                        "objective": t.objective,
                        "status": "BLOCKED",
                        "failure_reasons": list(t.draft.metadata.get("failure_reasons", [])),
                        "violations": list(t.draft.metadata.get("validation_violations", [])),
                    })

        campaign_status = "PASSED" if (len(sequence.touches) > 0 and len(blocked_touches) == 0) else "BLOCKED"
        sequence.status = campaign_status
        sequence.blocked_touches = blocked_touches

        all_passed = (
            len(sequence.touches) > 0
            and len(blocked_touches) == 0
            and all(bool(t.draft.metadata.get("passed", True)) for t in sequence.touches)
        )
        exit_decision = evaluate_whole_run_exit(
            run_id=sequence.sequence_id,
            mission_id=opp.opportunity_id,
            x2_passed=all_passed,
            quorum_passed=all_passed,
            pct_certificates_count=len(candidate.verified_facts),
        )
        sequence.metadata["x3_disposition"] = exit_decision.x3_disposition.value
        sequence.metadata["canonical_spine_stages"] = [s.value for s in CANONICAL_SPINE_STAGE_ORDER]

        if a_dir is not None:
            a_dir.mkdir(parents=True, exist_ok=True)
            seq_dict = {
                "sequence_id": sequence.sequence_id,
                "status": campaign_status,
                "x3_disposition": exit_decision.x3_disposition.value,
                "candidate_id": sequence.candidate_id,
                "opportunity_id": sequence.opportunity_id,
                "all_passed": all_passed,
                "sealed": all_passed,
                "touch_count": len(successful_touches),
                "total_planned_touches": len(sequence.touches),
                "touches": [
                    {
                        "touch_number": t.touch_number,
                        "day_offset": t.day_offset,
                        "channel": t.channel.value if hasattr(t.channel, "value") else str(t.channel),
                        "objective": t.objective,
                        "subject": t.draft.subject,
                        "body": t.draft.body,
                        "status": "PASSED",
                        "passed": True,
                        "validation_violations": list(t.draft.metadata.get("validation_violations", [])),
                    }
                    for t in successful_touches
                ],
                "blocked_touches": blocked_touches,
            }
            (a_dir / "campaign_sequence.json").write_text(
                json.dumps(seq_dict, indent=2) + "\n", encoding="utf-8"
            )
            export_bundle = export_final_outreach_bundle(
                a_dir,
                sequence=sequence,
                x3_disposition=exit_decision.x3_disposition.value,
                run_id=sequence.sequence_id,
                mission_id=opp.opportunity_id,
                candidate_name=candidate.full_name or "Amit Ayer",
                candidate_title=candidate.target_title or "Enterprise AI & Platform Executive",
                target_company=opp.company_name or "Citi",
                target_role=opp.role_title or "Head of AI Strategy",
                recipient_name=opp.recipient_name or "Executive Stakeholder",
            )
            sequence.metadata["export_bundle"] = export_bundle.to_dict()
            execute_canonical_10_stage_spine(
                a_dir,
                run_id=sequence.sequence_id,
                mission_id=opp.opportunity_id,
                x2_passed=all_passed,
                quorum_passed=all_passed,
                pct_certificates_count=len(candidate.verified_facts),
            )

        return sequence


__all__ = ["OutreachOrchestrator"]
