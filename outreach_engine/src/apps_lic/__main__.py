"""CLI entrypoint for outreach_engine / apps_lic.

Canonical command surface:
    python -m outreach_engine run [options]
    python -m outreach_engine eval --run-dir <completed_run>
    python -m outreach_engine show --run-dir <completed_run> --artifact draft|campaign|evaluation|validation|research
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

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


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return ["run", "--demo"]
    if values[0] in {"-h", "--help"}:
        return values
    actions = {"run", "eval", "show"}
    if values[0] not in actions:
        if values[0].startswith("-"):
            return ["run", *values]
    return values


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m outreach_engine",
        description="Grounded Executive Outreach Engine: Generate, evaluate, and inspect grounded multi-touch campaigns.",
    )
    subparsers = parser.add_subparsers(dest="action", metavar="ACTION")

    # 1. run action
    run_parser = subparsers.add_parser("run", help="Run the grounded executive outreach pipeline")
    run_parser.add_argument("--brief", "--mission", dest="brief", help="Path to opportunity brief / mission JSON fixture")
    run_parser.add_argument("--company", help="Target company name (enables autonomous briefing resolution)")
    run_parser.add_argument("--role", default="Engineering Leader", help="Target role title")
    run_parser.add_argument("--research", action="store_true", default=True, help="Enable autonomous research resolution")
    run_parser.add_argument("--demo", action="store_true", help="Run with demo mission fixture")
    run_parser.add_argument(
        "--channel",
        choices=["inmail", "connection_note", "email", "follow_up"],
        default="inmail",
        help="Target channel for outreach draft",
    )
    run_parser.add_argument(
        "--artifact-dir",
        help="Directory to persist run outputs and receipts (default: artifacts/outreach_engine/runs/<run_id>)",
    )
    run_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    # 2. eval action
    eval_parser = subparsers.add_parser("eval", help="Re-evaluate an existing outreach run without calling external providers")
    eval_parser.add_argument("--run-dir", required=True, help="Directory of a completed outreach run")
    eval_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    # 3. show action
    show_parser = subparsers.add_parser("show", help="Print an exact output artifact from a completed run")
    show_parser.add_argument("--run-dir", required=True, help="Directory of a completed outreach run")
    show_parser.add_argument(
        "--artifact",
        required=True,
        choices=("draft", "campaign", "evaluation", "validation", "research"),
        help="Artifact to inspect and print",
    )
    show_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    return parser


def _handle_run(args: argparse.Namespace) -> int:
    def log(msg: str) -> None:
        if not args.json:
            print(msg)

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    log("[outreach_engine] Starting Grounded Outreach Generator...")

    brief_path = args.brief
    if args.demo and not brief_path:
        fixture_path = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures" / "charles_truist_mission.json"
        if fixture_path.is_file():
            brief_path = str(fixture_path)

    if brief_path:
        log(f"[outreach_engine] Ingesting mission brief from {brief_path}...")
        candidate, opportunity = MissionLoader.load_from_file(brief_path)
    elif args.company:
        log(f"[outreach_engine] Target company specified: {args.company} ({args.role})...")
        candidate = CandidateProfile(
            candidate_id="cand_exec",
            full_name="Amit Ayer",
            target_title=args.role,
            executive_summary="Enterprise technology executive specializing in modern distributed platforms and governed agentic architectures.",
            verified_facts=[
                CandidateFact(
                    fact_id="fact_01",
                    category="scale",
                    statement="scaled enterprise core platform processing high-volume transactions with 99.995% reliability",
                    metric="99.995%",
                ),
                CandidateFact(
                    fact_id="fact_02",
                    category="architecture",
                    statement="architected layered agentic systems (L0 routing through L6 observability) with AST dependency governance",
                ),
            ],
            key_competencies=["Agentic Systems", "Enterprise AI Architecture", "Human-in-the-loop Governance"],
        )
        opportunity = TargetOpportunity(
            opportunity_id=f"opp_{args.company.lower()}",
            company_name=args.company,
            role_title=args.role,
            industry="Enterprise Technology",
            recipient_name="Hiring Leader",
            recipient_title=f"Head of {args.role}",
            recipient_class=RecipientClass.HIRING_MANAGER,
            relationship_distance=RelationshipDistance.COLD,
            strategic_priorities=[],
        )
    else:
        candidate = CandidateProfile(
            candidate_id="cand_001",
            full_name="Amit Ayer",
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
            key_competencies=["Agentic Systems", "Cloud Governance", "Platform Scaling"],
        )
        opportunity = TargetOpportunity(
            opportunity_id="opp_truist_01",
            company_name="Truist Enterprise Technology",
            role_title="Head of Engineering, Core Platforms",
            industry="Financial Services & Banking",
            recipient_name="Sarah Jenkins",
            recipient_title="Senior Director of Talent Acquisition",
            recipient_class=RecipientClass.TALENT_PARTNER,
            relationship_distance=RelationshipDistance.COLD,
            strategic_priorities=["cloud modern banking core", "zero-downtime reliability"],
        )

    # Resolve artifact directory
    if args.artifact_dir:
        artifact_dir = Path(args.artifact_dir).resolve()
    else:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        artifact_dir = repo_root / "artifacts" / "outreach_engine" / "runs" / run_id

    artifact_dir.mkdir(parents=True, exist_ok=True)

    channel = ChannelType(args.channel)
    orchestrator = OutreachOrchestrator()

    draft, val = orchestrator.generate_single_draft(
        candidate,
        opportunity,
        channel,
        auto_research=args.research,
        artifact_dir=artifact_dir,
    )

    evaluation = orchestrator.evaluate_draft(
        draft,
        candidate,
        opportunity,
        artifact_dir=artifact_dir,
    )

    sequence = orchestrator.generate_full_campaign(
        candidate,
        opportunity,
        channel,
        auto_research=args.research,
        artifact_dir=artifact_dir,
    )

    if args.json:
        result_payload = {
            "run_id": run_id,
            "artifact_dir": str(artifact_dir),
            "status": "PASSED" if val.is_valid and evaluation.passed else "FAILED",
            "resolution_source": draft.research_metadata.get("resolution_source", "none"),
            "draft": {
                "channel": channel.value,
                "subject": draft.subject,
                "body": draft.body,
                "character_count": draft.character_count,
                "template_id": draft.metadata.get("template_id", "default"),
            },
            "validation": {
                "is_valid": val.is_valid,
                "violations": val.violations,
                "warnings": val.warnings,
            },
            "evaluation": evaluation.to_dict(),
            "campaign_touches": [
                {
                    "touch_number": t.touch_number,
                    "day_offset": t.day_offset,
                    "channel": t.channel.value,
                    "objective": t.objective,
                }
                for t in sequence.touches
            ],
        }
        print(json.dumps(result_payload, indent=2))
        return 0 if val.is_valid else 1

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
    print(f"Rubric Judge Score: {'PASSED' if evaluation.passed else 'FAILED'}")
    print("=" * 60)

    print(f"\nGenerated Multi-Touch Campaign with {len(sequence.touches)} planned touches:")
    for t in sequence.touches:
        print(f"  - Touch {t.touch_number} (Day {t.day_offset}) via {t.channel.value}: {t.objective}")

    print(f"\n[outreach_engine] Artifacts sealed at: {artifact_dir}")

    return 0 if val.is_valid else 1


def _handle_eval(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        sys.stderr.write(f"Error: run directory does not exist: {run_dir}\n")
        return 1

    eval_file = run_dir / "evaluation_report.json"
    val_file = run_dir / "validation_report.json"

    if not eval_file.is_file():
        sys.stderr.write(f"Error: evaluation_report.json not found in: {run_dir}\n")
        return 1

    try:
        eval_data = json.loads(eval_file.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Error reading evaluation report: {exc}\n")
        return 1

    val_data = {}
    if val_file.is_file():
        try:
            val_data = json.loads(val_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if args.json:
        print(json.dumps({"evaluation": eval_data, "validation": val_data}, indent=2))
        return 0 if eval_data.get("passed", False) else 1

    print("\n" + "=" * 60)
    print(f"EVALUATION REPORT FOR RUN: {run_dir.name}")
    print("=" * 60)
    print(f"Rubric Judge Status: {'PASSED' if eval_data.get('passed') else 'FAILED'}")
    print(f"Hop 1 Classifier Score: {eval_data.get('hop1_classifier_score')}")
    print(f"Hop 2 Grounding Score:  {eval_data.get('hop2_grounding_score')}")
    print(f"Hop 6 Alignment Score:  {eval_data.get('hop6_alignment_score')}")
    print(f"Hop 8 Narrative Score:  {eval_data.get('hop8_narrative_score')}")
    if eval_data.get("feedback"):
        print(f"Feedback: {eval_data['feedback']}")
    if eval_data.get("remediation_hints"):
        print(f"Remediation Hints: {eval_data['remediation_hints']}")
    print("=" * 60)
    return 0 if eval_data.get("passed", False) else 1


def _handle_show(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        sys.stderr.write(f"Error: run directory does not exist: {run_dir}\n")
        return 1

    artifact_map = {
        "draft": ["outreach_draft.md", "outreach_draft.json"],
        "campaign": ["campaign_sequence.json"],
        "evaluation": ["evaluation_report.json"],
        "validation": ["validation_report.json"],
        "research": [
            "apps_research/runs/*/company_brief.md",
            "apps_research/runs/*/company_brief.json",
        ],
    }

    candidates = artifact_map.get(args.artifact)
    if not candidates:
        sys.stderr.write(f"Error: Unknown artifact choice: {args.artifact}\n")
        return 1

    target_file: Path | None = None
    for pattern in candidates:
        if "*" in pattern:
            matches = list(run_dir.glob(pattern))
            if matches:
                target_file = matches[0]
                break
        else:
            p = run_dir / pattern
            if p.is_file():
                target_file = p
                break

    if not target_file or not target_file.is_file():
        sys.stderr.write(f"Error: Artifact '{args.artifact}' was not found in: {run_dir}\n")
        return 1

    content = target_file.read_text(encoding="utf-8")
    if args.json and not target_file.name.endswith(".json"):
        print(json.dumps({"artifact": args.artifact, "file": target_file.name, "content": content}, indent=2))
    else:
        print(content)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    normalized = _normalize_argv(argv)
    parser = _build_parser()
    args = parser.parse_args(normalized)

    if args.action == "run":
        return _handle_run(args)
    elif args.action == "eval":
        return _handle_eval(args)
    elif args.action == "show":
        return _handle_show(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
