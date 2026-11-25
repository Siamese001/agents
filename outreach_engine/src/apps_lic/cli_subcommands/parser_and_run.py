"""CLI parser, argument normalization, and run action handler for apps_lic."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

from apps_lic.cli_subcommands.parity_commands import register_parity_subparsers
from apps_lic.domain.models import (
    AudiencePersona, CandidateProfileLoader, ChannelType, RecipientClass, RelationshipDistance, TargetOpportunity,
)
from apps_lic.pipeline.mission_loader import MissionLoader
from apps_lic.pipeline.orchestrator import OutreachOrchestrator

_KNOWN_SUBCOMMANDS = frozenset({
    "run",
    "patch-run",
    "eval",
    "validate",
    "show",
    "preflight",
    "models",
    "cache",
    "doctor",
})


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        return ["run", "--demo"]
    if values[0] in {"-h", "--help", "-v", "--version"}:
        return values
    if values[0].startswith("--patch-run"):
        if values[0] == "--patch-run" and len(values) >= 2:
            return ["patch-run", "--run-dir", values[1], *values[2:]]
        if "=" in values[0]:
            _, target = values[0].split("=", 1)
            return ["patch-run", "--run-dir", target, *values[1:]]
    if values[0] not in _KNOWN_SUBCOMMANDS and values[0].startswith("-"):
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
    run_parser.add_argument("--offline-smoke", action="store_true", help="Run deterministic offline smoke without external provider calls")
    run_parser.add_argument("--no-cache", "--fresh", dest="no_cache", action="store_true", help="Disable retrieval/provider caching for this run")
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
        choices=(
            "draft",
            "campaign",
            "evaluation",
            "validation",
            "research",
            "manifest",
            "receipt",
            "bundle",
            "review",
            "csv",
            "docx",
        ),
        help="Artifact to inspect and print",
    )
    show_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    # 4. validate action
    val_parser = subparsers.add_parser("validate", help="Validate an ad-hoc outreach draft against all 10 domain gates and 6 rubric lenses")
    val_parser.add_argument("--body", default="", help="Draft body text to validate")
    val_parser.add_argument("--file", dest="draft_file", help="Path to draft text or JSON file to validate")
    val_parser.add_argument("--subject", default="", help="Draft subject line")
    val_parser.add_argument("--channel", choices=["inmail", "connection_note", "email", "follow_up"], default="inmail", help="Target channel")
    val_parser.add_argument("--company", default="Target Company", help="Target company name for resonance and personalization checks")
    val_parser.add_argument("--role", default="Engineering Leader", help="Target role title")
    val_parser.add_argument("--priority", dest="priorities", action="append", default=[], help="Verified strategic priority (repeatable)")
    val_parser.add_argument("--unverified", action="store_true", help="Simulate unverified briefing resolution")
    val_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    # 5-9. parity actions: patch-run, preflight, models, cache, doctor
    register_parity_subparsers(subparsers)

    return parser


def _emit_error(args: argparse.Namespace, err_msg: str) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"status": "FAILED", "error": err_msg}, indent=2))
    sys.stderr.write(f"Error: {err_msg}\n")
    return 1


def _handle_run(args: argparse.Namespace, prog: str = "python -m outreach_engine") -> int:
    outreach_root = Path(__file__).resolve().parents[3]
    repo_root = Path(__file__).resolve().parents[4]
    try:
        with_offline = bool(getattr(args, "offline_smoke", False))
        try:
            from infrastructure.live_execution import load_agent_environment
            load_agent_environment(repo_root=repo_root)
        except (ImportError, OSError, ValueError):
            pass
        from agents.live_preflight import assert_engine_live_preflight
        assert_engine_live_preflight(prog, providers=("openai",), is_demo=bool(getattr(args, "demo", False)), allow_offline=with_offline)
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
        fixture_path = outreach_root / "data" / "fixtures" / "charles_truist_mission.json"
        if fixture_path.is_file():
            brief_path = str(fixture_path)

    if brief_path:
        log(f"[outreach_engine] Ingesting mission brief from {brief_path}...")
        b_file = Path(brief_path)
        if not b_file.is_file():
            cand_b = repo_root / brief_path
            if cand_b.is_file():
                b_file = cand_b
        try:
            raw_brief = b_file.read_text(encoding="utf-8") if b_file.is_file() else ""
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            return _emit_error(args, f"Failed reading brief file '{brief_path}': {exc}")
        if not b_file.is_file() or not raw_brief.strip():
            return _emit_error(args, f"Brief file '{brief_path}' is missing or empty.")
        has_explicit_sender_title = False
        try:
            parsed_b = json.loads(raw_brief)
            if isinstance(parsed_b, dict):
                sp_d, pl_d = parsed_b.get("sender_profile"), parsed_b.get("payload")
                has_explicit_sender_title = bool(
                    (isinstance(sp_d, dict) and sp_d.get("title"))
                    or parsed_b.get("target_title") or parsed_b.get("candidate_title")
                    or (isinstance(pl_d, dict) and pl_d.get("target_title"))
                )
        except json.JSONDecodeError:
            pass
        try:
            candidate, opportunity = MissionLoader.load_from_file(b_file)
        except Exception as exc:
            return _emit_error(args, f"Failed loading brief '{brief_path}': {exc}")
        opp_updates: dict[str, Any] = {}
        if getattr(args, "company", None):
            opp_updates["company_name"] = args.company
        if getattr(args, "role", None) is not None:
            opp_updates["role_title"] = args.role
            if not has_explicit_sender_title:
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

    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else (repo_root / "artifacts" / "outreach_engine" / "runs" / run_id)
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _emit_error(args, f"Cannot create artifact directory '{artifact_dir}': {exc}")
    channel = ChannelType(args.channel)
    persona = AudiencePersona.EXECUTIVE_CONTACT if getattr(args, "audience", "executive") == "executive" else AudiencePersona.EXECUTIVE_RECRUITER
    orchestrator = OutreachOrchestrator(offline_smoke=with_offline)

    t_total_start = time.perf_counter()
    try:
        t_res_start = time.perf_counter()
        opportunity = orchestrator.resolve_opportunity_briefing(
            opportunity, auto_research=args.research,
            artifact_runs_root=(artifact_dir / "apps_research" / "runs") if artifact_dir else None,
        )
        lat_res_ms = round((time.perf_counter() - t_res_start) * 1000, 2)
        t_draft_start = time.perf_counter()
        draft, val = orchestrator.generate_single_draft(
            candidate, opportunity, channel, audience_persona=persona, auto_research=args.research, artifact_dir=artifact_dir,
        )
        lat_draft_ms = round((time.perf_counter() - t_draft_start) * 1000, 2)
        t_val_start = time.perf_counter()
        lat_val_ms = round((time.perf_counter() - t_val_start) * 1000, 2)
        t_eval_start = time.perf_counter()
        evaluation = orchestrator.evaluate_draft(draft, candidate, opportunity, artifact_dir=artifact_dir)
        lat_eval_ms = round((time.perf_counter() - t_eval_start) * 1000, 2)
        t_camp_start = time.perf_counter()
        sequence = orchestrator.generate_full_campaign(
            candidate, opportunity, channel, audience_persona=persona, auto_research=args.research, artifact_dir=artifact_dir,
        )
        lat_camp_ms = round((time.perf_counter() - t_camp_start) * 1000, 2)
        lat_total_ms = round((time.perf_counter() - t_total_start) * 1000, 2)
        stage_latencies_ms = {
            "briefing_resolution_ms": lat_res_ms, "draft_generation_ms": lat_draft_ms,
            "validation_ms": lat_val_ms, "evaluation_ms": lat_eval_ms,
            "campaign_planning_ms": lat_camp_ms, "total_ms": lat_total_ms,
        }
        has_blocked_touch = bool(sequence.blocked_touches)
        all_touches_passed = not has_blocked_touch
        overall_passed = bool(val.passed and evaluation.passed and all_touches_passed)
        overall_status = "PASSED" if overall_passed else "BLOCKED"
        all_passed = overall_passed
        receipt_payload = {
            "run_id": run_id, "status": overall_status, "overall_passed": overall_passed,
            "all_touches_passed": all_touches_passed, "sealed": overall_passed,
            "stage_latencies_ms": stage_latencies_ms, "timestamp": time.time(),
        }
        (artifact_dir / "run_receipt.json").write_text(json.dumps(receipt_payload, indent=2) + "\n", encoding="utf-8")
        try:
            from infrastructure.config.env_loader import get_env_str
            if ("pytest" not in sys.modules and not get_env_str("PYTEST_CURRENT_TEST")) or get_env_str("AGENTS_TRACE_IN_PYTEST") == "1":
                from agents.observability.eval_flywheel import EvalFlywheelEngine
                from agents.observability.flywheel_sync_hook import sync_flywheel_after_run
                from agents.observability.trace_collector import compute_scenario_fingerprint, emit_post_run_trace_safe

                is_smoke = bool(getattr(args, "offline_smoke", False) or getattr(args, "demo", False))
                raw_in = {
                    "company": str(opportunity.company_name or ""),
                    "role": str(opportunity.role_title or ""),
                    "channel": str(channel.value),
                    "offline_smoke": is_smoke,
                }
                scen_fp = compute_scenario_fingerprint(
                    app_id="apps_lic",
                    raw_input=raw_in,
                    is_smoke_or_demo=is_smoke,
                )
                eff_x3 = "X3D_ALLOW_FINISH" if overall_passed else ("X3E_SAFE_ABSTAIN" if is_smoke else "X3B_ESCALATE_HITL")
                fail_reasons = [str(r) for r in (val.failure_reasons or val.violations or ()) if str(r).strip()]
                EvalFlywheelEngine().ingest_product_run(
                    app_id="apps_lic",
                    run_id=run_id,
                    x3_disposition=eff_x3,
                    passed=overall_passed,
                    failure_reasons=fail_reasons,
                    score=1.0 if overall_passed else 0.0,
                    scenario_fingerprint=scen_fp,
                    is_smoke_or_demo=is_smoke,
                )
                emit_post_run_trace_safe(
                    app_id="apps_lic",
                    run_id=run_id,
                    terminal_status="PASS" if overall_passed else "FAIL",
                    raw_input=raw_in,
                    output_summary={
                        "artifact_dir": str(artifact_dir),
                        "status": overall_status,
                        "scenario_fingerprint": scen_fp,
                    },
                    gate_outcomes={
                        "x3_disposition": eff_x3,
                        "failure_reasons": fail_reasons,
                        "x2_gates": {
                            "validation_passed": bool(val.passed),
                            "evaluation_passed": bool(evaluation.passed),
                            "all_touches_passed": bool(all_touches_passed),
                        },
                    },
                    telemetry={"latency_ms": float(lat_total_ms)},
                    scenario_fingerprint=scen_fp,
                    is_smoke_or_demo=is_smoke,
                )
                sync_flywheel_after_run()
        except (ImportError, OSError, ValueError, RuntimeError):  # guardian: allow-silent-swallow -- observer-only trace hook must never fail outreach run
            pass
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
            "run_id": run_id, "artifact_dir": str(artifact_dir), "status": overall_status,
            "overall_passed": all_passed, "all_touches_passed": not has_blocked_touch,
            "audience_persona": persona.value,
            "resolution_source": draft.research_metadata.get("resolution_source", "none"),
            "stage_latencies_ms": stage_latencies_ms, "total_latency_ms": lat_total_ms,
            "draft": {
                "channel": channel.value, "subject": draft.subject,
                "body": draft.body if val.passed else "", "character_count": draft.character_count,
                "template_id": draft.metadata.get("template_id", "default"),
                "signature_block": draft.signature_block if val.passed else "",
                "status": val.status, "sealed": val.passed,
            },
            "validation": {
                "status": val.status, "is_valid": val.is_valid, "violations": val.violations,
                "warnings": val.warnings, "failure_reasons": val.failure_reasons,
            },
            "evaluation": evaluation.to_dict(),
            "campaign_status": sequence.status,
            "campaign_touches": [
                {
                    "touch_number": t.touch_number, "day_offset": t.day_offset, "channel": t.channel.value,
                    "objective": t.objective, "status": t.draft.metadata.get("status", "PASSED"),
                    "passed": bool(t.draft.metadata.get("passed", True)), "promoted": bool(t.draft.metadata.get("passed", True)),
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

    print("\n" + "=" * 60 + f"\nOUTREACH DRAFT ({channel.value.upper()} | {persona.value.upper()}):\n" + "=" * 60)
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
    print("=" * 60 + f"\n\nGenerated Multi-Touch Campaign with {len(sequence.touches)} planned touches (Status: {sequence.status}):")
    for t in sequence.touches:
        t_pass_str = "PASSED" if t.draft.metadata.get("passed", True) else "BLOCKED"
        print(f"  - Touch {t.touch_number} (Day {t.day_offset}) via {t.channel.value} [{t_pass_str}]: {t.objective}")
        if t.draft.metadata.get("status") == "BLOCKED":
            print(f"      Failure reasons: {t.draft.metadata.get('failure_reasons', [])}")
    print(f"\n[outreach_engine] Artifacts sealed at: {artifact_dir}" if all_passed else f"\n[outreach_engine] Unsealed diagnostic artifacts stored at: {artifact_dir}")
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


__all__ = [
    "_build_parser",
    "_emit_error",
    "_handle_run",
    "_normalize_argv",
]
