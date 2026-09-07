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
    TargetOpportunity,
)
from apps_lic.pipeline.orchestrator import OutreachOrchestrator


def main() -> int:
    parser = argparse.ArgumentParser(description="apps_lic_v2: Standalone Outreach Generator")
    parser.add_argument("--brief", help="Path to opportunity brief JSON fixture")
    parser.add_argument(
        "--channel",
        choices=["inmail", "connection_note", "email", "follow_up"],
        default="inmail",
        help="Target channel for outreach draft",
    )
    args = parser.parse_args()

    print("[apps_lic_v2] Starting Standalone Outreach Generator...")

    # Load candidate profile
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

    # Opportunity details
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
