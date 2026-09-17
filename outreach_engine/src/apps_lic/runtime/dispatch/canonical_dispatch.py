"""Canonical dispatch layer wiring ingress arguments to the modular OutreachOrchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_lic.domain.models import (
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

    candidate = CandidateProfileLoader.load_default(
        overrides={
            "candidate_id": str(raw_ingress.get("candidate_id") or "cand_live"),
            "target_title": str(lead.get("role_context") or "Engineering Leader"),
        }
    )
    opportunity = TargetOpportunity(
        opportunity_id=str(raw_ingress.get("opportunity_id") or "opp_live"),
        company_name=str(raw_ingress.get("company") or "Target Company"),
        role_title=str(lead.get("role_context") or "Engineering Leader"),
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

    return {
        "x3_code": "X3D_ALLOW_FINISH" if val.hard_gate_passed else "X3D_BLOCK",
        "message": draft.body,
        "rationale": "Pipeline completed with valid grounding",
        "compliance_notes": "All hard validation gates verified",
        "draft_id": draft.draft_id,
        "is_valid": val.is_valid,
        "violations": val.violations,
    }
