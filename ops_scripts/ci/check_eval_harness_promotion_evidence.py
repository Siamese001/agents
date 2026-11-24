#!/usr/bin/env python3
"""Canonical CI and Readiness Promotion Gate for the Resume & Outreach Eval Harness.

Supports two execution modes:
1. ``--manifest <path>``: verify an existing sealed ``evidence_manifest.json`` fail-closed.
2. ``--run-offline``: execute the deterministic offline Resume (``apps_rg``) & Outreach
   (``apps_lic``) evaluation harness, verify all receipts against named baselines and
   G5/G6 calibration floors, and optionally ingest telemetry into the learning flywheel.

Exit codes:
    0: PASS
    1: BLOCKED (missing receipt, invalid schema, probe failure, or calibration failure)
    2: REGRESSION (baseline score drop or regression verdict)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from apps_eval.harness_orchestrator import run_unified_eval_harness
from apps_eval.promotion_gate import verify_promotion_evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed CI/readiness promotion gate for Resume & Outreach eval harness."
    )
    parser.add_argument("--repo-root", default=str(_REPO_ROOT), help="Repository root path")
    parser.add_argument("--manifest", default=None, help="Existing sealed evidence_manifest.json to verify")
    parser.add_argument(
        "--run-offline",
        action="store_true",
        default=False,
        help="Execute deterministic offline Resume & Outreach harness before verifying promotion gate",
    )
    parser.add_argument(
        "--fast-dev",
        action="store_true",
        default=False,
        help="Fast dev-only mode for git pre-push (dev suites + G5/G6 calibration + baseline check)",
    )
    parser.add_argument("--app", choices=("all", "apps_rg", "apps_lic"), default="all")
    parser.add_argument("--out-dir", default=None, help="Directory for harness artifacts when --run-offline is used")
    parser.add_argument("--out", default=None, help="Optional path to write final_gate_report.json")
    parser.add_argument("--max-score-drop", type=float, default=0.05)
    parser.add_argument(
        "--ingest-flywheel",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Optionally ingest the run manifest into EvalFlywheelEngine stores",
    )
    parser.add_argument("--json", action="store_true", default=False)
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    manifest_path: Path
    manifest_payload: dict[str, Any] | None = None

    if args.run_offline:
        target_out = (
            Path(args.out_dir).resolve()
            if args.out_dir
            else (repo_root / "artifacts" / "eval_harness" / "ci_latest").resolve()
        )
        manifest_payload = run_unified_eval_harness(
            repo_root,
            app=args.app,
            mode="offline",
            include_holdout=not bool(args.fast_dev),
            fast_dev=bool(args.fast_dev),
            out_dir=target_out,
        )
        manifest_path = Path(manifest_payload["manifest_path"]).resolve()
    elif args.manifest:
        manifest_path = Path(args.manifest).resolve()
    else:
        manifest_path = (repo_root / "artifacts" / "eval_harness" / "latest" / "evidence_manifest.json").resolve()

    gate_res = verify_promotion_evidence(
        manifest_path,
        require_holdout=not bool(args.fast_dev),
        require_engine_probes=not bool(args.fast_dev),
        max_score_drop=float(args.max_score_drop),
    )

    flywheel_summary: dict[str, Any] | None = None
    if bool(args.ingest_flywheel) and manifest_path.is_file():
        from agents.observability.eval_flywheel import EvalFlywheelEngine
        from agents.observability.flywheel_sync_hook import sync_flywheel_after_run

        flywheel_summary = EvalFlywheelEngine().ingest_manifest(manifest_payload or manifest_path)
        sync_res = sync_flywheel_after_run(
            repo_root=repo_root,
            manifest_payload=manifest_payload or manifest_path,
        )
        if sync_res is not None:
            flywheel_summary["unified_sync"] = sync_res

    report = gate_res.to_dict()
    if flywheel_summary is not None:
        report["flywheel"] = flywheel_summary

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (repo_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"[EVAL HARNESS GATE: {gate_res.status}] "
            f"checks_passed={sum(1 for ok in gate_res.checks.values() if ok)}/{len(gate_res.checks)} "
            f"manifest={gate_res.manifest_path}"
        )
        for reason in gate_res.regression_reasons:
            print(f"  [REGRESSION] {reason}", file=sys.stderr)
        for reason in gate_res.blocking_reasons:
            print(f"  [BLOCKED] {reason}", file=sys.stderr)

    return gate_res.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
