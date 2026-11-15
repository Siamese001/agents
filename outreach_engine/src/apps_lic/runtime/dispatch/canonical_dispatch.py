"""Canonical dispatch layer wiring ingress arguments to the modular OutreachOrchestrator.

Unifies execution onto the canonical 10-stage spine (`U0..X3`) under
`INV-SINGLE-CANONICAL-PIPELINE` and `INV-LIC-REAL-LLM-FOR-FINISH`.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from apps_lic.domain.models import (
    AudiencePersona,
    AuthoritativeVerdict,
    CandidateProfileLoader,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.runtime.run_bundle_index import write_canonical_spine_bundle
from apps_lic.runtime.spine_contracts import (
    ExecutionMode,
    SpineStageId,
    SpineStageStatus,
)
from apps_lic.runtime.stage_ledger import OutreachStageLedgerBuilder
from apps_lic.runtime.whole_run_exit import evaluate_whole_run_exit


def build_cli_ingress_raw(**kwargs: Any) -> dict[str, Any]:
    """Capture and standardize raw CLI/adapter ingress parameters."""
    return dict(kwargs)


def run_canonical_apps_lic_spine(
    raw_ingress: dict[str, Any],
    artifact_dir: Path | str,
) -> dict[str, Any]:
    """Execute canonical 10-stage outreach pipeline (`U0..X3`) through OutreachOrchestrator."""
    t0 = time.perf_counter()
    try:
        artifact_path = Path(artifact_dir)
        artifact_path.mkdir(parents=True, exist_ok=True)
        orchestrator = OutreachOrchestrator()

        lead = (
            raw_ingress.get("lead_profile")
            if isinstance(raw_ingress.get("lead_profile"), dict)
            else {}
        )
        rc_str = str(
            raw_ingress.get("recipient_class") or lead.get("recipient_class") or "recruiter"
        ).lower()
        if "board" in rc_str:
            recipient_class = RecipientClass.BOARD_MEMBER
        elif "recruiter" in rc_str or "talent" in rc_str:
            recipient_class = RecipientClass.TALENT_PARTNER
        elif "executive" in rc_str or "peer" in rc_str:
            recipient_class = RecipientClass.EXECUTIVE_PEER
        else:
            recipient_class = RecipientClass.HIRING_MANAGER

        rd_str = str(
            raw_ingress.get("relationship_distance")
            or lead.get("relationship_distance")
            or "cold"
        ).lower()
        if "warm" in rd_str or "referral" in rd_str:
            rel_dist = RelationshipDistance.WARM_REFERRAL
        elif "former" in rd_str or "colleague" in rd_str:
            rel_dist = RelationshipDistance.FORMER_COLLEAGUE
        elif "second" in rd_str:
            rel_dist = RelationshipDistance.SECOND_DEGREE
        else:
            rel_dist = RelationshipDistance.COLD

        ch_str = str(raw_ingress.get("channel") or "inmail").lower()
        if "connect" in ch_str:
            channel = ChannelType.LINKEDIN_CONNECTION
        elif "follow" in ch_str:
            channel = ChannelType.FOLLOW_UP
        elif "email" in ch_str:
            channel = ChannelType.EMAIL
        else:
            channel = ChannelType.LINKEDIN_INMAIL

        effective_role = str(
            raw_ingress.get("target_role")
            or raw_ingress.get("role_title")
            or raw_ingress.get("role")
            or lead.get("role_context")
            or "Engineering Leader"
        )

        raw_priorities = (
            raw_ingress.get("strategic_priorities")
            or lead.get("strategic_priorities")
            or []
        )
        priorities = (
            [str(p).strip() for p in raw_priorities if str(p).strip()]
            if isinstance(raw_priorities, (list, tuple))
            else []
        )

        persona: AudiencePersona | None = None
        ap_raw = raw_ingress.get("audience_persona")
        if isinstance(ap_raw, AudiencePersona):
            persona = ap_raw
        elif isinstance(ap_raw, str) and ap_raw.strip():
            ap_lower = ap_raw.strip().lower()
            if "recruiter" in ap_lower:
                persona = AudiencePersona.EXECUTIVE_RECRUITER
            elif "contact" in ap_lower or "executive" in ap_lower:
                persona = AudiencePersona.EXECUTIVE_CONTACT

        candidate = CandidateProfileLoader.load_default(
            overrides={
                "candidate_id": str(raw_ingress.get("candidate_id") or "cand_live"),
                "target_title": effective_role,
            }
        )
        opportunity = TargetOpportunity(
            opportunity_id=str(raw_ingress.get("opportunity_id") or "opp_live"),
            company_name=str(raw_ingress.get("company") or "Target Company"),
            role_title=effective_role,
            industry=str(raw_ingress.get("industry") or "Enterprise Technology"),
            recipient_name=str(
                lead.get("name") or raw_ingress.get("recipient_name") or "Jordan"
            ),
            recipient_title=str(
                lead.get("title")
                or raw_ingress.get("recipient_title")
                or "Talent Partner"
            ),
            recipient_class=recipient_class,
            relationship_distance=rel_dist,
            strategic_priorities=priorities,
            briefing_text=str(
                raw_ingress.get("manual_brief") or raw_ingress.get("briefing_text") or ""
            ),
        )

        draft, val = orchestrator.generate_single_draft(
            candidate,
            opportunity,
            channel,
            audience_persona=persona,
            artifact_dir=artifact_path,
        )

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        raw_passed = getattr(val, "passed", None)
        if isinstance(val, AuthoritativeVerdict):
            passed = bool(val.passed) and bool(val.hard_gate_passed)
        elif isinstance(raw_passed, bool):
            passed = raw_passed and bool(getattr(val, "hard_gate_passed", True))
        else:
            passed = False

        hard_gate_ok = bool(getattr(val, "hard_gate_passed", False)) and passed
        offline_smoke = bool(raw_ingress.get("offline_smoke", False))
        exec_mode_raw = raw_ingress.get(
            "execution_mode",
            ExecutionMode.OFFLINE_SMOKE.value
            if offline_smoke
            else ExecutionMode.REAL_LLM.value,
        )
        used_fallback = bool(raw_ingress.get("used_fallback", False))
        drafter_family = raw_ingress.get("drafter_family")
        model_id = raw_ingress.get("model_id")
        provider_id = raw_ingress.get("provider_id")

        run_id = str(raw_ingress.get("run_id") or getattr(draft, "draft_id", "run_live"))
        mission_id = str(opportunity.opportunity_id or "opp_live")

        exit_decision = evaluate_whole_run_exit(
            run_id=run_id,
            mission_id=mission_id,
            execution_mode=exec_mode_raw,
            x2_passed=hard_gate_ok,
            quorum_passed=passed,
            used_fallback=used_fallback,
            drafter_family=str(drafter_family) if drafter_family else None,
            provider_id=str(provider_id) if provider_id else None,
            model_id=str(model_id) if model_id else None,
            pct_certificates_count=len(getattr(draft, "grounded_facts_used", []) or []),
            offline_smoke=offline_smoke,
        )

        ledger_builder = OutreachStageLedgerBuilder(
            run_id=run_id,
            mission_id=mission_id,
            execution_mode=exit_decision.execution_mode,
        )
        ledger_builder.record_remaining_canonical_stages(
            stage_statuses={
                SpineStageId.X2.value: (
                    SpineStageStatus.PASS if hard_gate_ok else SpineStageStatus.FAIL
                ),
                SpineStageId.X1D.value: (
                    SpineStageStatus.PASS if passed else SpineStageStatus.FAIL
                ),
                SpineStageId.X3.value: (
                    SpineStageStatus.PASS
                    if exit_decision.allow_finish
                    else SpineStageStatus.BLOCKED
                ),
            }
        )
        bundle = write_canonical_spine_bundle(
            artifact_path,
            ledger_builder=ledger_builder,
            exit_decision=exit_decision,
        )

        raw_violations = (
            list(getattr(val, "violations", []))
            if getattr(val, "violations", None)
            else []
        )
        raw_failure_reasons = (
            list(getattr(val, "failure_reasons", []))
            if getattr(val, "failure_reasons", None)
            else []
        )
        if not raw_failure_reasons and not passed:
            raw_failure_reasons = (
                list(getattr(val, "feedback", []))
                if getattr(val, "feedback", None)
                else ["Authoritative rubric judge failure"]
            )

        if passed:
            rationale = "Pipeline completed with valid grounding"
            compliance_notes = "All hard validation gates verified"
        elif not bool(getattr(val, "hard_gate_passed", True)):
            violation_summary = (
                "; ".join(raw_violations)
                if raw_violations
                else "Unknown validation violation"
            )
            rationale = f"Pipeline blocked by validation gates: {violation_summary}"
            compliance_notes = f"Hard validation gates failed: {violation_summary}"
        else:
            judge_summary = "; ".join(raw_failure_reasons)
            rationale = f"Pipeline blocked by judge gates: {judge_summary}"
            compliance_notes = f"Authoritative judge gates failed: {judge_summary}"

        allow_finish = bool(passed and exit_decision.allow_finish)
        return {
            "x3_code": "X3D_ALLOW_FINISH" if allow_finish else "X3D_BLOCK",
            "x3_disposition": exit_decision.x3_disposition.value,
            "execution_mode": exit_decision.execution_mode.value,
            "message": draft.body if allow_finish else "",
            "rationale": rationale,
            "compliance_notes": compliance_notes,
            "draft_id": draft.draft_id,
            "is_valid": allow_finish,
            "violations": raw_violations,
            "failure_reasons": raw_failure_reasons,
            "latency_ms": latency_ms,
            "stage_ledger_path": bundle.stage_ledger_path,
            "terminal_manifest_path": bundle.terminal_manifest_path,
            "completion_receipt_path": bundle.completion_receipt_path,
            "bundle_index_path": bundle.bundle_index_path,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "x3_code": "X3D_BLOCK",
            "x3_disposition": "X3E_SAFE_ABSTAIN",
            "execution_mode": "REAL_LLM",
            "message": "",
            "rationale": f"Pipeline exception: {type(exc).__name__}: {exc}",
            "compliance_notes": f"Pipeline execution failed: {exc}",
            "draft_id": "",
            "is_valid": False,
            "violations": [f"{type(exc).__name__}: {exc}"],
            "failure_reasons": [f"{type(exc).__name__}: {exc}"],
            "latency_ms": latency_ms,
        }


__all__ = ["build_cli_ingress_raw", "run_canonical_apps_lic_spine"]
