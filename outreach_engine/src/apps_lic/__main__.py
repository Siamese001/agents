"""CLI entrypoint for outreach_engine / apps_lic."""

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
from apps_lic.pipeline.mission_loader import MissionLoader
from apps_lic.pipeline.orchestrator import OutreachOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser(description="outreach_engine: Grounded Executive Outreach Generator")
    parser.add_argument("--brief", "--mission", dest="brief", help="Path to opportunity brief / mission JSON fixture")
    parser.add_argument("--company", help="Target company name (enables autonomous briefing resolution)")
    parser.add_argument("--role", default="Engineering Leader", help="Target role title")
    parser.add_argument("--research", action="store_true", default=True, help="Enable autonomous research resolution")
    parser.add_argument("--demo", action="store_true", help="Run with demo mission fixture")
    parser.add_argument(
        "--channel",
        choices=["inmail", "connection_note", "email", "follow_up"],
        default="inmail",
        help="Target channel for outreach draft",
    )
    args = parser.parse_args()

    print("[outreach_engine] Starting Grounded Outreach Generator...")

    brief_path = args.brief
    if args.demo and not brief_path:
        fixture_path = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures" / "charles_truist_mission.json"
        if fixture_path.is_file():
            brief_path = str(fixture_path)

    if brief_path:
        print(f"[outreach_engine] Ingesting mission brief from {brief_path}...")
        candidate, opportunity = MissionLoader.load_from_file(brief_path)
    elif args.company:
        print(f"[outreach_engine] Target company specified: {args.company} ({args.role})...")
        candidate = CandidateProfile(
            candidate_id="cand_exec",
            full_name="Alex Mercer",
            target_title=args.role,
            executive_summary="Enterprise technology executive specializing in modern distributed platforms.",
            verified_facts=[
                CandidateFact(
                    fact_id="fact_01",
                    category="scale",
                    statement="scaled enterprise core platform processing high-volume transactions with 99.995% reliability",
                    metric="99.995%",
                ),
            ],
        )
        opportunity = TargetOpportunity(
            opportunity_id=f"opp_{args.company.lower()}",
            company_name=args.company,
            role_title=args.role,
            industry="Enterprise Technology",
            recipient_name="Hiring Leader",
            recipient_title=f"Head of {args.role}",
            recipient_class=RecipientClass.HIRING_MANAGER,
        )
    else:
        candidate = CandidateProfile(
            candidate_id="cand_001",
            full_name="Alex Mercer",
            target_title="VP of Enterprise Engineering",
            executive_summary="Executive technology leader specializing in modern distributed systems.",
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

    draft, val = orchestrator.generate_single_draft(
        candidate,
        opportunity,
        channel,
        auto_research=args.research,
    )

    print("\n" + "=" * 60)
    print(f"OUTREACH DRAFT ({channel.value.upper()}):")
    print("=" * 60)
    print(f"Subject: {draft.subject}")
    print("-" * 60)
    print(draft.body)
    print("=" * 60)
    print(f"Template Used: {draft.metadata.get('template_id', 'default')}")
    print(f"Character Count: {draft.character_count}")
    print(f"Research Resolution: {draft.research_metadata.get('resolution_source', 'none')}")
    print(f"Validation Status: {'PASSED' if val.is_valid else 'FAILED'}")
    if val.violations:
        print(f"Violations: {val.violations}")
    if val.warnings:
        print(f"Warnings: {val.warnings}")
    print("=" * 60)

    sequence = orchestrator.generate_full_campaign(
        candidate,
        opportunity,
        channel,
        auto_research=args.research,
    )
    print(f"\nGenerated Multi-Touch Campaign with {len(sequence.touches)} planned touches:")
    for t in sequence.touches:
        print(f"  - Touch {t.touch_number} (Day {t.day_offset}) via {t.channel.value}: {t.objective}")

    return 0 if val.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
