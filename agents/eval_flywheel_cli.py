"""Unified CLI handlers for Resume & Outreach Eval Harness and Closed-Loop Flywheel.

Exposes:
    python -m agents eval-flywheel run [--app all|apps_rg|apps_lic] [--mode offline|live] ...
    python -m agents eval-flywheel gate --manifest PATH [--json]
    python -m agents eval-flywheel trend [--records-root PATH] [--app all|apps_rg|apps_lic] [--json]
    python -m agents eval-flywheel promote-baseline --suite SUITE --record PATH [--json]
    python -m agents eval-flywheel status [--json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agents.observability.eval_flywheel import EvalFlywheelEngine
from agents.orchestration.learning_store import resolve_primary_repo_root


def register_eval_flywheel_subparser(subparsers: Any) -> argparse.ArgumentParser:
    """Register 'eval-flywheel' command subparser on the unified agents CLI."""
    ef_parser = subparsers.add_parser(
        "eval-flywheel",
        aliases=["eval_flywheel"],
        help="Run Resume & Outreach evaluation harness, promotion gates, baselines, and closed-loop flywheel",
    )
    ef_sub = ef_parser.add_subparsers(dest="eval_flywheel_command", metavar="COMMAND")

    run_p = ef_sub.add_parser("run", help="Execute unified Resume & Outreach eval harness")
    run_p.add_argument("--app", choices=("all", "apps_rg", "apps_lic"), default="all")
    run_p.add_argument("--mode", choices=("offline", "live"), default="offline")
    run_p.add_argument("--include-holdout", action=argparse.BooleanOptionalAction, default=True)
    run_p.add_argument("--fast-dev", action="store_true", default=False)
    run_p.add_argument("--rg-run-dir", default=None)
    run_p.add_argument("--lic-run-dir", default=None)
    run_p.add_argument("--out-dir", default=None)
    run_p.add_argument("--baseline-dir", default=None)
    run_p.add_argument("--ingest-flywheel", action=argparse.BooleanOptionalAction, default=True)
    run_p.add_argument("--learning-db", default=None)
    run_p.add_argument("--triage-root", default=None)
    run_p.add_argument("--json", action="store_true")

    gate_p = ef_sub.add_parser("gate", help="Verify sealed promotion evidence manifest fail-closed")
    gate_p.add_argument("--manifest", required=True)
    gate_p.add_argument("--require-holdout", action=argparse.BooleanOptionalAction, default=True)
    gate_p.add_argument("--require-engine-probes", action=argparse.BooleanOptionalAction, default=True)
    gate_p.add_argument("--max-score-drop", type=float, default=0.05)
    gate_p.add_argument("--json", action="store_true")

    trend_p = ef_sub.add_parser("trend", help="Build historical trend dashboard over persisted eval records")
    trend_p.add_argument("--records-root", default="artifacts/eval_harness/latest/runs")
    trend_p.add_argument("--out-dir", default="artifacts/eval_harness/latest/trends")
    trend_p.add_argument("--app", choices=("all", "apps_rg", "apps_lic"), default="all")
    trend_p.add_argument("--json", action="store_true")

    promo_p = ef_sub.add_parser("promote-baseline", help="Promote a passing eval record to a named baseline")
    promo_p.add_argument("--suite", required=True)
    promo_p.add_argument("--record", required=True)
    promo_p.add_argument("--baseline-dir", default="apps_eval/baselines")
    promo_p.add_argument("--allow-snapshot-grader-only", action="store_true", default=False)
    promo_p.add_argument("--json", action="store_true")

    status_p = ef_sub.add_parser("status", help="Show combined eval harness, baseline, drift, and triage status")
    status_p.add_argument("--manifest", default="artifacts/eval_harness/latest/evidence_manifest.json")
    status_p.add_argument("--baseline-dir", default="apps_eval/baselines")
    status_p.add_argument("--learning-db", default=None)
    status_p.add_argument("--triage-root", default=None)
    status_p.add_argument("--json", action="store_true")

    return ef_parser


def _emit(payload: dict[str, Any], as_json: bool, title: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"=== {title} ===")
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                print(f"  {key}: {json.dumps(value, sort_keys=True)[:200]}")
            else:
                print(f"  {key}: {value}")


def run_eval_flywheel(args: argparse.Namespace) -> int:
    """Dispatch `python -m agents eval-flywheel <command>`."""
    cmd = getattr(args, "eval_flywheel_command", None) or "status"
    repo_root = Path(__file__).resolve().parents[1]
    as_json = bool(getattr(args, "json", False))

    if cmd == "run":
        from apps_eval.harness_orchestrator import run_unified_eval_harness
        from apps_eval.promotion_gate import verify_promotion_evidence

        manifest = run_unified_eval_harness(
            repo_root,
            app=args.app,
            mode=args.mode,
            include_holdout=bool(args.include_holdout),
            fast_dev=bool(args.fast_dev),
            out_dir=args.out_dir,
            baseline_dir=args.baseline_dir,
            rg_run_dir=args.rg_run_dir,
            lic_run_dir=args.lic_run_dir,
        )
        gate_res = verify_promotion_evidence(
            manifest["manifest_path"],
            require_holdout=bool(args.include_holdout) and not bool(args.fast_dev),
            require_engine_probes=not bool(args.fast_dev),
        )
        flywheel_res: dict[str, Any] = {"status": "SKIPPED"}
        if bool(args.ingest_flywheel):
            engine = EvalFlywheelEngine(
                learning_db_path=args.learning_db,
                triage_root=args.triage_root,
            )
            flywheel_res = engine.ingest_manifest(manifest)

        payload = {
            "status": gate_res.status,
            "exit_code": gate_res.exit_code,
            "manifest_path": manifest["manifest_path"],
            "elapsed_s": manifest.get("elapsed_s", 0.0),
            "promotion_gate": gate_res.to_dict(),
            "flywheel_ingested": bool(args.ingest_flywheel),
            "flywheel": flywheel_res,
        }
        _emit(payload, as_json, "Resume & Outreach Eval Harness Run")
        return gate_res.exit_code

    if cmd == "gate":
        from apps_eval.promotion_gate import verify_promotion_evidence

        gate_res = verify_promotion_evidence(
            args.manifest,
            require_holdout=bool(args.require_holdout),
            require_engine_probes=bool(args.require_engine_probes),
            max_score_drop=float(args.max_score_drop),
        )
        _emit(gate_res.to_dict(), as_json, "Promotion Evidence Gate")
        return gate_res.exit_code

    if cmd == "trend":
        from apps_eval.trends import emit_trend_dashboard

        app_arg = "" if args.app == "all" else args.app
        summary = emit_trend_dashboard(
            records_root=Path(args.records_root),
            app_id=app_arg,
            out_dir=Path(args.out_dir),
            emit_l6_shadow=True,
        )
        payload = summary.to_dict() if hasattr(summary, "to_dict") else dict(summary)
        _emit(payload, as_json, "Eval Harness Trend Dashboard")
        return 0

    if cmd == "promote-baseline":
        from apps_eval.baselines import promote_baseline
        from apps_eval.bootstrap_baselines import SNAPSHOT_GRADER_ONLY_SUITES

        require_pass = not (
            bool(args.allow_snapshot_grader_only) and args.suite in SNAPSHOT_GRADER_ONLY_SUITES
        )
        target = promote_baseline(
            args.record,
            args.suite,
            baseline_dir=args.baseline_dir,
            require_pass=require_pass,
        )
        payload = {
            "status": "PROMOTED",
            "suite": args.suite,
            "baseline_path": target.as_posix(),
        }
        _emit(payload, as_json, "Named Baseline Promotion")
        return 0

    # status
    from apps_eval.bootstrap_baselines import verify_named_baselines
    from apps_eval.promotion_gate import verify_promotion_evidence

    bdir = Path(args.baseline_dir)
    if not bdir.is_absolute():
        bdir = (repo_root / bdir).resolve()
    baselines = verify_named_baselines(baseline_dir=bdir)

    mpath = Path(args.manifest)
    if not mpath.is_absolute():
        mpath = (repo_root / mpath).resolve()
    latest_gate = (
        verify_promotion_evidence(mpath).to_dict()
        if mpath.is_file()
        else {"status": "NOT_RUN", "manifest_path": mpath.as_posix()}
    )

    engine = EvalFlywheelEngine(
        learning_db_path=args.learning_db,
        triage_root=args.triage_root,
    )
    fb_store = engine._open_feedback_store()
    try:
        fb_summary = fb_store.get_summary()
    finally:
        fb_store.close()

    traj_summary = engine._open_trajectory_engine().export_summary()
    cal_status = engine.get_calibration_status()
    grad_status = engine.get_graduation_status()
    pending_triage = engine.list_triage_candidates(pending_only=True)

    payload = {
        "repo_root": resolve_primary_repo_root(repo_root).as_posix(),
        "baselines": baselines,
        "latest_promotion_gate": latest_gate,
        "calibration": cal_status,
        "graduation": grad_status,
        "pending_triage_count": len(pending_triage),
        "feedback_learning": fb_summary,
        "trajectory_learning": traj_summary,
    }
    _emit(payload, as_json, "Eval Harness & Flywheel Status")
    return 0 if baselines.get("status") == "PASS" else 1
