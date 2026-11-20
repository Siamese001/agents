"""Helper stage runners and argument parser for Unified CLI Entrypoint (`agents/cli.py`)."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agents",
        description="Sovereign Agentic Platform: Unified CLI entrypoint for Resume Engine and Outreach Engine.",
    )
    parser.add_argument("--version", action="version", version="agents 1.0.0")
    subparsers = parser.add_subparsers(dest="engine", metavar="ENGINE")

    subparsers.add_parser(
        "resume",
        help="Run, patch-run, eval, validate, show, preflight, models, cache, or doctor on Resume Graph Engine (apps_rg)",
        add_help=False,
    )
    subparsers.add_parser(
        "outreach",
        help="Run, patch-run, eval, validate, show, preflight, models, cache, or doctor on Executive Outreach Engine (apps_lic)",
        add_help=False,
    )

    e2e_parser = subparsers.add_parser(
        "e2e", help="Run unified end-to-end lifecycle (Research -> Tailored Resume -> Executive Outreach)"
    )
    e2e_parser.add_argument(
        "--company", "--target-company", dest="company", default="Anthropic", help="Target company name (default: Anthropic)"
    )
    e2e_parser.add_argument(
        "--role", "--target-role", dest="role", default="Manager of Applied AI Architecture, Partnerships", help="Target role title"
    )
    e2e_parser.add_argument("--jd", default="", help="Optional JD file path or inline text")
    e2e_parser.add_argument("--resume", default="", help="Optional base-resume JSON, Markdown, or text path")
    e2e_parser.add_argument("--brief", help="Optional path to briefing JSON fixture")
    e2e_parser.add_argument("--demo", action="store_true", help="Run with canonical demo fixtures")
    e2e_parser.add_argument("--offline-smoke", action="store_true", help="Run deterministic offline smoke for both Resume and Outreach engines")
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

    from agents.learning_cli import register_learning_subparser
    register_learning_subparser(subparsers)

    from agents.eval_flywheel_cli import register_eval_flywheel_subparser
    register_eval_flywheel_subparser(subparsers)

    health_p = subparsers.add_parser(
        "check",
        aliases=["health"],
        help="Fast local health-check covering startup, orchestration, engines, contracts, and failure handling",
    )
    health_p.add_argument("-v", "--verbose", action="store_true", help="Show verbose pytest execution details")
    health_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    health_p.add_argument("--domain", help="Filter by domain (startup, orchestration, engines, contracts, failure)")

    return parser


def build_stage_research_handler(
    *,
    args: argparse.Namespace,
    base_dir: Path,
    logs_dir: Path,
    run_id: str,
    company: str,
    role: str,
    research_enabled: bool,
    research_label: str,
    summary_payload: dict[str, Any],
) -> Any:
    """Return stage 1 handler for upstream company research."""

    def _stage_research(_ctx: dict[str, Any]) -> dict[str, Any]:
        t_stage_start = time.perf_counter()
        if not research_enabled:
            if not args.json:
                print(f">>> [Stage 1/4] Upstream Company Research: {research_label} (governed decoupled status).")
            lat_ms = round((time.perf_counter() - t_stage_start) * 1000, 2)
            summary_payload["stages"]["company_research"] = {
                "configured_status": research_label,
                "status": "SKIPPED",
                "reason": "Research stage explicitly disabled or decoupled in current CLI profile",
                "latency_ms": lat_ms,
                "failure_reasons": [],
            }
            return {"status": "SKIPPED"}

        if not args.json:
            print(">>> [Stage 1/4] Running Upstream Company Research (apps_research)...")
        from agents.e2e_output import isolate_child_output

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
                    jd_text = jd_p.read_text(encoding="utf-8") if jd_p.is_file() else str(args.jd)
                except OSError:
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
            with isolate_child_output(logs_dir / "company_research.log"):
                res = dispatch_resume_research_briefing(req, bridge=bridge)
            if not isinstance(res, ResumeBriefingReady):
                err_msg = getattr(res, "detail", "Research dispatch failed")
                raise RuntimeError(f"Upstream research failed: {err_msg}")

            briefing_file = Path(res.research_briefing_path)
            canonical_briefing = research_artifact_dir / "briefing.md"
            if briefing_file.is_file() and briefing_file.resolve() != canonical_briefing.resolve():
                shutil.copy2(briefing_file, canonical_briefing)
                briefing_file = canonical_briefing

            lat_ms = round((time.perf_counter() - t_stage_start) * 1000, 2)
            summary_payload["stages"]["company_research"] = {
                "configured_status": research_label,
                "exit_code": 0,
                "status": "PASSED",
                "briefing_path": str(briefing_file),
                "brief_sha256": res.brief_sha256,
                "evidence_count": res.research_evidence_count,
                "latency_ms": lat_ms,
                "failure_reasons": [],
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
            lat_ms = round((time.perf_counter() - t_stage_start) * 1000, 2)
            stage_status = "BLOCKED" if "blocked" in str(exc).lower() else "FAILED"
            summary_payload["stages"]["company_research"] = {
                "configured_status": research_label,
                "status": stage_status,
                "error": str(exc),
                "latency_ms": lat_ms,
                "failure_reasons": [str(exc)],
            }
            if not args.json:
                sys.stderr.write(f"[agents e2e] Error: Upstream research failed fail-closed: {exc}\n")
            raise

    return _stage_research


def build_stage_resume_handler(
    *,
    args: argparse.Namespace,
    base_dir: Path,
    logs_dir: Path,
    run_id: str,
    company: str,
    role: str,
    prewarm_executor: ThreadPoolExecutor | None,
    prewarm_future: Future[None] | None,
    summary_payload: dict[str, Any],
) -> Any:
    """Return stage 2 handler for resume tailoring."""

    def _stage_resume(ctx: dict[str, Any]) -> dict[str, Any]:
        t_stage_start = time.perf_counter()
        if args.skip_resume:
            if not args.json:
                print("\n>>> [Stage 2/4] Resume tailoring skipped (--skip-resume).")
            lat_ms = round((time.perf_counter() - t_stage_start) * 1000, 2)
            summary_payload["stages"]["resume_tailoring"] = {
                "status": "SKIPPED",
                "reason": "Resume tailoring skipped (--skip-resume)",
                "latency_ms": lat_ms,
                "failure_reasons": [],
            }
            return {"status": "SKIPPED"}

        if not args.json:
            print("\n>>> [Stage 2/4] Tailoring Executive Resume via Resume Graph Engine (apps_rg)...")

        if prewarm_future is not None:
            try:
                prewarm_future.result(timeout=2.0)
            except (TimeoutError, OSError, RuntimeError, ValueError):  # guardian: allow-silent-swallow -- prewarm timeout is non-blocking; proceed to synchronous import
                pass
            if prewarm_executor is not None:
                prewarm_executor.shutdown(wait=False)

        os.environ.setdefault("APPS_RG_ROUTE_SIGNING_POSTURE", "ephemeral_dev")

        from apps_rg.__main__ import main as resume_main
        from agents.e2e_artifacts import (
            resolve_and_verify_resume_artifact,
            resolve_run_scoped_resume_proofs_dir,
            run_offline_deterministic_resume_stage,
        )
        from agents.e2e_output import isolate_child_output

        try:
            if getattr(args, "offline_smoke", False):
                with isolate_child_output(logs_dir / "resume_tailoring.log"):
                    rg_code = run_offline_deterministic_resume_stage(base_dir=base_dir, company=company, role=role, args=args)
            else:
                research_ctx = ctx.get("step_company_research") or {}
                bpath = Path(research_ctx["briefing_path"]) if isinstance(research_ctx, dict) and research_ctx.get("briefing_path") else None
                briefing_path = str(bpath) if bpath and bpath.is_file() else ""
                run_proofs_dir = resolve_run_scoped_resume_proofs_dir(run_id)
                resume_args = ["run", "--target-company", company, "--target-role", role, "--artifact-dir", str(run_proofs_dir)]
                for flag, val in (("--briefing", briefing_path), ("--jd", args.jd), ("--resume", args.resume)):
                    if val:
                        resume_args.extend([flag, val])
                with isolate_child_output(logs_dir / "resume_tailoring.log"):
                    rg_code = resume_main(resume_args)
        except Exception as exc:
            lat_ms, err_type = round((time.perf_counter() - t_stage_start) * 1000, 2), type(exc).__name__
            err_msg = f"{err_type}: {exc}"
            summary_payload["stages"]["resume_tailoring"] = {
                "exit_code": 1, "status": "FAILED", "error_type": err_type, "error": str(exc),
                "latency_ms": lat_ms, "failure_reasons": [err_msg],
            }
            if not args.json:
                sys.stderr.write(f"[agents e2e] Error: Resume generation raised {err_msg}\n")
            raise

        lat_ms = round((time.perf_counter() - t_stage_start) * 1000, 2)
        if rg_code != 0:
            err_msg = f"apps_rg returned non-zero exit code: {rg_code}"
            summary_payload["stages"]["resume_tailoring"] = {
                "exit_code": rg_code, "status": "FAILED", "error_type": "NonZeroExitCode", "error": err_msg,
                "latency_ms": lat_ms, "failure_reasons": [err_msg],
            }
            if not args.json:
                sys.stderr.write(f"[agents e2e] Error: Resume generation returned non-zero exit code {rg_code}.\n")
            raise RuntimeError(err_msg)

        res = resolve_and_verify_resume_artifact(
            run_id=run_id, base_dir=base_dir, rg_code=rg_code, summary_payload=summary_payload, args=args,
        )
        summary_payload["stages"]["resume_tailoring"]["latency_ms"] = lat_ms
        return res

    return _stage_resume


def build_stage_outreach_handler(
    *,
    args: argparse.Namespace,
    base_dir: Path,
    logs_dir: Path,
    company: str,
    role: str,
    research_enabled: bool,
    summary_payload: dict[str, Any],
) -> Any:
    """Return stage 3 handler for executive outreach generation."""

    def _stage_outreach(ctx: dict[str, Any]) -> dict[str, Any]:
        t_stage_start = time.perf_counter()
        from apps_lic.__main__ import main as outreach_main
        from agents.e2e_output import isolate_child_output

        outreach_artifact_dir = base_dir / "outreach"
        outreach_artifact_dir.mkdir(parents=True, exist_ok=True)
        outreach_args = ["run", "--artifact-dir", str(outreach_artifact_dir)]

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
        if getattr(args, "offline_smoke", False):
            outreach_args.append("--offline-smoke")
            if not research_enabled:
                outreach_args.append("--no-research")

        outreach_args.extend(["--company", company, "--role", role])

        if not args.json:
            print("\n>>> [Stage 3/4] Generating Grounded Executive Outreach (outreach_engine)...")

        with isolate_child_output(logs_dir / "executive_outreach.log"):
            oe_code = outreach_main(outreach_args, prog="python -m agents e2e")

        lat_ms = round((time.perf_counter() - t_stage_start) * 1000, 2)
        if oe_code != 0:
            err_msg = f"Outreach generation returned non-zero exit code: {oe_code}"
            summary_payload["stages"]["executive_outreach"] = {
                "exit_code": oe_code, "status": "FAILED", "error": err_msg,
                "latency_ms": lat_ms, "failure_reasons": [err_msg],
            }
            if not args.json:
                sys.stderr.write(f"[agents e2e] Outreach generation returned non-zero exit code: {oe_code}.\n")
            raise RuntimeError(err_msg)

        from agents.e2e_artifacts import resolve_and_verify_outreach_artifact

        res = resolve_and_verify_outreach_artifact(
            outreach_artifact_dir=outreach_artifact_dir,
            oe_code=oe_code,
            outreach_main_callable=outreach_main,
            summary_payload=summary_payload,
            args=args,
        )
        summary_payload["stages"]["executive_outreach"]["latency_ms"] = lat_ms
        return res

    return _stage_outreach
