"""CLI entrypoint for apps_lic_v2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
    ChannelType,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)
from apps_lic.pipeline.orchestrator import OutreachOrchestrator


def load_mission_from_file(brief_path: Path) -> tuple[CandidateProfile, TargetOpportunity]:
    """Loads candidate and target opportunity from a JSON mission fixture."""
    with open(brief_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle charles_truist_mission.json structure
    if "sender_profile" in data and "recipient_profile" in data:
        sp = data["sender_profile"]
        rp = data["recipient_profile"]
        jd = data.get("job_description", {})

        candidate = CandidateProfile(
            candidate_id="cand_amit",
            full_name=sp.get("name", "Amit Ayer"),
            target_title=sp.get("title", "AI/ML Engineering Leader"),
            executive_summary=sp.get("background", "Enterprise AI systems architect."),
            verified_facts=[
                CandidateFact(
                    fact_id="fact_01",
                    category="architecture",
                    statement="architected layered agentic systems (L0 routing through L6 observability) with AST dependency governance",
                ),
                CandidateFact(
                    fact_id="fact_02",
                    category="delivery",
                    statement="delivered multi-MCP enterprise agentic tooling for frontline banking care operations",
                ),
            ],
            key_competencies=["Agentic AI", "Enterprise Architecture", "LLM Guardrails", "HITL Systems"],
        )

        opportunity = TargetOpportunity(
            opportunity_id="opp_truist_mission",
            company_name=rp.get("company", jd.get("company", "Truist")),
            role_title=jd.get("title", "Head of Enterprise Agentic Strategy"),
            industry="Banking & Financial Services",
            recipient_name=rp.get("name", "Charles Morris"),
            recipient_title=rp.get("title", "SVP, Agentic Enterprise Strategy"),
            recipient_class=RecipientClass.EXECUTIVE_PEER,
            relationship_distance=RelationshipDistance.COLD,
            strategic_priorities=[
                jd.get("summary", "Care Center frontline adoption and reusable agentic primitives"),
            ],
        )
        return candidate, opportunity

    # Handle truist_pascal_brief.json structure
    if "recipient_company" in data:
        candidate = CandidateProfile(
            candidate_id="cand_001",
            full_name="Alex Mercer",
            target_title=data.get("target_role", "VP of Engineering"),
            executive_summary="Senior enterprise technology executive.",
            verified_facts=[
                CandidateFact(
                    fact_id="fact_01",
                    category="scale",
                    statement="scaled enterprise core platform processing high-volume financial transactions",
                )
            ],
        )
        opportunity = TargetOpportunity(
            opportunity_id="opp_pascal",
            company_name=data.get("recipient_company", "Truist"),
            role_title=data.get("target_role", "Engineering Leader"),
            industry="Financial Services",
            recipient_name=data.get("recipient_name", "Pascal"),
            recipient_title=data.get("recipient_title", "Head of Enterprise Engineering"),
            recipient_class=RecipientClass.HIRING_MANAGER,
            relationship_distance=RelationshipDistance.COLD,
            strategic_priorities=["Core platform modernization"],
        )
        return candidate, opportunity

    raise ValueError(f"Unrecognized brief structure in {brief_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="apps_lic_v2: Standalone Outreach Generator")
    parser.add_argument("--brief", help="Path to opportunity brief / mission JSON fixture")
    parser.add_argument(
        "--channel",
        choices=["inmail", "connection_note", "email", "follow_up"],
        default="inmail",
        help="Target channel for outreach draft",
    )
    args = parser.parse_args()

    print("[apps_lic_v2] Starting Standalone Outreach Generator...")

    if args.brief:
        brief_file = Path(args.brief)
        if not brief_file.is_file():
            # Try resolving relative to package repo root
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            brief_file = repo_root / args.brief
        if not brief_file.is_file():
            print(f"Error: Brief file not found: {args.brief}", file=sys.stderr)
            return 1
        print(f"[apps_lic_v2] Ingesting mission brief from {brief_file.name}...")
        candidate, opportunity = load_mission_from_file(brief_file)
    else:
        # Default sample profile
        candidate = CandidateProfile(
            candidate_id="cand_001",
            full_name="Alex Mercer",
            target_title="VP of Enterprise Engineering",
            executive_summary="Executive technology leader specializing in modern distributed systems and enterprise modernization.",
            verified_facts=[
                CandidateFact(
                    fact_id="fact_01",
                    category="scale",
                    statement="scaled distributed platform processing $4.2B annual volume at 99.995% reliability",
                    metric="$4.2B",
                ),
                CandidateFact(
                    fact_id="fact_02",
                    category="efficiency",
                    statement="reduced infrastructure operating expenditures by 38% via cloud governance",
                    metric="38%",
                ),
            ],
        )
        opportunity = TargetOpportunity(
            opportunity_id="opp_truist_01",
            company_name="Truist Enterprise Technology",
            role_title="Head of Engineering, Core Platforms",
            industry="Financial Services & Banking",
            recipient_name="Sarah Jenkins",
            recipient_title="Senior Director of Talent Acquisition",
            recipient_class=RecipientClass.TALENT_PARTNER,
            strategic_priorities=["cloud modern banking core", "zero-downtime reliability"],
        )

    channel = ChannelType(args.channel)
    orchestrator = OutreachOrchestrator()
    
    draft, val = orchestrator.generate_single_draft(candidate, opportunity, channel)
    
    print("\n" + "=" * 60)
    print(f"OUTREACH DRAFT ({channel.value.upper()}):")
    print("=" * 60)
    print(f"Subject: {draft.subject}")
    print("-" * 60)
    print(draft.body)
    print("=" * 60)
    print(f"Template Used: {draft.metadata.get('context_keys', ['default'])[0]}")
    print(f"Character Count: {draft.character_count}")
    print(f"Validation Status: {'PASSED' if val.is_valid else 'FAILED'}")
    if val.violations:
        print(f"Violations: {val.violations}")
    if val.warnings:
        print(f"Warnings: {val.warnings}")
    print("=" * 60)

    # Campaign sequence
    sequence = orchestrator.generate_full_campaign(candidate, opportunity, channel)
    print(f"\nGenerated Multi-Touch Campaign with {len(sequence.touches)} planned touches:")
    for t in sequence.touches:
        print(f"  - Touch {t.touch_number} (Day {t.day_offset}) via {t.channel.value}: {t.objective}")

    return 0 if val.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
