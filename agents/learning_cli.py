"""CLI handlers and parser registration for System Learning, drift audit, and trajectory inspection."""

from __future__ import annotations

import argparse
import json
from typing import Any


def register_learning_subparser(subparsers: Any) -> argparse.ArgumentParser:
    """Register 'learning' and 'system_learning' command subparsers."""
    learning_parser = subparsers.add_parser(
        "learning",
        help="Inspect and audit system learning, calibration drift, and golden trajectories",
    )
    learning_sub = learning_parser.add_subparsers(dest="learning_command", metavar="COMMAND")

    status_p = learning_sub.add_parser("status", help="Show aggregate system learning health and failure patterns")
    status_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    drift_p = learning_sub.add_parser("drift", help="Audit judge calibration drift and statistical z-scores")
    drift_p.add_argument("--criterion", help="Specific criterion to inspect")
    drift_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    traj_p = learning_sub.add_parser("trajectories", help="Inspect mined golden execution trajectories")
    traj_p.add_argument("--task-type", default="general", help="Filter by task category")
    traj_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    return learning_parser


def run_learning(args: argparse.Namespace) -> int:
    """Execute system learning inspection, calibration audit, and trajectory mining commands."""
    cmd = getattr(args, "learning_command", None) or "status"

    if cmd == "status":
        from agents.context.precedent_bridge import RuntimePrecedentBridge
        from agents.observability.trajectory_learning import TrajectoryLearningEngine
        from agents.orchestration.learning_store import FeedbackLearningStore

        fb_store = FeedbackLearningStore()
        prec_bridge = RuntimePrecedentBridge()
        traj_engine = TrajectoryLearningEngine()

        fb_summary = fb_store.get_summary()
        traj_summary = traj_engine.export_summary()
        prec_factor = prec_bridge.get_category_learning_factor("general")

        payload = {
            "status": "HEALTHY",
            "feedback_learning": fb_summary,
            "trajectory_learning": traj_summary,
            "precedent_bridge_healthy": prec_bridge.is_healthy(),
            "baseline_precedent_factor": prec_factor,
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
            if fb_summary["top_failure_patterns"]:
                print("\nTop Recurring Failure Patterns:")
                for pat in fb_summary["top_failure_patterns"]:
                    print(
                        f"  - [{pat['failure_kind']}] {pat['normalized_constraint']}: "
                        f"{pat['occurrence_count']} occurrences, {pat['success_rate']:.1%} resolution"
                    )
        return 0

    if cmd == "drift":
        from agents.telemetry.calibration import JudgeCalibrator

        calibrator = JudgeCalibrator()
        crit = getattr(args, "criterion", None)
        stats = calibrator.drift_detector.get_stats(crit) if crit else {}
        drift_res = (
            calibrator.drift_detector.detect_drift(crit, 0.70)
            if crit
            else {"drift_detected": False, "reason": "No criterion specified"}
        )

        payload = {
            "criterion": crit or "ALL",
            "calibration_thresholds": calibrator.profile.criterion_thresholds,
            "statistical_drift": drift_res,
            "distribution_stats": stats,
        }

        if getattr(args, "json", False):
            print(json.dumps(payload, indent=2))
        else:
            print("=== Judge Calibration & Statistical Drift Audit ===")
            print(f"Criterion:        {crit or 'ALL'}")
            print(f"Drift Detected:   {drift_res.get('drift_detected', False)}")
            print(f"Diagnostic:       {drift_res.get('reason', '')}")
            print("\nBaseline Thresholds:")
            for k, v in calibrator.profile.criterion_thresholds.items():
                print(f"  - {k}: {v:.2f}")
        return 0

    if cmd == "trajectories":
        from agents.observability.trajectory_learning import TrajectoryLearningEngine

        traj_engine = TrajectoryLearningEngine()
        task_type = getattr(args, "task_type", "general")
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

    return 0
