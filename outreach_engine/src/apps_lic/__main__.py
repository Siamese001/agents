"""CLI entrypoint for outreach_engine / apps_lic.

Canonical command surface:
    python -m outreach_engine run [options]
    python -m outreach_engine eval --run-dir <completed_run>
    python -m outreach_engine show --run-dir <completed_run> --artifact draft|campaign|evaluation|validation|research
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

from apps_lic.domain.models import (
    AudiencePersona,
    CandidateFact,
    CandidateProfile,
    CandidateProfileLoader,
    ChannelType,
    OutreachMessageDraft,
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
    if values[0] in {"-h", "--help", "-v", "--version"}:
        return values
    actions = {"run", "eval", "show"}
    if values[0] not in actions:
        if values[0].startswith("-"):
            return ["run", *values]
    return values


def _build_parser(prog: str = "python -m outreach_engine") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Grounded Executive Outreach Engine: Generate, evaluate, and inspect grounded multi-touch campaigns.",
    )
    parser.add_argument("--version", action="version", version="outreach_engine 1.0.0")
    subparsers = parser.add_subparsers(dest="action", metavar="ACTION")

    # 1. run action
    run_parser = subparsers.add_parser("run", help="Run the grounded executive outreach pipeline")
    run_parser.add_argument("--brief", "--mission", dest="brief", help="Path to opportunity brief / mission JSON fixture")
    run_parser.add_argument("--company", help="Target company name (enables autonomous briefing resolution)")
    run_parser.add_argument("--role", default=None, help="Target role title (overrides brief role title when specified)")
    run_parser.add_argument("--research", action=argparse.BooleanOptionalAction, default=True, help="Enable or disable autonomous research resolution (e.g. --no-research)")
    run_parser.add_argument("--demo", action="store_true", help="Run with demo mission fixture")
    run_parser.add_argument("--channel", choices=["inmail", "connection_note", "email", "follow_up"], default="inmail", help="Target channel for outreach draft")
    run_parser.add_argument("--audience", choices=["executive", "recruiter"], default="executive", help="Target audience persona: executive or recruiter")
    run_parser.add_argument("--artifact-dir", help="Directory to persist run outputs and receipts")
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
        choices=("draft", "campaign", "evaluation", "validation", "research", "manifest", "receipt"),
        help="Artifact to inspect and print",
    )
    show_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    return parser


def _handle_run(args: argparse.Namespace, prog: str = "python -m outreach_engine") -> int:
    try:
        try:
            from infrastructure.live_execution import load_agent_environment
            load_agent_environment(repo_root=Path(__file__).resolve().parent.parent.parent.parent)
        except Exception:
            pass
        from agents.live_preflight import assert_engine_live_preflight
        assert_engine_live_preflight(prog, providers=("openai",), is_demo=bool(getattr(args, "demo", False)))
    except ImportError as err:
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": f"Preflight import failure: {err}"}, indent=2), flush=True)
        sys.stderr.write(f"[{prog}] FATAL: Preflight module import failed:\n{err}\n")
        return 2
    except Exception as exc:
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2), flush=True)
        sys.stderr.write(f"[{prog}] Preflight Credential Failure:\n{exc}\n")
        return 2

    def log(msg: str) -> None:
        if not getattr(args, "json", False):
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
        opp_updates: dict[str, Any] = {}
        if getattr(args, "company", None):
            opp_updates["company_name"] = args.company
        if getattr(args, "role", None) is not None:
            opp_updates["role_title"] = args.role
            candidate = dataclasses.replace(candidate, target_title=args.role)
        if opp_updates:
            opportunity = dataclasses.replace(opportunity, **opp_updates)
    elif args.company:
        target_role = args.role or "Engineering Leader"
        log(f"[outreach_engine] Target company specified: {args.company} ({target_role})...")
        candidate = CandidateProfileLoader.load_default(overrides={"candidate_id": "cand_exec", "target_title": target_role})
        opportunity = TargetOpportunity(
            opportunity_id=f"opp_{args.company.lower()}", company_name=args.company, role_title=target_role,
            industry="Enterprise Technology", recipient_name="Hiring Leader", recipient_title=f"Head of {target_role}",
            recipient_class=RecipientClass.HIRING_MANAGER, relationship_distance=RelationshipDistance.COLD,
        )
    else:
        target_role = args.role or "VP of Enterprise Engineering"
        candidate = CandidateProfileLoader.load_default(overrides={"candidate_id": "cand_001", "target_title": target_role})
        opportunity = TargetOpportunity(
            opportunity_id="opp_truist_01", company_name="Truist Enterprise Technology",
            role_title=args.role or "Head of Engineering, Core Platforms", industry="Financial Services & Banking",
            recipient_name="Sarah Jenkins", recipient_title="Senior Director of Talent Acquisition",
            recipient_class=RecipientClass.TALENT_PARTNER, relationship_distance=RelationshipDistance.COLD,
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
    persona = (
        AudiencePersona.EXECUTIVE_CONTACT
        if getattr(args, "audience", "executive") == "executive"
        else AudiencePersona.EXECUTIVE_RECRUITER
    )
    orchestrator = OutreachOrchestrator()

    t_total_start = time.perf_counter()
    try:
        # Stage 1: Briefing Resolution (Executed once, eliminating redundant second resolution)
        t_res_start = time.perf_counter()
        opportunity = orchestrator.resolve_opportunity_briefing(
            opportunity,
            auto_research=args.research,
            artifact_runs_root=(artifact_dir / "apps_research" / "runs") if artifact_dir else None,
        )
        lat_res_ms = round((time.perf_counter() - t_res_start) * 1000, 2)

        # Stage 2: Draft Generation & Context Assembly
        t_draft_start = time.perf_counter()
        draft, val = orchestrator.generate_single_draft(
            candidate,
            opportunity,
            channel,
            audience_persona=persona,
            auto_research=args.research,
            artifact_dir=artifact_dir,
        )
        lat_draft_ms = round((time.perf_counter() - t_draft_start) * 1000, 2)

        # Stage 3: Validation Verification (derived from AuthoritativeVerdict)
        t_val_start = time.perf_counter()
        lat_val_ms = round((time.perf_counter() - t_val_start) * 1000, 2)

        # Stage 4: Rubric Evaluation
        t_eval_start = time.perf_counter()
        evaluation = orchestrator.evaluate_draft(
            draft,
            candidate,
            opportunity,
            artifact_dir=artifact_dir,
        )
        lat_eval_ms = round((time.perf_counter() - t_eval_start) * 1000, 2)

        # Stage 5: Multi-Touch Campaign Planning
        t_camp_start = time.perf_counter()
        sequence = orchestrator.generate_full_campaign(
            candidate,
            opportunity,
            channel,
            audience_persona=persona,
            auto_research=args.research,
            artifact_dir=artifact_dir,
        )
        lat_camp_ms = round((time.perf_counter() - t_camp_start) * 1000, 2)

        lat_total_ms = round((time.perf_counter() - t_total_start) * 1000, 2)
        stage_latencies_ms = {
            "briefing_resolution_ms": lat_res_ms,
            "draft_generation_ms": lat_draft_ms,
            "validation_ms": lat_val_ms,
            "evaluation_ms": lat_eval_ms,
            "campaign_planning_ms": lat_camp_ms,
            "total_ms": lat_total_ms,
        }

        has_blocked_touch = bool(sequence.blocked_touches)
        all_touches_passed = not has_blocked_touch
        overall_passed = bool(val.passed and evaluation.passed and all_touches_passed)
        overall_status = "PASSED" if overall_passed else "BLOCKED"
        all_passed = overall_passed

        receipt_payload = {
            "run_id": run_id,
            "status": overall_status,
            "overall_passed": overall_passed,
            "all_touches_passed": all_touches_passed,
            "sealed": overall_passed,
            "stage_latencies_ms": stage_latencies_ms,
            "timestamp": time.time(),
        }
        (artifact_dir / "run_receipt.json").write_text(json.dumps(receipt_payload, indent=2) + "\n", encoding="utf-8")

    except Exception as exc:
        lat_total_ms = round((time.perf_counter() - t_total_start) * 1000, 2)
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": str(exc), "total_latency_ms": lat_total_ms}, indent=2), flush=True)
        sys.stderr.write(f"[{prog}] FATAL: Outreach pipeline execution error: {exc}\n")
        return 1

    if getattr(args, "json", False):
        all_failure_reasons = list(val.failure_reasons)
        for bt in sequence.blocked_touches:
            for r in bt.get("failure_reasons", []):
                msg = f"Touch {bt['touch_number']}: {r}"
                if msg not in all_failure_reasons:
                    all_failure_reasons.append(msg)

        result_payload = {
            "run_id": run_id,
            "artifact_dir": str(artifact_dir),
            "status": overall_status,
            "overall_passed": all_passed,
            "all_touches_passed": not has_blocked_touch,
            "audience_persona": persona.value,
            "resolution_source": draft.research_metadata.get("resolution_source", "none"),
            "stage_latencies_ms": stage_latencies_ms,
            "total_latency_ms": lat_total_ms,
            "draft": {
                "channel": channel.value,
                "subject": draft.subject,
                "body": draft.body if val.passed else "",
                "character_count": draft.character_count,
                "template_id": draft.metadata.get("template_id", "default"),
                "signature_block": draft.signature_block if val.passed else "",
                "status": val.status,
                "sealed": val.passed,
            },
            "validation": {
                "status": val.status,
                "is_valid": val.is_valid,
                "violations": val.violations,
                "warnings": val.warnings,
                "failure_reasons": val.failure_reasons,
            },
            "evaluation": evaluation.to_dict(),
            "campaign_status": sequence.status,
            "campaign_touches": [
                {
                    "touch_number": t.touch_number,
                    "day_offset": t.day_offset,
                    "channel": t.channel.value,
                    "objective": t.objective,
                    "status": t.draft.metadata.get("status", "PASSED"),
                    "passed": bool(t.draft.metadata.get("passed", True)),
                    "promoted": bool(t.draft.metadata.get("passed", True)),
                    "failure_reasons": list(t.draft.metadata.get("failure_reasons", [])),
                    "validation_violations": list(t.draft.metadata.get("validation_violations", [])),
                }
                for t in sequence.touches
            ],
            "blocked_touches": sequence.blocked_touches,
        }
        if not all_passed:
            result_payload["failure_reasons"] = all_failure_reasons

        print(json.dumps(result_payload, indent=2))
        return 0 if all_passed else 1

    print("\n" + "=" * 60)
    print(f"OUTREACH DRAFT ({channel.value.upper()} | {persona.value.upper()}):\n" + "=" * 60)
    if val.passed:
        print(f"Subject: {draft.subject}\n" + "-" * 60 + f"\n{draft.body}")
        if draft.signature_block:
            print("-" * 60 + f"\n{draft.signature_block}")
    else:
        print(f"Subject: {draft.subject} [BLOCKED - NOT SEALED]\n" + "-" * 60 + "\n[Draft unsealed due to policy/judge violation]")
    print("=" * 60)
    print(f"Template Used: {draft.metadata.get('template_id', 'default')}\nCharacter Count: {draft.character_count}\nResearch Resolution: {draft.research_metadata.get('resolution_source', 'none')}")
    print(f"Stage Latencies: Resolution: {lat_res_ms}ms | Draft: {lat_draft_ms}ms | Validation: {lat_val_ms}ms | Evaluation: {lat_eval_ms}ms | Campaign: {lat_camp_ms}ms | Total: {lat_total_ms}ms")
    print(f"Authoritative Verdict: {val.status}\nValidation Status: {'PASSED' if val.is_valid else 'FAILED'}")
    if val.violations:
        print(f"Violations: {val.violations}")
    if val.warnings:
        print(f"Warnings: {val.warnings}")
    print(f"Rubric Judge Score: {'PASSED' if evaluation.passed else 'FAILED'} (Composite: {evaluation.composite_score:.2f} [{evaluation.score_band}])")
    for k, v in evaluation.lens_scores.items():
        print(f"  - {k}: {v:.2f}")
    if evaluation.feedback:
        print(f"Feedback: {evaluation.feedback}")
    print("=" * 60)

    print(f"\nGenerated Multi-Touch Campaign with {len(sequence.touches)} planned touches (Status: {sequence.status}):")
    for t in sequence.touches:
        t_pass_str = "PASSED" if t.draft.metadata.get("passed", True) else "BLOCKED"
        print(f"  - Touch {t.touch_number} (Day {t.day_offset}) via {t.channel.value} [{t_pass_str}]: {t.objective}")
        if t.draft.metadata.get("status") == "BLOCKED":
            print(f"      Failure reasons: {t.draft.metadata.get('failure_reasons', [])}")

    out_msg = f"\n[outreach_engine] Artifacts sealed at: {artifact_dir}" if all_passed else f"\n[outreach_engine] Unsealed diagnostic artifacts stored at: {artifact_dir}"
    print(out_msg)

    if not all_passed:
        sys.stderr.write("\n" + "!" * 60 + "\n[outreach_engine] BLOCKED: Outreach draft or campaign touch failed authoritative verification.\n")
        if val.violations:
            sys.stderr.write(f"Violations: {val.violations}\n")
        if val.failure_reasons:
            sys.stderr.write(f"Draft Failures: {val.failure_reasons}\n")
        if not evaluation.passed:
            sys.stderr.write(f"Rubric Failures: {evaluation.feedback}\n")
        for bt in getattr(sequence, "blocked_touches", []):
            sys.stderr.write(f"Touch {bt['touch_number']} Failures: {bt['failure_reasons']}\n")
        sys.stderr.write("!" * 60 + "\n")
        return 1

    return 0


def _reconstruct_eval_draft(run_dir: Path, manifest_data: dict[str, Any] | None = None) -> OutreachMessageDraft | None:
    m_ch = manifest_data.get("channel") if manifest_data else None
    m_persona = manifest_data.get("audience_persona") if manifest_data else None
    m_facts = list(manifest_data.get("grounded_facts_used", [])) if manifest_data else []

    draft_file = run_dir / "outreach_draft.json"
    if draft_file.is_file():
        try:
            d = json.loads(draft_file.read_text(encoding="utf-8"))
            ch_raw = d.get("channel") or m_ch
            if ch_raw not in ChannelType._value2member_map_:
                return None
            persona_raw = d.get("audience_persona") or m_persona
            persona = AudiencePersona.EXECUTIVE_RECRUITER if persona_raw in ("recruiter", "executive_recruiter", AudiencePersona.EXECUTIVE_RECRUITER.value) else AudiencePersona.EXECUTIVE_CONTACT
            return OutreachMessageDraft(
                draft_id=d.get("draft_id", "draft_eval"),
                channel=ChannelType(ch_raw),
                subject=d.get("subject", ""),
                body=d.get("body", ""),
                signature_block=d.get("signature_block", ""),
                audience_persona=persona,
                grounded_facts_used=list(d.get("grounded_facts_used", [])),
                research_metadata=dict(d.get("research_metadata", {})),
                metadata=dict(d.get("metadata", {})),
            )
        except Exception:
            return None

    draft_md = run_dir / "outreach_draft.md"
    if draft_md.is_file():
        try:
            md_text = draft_md.read_text(encoding="utf-8")
            hm = re.search(r"^#\s+Outreach Draft:\s*([A-Za-z_]+)", md_text, re.MULTILINE)
            ch_raw = (hm.group(1).lower() if hm else None) or m_ch
            if ch_raw not in ChannelType._value2member_map_:
                return None
            subj = next((l.split(":", 1)[1].strip() for l in md_text.splitlines() if l.startswith(("**Subject**:", "Subject:"))), "")
            bm = re.search(r"```text\s*\n(.*?)\n```", md_text, re.DOTALL)
            persona = AudiencePersona.EXECUTIVE_RECRUITER if m_persona in ("recruiter", "executive_recruiter", AudiencePersona.EXECUTIVE_RECRUITER.value) else AudiencePersona.EXECUTIVE_CONTACT
            return OutreachMessageDraft(
                draft_id="draft_from_md",
                channel=ChannelType(ch_raw),
                subject=subj,
                body=bm.group(1).strip() if bm else md_text.strip(),
                grounded_facts_used=m_facts,
                audience_persona=persona,
            )
        except Exception:
            return None
    return None


def _reconstruct_eval_context(manifest_file: Path) -> tuple[CandidateProfile, TargetOpportunity]:
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Authentic saved context '{manifest_file.name}' not found")
    m = json.loads(manifest_file.read_text(encoding="utf-8"))
    cdata, odata = m.get("candidate"), m.get("opportunity")
    if not isinstance(cdata, dict) or not isinstance(odata, dict):
        raise ValueError(f"Corrupt manifest '{manifest_file.name}'")

    facts = [
        CandidateFact(
            fact_id=f["fact_id"],
            category=f.get("category", "general"),
            statement=f.get("statement", ""),
            metric=f.get("metric"),
            source_reference=f.get("source_reference"),
        )
        for f in cdata.get("verified_facts", [])
        if isinstance(f, dict) and "fact_id" in f
    ]
    cand = CandidateProfile(
        candidate_id=cdata.get("candidate_id", ""),
        full_name=cdata.get("full_name", ""),
        target_title=cdata.get("target_title", ""),
        current_title=cdata.get("current_title", ""),
        executive_summary=cdata.get("executive_summary", ""),
        verified_facts=facts,
        key_competencies=list(cdata.get("key_competencies", [])),
        linkedin_url=cdata.get("linkedin_url", ""),
        phone=cdata.get("phone", ""),
    )
    rc_raw, rd_raw = odata.get("recipient_class"), odata.get("relationship_distance")
    rc = RecipientClass(rc_raw) if rc_raw in RecipientClass._value2member_map_ else RecipientClass.HIRING_MANAGER
    rd = RelationshipDistance(rd_raw) if rd_raw in RelationshipDistance._value2member_map_ else RelationshipDistance.COLD
    opp = TargetOpportunity(
        opportunity_id=odata.get("opportunity_id", ""),
        company_name=odata.get("company_name", ""),
        role_title=odata.get("role_title", ""),
        industry=odata.get("industry", ""),
        recipient_name=odata.get("recipient_name", ""),
        recipient_title=odata.get("recipient_title", ""),
        recipient_class=rc,
        relationship_distance=rd,
        strategic_priorities=list(odata.get("strategic_priorities", [])),
        briefing_text=odata.get("briefing_text", ""),
        research_digest=odata.get("research_digest", ""),
        evidence_items=list(odata.get("evidence_items", [])),
        sealed_resolution=odata.get("sealed_resolution"),
    )
    return cand, opp


def _handle_eval(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        err_msg = f"Run directory does not exist: {run_dir}"
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": err_msg}, indent=2))
        sys.stderr.write(f"Error: {err_msg}\n")
        return 1

    manifest_file = run_dir / "run_manifest.json"
    if not manifest_file.is_file():
        err_msg = f"Authentic saved context 'run_manifest.json' not found in: {run_dir}"
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": err_msg}, indent=2))
        sys.stderr.write(f"Error: {err_msg}\n")
        return 1

    try:
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        candidate, opportunity = _reconstruct_eval_context(manifest_file)
    except Exception as exc:
        err_msg = f"Failed to reconstruct authentic saved context from 'run_manifest.json': {exc}"
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": err_msg}, indent=2))
        sys.stderr.write(f"Error: {err_msg}\n")
        return 1

    draft = _reconstruct_eval_draft(run_dir, manifest_data=manifest_data)
    if draft is None:
        err_msg = f"Neither outreach_draft.json nor outreach_draft.md found or readable in: {run_dir}"
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": err_msg}, indent=2))
        sys.stderr.write(f"Error: {err_msg}\n")
        return 1

    orchestrator = OutreachOrchestrator()
    verdict = orchestrator.evaluate_authoritative_draft(draft, candidate, opportunity, artifact_dir=None)
    eval_report = orchestrator.judge.report_from_verdict(verdict)

    val_dict = {
        "status": verdict.status,
        "is_valid": verdict.is_valid,
        "violations": verdict.violations,
        "warnings": verdict.warnings,
        "failure_reasons": verdict.failure_reasons,
        "scores": verdict.scores,
    }
    overall_passed = verdict.passed

    if args.json:
        print(json.dumps({
            "status": "PASSED" if overall_passed else "FAILED",
            "is_valid": verdict.is_valid,
            "evaluation": eval_report.to_dict(),
            "validation": val_dict,
        }, indent=2))
        return 0 if overall_passed else 1

    print("\n" + "=" * 60 + f"\nLIVE EVALUATION REPORT FOR RUN: {run_dir.name}\n" + "=" * 60)
    print(f"Validation Status: {'PASSED' if verdict.is_valid else 'FAILED'}")
    if verdict.violations:
        print(f"Validation Violations: {verdict.violations}")
    print(f"Rubric Judge Status: {'PASSED' if eval_report.passed else 'FAILED'} (Composite: {eval_report.composite_score:.2f} [{eval_report.score_band}])")
    for k, v in eval_report.lens_scores.items():
        print(f"  - {k}: {v:.2f}")
    if eval_report.feedback:
        print(f"Feedback: {eval_report.feedback}")
    if eval_report.remediation_hints:
        print(f"Remediation Hints: {eval_report.remediation_hints}")
    print("=" * 60)
    return 0 if overall_passed else 1


def _handle_show(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        err = f"Run directory does not exist: {run_dir}"
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": err}, indent=2))
        sys.stderr.write(f"Error: {err}\n")
        return 1

    artifact_map = {
        "draft": ["outreach_draft.md", "outreach_draft.json"],
        "campaign": ["campaign_sequence.json"],
        "evaluation": ["evaluation_report.json"],
        "validation": ["validation_report.json"],
        "research": ["apps_research/runs/*/company_brief.md", "apps_research/runs/*/company_brief.json"],
        "manifest": ["run_manifest.json"],
        "receipt": ["run_receipt.json"],
    }
    target_file = None
    for pattern in artifact_map.get(args.artifact, []):
        matches = list(run_dir.glob(pattern)) if "*" in pattern else [run_dir / pattern]
        for p in matches:
            if p.is_file():
                target_file = p
                break
        if target_file:
            break

    if not target_file or not target_file.is_file():
        err = f"Artifact '{args.artifact}' was not found in: {run_dir}"
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": err}, indent=2))
        sys.stderr.write(f"Error: {err}\n")
        return 1

    content = target_file.read_text(encoding="utf-8")
    if getattr(args, "json", False) and not target_file.name.endswith(".json"):
        print(json.dumps({"artifact": args.artifact, "file": target_file.name, "content": content}, indent=2))
    else:
        print(content)
    return 0


def main(argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    normalized = _normalize_argv(argv)
    if prog is None:
        prog = "python -m apps_lic" if (len(sys.argv) > 0 and "apps_lic" in sys.argv[0]) else "python -m outreach_engine"
    parser = _build_parser(prog=prog)
    args = parser.parse_args(normalized)

    handlers = {"run": lambda: _handle_run(args, prog=prog), "eval": lambda: _handle_eval(args), "show": lambda: _handle_show(args)}
    handler = handlers.get(args.action)
    if handler:
        return handler()
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
