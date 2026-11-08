"""Non-mock Wave 2 tests for OutreachOrchestrator, canonical dispatch, and MissionLoader."""

from __future__ import annotations

from pathlib import Path

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateFact,
    CandidateProfile,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.pipeline.mission_loader import MissionLoader
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.runtime.dispatch.canonical_dispatch import run_canonical_apps_lic_spine


def test_orchestrator_board_member_connection_note_auto_upgrades_to_inmail(tmp_path: Path) -> None:
    """Defect 4 (HITL outreach-board-channel-02): Board Member + connection_note auto-upgrades to InMail."""
    orchestrator = OutreachOrchestrator()
    candidate = CandidateProfile(
        candidate_id="cand_board",
        full_name="Jordan Reed",
        target_title="Chief AI & Platform Officer",
        current_title="VP of AI Platform",
        executive_summary="Enterprise AI platform leader.",
        key_competencies=["AI Governance", "Cloud Scale"],
        verified_facts=[
            CandidateFact(
                fact_id="f_board_01",
                category="scale",
                statement="scaled distributed enterprise platform processing $4.2B annual volume with 99.995% reliability",
                metric="$4.2B / 99.995%",
                source_reference="canonical_profile",
            )
        ],
    )
    opp = TargetOpportunity(
        opportunity_id="opp_board_01",
        company_name="Truist",
        role_title="Chief AI Officer",
        industry="Banking & Financial Services",
        recipient_name="Evelyn Sterling",
        recipient_title="Chair of the Technology & Risk Committee, Board of Directors",
        recipient_class=RecipientClass.BOARD_MEMBER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["Enterprise AI risk governance and core banking platform resilience"],
    )

    draft, verdict = orchestrator.generate_single_draft(
        candidate,
        opp,
        ChannelType.LINKEDIN_CONNECTION,
        auto_research=False,
        artifact_dir=tmp_path / "board_run",
    )

    assert draft.channel == ChannelType.LINKEDIN_INMAIL
    assert draft.research_metadata.get("channel_upgraded_from") == "connection_note"
    assert verdict.passed is True
    assert verdict.lens_scores["lens1_altitude"] >= 0.70


def test_canonical_dispatch_preserves_board_member_distance_priorities_and_persona(tmp_path: Path) -> None:
    """Defect 5: run_canonical_apps_lic_spine preserves board_member, relationship_distance, priorities, and persona."""
    raw_ingress = {
        "company": "Truist",
        "target_role": "Chief Technology Officer",
        "industry": "Banking & Financial Services",
        "recipient_class": "board_member",
        "relationship_distance": "warm_referral",
        "channel": "connection_note",
        "audience_persona": "executive_contact",
        "strategic_priorities": [
            "Accelerate enterprise AI governance and multi-cloud core banking resilience"
        ],
        "lead_profile": {
            "name": "Arthur Pendelton",
            "title": "Board Director",
        },
    }

    res = run_canonical_apps_lic_spine(raw_ingress, tmp_path / "spine_board")
    assert res["is_valid"] is True
    assert res["x3_code"] == "X3D_ALLOW_FINISH"
    assert "shared network" in res["message"]


def test_orchestrator_follow_up_single_draft_passes_all_lenses(
    sample_candidate: CandidateProfile,
    sample_opportunity: TargetOpportunity,
) -> None:
    """Defect 7: Single-draft ChannelType.FOLLOW_UP passes Lens 2 and Lens 3 with and without priorities."""
    from dataclasses import replace

    orchestrator = OutreachOrchestrator()

    draft1, verdict1 = orchestrator.generate_single_draft(
        sample_candidate,
        sample_opportunity,
        ChannelType.FOLLOW_UP,
        auto_research=False,
    )
    assert verdict1.passed is True
    assert len(draft1.body) <= 800
    assert verdict1.lens_scores["lens2_grounding"] >= 0.99
    assert verdict1.lens_scores["lens3_resonance"] >= 0.70

    opp_no_prio = replace(sample_opportunity, strategic_priorities=[])
    draft2, verdict2 = orchestrator.generate_single_draft(
        sample_candidate,
        opp_no_prio,
        ChannelType.FOLLOW_UP,
        auto_research=True,
    )
    assert verdict2.passed is True
    assert len(draft2.body) <= 800
    assert verdict2.lens_scores["lens2_grounding"] >= 0.99
    assert verdict2.lens_scores["lens3_resonance"] >= 0.70


def test_mission_loader_load_from_dict_honors_custom_facts_recipient_class_and_distance() -> None:
    """Defect 8: MissionLoader.load_from_dict parses caller-supplied verified_facts, recipient_class, and relationship_distance."""
    payload = {
        "sender_profile": {
            "name": "Elena Rostova",
            "title": "SVP of Distributed Systems",
            "current_title": "VP of Core Infrastructure",
            "background": "Distributed systems executive.",
            "verified_facts": [
                {
                    "fact_id": "custom_fact_99",
                    "category": "reliability",
                    "statement": "architected global settlement engine processing $12B daily volume with 99.999% uptime",
                    "metric": "$12B / 99.999%",
                    "source_reference": "custom_audit_2026",
                }
            ],
        },
        "recipient_profile": {
            "name": "Marcus Vance",
            "title": "Board Member, Audit & Technology Committee",
            "company": "Citigroup",
            "recipient_class": "board_member",
            "relationship_distance": "warm_referral",
        },
        "job_description": {
            "title": "SVP of Distributed Systems",
            "company": "Citigroup",
            "responsibilities": ["Modernize cross-border institutional settlement platforms"],
        },
    }

    cand, opp = MissionLoader.load_from_dict(payload, default_id="custom_01")
    assert len(cand.verified_facts) == 1
    assert cand.verified_facts[0].fact_id == "custom_fact_99"
    assert "$12B" in cand.verified_facts[0].statement
    assert opp.recipient_class == RecipientClass.BOARD_MEMBER
    assert opp.relationship_distance == RelationshipDistance.WARM_REFERRAL
    assert opp.company_name == "Citigroup"
