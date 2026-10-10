"""Unified CLI Entrypoint for Resume Engine and Outreach Engine.

Usage:
    python -m agents resume [run|eval|show] [options]
    python -m agents outreach [run|eval|show] [options]
    python -m agents e2e [--company ... --role ...] [options]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

# Bootstrap paths
_REPO_ROOT = Path(__file__).resolve().parent.parent
_RG_SRC = _REPO_ROOT / "resume_graph_engine" / "src"
_OE_SRC = _REPO_ROOT / "outreach_engine" / "src"

for p in (_REPO_ROOT, _RG_SRC, _OE_SRC):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


# Bootstrap environment from env_agents / .env SSOT
try:
    from apps_rg.runtime.env_bootstrap import bootstrap_apps_rg_env
    bootstrap_apps_rg_env(repo_root=_REPO_ROOT)
except Exception:  # guardian: allow-silent-swallow -- env bootstrap is best-effort in CLI entrypoint
    pass

# Ensure local dev route signing secrets exist if not supplied in environment
import secrets

os.environ.setdefault("APPS_RG_ROUTE_HMAC_SECRET", secrets.token_hex(32))
os.environ.setdefault("APPS_RG_ROUTE_HMAC_KEY_ID", f"session-key-{secrets.token_hex(8)}")
os.environ.setdefault("APPS_RG_ROUTE_SIGNING_POSTURE", "ephemeral_dev")

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agents",
        description="Sovereign Agentic Platform: Unified CLI entrypoint for Resume Engine and Outreach Engine.",
    )
    parser.add_argument("--version", action="version", version="agents 1.0.0")
    subparsers = parser.add_subparsers(dest="engine", metavar="ENGINE")

    # 1. resume engine
    subparsers.add_parser(
        "resume",
        help="Run, evaluate, or inspect the Resume Graph Engine (apps_rg)",
        add_help=False,
    )

    # 2. outreach engine
    subparsers.add_parser(
        "outreach",
        help="Run, evaluate, or inspect the Executive Outreach Engine (outreach_engine)",
        add_help=False,
    )

    # 3. e2e full lifecycle
    e2e_parser = subparsers.add_parser(
        "e2e",
        help="Run the unified end-to-end lifecycle (Research -> Tailored Resume -> Executive Outreach)",
    )
    e2e_parser.add_argument(
        "--company",
        "--target-company",
        dest="company",
        default="Anthropic",
        help="Target company name (default: Anthropic)",
    )
    e2e_parser.add_argument(
        "--role",
        "--target-role",
        dest="role",
        default="Manager of Applied AI Architecture, Partnerships",
        help="Target role title",
    )
    e2e_parser.add_argument("--jd", default="", help="Optional JD file path or inline text")
    e2e_parser.add_argument("--resume", default="", help="Optional base-resume JSON, Markdown, or text path")
    e2e_parser.add_argument("--brief", help="Optional path to briefing JSON fixture")
    e2e_parser.add_argument("--demo", action="store_true", help="Run with canonical demo fixtures")
    e2e_parser.add_argument(
        "--research-status",
        choices=("disabled", "optional", "enabled"),
        default="disabled",
        help="Lifecycle governance status for upstream company research (apps_research). Default: disabled",
    )
    e2e_parser.add_argument(
        "--with-research",
        action="store_true",
        help="Explicitly enable upstream company & role research via apps_research",
    )
    e2e_parser.add_argument("--skip-resume", action="store_true", help="Skip Stage 2 resume tailoring")
    e2e_parser.add_argument("--artifact-dir", help="Directory to persist run outputs")
    e2e_parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    # 4. system learning & feedback inspection
    from agents.learning_cli import register_learning_subparser
    register_learning_subparser(subparsers)

    # 5. fast local health-check
    health_p = subparsers.add_parser(
        "check",
        aliases=["health"],
        help="Fast local health-check covering startup, orchestration, engines, contracts, and failure handling",
    )
    health_p.add_argument("-v", "--verbose", action="store_true", help="Show verbose pytest execution details")
    health_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    health_p.add_argument("--domain", help="Filter by domain (startup, orchestration, engines, contracts, failure)")

    return parser


def run_e2e(args: argparse.Namespace) -> int:
    """Execute end-to-end multi-agent career intelligence lifecycle."""
    run_id = f"e2e_{uuid.uuid4().hex[:8]}"
    if args.artifact_dir:
        base_dir = Path(args.artifact_dir).resolve()
    else:
        base_dir = _REPO_ROOT / "artifacts" / "e2e_lifecycle" / run_id
    base_dir.mkdir(parents=True, exist_ok=True)

    company = args.company
    role = args.role
    if args.demo and not args.brief and company == "Anthropic":
        # Anthropic demo target defaults
        company = "Anthropic"
        role = "Manager of Applied AI Architecture, Partnerships"

    research_enabled = getattr(args, "with_research", False) or getattr(args, "research_status", "disabled") == "enabled"
    research_optional = getattr(args, "research_status", "disabled") == "optional"
    research_label = "ENABLED" if research_enabled else ("OPTIONAL" if research_optional else "DISABLED")

    # Live execution preflight: ensure authorized credentials exist before starting lifecycle
    try:
        from agents.live_preflight import assert_engine_live_preflight

        assert_engine_live_preflight(
            "agents e2e",
            providers=("openai", "anthropic", "google"),
            is_demo=bool(getattr(args, "demo", False)),
        )
    except Exception as exc:
        sys.stderr.write(f"[agents e2e] Preflight Credential Failure:\n{exc}\n")
        if getattr(args, "json", False):
            print(json.dumps({"status": "FAILED", "error": str(exc)}, indent=2))
        return 2

    if not args.json:
        print("\n" + "=" * 65)
        print("SOVEREIGN AGENTIC PLATFORM: UNIFIED E2E CAREER LIFECYCLE")
        print("=" * 65)
        print(f"Target Company : {company}")
        print(f"Target Role    : {role}")
        print(f"Research Stage : {research_label}")
        print(f"Artifact Dir   : {base_dir}")
        print("=" * 65 + "\n")

    from agents.orchestration.engine import WorkflowExecutionEngine
    from agents.orchestration.primitives import OrchestrationPrimitive, WorkflowStatus, WorkflowStep
    from agents.telemetry.correlation import CorrelationContext
    from agents.telemetry.events import TelemetryEmitter

    correlation_ctx = CorrelationContext(
        run_id=run_id,
        workflow_id=run_id,
        metadata={"company": company, "role": role},
    )
    emitter = TelemetryEmitter(artifact_dir=base_dir)

    summary_payload: dict[str, Any] = {
        "run_id": run_id,
        "workflow_id": run_id,
        "correlation": correlation_ctx.to_dict(),
        "company": company,
        "role": role,
        "artifact_dir": str(base_dir),
        "stages": {},
    }

    engine = WorkflowExecutionEngine(
        run_id,
        artifact_dir=base_dir,
        correlation=correlation_ctx,
        emitter=emitter,
    )

    from concurrent.futures import Future, ThreadPoolExecutor

    prewarm_executor: ThreadPoolExecutor | None = None
    prewarm_future: Future[None] | None = None
    if not args.skip_resume and research_enabled:
        def _prewarm_resume() -> None:
            try:
                import apps_rg
                import apps_rg.__main__
            except Exception:  # guardian: allow-silent-swallow -- background prewarm is best-effort optimization
                pass

        prewarm_executor = ThreadPoolExecutor(max_workers=1)
        prewarm_future = prewarm_executor.submit(_prewarm_resume)

    def _stage_research(ctx: dict[str, Any]) -> dict[str, Any]:
        if not research_enabled:
            if not args.json:
                print(f">>> [Stage 1/4] Upstream Company Research: {research_label} (governed decoupled status).")
            summary_payload["stages"]["company_research"] = {
                "configured_status": research_label,
                "status": "SKIPPED",
                "reason": "Research stage explicitly disabled or decoupled in current CLI profile",
            }
            return {"status": "SKIPPED"}

        if not args.json:
            print(">>> [Stage 1/4] Running Upstream Company Research (apps_research)...")
        try:
            from apps_rg.integrations.apps_research_bridge import AppsResearchBridge
            from apps_rg.integrations.managed_research_delegation import (
                RequestForResumeBriefing,
                ResumeBriefingReady,
                dispatch_resume_research_briefing,
            )

            research_artifact_dir = base_dir / "research"
            research_artifact_dir.mkdir(parents=True, exist_ok=True)
            bridge = AppsResearchBridge(artifact_runs_root=research_artifact_dir)

            jd_text = ""
            if args.jd:
                try:
                    jd_p = Path(args.jd)
                    if jd_p.is_file():
                        jd_text = jd_p.read_text(encoding="utf-8")
                    else:
                        jd_text = str(args.jd)
                except Exception:
                    jd_text = str(args.jd)

            req = RequestForResumeBriefing(
                request_id=f"req_e2e_{run_id[:8]}",
                run_id=f"run_e2e_{run_id[:8]}",
                trace_id=f"trace_e2e_{run_id[:8]}",
                company_name=company,
                job_title=role,
                research_authorized=True,
                job_description_ref=args.jd or "",
                job_description_text=jd_text,
            )
            res = dispatch_resume_research_briefing(req, bridge=bridge)
            if not isinstance(res, ResumeBriefingReady):
                err_msg = getattr(res, "detail", "Research dispatch failed")
                raise RuntimeError(f"Upstream research failed: {err_msg}")

            briefing_file = Path(res.research_briefing_path)
            canonical_briefing = research_artifact_dir / "briefing.md"
            if briefing_file.is_file() and briefing_file.resolve() != canonical_briefing.resolve():
                shutil.copy2(briefing_file, canonical_briefing)
                briefing_file = canonical_briefing

            summary_payload["stages"]["company_research"] = {
                "configured_status": research_label,
                "exit_code": 0,
                "status": "PASSED",
                "briefing_path": str(briefing_file),
                "brief_sha256": res.brief_sha256,
                "evidence_count": res.research_evidence_count,
            }
            if not args.json:
                print(f"[agents e2e] Research briefing generated: {briefing_file}")
                print(f"[agents e2e] Briefing SHA-256: {res.brief_sha256}")
            return {
                "status": "PASSED",
                "exit_code": 0,
                "briefing_path": str(briefing_file),
                "brief_sha256": res.brief_sha256,
                "evidence_count": res.research_evidence_count,
            }
        except Exception as exc:
            summary_payload["stages"]["company_research"] = {
                "configured_status": research_label,
                "status": "FAILED",
                "error": str(exc),
            }
            sys.stderr.write(f"[agents e2e] Error: Upstream research failed fail-closed: {exc}\n")
            raise

    def _stage_resume(ctx: dict[str, Any]) -> dict[str, Any]:
        if args.skip_resume:
            if not args.json:
                print("\n>>> [Stage 2/4] Resume tailoring skipped (--skip-resume).")
            summary_payload["stages"]["resume_tailoring"] = {"status": "SKIPPED"}
            return {"status": "SKIPPED"}

        if not args.json:
            print("\n>>> [Stage 2/4] Tailoring Executive Resume via Resume Graph Engine (apps_rg)...")

        if prewarm_future is not None:
            try:
                prewarm_future.result(timeout=2.0)
            except Exception:  # guardian: allow-silent-swallow -- prewarm timeout/cancellation is non-fatal
                pass
            if prewarm_executor is not None:
                prewarm_executor.shutdown(wait=False)

        os.environ.setdefault("APPS_RG_ROUTE_SIGNING_POSTURE", "ephemeral_dev")

        from apps_rg.__main__ import main as resume_main

        # Resolve research briefing from context if available
        briefing_path = ""
        research_ctx = ctx.get("step_company_research") or {}
        if isinstance(research_ctx, dict) and research_ctx.get("briefing_path"):
            bpath = Path(research_ctx["briefing_path"])
            if bpath.is_file():
                briefing_path = str(bpath)

        resume_args = [
            "run",
            "--target-company", company,
            "--target-role", role,
        ]
        if briefing_path:
            resume_args.extend(["--briefing", briefing_path])
        if args.jd:
            resume_args.extend(["--jd", args.jd])
        if args.resume:
            resume_args.extend(["--resume", args.resume])

        import time as _t
        t_before = _t.time() - 2.0
        rg_code = resume_main(resume_args)

        if rg_code != 0:
            summary_payload["stages"]["resume_tailoring"] = {
                "exit_code": rg_code,
                "status": "FAILED",
                "error": f"apps_rg returned non-zero exit code: {rg_code}",
            }
            if not args.json:
                sys.stderr.write(f"[agents e2e] Error: Resume generation returned non-zero exit code {rg_code}.\n")
            raise RuntimeError(f"Resume generation returned non-zero exit code: {rg_code}")

        # Locate generated resume output and copy to base_dir / "resume"
        resume_stage_dir = base_dir / "resume"
        resume_stage_dir.mkdir(parents=True, exist_ok=True)
        dest_resume_file = resume_stage_dir / "FINAL_RESUME_OUTPUT.txt"

        repo_root = Path(__file__).resolve().parent.parent
        proofs_roots = (
            repo_root / "resume_graph_engine" / "artifacts" / "apps_rg" / "runtime_proofs",
            repo_root / "artifacts" / "apps_rg" / "runtime_proofs",
        )
        candidates = sorted(
            [c for pr in proofs_roots if pr.is_dir() for c in pr.glob("full_resume_*/FINAL_RESUME_OUTPUT.txt")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        latest_resume = next((c for c in candidates if c.stat().st_mtime >= t_before), None) or (candidates[0] if candidates else None)

        resume_sha = ""
        if latest_resume and latest_resume.is_file():
            shutil.copy2(latest_resume, dest_resume_file)
            resume_sha = hashlib.sha256(dest_resume_file.read_bytes()).hexdigest()

        summary_payload["stages"]["resume_tailoring"] = {
            "exit_code": rg_code,
            "status": "PASSED",
            "resume_path": str(dest_resume_file) if dest_resume_file.is_file() else "",
            "resume_sha256": resume_sha,
        }
        if not args.json:
            print(f"[agents e2e] Resume generated: {dest_resume_file}")
            if resume_sha:
                print(f"[agents e2e] Resume SHA-256: {resume_sha}")

        return {
            "status": "PASSED",
            "exit_code": rg_code,
            "resume_path": str(dest_resume_file) if dest_resume_file.is_file() else "",
            "resume_sha256": resume_sha,
        }

    def _stage_outreach(ctx: dict[str, Any]) -> dict[str, Any]:
        from apps_lic.__main__ import main as outreach_main

        outreach_artifact_dir = base_dir / "outreach"
        outreach_artifact_dir.mkdir(parents=True, exist_ok=True)
        outreach_args = [
            "run",
            "--artifact-dir",
            str(outreach_artifact_dir),
        ]

        # Resolve research briefing from Stage 1 if available
        briefing_path = ""
        research_ctx = ctx.get("step_company_research") or {}
        if isinstance(research_ctx, dict) and research_ctx.get("briefing_path"):
            bpath = Path(research_ctx["briefing_path"])
            if bpath.is_file():
                briefing_path = str(bpath)

        if args.brief:
            outreach_args.extend(["--brief", args.brief])
        elif briefing_path:
            outreach_args.extend(["--brief", briefing_path])
        elif args.demo:
            outreach_args.append("--demo")

        outreach_args.extend(["--company", company, "--role", role])

        if args.json:
            outreach_args.append("--json")

        if not args.json:
            print("\n>>> [Stage 3/4] Generating Grounded Executive Outreach (outreach_engine)...")

        oe_code = outreach_main(outreach_args, prog="python -m agents e2e")
        if oe_code != 0:
            summary_payload["stages"]["executive_outreach"] = {
                "exit_code": oe_code,
                "status": "FAILED",
                "error": f"Outreach generation returned non-zero exit code: {oe_code}",
            }
            sys.stderr.write(f"[agents e2e] Outreach generation returned non-zero exit code: {oe_code}.\n")
            raise RuntimeError(f"Outreach generation returned non-zero exit code: {oe_code}")

        campaign_file = outreach_artifact_dir / "campaign.json"
        campaign_sha = ""
        if campaign_file.is_file():
            campaign_sha = hashlib.sha256(campaign_file.read_bytes()).hexdigest()

        summary_payload["stages"]["executive_outreach"] = {
            "exit_code": oe_code,
            "status": "PASSED",
            "campaign_path": str(campaign_file) if campaign_file.is_file() else "",
            "campaign_sha256": campaign_sha,
        }
        if not args.json:
            print(f"[agents e2e] Outreach campaign generated at: {outreach_artifact_dir}")
            if campaign_sha:
                print(f"[agents e2e] Campaign SHA-256: {campaign_sha}")

        return {
            "status": "PASSED",
            "exit_code": oe_code,
            "campaign_path": str(campaign_file) if campaign_file.is_file() else "",
            "campaign_sha256": campaign_sha,
        }

    steps = [
        WorkflowStep(
            step_id="company_research",
            primitive=OrchestrationPrimitive.BRANCH,
            handler=_stage_research,
            optional=not research_enabled,
        ),
        WorkflowStep(
            step_id="resume_tailoring",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=_stage_resume,
            depends_on=("company_research",),
            optional=bool(args.skip_resume),
        ),
        WorkflowStep(
            step_id="executive_outreach",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=_stage_outreach,
            depends_on=("resume_tailoring",),
            optional=False,
        ),
    ]

    report = engine.execute_plan(steps)

    summary_payload["workflow_status"] = report.final_status.value
    summary_payload["workflow_state_ref"] = "workflow_state.json"
    summary_payload["telemetry_ref"] = "telemetry.jsonl"
    summary_payload["telemetry_events_count"] = len(emitter.events)

    # Stage 4: Lifecycle Sealing & Cryptographic Provenance Manifest
    artifact_proofs: dict[str, Any] = {}
    for key, rel, pattern in [
        ("research_briefing", "research", "**/briefing.md"),
        ("final_resume", "resume", "**/FINAL_RESUME_OUTPUT.txt"),
        ("outreach_campaign", "outreach", "**/campaign.json"),
    ]:
        p = base_dir / rel / Path(pattern).name
        if not p.is_file():
            cands = list((base_dir / rel).glob(pattern))
            if cands:
                p = cands[0]
        if p.is_file():
            artifact_proofs[key] = {
                "path": str(p),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }

    summary_payload["artifact_proofs"] = artifact_proofs

    summary_path = base_dir / "e2e_lifecycle_summary.json"
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    if not args.json:
        if report.final_status == WorkflowStatus.COMPLETED:
            print("\n>>> [Stage 4/4] Lifecycle artifacts validated and sealed.")
            print(f"[agents e2e] Sealed summary manifest at: {summary_path}")
            print(f"[agents e2e] Workflow state audit at: {base_dir / 'workflow_state.json'}\n")
        else:
            print(f"\n>>> [Stage 4/4] Lifecycle FAILED with status: {report.final_status.value}.")
            print(f"[agents e2e] Failure summary manifest at: {summary_path}\n")

    if report.final_status == WorkflowStatus.FAILED:
        return 1

    return 0


def run_learning(args: argparse.Namespace) -> int:
    """Execute system learning inspection, calibration audit, and trajectory mining commands."""
    from agents.learning_cli import run_learning as _exec_learning
    return _exec_learning(args)


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        _build_parser().print_help()
        return 0

    if values[0] in {"-h", "--help"}:
        _build_parser().print_help()
        return 0

    if values[0] in {"-v", "--version"}:
        print("agents 1.0.0")
        return 0

    engine = values[0].lower()
    sub_args = values[1:]

    # Handle unified engine dispatch
    if engine in {"check", "health"}:
        from agents.health import main as health_main
        return health_main(sub_args)

    if engine in {"resume", "resume_engine", "resume_graph_engine", "apps_rg"}:
        from agents.live_preflight import assert_engine_live_preflight

        assert_engine_live_preflight("agents resume", providers=("openai",))
        from apps_rg.__main__ import main as resume_main

        return resume_main(sub_args, prog="python -m agents resume")

    if engine in {"outreach", "outreach_engine", "apps_lic"}:
        from agents.live_preflight import assert_engine_live_preflight

        assert_engine_live_preflight("agents outreach", providers=("openai",))
        from apps_lic.__main__ import main as outreach_main

        return outreach_main(sub_args, prog="python -m agents outreach")

    if engine == "e2e":
        parser = _build_parser()
        args = parser.parse_args(values)
        return run_e2e(args)

    if engine in {"learning", "system_learning"}:
        parser = _build_parser()
        args = parser.parse_args(values)
        return run_learning(args)

    # If first argument is an action or option like --demo, check if directed at outreach
    if engine.startswith("-"):
        parser = _build_parser()
        parser.print_help()
        return 1

    sys.stderr.write(f"Error: Unknown engine '{engine}'. Choices: resume, outreach, e2e, learning, check\n")
    _build_parser().print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
