#!/usr/bin/env python3
"""Unified Eval Flywheel Cycle CLI for `agents` (sandbox-capable, $0.00 marginal API cost).

Stages:
1. Drain RunTraces via atomic byte-offset cursor (or read snapshot traces in --sandbox).
2. Deterministic zero-API-cost online grade backfill.
3. Multi-surface findings consolidation (respecting distinct source_root vs output_root).
4. FailureCluster building and 80/20 hash-stratified golden case promotion.
5. Longitudinal drift (anchor-peak + rolling) and Pareto frontier checks.
6. Candidate ImprovementProposal synthesis (staged for shadow replay / policy routing).

Exit codes:
- 0: PASS (healthy cycle, zero drift alerts)
- 1: HARD_FAIL (invalid path, boundary/contract error)
- 2: DRIFT_ALERT (longitudinal rolling or anchor-peak drift detected)
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.learning.proposal_generator import synthesize_proposals_from_clusters
from agents.observability.findings_consolidator import (
    build_failure_clusters,
    consolidate_all_findings,
)
from agents.observability.trace_collector import RunTraceCollector
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from apps_eval.contracts.schemas import RunTrace, utc_now_iso
from apps_eval.longitudinal import LongitudinalEvaluationTracker
from apps_eval.online_grader import backfill_online_grades
from apps_eval.triage_promoter import promote_golden_cases


def _guard_non_output_path(path: Path) -> None:
    resolved = Path(path).resolve()
    if "output" in [p.lower() for p in resolved.parts]:
        raise ValueError(f"Refusing to run flywheel writes under production output/: {resolved}")


def _read_all_traces(traces_path: Path) -> list[RunTrace]:
    if not traces_path.is_file():
        return []
    out: list[RunTrace] = []
    for line in traces_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            out.append(RunTrace.from_dict(json.loads(s)))
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return out


def run_eval_flywheel_cycle(
    *,
    repo_root: Path,
    source_root: Path,
    output_root: Path,
    sandbox: bool = False,
    cutoff_utc: str | None = None,
    active_rubric_version: str = "rubric.v1",
) -> tuple[int, dict[str, Any]]:
    _guard_non_output_path(output_root)
    src = Path(source_root).resolve()
    out = Path(output_root).resolve()
    out.mkdir(parents=True, exist_ok=True)

    traces_file = src / "run_traces.jsonl"
    if sandbox:
        traces = _read_all_traces(traces_file)
    else:
        collector = RunTraceCollector(
            traces_path=traces_file,
            cursor_path=out / "run_traces_cursor.json",
        )
        traces = collector.drain_new_traces()
        if not traces and traces_file.is_file():
            traces = _read_all_traces(traces_file)

    online_ledger = out / "online_eval_ledger.jsonl"
    backfill_res = backfill_online_grades(traces, online_ledger)

    consol_res = consolidate_all_findings(
        source_root=src,
        output_root=out,
        online_ledger_path=online_ledger,
        hitl_db_path=repo_root / "artifacts" / "governance" / "hitl_decisions.sqlite",
        feedback_db_path=src / "feedback_learning.sqlite",
        triage_root=repo_root / "data" / "eval" / "triage",
        cutoff_utc=cutoff_utc,
    )

    q = SqliteFindingsQueueStore(out / "remediation_queue.sqlite")
    try:
        clusters = build_failure_clusters(q.list_findings(limit=5000))
    finally:
        q.close()

    golden_res = promote_golden_cases(
        output_dataset_path=out / "golden_eval_cases.json",
        traces=traces,
        eligible_clusters=clusters,
        repo_root=repo_root,
    )

    proposals = synthesize_proposals_from_clusters(
        clusters,
        repo_root=repo_root,
    )

    # Check longitudinal drift if ledger exists in source_root or output_root.
    drift_alerts: list[dict[str, Any]] = []
    long_ledger = src / "longitudinal_eval_ledger.json"
    if not long_ledger.is_file():
        long_ledger = out / "longitudinal_eval_ledger.json"
    if long_ledger.is_file():
        tracker = LongitudinalEvaluationTracker(long_ledger)
        suites = sorted({e.benchmark_suite for e in tracker.entries})
        for suite_name in suites:
            suite_entries = [e for e in tracker.entries if e.benchmark_suite == suite_name]
            metric_keys = sorted({k for e in suite_entries for k in e.metrics.keys()})
            for mk in metric_keys:
                cum = tracker.detect_cumulative_merge_drift(
                    benchmark_suite=suite_name,
                    metric_name=mk,
                    active_rubric_version=active_rubric_version,
                )
                if cum.get("status") == "DRIFT_ALERT":
                    drift_alerts.append({"detector": "cumulative_anchor_peak", **cum})
                roll = tracker.detect_rolling_window_drift(
                    benchmark_suite=suite_name,
                    metric_name=mk,
                    active_rubric_version=active_rubric_version,
                )
                if roll.get("status") == "DRIFT_ALERT":
                    drift_alerts.append({"detector": "rolling_window", **roll})

    exit_code = 2 if drift_alerts else 0
    receipt = {
        "schema_version": "agents.eval_flywheel_cycle_receipt.v1",
        "executed_at_utc": utc_now_iso(),
        "source_runtime_root": src.as_posix(),
        "output_runtime_root": out.as_posix(),
        "sandbox": sandbox,
        "marginal_api_cost_usd": 0.0,
        "trace_count": len(traces),
        "online_backfill": backfill_res,
        "findings_consolidation": {
            "total_findings": consol_res["total_findings"],
            "counts_by_status": consol_res["counts_by_status"],
            "counts_by_track": consol_res["counts_by_track"],
            "cluster_count": consol_res["cluster_count"],
        },
        "golden_promotion": {
            "total_cases": golden_res["total_cases"],
            "counts_by_split": golden_res["counts_by_split"],
            "dataset_digest": golden_res["dataset_digest"],
        },
        "synthesized_proposals_count": len(proposals),
        "synthesized_proposals": [p.to_dict() for p in proposals],
        "drift_alerts": drift_alerts,
        "exit_code": exit_code,
    }
    receipt_path = out / "flywheel_cycle_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return exit_code, receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute one continuous eval flywheel cycle.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--source-root", default=None, help="Source learning artifacts directory.")
    parser.add_argument("--output-root", default=None, help="Output learning artifacts directory.")
    parser.add_argument("--sandbox", action="store_true", help="Run in an isolated temp output directory.")
    parser.add_argument("--cutoff-utc", default=None, help="Optional ISO-8601 cutoff for archiving legacy findings.")
    parser.add_argument("--rubric-version", default="rubric.v1", help="Active rubric version for drift checks.")
    parser.add_argument("--json", action="store_true", help="Emit full JSON receipt.")
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    src = Path(args.source_root).resolve() if args.source_root else (root / "artifacts" / "learning")

    try:
        if args.sandbox:
            with tempfile.TemporaryDirectory(prefix="agents-flywheel-sandbox-") as td:
                code, receipt = run_eval_flywheel_cycle(
                    repo_root=root,
                    source_root=src,
                    output_root=Path(td),
                    sandbox=True,
                    cutoff_utc=args.cutoff_utc,
                    active_rubric_version=args.rubric_version,
                )
        else:
            out = Path(args.output_root).resolve() if args.output_root else src
            code, receipt = run_eval_flywheel_cycle(
                repo_root=root,
                source_root=src,
                output_root=out,
                sandbox=False,
                cutoff_utc=args.cutoff_utc,
                active_rubric_version=args.rubric_version,
            )
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "HARD_FAIL", "error": str(exc)}, indent=2))
        return 1

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(
            f"[eval-flywheel-cycle] exit={code} traces={receipt['trace_count']} "
            f"findings={receipt['findings_consolidation']['total_findings']} "
            f"golden={receipt['golden_promotion']['total_cases']} "
            f"proposals={receipt['synthesized_proposals_count']} "
            f"drift_alerts={len(receipt['drift_alerts'])}"
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
