"""Unified CLI Entrypoint for Resume Engine and Outreach Engine.

Usage:
    python -m agents resume [run|patch-run|eval|validate|show|preflight|models|cache|doctor] [options]
    python -m agents outreach [run|patch-run|eval|validate|show|preflight|models|cache|doctor] [options]
    python -m agents e2e [--company ... --role ...] [options]
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Sequence

from agents._cli_helpers import (
    build_cli_parser,
    build_stage_outreach_handler,
    build_stage_research_handler,
    build_stage_resume_handler,
)

# Bootstrap paths
_REPO_ROOT = Path(__file__).resolve().parent.parent
_RG_SRC = _REPO_ROOT / "resume_graph_engine" / "src"
_OE_SRC = _REPO_ROOT / "outreach_engine" / "src"

for p in (_REPO_ROOT, _RG_SRC, _OE_SRC):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


# Bootstrap environment from env_agents / .env SSOT
try:
    from apps_rg.runtime.env_bootstrap import apply_route_signing_posture, bootstrap_apps_rg_env
    bootstrap_apps_rg_env(repo_root=_REPO_ROOT)
    os.environ.setdefault("APPS_RG_ROUTE_SIGNING_POSTURE", "ephemeral_dev")
    apply_route_signing_posture(repo_root=_REPO_ROOT)
except (ImportError, OSError, RuntimeError, ValueError):  # guardian: allow-silent-swallow -- fallback if apps_rg runtime environment bootstrap is not yet present
    pass

# Ensure local dev route signing secrets exist if not supplied in environment
os.environ.setdefault("APPS_RG_ROUTE_HMAC_SECRET", secrets.token_hex(32))
os.environ.setdefault("APPS_RG_ROUTE_HMAC_KEY_ID", f"session-key-{secrets.token_hex(8)}")
os.environ.setdefault("APPS_RG_ROUTE_SIGNING_POSTURE", "ephemeral_dev")


def _build_parser() -> argparse.ArgumentParser:
    return build_cli_parser()


def run_e2e(args: argparse.Namespace) -> int:
    """Execute end-to-end multi-agent career intelligence lifecycle."""
    import time

    overall_start_tick = time.perf_counter()
    run_id = f"e2e_{uuid.uuid4().hex[:8]}"
    if args.artifact_dir:
        base_dir = Path(args.artifact_dir).resolve()
    else:
        base_dir = _REPO_ROOT / "artifacts" / "e2e_lifecycle" / run_id
    base_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    company = args.company
    role = args.role
    if args.demo and not args.brief and company == "Anthropic":
        company = "Anthropic"
        role = "Manager of Applied AI Architecture, Partnerships"

    research_enabled = getattr(args, "with_research", False) or getattr(args, "research_status", "disabled") == "enabled"
    research_optional = getattr(args, "research_status", "disabled") == "optional"
    research_label = "ENABLED" if research_enabled else ("OPTIONAL" if research_optional else "DISABLED")

    try:
        from agents.live_preflight import assert_engine_live_preflight

        assert_engine_live_preflight(
            "agents e2e",
            providers=("openai", "anthropic", "google"),
            is_demo=bool(getattr(args, "demo", False)),
            allow_offline=bool(getattr(args, "offline_smoke", False)),
        )
    except Exception as exc:
        preflight_latency_ms = round((time.perf_counter() - overall_start_tick) * 1000, 2)
        sys.stderr.write(f"[agents e2e] Preflight Credential Failure:\n{exc}\n")
        if getattr(args, "json", False):
            from agents.e2e_output import emit_authoritative_lifecycle_json

            preflight_payload = {
                "run_id": run_id,
                "status": "BLOCKED",
                "workflow_status": "FAILED",
                "company": company,
                "role": role,
                "artifact_dir": str(base_dir),
                "stages": {
                    "preflight": {
                        "status": "FAILED",
                        "latency_ms": preflight_latency_ms,
                        "error": str(exc),
                        "failure_reasons": [str(exc)],
                    }
                },
                "artifact_hashes": {},
                "artifact_proofs": {},
                "latency": {
                    "total_ms": preflight_latency_ms,
                    "stages_ms": {"preflight": preflight_latency_ms},
                },
                "failure_reasons": [f"Preflight Credential Failure: {exc}"],
            }
            emit_authoritative_lifecycle_json(preflight_payload)
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
    from agents.orchestration.primitives import OrchestrationPrimitive, WorkflowStep
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

    prewarm_executor: ThreadPoolExecutor | None = None
    prewarm_future: Future[None] | None = None
    if not args.skip_resume and research_enabled:
        def _prewarm_resume() -> None:
            try:
                import apps_rg
                import apps_rg.__main__
            except (ImportError, OSError, RuntimeError, ValueError):  # guardian: allow-silent-swallow -- prewarm background import failure is non-fatal
                pass

        prewarm_executor = ThreadPoolExecutor(max_workers=1)
        prewarm_future = prewarm_executor.submit(_prewarm_resume)

    _stage_research = build_stage_research_handler(
        args=args,
        base_dir=base_dir,
        logs_dir=logs_dir,
        run_id=run_id,
        company=company,
        role=role,
        research_enabled=research_enabled,
        research_label=research_label,
        summary_payload=summary_payload,
    )
    _stage_resume = build_stage_resume_handler(
        args=args,
        base_dir=base_dir,
        logs_dir=logs_dir,
        run_id=run_id,
        company=company,
        role=role,
        prewarm_executor=prewarm_executor,
        prewarm_future=prewarm_future,
        summary_payload=summary_payload,
    )
    _stage_outreach = build_stage_outreach_handler(
        args=args,
        base_dir=base_dir,
        logs_dir=logs_dir,
        company=company,
        role=role,
        research_enabled=research_enabled,
        summary_payload=summary_payload,
    )

    is_offline = bool(getattr(args, "offline_smoke", False))
    resume_timeout = 180.0 if is_offline else 900.0
    outreach_timeout = 120.0 if is_offline else 300.0

    steps = [
        WorkflowStep(
            step_id="company_research",
            primitive=OrchestrationPrimitive.BRANCH,
            handler=_stage_research,
            optional=not research_enabled,
            idempotent=True,
            is_product_stage=True,
            timeout=60.0,
        ),
        WorkflowStep(
            step_id="resume_tailoring",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=_stage_resume,
            depends_on=("company_research",),
            optional=bool(args.skip_resume),
            idempotent=False,
            is_product_stage=True,
            timeout=resume_timeout,
        ),
        WorkflowStep(
            step_id="executive_outreach",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=_stage_outreach,
            depends_on=("resume_tailoring",),
            optional=False,
            idempotent=False,
            is_product_stage=True,
            timeout=outreach_timeout,
        ),
    ]

    report = engine.execute_plan(steps)

    summary_payload["workflow_status"] = report.final_status.value
    summary_payload["workflow_state_ref"] = "workflow_state.json"
    summary_payload["telemetry_ref"] = "telemetry.jsonl"
    summary_payload["telemetry_events_count"] = len(emitter.events)

    from agents.e2e_artifacts import seal_lifecycle_manifest

    rc = seal_lifecycle_manifest(
        base_dir=base_dir,
        summary_payload=summary_payload,
        report=report,
        args=args,
        research_enabled=research_enabled,
        overall_start_tick=overall_start_tick,
    )
    from infrastructure.config.env_loader import get_env_str

    if ("pytest" not in sys.modules and not os.environ.get("PYTEST_CURRENT_TEST")) or get_env_str("AGENTS_TRACE_IN_PYTEST") == "1":
        try:
            from agents.observability.eval_flywheel import EvalFlywheelEngine
            from agents.observability.flywheel_sync_hook import sync_flywheel_after_run
            from agents.observability.trace_collector import compute_scenario_fingerprint, emit_post_run_trace_safe

            fw = EvalFlywheelEngine()
            stages = summary_payload.get("stages") or {}
            is_smoke = bool(getattr(args, "offline_smoke", False) or getattr(args, "demo", False))
            total_elapsed_ms = round((time.perf_counter() - overall_start_tick) * 1000.0, 2)
            for stage_key, app_id in (
                ("resume_tailoring", "apps_rg"),
                ("executive_outreach", "apps_lic"),
                ("research", "apps_research"),
            ):
                st = stages.get(stage_key)
                if isinstance(st, dict) and st.get("status") not in (None, "SKIPPED"):
                    ok = str(st.get("status", "")).upper() in ("SUCCESS", "PASS", "PASSED", "COMPLETED")
                    raw_in = {
                        "stage": stage_key,
                        "company": str(getattr(args, "company", "") or ""),
                        "role": str(getattr(args, "role", "") or ""),
                        "research_enabled": research_enabled,
                        "offline_smoke": is_smoke,
                    }
                    scen_fp = compute_scenario_fingerprint(
                        app_id=app_id,
                        raw_input=raw_in,
                        is_smoke_or_demo=is_smoke,
                    )
                    st_reasons = [str(r) for r in (st.get("failure_reasons") or ()) if str(r).strip()]
                    if app_id in ("apps_rg", "apps_lic"):
                        st_x3 = str(st.get("x3_disposition") or "").strip()
                        eff_x3 = (
                            "X3D_ALLOW_FINISH"
                            if ok
                            else (st_x3 if st_x3 and st_x3 != "X3D_ALLOW_FINISH" else "X3A_DENY_REROUTE")
                        )
                        if not ok and not st_reasons:
                            st_reasons = [f"stage_failed:{stage_key}:{st.get('status') or 'FAILED'}"]
                        fw.ingest_product_run(
                            app_id=app_id,
                            run_id=run_id,
                            x3_disposition=eff_x3,
                            passed=ok,
                            failure_reasons=st_reasons,
                            score=1.0 if ok else 0.0,
                            scenario_fingerprint=scen_fp,
                            is_smoke_or_demo=is_smoke,
                        )
                    emit_post_run_trace_safe(
                        app_id=app_id,
                        run_id=run_id,
                        session_id=run_id,
                        terminal_status="PASS" if ok else "FAIL",
                        raw_input=raw_in,
                        output_summary={
                            "workflow_status": summary_payload.get("workflow_status"),
                            "scenario_fingerprint": scen_fp,
                        },
                        gate_outcomes={
                            "failure_reasons": st_reasons,
                            "x2_gates": {f"{stage_key}_passed": bool(ok)},
                        },
                        telemetry={
                            "events_count": summary_payload.get("telemetry_events_count", 0),
                            "latency_ms": float(st.get("latency_ms") or total_elapsed_ms or 1.0),
                        },
                        scenario_fingerprint=scen_fp,
                        is_smoke_or_demo=is_smoke,
                    )
            sync_flywheel_after_run()
        except (ImportError, OSError, ValueError, RuntimeError):  # guardian: allow-silent-swallow -- observer-only flywheel hook must never mutate or fail e2e product runs
            pass
    return rc


def run_learning(args: argparse.Namespace) -> int:
    """Execute system learning inspection, calibration audit, and trajectory mining commands."""
    from agents.learning_cli import run_learning as _exec_learning
    return _exec_learning(args)


def run_eval_flywheel(args: argparse.Namespace) -> int:
    """Execute Resume & Outreach eval harness and closed-loop flywheel commands."""
    from agents.eval_flywheel_cli import run_eval_flywheel as _exec_eval_flywheel
    return _exec_eval_flywheel(args)


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

    if engine in {"check", "health"}:
        from agents.health import main as health_main
        return health_main(sub_args)

    _non_live_subcommands = {
        "eval",
        "show",
        "validate",
        "models",
        "cache",
        "doctor",
        "preflight",
        "patch-run",
    }
    _is_patch_flag = bool(sub_args and sub_args[0].startswith("--patch-run"))
    _needs_live = (
        not any(a in {"-h", "--help", "-v", "--version"} for a in sub_args)
        and not (sub_args and sub_args[0] in _non_live_subcommands)
        and not _is_patch_flag
    )
    if engine in {"resume", "resume_engine", "resume_graph_engine", "apps_rg"}:
        from agents.live_preflight import assert_engine_live_preflight

        if _needs_live:
            assert_engine_live_preflight(
                "agents resume",
                providers=("openai",),
                is_demo=("--demo" in sub_args),
                allow_offline=("--offline-smoke" in sub_args),
            )
        from apps_rg.__main__ import main as resume_main

        return resume_main(sub_args, prog="python -m agents resume")

    if engine in {"outreach", "outreach_engine", "apps_lic"}:
        from agents.live_preflight import assert_engine_live_preflight

        if _needs_live:
            assert_engine_live_preflight(
                "agents outreach",
                providers=("openai",),
                is_demo=("--demo" in sub_args),
                allow_offline=("--offline-smoke" in sub_args),
            )
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

    if engine in {"eval-flywheel", "eval_flywheel"}:
        parser = _build_parser()
        args = parser.parse_args(values)
        return run_eval_flywheel(args)

    if engine.startswith("-"):
        parser = _build_parser()
        parser.print_help()
        return 1

    sys.stderr.write(f"Error: Unknown engine '{engine}'. Choices: resume, outreach, e2e, learning, eval-flywheel, check\n")
    _build_parser().print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
