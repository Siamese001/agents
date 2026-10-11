"""Canonical dispatch layer wiring ingress arguments to the modular OutreachOrchestrator."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from apps_lic.domain.models import (
    AuthoritativeVerdict,
    CandidateProfile,
    CandidateProfileLoader,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.pipeline.orchestrator import OutreachOrchestrator


def build_cli_ingress_raw(**kwargs: Any) -> dict[str, Any]:
    """Capture and standardize raw CLI/adapter ingress parameters."""
    return dict(kwargs)


def run_canonical_apps_lic_spine(
    raw_ingress: dict[str, Any],
    artifact_dir: Path,
) -> dict[str, Any]:
    """Execute canonical outreach pipeline through OutreachOrchestrator."""
    t0 = time.perf_counter()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    orchestrator = OutreachOrchestrator()

    lead = raw_ingress.get("lead_profile") or {}
    rc_str = str(raw_ingress.get("recipient_class") or "recruiter").lower()
    if "recruiter" in rc_str or "talent" in rc_str:
        recipient_class = RecipientClass.TALENT_PARTNER
    elif "executive" in rc_str or "peer" in rc_str:
        recipient_class = RecipientClass.EXECUTIVE_PEER
    else:
        recipient_class = RecipientClass.HIRING_MANAGER

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
        recipient_name=str(lead.get("name") or "Jordan"),
        recipient_title=str(lead.get("title") or "Talent Partner"),
        recipient_class=recipient_class,
        briefing_text=str(raw_ingress.get("manual_brief") or ""),
    )

    draft, val = orchestrator.generate_single_draft(
        candidate,
        opportunity,
        channel,
        artifact_dir=artifact_dir,
    )

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    # AuthoritativeVerdict.passed is the exclusive authority for completion and X3 disposition.
    # Completion must NEVER be authorized through hard_gate_passed alone.
    raw_passed = getattr(val, "passed", None)
    if isinstance(val, AuthoritativeVerdict):
        passed = bool(val.passed) and bool(val.hard_gate_passed)
    elif isinstance(raw_passed, bool):
        passed = raw_passed and bool(getattr(val, "hard_gate_passed", True))
    else:
        # If val is not an AuthoritativeVerdict or does not have an explicit boolean passed,
        # never allow completion (never fallback to hard_gate_passed or is_valid alone).
        passed = False

    raw_violations = list(getattr(val, "violations", [])) if getattr(val, "violations", None) else []
    raw_failure_reasons = list(getattr(val, "failure_reasons", [])) if getattr(val, "failure_reasons", None) else []
    if not raw_failure_reasons and not passed:
        raw_failure_reasons = list(getattr(val, "feedback", [])) if getattr(val, "feedback", None) else []
        if not raw_failure_reasons:
            raw_failure_reasons = ["Authoritative rubric judge failure"]

    if passed:
        rationale = "Pipeline completed with valid grounding"
        compliance_notes = "All hard validation gates verified"
    else:
        if not bool(getattr(val, "hard_gate_passed", True)):
            violation_summary = "; ".join(raw_violations) if raw_violations else "Unknown validation violation"
            rationale = f"Pipeline blocked by validation gates: {violation_summary}"
            compliance_notes = f"Hard validation gates failed: {violation_summary}"
        else:
            judge_summary = "; ".join(raw_failure_reasons)
            rationale = f"Pipeline blocked by judge gates: {judge_summary}"
            compliance_notes = f"Authoritative judge gates failed: {judge_summary}"

    return {
        "x3_code": "X3D_ALLOW_FINISH" if passed else "X3D_BLOCK",
        "message": draft.body if passed else "",
        "rationale": rationale,
        "compliance_notes": compliance_notes,
        "draft_id": draft.draft_id,
        "is_valid": passed,
        "violations": raw_violations,
        "failure_reasons": raw_failure_reasons,
        "latency_ms": latency_ms,
    }
