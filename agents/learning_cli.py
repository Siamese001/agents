"""CLI handlers and parser registration for System Learning, drift audit, triage, and trajectories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def register_learning_subparser(subparsers: Any) -> argparse.ArgumentParser:
    """Register 'learning' and 'system_learning' command subparsers."""
    learning_parser = subparsers.add_parser(
        "learning",
        help="Inspect and audit system learning, calibration drift, triage queue, and golden trajectories",
    )
    learning_sub = learning_parser.add_subparsers(dest="learning_command", metavar="COMMAND")

    status_p = learning_sub.add_parser("status", help="Show aggregate system learning health and failure patterns")
    status_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    drift_p = learning_sub.add_parser("drift", help="Audit judge calibration drift and statistical z-scores")
    drift_p.add_argument("--criterion", help="Specific criterion to inspect")
    drift_p.add_argument("--history-path", default=None, help="Optional calibration history JSON path")
    drift_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    traj_p = learning_sub.add_parser("trajectories", help="Inspect mined golden execution trajectories")
    traj_p.add_argument("--task-type", default="apps_rg", help="Filter by task category (e.g., apps_rg, apps_lic, general)")
    traj_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    rec_p = learning_sub.add_parser(
        "record-lesson",
        help="Record a verified feedback failure signature and resolution lesson",
    )
    rec_p.add_argument("--failure-kind", required=True, help="Failure taxonomy category")
    rec_p.add_argument("--constraint", required=True, help="Normalized failure constraint description")
    rec_p.add_argument("--repair-hint", required=True, help="Verified repair hint")
    rec_p.add_argument("--run-id", required=True, help="Originating run or session identifier")
    rec_p.add_argument("--action-taken", default="OPERATOR_FEEDBACK_RESOLUTION", help="Resolution action code")
    rec_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    triage_p = learning_sub.add_parser("triage-list", help="List ADR-040 staged triage promotion candidates")
    triage_p.add_argument("--app", choices=("all", "apps_rg", "apps_lic"), default="all")
    triage_p.add_argument("--all", dest="include_promoted", action="store_true", help="Include already promoted packets")
    triage_p.add_argument("--triage-root", default=None)
    triage_p.add_argument("--json", action="store_true")

    promo_p = learning_sub.add_parser(
        "promote-candidate",
        help="Human-gated promotion of an ADR-040 triage candidate into an apps_eval suite",
    )
    promo_p.add_argument("candidate_id", help="Triage candidate identifier or packet path")
    promo_p.add_argument("--target", choices=("dev", "holdout"), default="dev")
    promo_p.add_argument("--reviewer", default="operator")
    promo_p.add_argument("--triage-root", default=None)
    promo_p.add_argument("--dry-run", action="store_true")
    promo_p.add_argument("--json", action="store_true")

    grad_p = learning_sub.add_parser("graduation-status", help="Inspect capability-to-regression graduation streaks")
    grad_p.add_argument("--state-path", default=None)
    grad_p.add_argument("--json", action="store_true")

    ingest_p = learning_sub.add_parser("ingest-eval", help="Ingest a sealed evidence_manifest.json into the flywheel")
    ingest_p.add_argument("--manifest", required=True, help="Path to evidence_manifest.json")
    ingest_p.add_argument("--learning-db", default=None)
    ingest_p.add_argument("--triage-root", default=None)
    ingest_p.add_argument("--json", action="store_true")

    return learning_parser


def _resolve_candidate_packet(candidate_id: str, triage_root: str | None) -> Path | None:
    direct = Path(candidate_id)
    if direct.is_file():
        return direct.resolve()
    from agents.observability.eval_flywheel import EvalFlywheelEngine

    engine = EvalFlywheelEngine(triage_root=triage_root)
    for pkt in engine.list_triage_candidates(pending_only=False):
        if pkt.get("candidate_id") == candidate_id:
            return Path(str(pkt["_path"])).resolve()
    return None


def run_learning(args: argparse.Namespace) -> int:
    """Execute system learning inspection, calibration audit, triage, and trajectory commands."""
    cmd = getattr(args, "learning_command", None) or "status"

    if cmd == "status":
        from agents.context.precedent_bridge import RuntimePrecedentBridge
        from agents.observability.eval_flywheel import EvalFlywheelEngine
        from agents.observability.trajectory_learning import (
            DEFAULT_TRAJECTORY_STORE_PATH,
            TrajectoryLearningEngine,
        )
        from agents.orchestration.learning_store import FeedbackLearningStore

        fb_store = FeedbackLearningStore()
        try:
            fb_summary = fb_store.get_summary()
        finally:
            fb_store.close()
        prec_bridge = RuntimePrecedentBridge()
        traj_engine = TrajectoryLearningEngine(store_path=DEFAULT_TRAJECTORY_STORE_PATH)
        fw_engine = EvalFlywheelEngine()

        traj_summary = traj_engine.export_summary()
        prec_factor = prec_bridge.get_category_learning_factor("general")
        cal_status = fw_engine.get_calibration_status()
        pending_triage = fw_engine.list_triage_candidates(pending_only=True)

        payload = {
            "status": "HEALTHY",
            "feedback_learning": fb_summary,
            "trajectory_learning": traj_summary,
            "precedent_bridge_healthy": prec_bridge.is_healthy(),
            "baseline_precedent_factor": prec_factor,
            "calibration_status": cal_status.get("status", "NO_HISTORY"),
            "calibration_alerts": cal_status.get("alerts", []),
            "pending_triage_count": len(pending_triage),
        }

        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print("=== Sovereign Agentic Platform: System Learning Status ===")
            print(f"Store Path:                {fb_summary['store_location']}")
            print(f"Total Failure Signatures:  {fb_summary['total_failure_signatures']}")
            print(f"Total Resolutions Tracked: {fb_summary['total_resolutions_recorded']}")
            print(f"Overall Success Rate:      {fb_summary['overall_success_rate']:.1%}")
            print(f"Precedent Bridge Active:   {prec_bridge.is_healthy()}")
            print(f"Mined Golden Trajectories: {traj_summary['total_golden_trajectories']}")
            print(f"Calibration Status:        {payload['calibration_status']}")
            print(f"Pending Triage Candidates: {payload['pending_triage_count']}")
            if fb_summary["top_failure_patterns"]:
                print("\nTop Recurring Failure Patterns:")
                for pat in fb_summary["top_failure_patterns"]:
                    print(
                        f"  - [{pat['failure_kind']}] {pat['normalized_constraint']}: "
                        f"{pat['occurrence_count']} occurrences, {pat['success_rate']:.1%} resolution"
                    )
        return 0

    if cmd == "drift":
        from agents.observability.eval_flywheel import EvalFlywheelEngine
        from agents.telemetry.calibration import JudgeCalibrator

        calibrator = JudgeCalibrator()
        fw_engine = EvalFlywheelEngine(calibration_history_path=getattr(args, "history_path", None))
        persisted = fw_engine.get_calibration_status()
        crit = getattr(args, "criterion", None)
        drift_map = persisted.get("drift_summary") or {}
        if crit and crit in drift_map:
            entry = drift_map[crit]
            stats = entry.get("stats") or {}
            drift_res = {
                "drift_detected": bool(entry.get("drift_detected", False)),
                "z_score": entry.get("z_score", 0.0),
                "latest": entry.get("latest", 0.0),
                "hard_floor_breach": bool(entry.get("hard_floor_breach", False)),
            }
        else:
            stats = {k: v.get("stats", {}) for k, v in drift_map.items()}
            drift_res = {
                "drift_detected": bool(persisted.get("alerts")),
                "alerts": persisted.get("alerts", []),
                "status": persisted.get("status", "NO_HISTORY"),
            }

        payload = {
            "criterion": crit or "ALL",
            "calibration_thresholds": calibrator.profile.criterion_thresholds,
            "statistical_drift": drift_res,
            "distribution_stats": stats,
            "history_path": persisted.get("history_path", ""),
        }

        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print("=== Judge Calibration & Statistical Drift Audit ===")
            print(f"Criterion:        {crit or 'ALL'}")
            print(f"Drift Detected:   {drift_res.get('drift_detected', False)}")
            print(f"Status:           {persisted.get('status', 'NO_HISTORY')}")
            if persisted.get("alerts"):
                print("Alerts:")
                for alert in persisted["alerts"]:
                    print(f"  - {alert}")
            print("\nBaseline Thresholds:")
            for k, v in calibrator.profile.criterion_thresholds.items():
                print(f"  - {k}: {v:.2f}")
        return 0

    if cmd == "trajectories":
        from agents.observability.trajectory_learning import (
            DEFAULT_TRAJECTORY_STORE_PATH,
            TrajectoryLearningEngine,
        )

        traj_engine = TrajectoryLearningEngine(store_path=DEFAULT_TRAJECTORY_STORE_PATH)
        task_type = getattr(args, "task_type", "apps_rg")
        exemplars = traj_engine.get_exemplars_for_task(task_type)
        payload = {
            "task_type": task_type,
            "count": len(exemplars),
            "exemplars": [e.to_dict() for e in exemplars],
        }

        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print(f"=== Mined Golden Trajectories (Task: {task_type}) ===")
            if not exemplars:
                print("  No golden trajectories indexed for this task type yet.")
            for ex in exemplars:
                print(
                    f"  - [{ex.exemplar_id}] Run: {ex.run_id} | Efficiency: {ex.efficiency_score:.2f} | "
                    f"Steps: {' -> '.join(ex.step_sequence)}"
                )
        return 0

    if cmd == "record-lesson":
        from agents.orchestration.learning_store import FeedbackLearningStore

        fb_store = FeedbackLearningStore()
        try:
            sig_hash = fb_store.record_feedback_lesson(
                args.failure_kind,
                args.constraint,
                run_id=args.run_id,
                repair_hint=args.repair_hint,
                action_taken=getattr(args, "action_taken", "OPERATOR_FEEDBACK_RESOLUTION"),
                outcome="SUCCESS",
            )
            summary = fb_store.get_summary()
        finally:
            fb_store.close()

        payload = {
            "status": "RECORDED",
            "signature_hash": sig_hash,
            "run_id": args.run_id,
            "store_location": summary["store_location"],
            "total_failure_signatures": summary["total_failure_signatures"],
            "total_resolutions_recorded": summary["total_resolutions_recorded"],
        }
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"Recorded lesson [{sig_hash}] for {args.run_id} "
                f"(signatures={summary['total_failure_signatures']}, "
                f"resolutions={summary['total_resolutions_recorded']})."
            )
        return 0

    if cmd == "triage-list":
        from agents.observability.eval_flywheel import EvalFlywheelEngine

        engine = EvalFlywheelEngine(triage_root=getattr(args, "triage_root", None))
        items = engine.list_triage_candidates(
            app_filter=getattr(args, "app", "all"),
            pending_only=not bool(getattr(args, "include_promoted", False)),
        )
        payload = {"count": len(items), "candidates": items}
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print(f"=== ADR-040 Triage Queue ({len(items)} items) ===")
            for item in items:
                print(
                    f"  - [{item.get('candidate_id')}] app={item.get('app_id')} "
                    f"status={item.get('status')} reason={item.get('trigger_reason')}"
                )
        return 0

    if cmd == "promote-candidate":
        from apps_eval.triage_promoter import promote_staged_triage_packet

        pkt_path = _resolve_candidate_packet(args.candidate_id, getattr(args, "triage_root", None))
        if pkt_path is None:
            err = {"status": "ERROR", "error": f"triage candidate not found: {args.candidate_id}"}
            if getattr(args, "json", False):
                print(json.dumps(err, indent=2))
            else:
                print(err["error"])
            return 1
        res = promote_staged_triage_packet(
            pkt_path,
            target_split=args.target,
            reviewer=args.reviewer,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print(f"{res['status']}: {res['scenario_id']} -> {res['suite_id']}")
        return 0

    if cmd == "graduation-status":
        from agents.observability.eval_flywheel import EvalFlywheelEngine

        engine = EvalFlywheelEngine(graduation_state_path=getattr(args, "state_path", None))
        payload = engine.get_graduation_status()
        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print("=== Capability-to-Regression Graduation Status ===")
            print(f"Target Consecutive Passes: {payload.get('consecutive_target')}")
            print(f"Graduation Ready Suites:   {payload.get('graduation_ready_suites', [])}")
        return 0

    if cmd == "ingest-eval":
        from agents.observability.eval_flywheel import EvalFlywheelEngine

        engine = EvalFlywheelEngine(
            learning_db_path=getattr(args, "learning_db", None),
            triage_root=getattr(args, "triage_root", None),
        )
        res = engine.ingest_manifest(args.manifest)
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print(
                f"Ingested {args.manifest}: failures={len(res['harvested_failures'])}, "
                f"resolutions={len(res['recorded_resolutions'])}, "
                f"exemplars={len(res['mined_exemplars'])}, "
                f"triage_staged={len(res['staged_triage_candidates'])}"
            )
        return 0

    return 0
