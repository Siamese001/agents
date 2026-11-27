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
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.learning.flywheel_hitl_dispatcher import dispatch_cycle_remediation
from agents.learning.policy_router import load_auto_apply_policy
from agents.learning.proposal_generator import synthesize_proposals_from_clusters
from agents.observability.findings_consolidator import (
    build_failure_clusters,
    consolidate_all_findings,
)
from agents.observability.flywheel_sync_hook import record_manifest_to_longitudinal_ledger
from agents.observability.trace_collector import RunTraceCollector
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from agents.persistence.sqlite.learning_ledger_store import SqliteLearningLedgerStore
from apps_eval.contracts.schemas import HoldoutReplayVerdict, RunTrace, utc_now_iso
from apps_eval.holdout_replay import CandidateRunnerFn
from apps_eval.longitudinal import LongitudinalEvaluationTracker
from apps_eval.online_grader import backfill_online_grades, load_online_eval_records
from apps_eval.triage_promoter import promote_golden_cases


def _snapshot_sqlite_db(source_db: Path, target_db: Path) -> None:
    """Atomically snapshot a SQLite DB (including WAL state) into target_db for sandbox preflight."""
    target_db.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(source_db))
    try:
        dst_conn = sqlite3.connect(str(target_db))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def _resolve_cycle_learning_ledger_path(
    repo_root: Path,
    src: Path,
    out: Path,
    ledger_db_path: Path | None,
    *,
    sandbox: bool,
) -> Path:
    if ledger_db_path is not None:
        return Path(ledger_db_path).resolve()
    canonical_learning_dir = (repo_root / "artifacts" / "learning").resolve()
    live_ledger = canonical_learning_dir / "learning_ledger.sqlite"
    if not sandbox:
        return live_ledger
    sandbox_ledger = out / "learning_ledger.sqlite"
    source_ledger = (
        (src / "learning_ledger.sqlite")
        if (src / "learning_ledger.sqlite").is_file()
        else (live_ledger if src == canonical_learning_dir and live_ledger.is_file() else None)
    )
    if source_ledger is not None and not sandbox_ledger.is_file():
        _snapshot_sqlite_db(source_ledger, sandbox_ledger)
    return sandbox_ledger


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


def _read_operator_corrections(corr_path: Path) -> list[dict[str, Any]]:
    if not corr_path.is_file():
        return []
    retracted: set[str] = set()
    rows: list[dict[str, Any]] = []
    for line in corr_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            if obj.get("retracted") is True and obj.get("correction_id"):
                retracted.add(str(obj["correction_id"]))
            else:
                rows.append(obj)
    return [r for r in rows if str(r.get("correction_id") or "") not in retracted]


def _load_current_bounded_config_values(repo_root: Path) -> dict[str, float]:
    policy = load_auto_apply_policy(repo_root)
    bounds = (policy.get("tier_a_auto_apply") or {}).get("bounded_numeric_parameters") or {}
    loaded_files: dict[str, dict[str, Any]] = {}
    out: dict[str, float] = {}
    for ref in bounds:
        if "::" not in ref:
            continue
        rel_path, dotted_key = ref.split("::", 1)
        if rel_path not in loaded_files:
            cfg_file = Path(repo_root).resolve() / rel_path
            if cfg_file.is_file():
                loaded_files[rel_path] = dict(yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {})
            else:
                loaded_files[rel_path] = {}
        cur: Any = loaded_files[rel_path]
        found = True
        for part in dotted_key.split("."):
            if not isinstance(cur, Mapping) or part not in cur:
                found = False
                break
            cur = cur[part]
        if found and isinstance(cur, (int, float)) and not isinstance(cur, bool):
            out[ref] = float(cur)
    return out


def run_eval_flywheel_cycle(
    *,
    repo_root: Path,
    source_root: Path,
    output_root: Path,
    sandbox: bool = False,
    cutoff_utc: str | None = None,
    active_rubric_version: str = "rubric.v1",
    emit_next_hitl_question: bool = True,
    auto_apply_tier_a: bool = True,
    confidence_margin: float = 0.30,
    holdout_verdicts: Mapping[str, HoldoutReplayVerdict] | None = None,
    canary_metrics_by_proposal: Mapping[str, Mapping[str, Any]] | None = None,
    baseline_metrics_by_proposal: Mapping[str, Mapping[str, Any]] | None = None,
    shadow_runner: CandidateRunnerFn | None = None,
    curated_holdout_seeds: Sequence[Mapping[str, Any]] = (),
    hitl_db_path: Path | None = None,
    ledger_db_path: Path | None = None,
    manifest_payload: Mapping[str, Any] | Path | str | None = None,
    harvest_borderline: bool = False,
    daily_harvest_cap: int = 3,
    fail_on_pending_action: bool = False,
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
    failed_online_ids = [
        str(r.get("trace_id") or "")
        for r in load_online_eval_records(online_ledger)
        if r.get("passed") is False and r.get("trace_id")
    ]

    effective_hitl_db = (
        Path(hitl_db_path).resolve()
        if hitl_db_path is not None
        else (
            (src / "hitl_decisions.sqlite")
            if sandbox and (src / "hitl_decisions.sqlite").is_file()
            else (repo_root / "artifacts" / "governance" / "hitl_decisions.sqlite")
        )
    )
    consol_res = consolidate_all_findings(
        source_root=src,
        output_root=out,
        online_ledger_path=online_ledger,
        hitl_db_path=effective_hitl_db,
        feedback_db_path=src / "feedback_learning.sqlite",
        triage_root=repo_root / "data" / "eval" / "triage",
        cutoff_utc=cutoff_utc,
    )

    golden_path = out / "golden_eval_cases.json"
    operator_corrections = _read_operator_corrections(src / "operator_corrections.jsonl")
    q = SqliteFindingsQueueStore(out / "remediation_queue.sqlite")
    effective_ledger_path = _resolve_cycle_learning_ledger_path(
        repo_root, src, out, ledger_db_path, sandbox=sandbox
    )
    ledger_store = SqliteLearningLedgerStore(effective_ledger_path)
    try:
        clusters = build_failure_clusters(q.list_findings(limit=5000))
        golden_res = promote_golden_cases(
            output_dataset_path=golden_path,
            traces=traces,
            eligible_clusters=clusters,
            operator_corrections=operator_corrections,
            curated_holdout_seeds=curated_holdout_seeds,
            failed_trace_ids=failed_online_ids,
            repo_root=repo_root,
        )
        current_vals = _load_current_bounded_config_values(repo_root)
        grad_path = (
            (out / "capability_graduation_state.json")
            if (out / "capability_graduation_state.json").is_file()
            else (src / "capability_graduation_state.json")
        )
        proposals = synthesize_proposals_from_clusters(
            clusters,
            repo_root=repo_root,
            current_config_values=current_vals,
            graduation_state_path=grad_path,
        )
        dispatch_res = dispatch_cycle_remediation(
            repo_root=repo_root,
            output_root=out,
            queue_store=q,
            clusters=clusters,
            proposals=proposals,
            golden_dataset_path=golden_path,
            ledger_store=ledger_store,
            sandbox=sandbox,
            emit_next_hitl_question=emit_next_hitl_question,
            auto_apply_tier_a=auto_apply_tier_a,
            confidence_margin=confidence_margin,
            holdout_verdicts=holdout_verdicts,
            canary_metrics_by_proposal=canary_metrics_by_proposal,
            baseline_metrics_by_proposal=baseline_metrics_by_proposal,
            shadow_runner=shadow_runner,
        )
        post_snapshot = q.export_snapshot(out / "remediation_queue_snapshot.json")
    finally:
        ledger_store.close()
        q.close()

    # Check longitudinal drift if ledger exists in source_root or output_root.
    drift_alerts: list[dict[str, Any]] = []
    long_ledger = out / "longitudinal_eval_ledger.json"
    if not long_ledger.is_file() and (src / "longitudinal_eval_ledger.json").is_file():
        if sandbox:
            long_ledger.write_bytes((src / "longitudinal_eval_ledger.json").read_bytes())
        else:
            long_ledger = src / "longitudinal_eval_ledger.json"

    eff_manifest: Mapping[str, Any] | Path | str | None = manifest_payload
    if eff_manifest is None:
        canonical_learning_dir = (repo_root / "artifacts" / "learning").resolve()
        harness_base = (
            (repo_root / "artifacts" / "eval_harness")
            if src == canonical_learning_dir
            else (src.parent / "eval_harness")
        )
        for cand_m in (
            harness_base / "ci_latest" / "evidence_manifest.json",
            harness_base / "latest" / "evidence_manifest.json",
        ):
            if cand_m.is_file():
                eff_manifest = cand_m
                break
    if eff_manifest is not None:
        record_manifest_to_longitudinal_ledger(
            eff_manifest,
            ledger_path=long_ledger,
            repo_root=repo_root,
            active_rubric_version=active_rubric_version,
        )

    if long_ledger.is_file():
        tracker = LongitudinalEvaluationTracker(long_ledger)
        suites = sorted({e.benchmark_suite for e in tracker.entries})
        for suite_name in suites:
            suite_entries = [e for e in tracker.entries if e.benchmark_suite == suite_name]
            metric_keys = sorted({k for e in suite_entries for k in e.metrics.keys()})
            for mk in metric_keys:
                if mk == "clean_fpr":
                    continue
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

    harvest_summary: dict[str, Any] = {"harvested_count": 0}
    if harvest_borderline:
        from apps_eval._core_governance_bridge import harvest_borderline_candidates

        cands = [
            {
                **r,
                "case_id": r.get("trace_id") or r.get("run_id"),
                "surface": r.get("surface") or r.get("app_id") or "agents_core",
                "groundedness": (r.get("metrics") or {}).get("groundedness", r.get("groundedness")),
                "prompt_text": r.get("prompt_text") or r.get("input_summary") or f"Trace {r.get('trace_id')}",
                "output_text": r.get("output_text") or r.get("output_summary") or "",
            }
            for r in load_online_eval_records(online_ledger)
        ]
        harvest_summary = harvest_borderline_candidates(
            cands, out / "judge_calibration_queue.jsonl", daily_cap=daily_harvest_cap
        )

    has_pending_action = bool(
        int(dispatch_res.get("pending_hitl_count", 0)) > 0
        or int(dispatch_res.get("auto_applied_count", 0)) > 0
    )
    if drift_alerts:
        exit_code = 2
    elif fail_on_pending_action and has_pending_action:
        exit_code = 3
    else:
        exit_code = 0
    receipt = {
        "schema_version": "agents.eval_flywheel_cycle_receipt.v1",
        "executed_at_utc": utc_now_iso(),
        "source_runtime_root": src.as_posix(),
        "output_runtime_root": out.as_posix(),
        "sandbox": sandbox,
        "emit_next_hitl_question": emit_next_hitl_question,
        "marginal_api_cost_usd": 0.0,
        "trace_count": len(traces),
        "online_backfill": backfill_res,
        "borderline_harvest": harvest_summary,
        "findings_consolidation": {
            "total_findings": post_snapshot["total_findings"],
            "counts_by_status": post_snapshot["counts_by_status"],
            "counts_by_track": post_snapshot["counts_by_track"],
            "cluster_count": consol_res["cluster_count"],
        },
        "golden_promotion": {
            "total_cases": golden_res["total_cases"],
            "counts_by_split": golden_res["counts_by_split"],
            "dataset_digest": golden_res["dataset_digest"],
        },
        "synthesized_proposals_count": len(proposals),
        "synthesized_proposals": [p.to_dict() for p in proposals],
        "auto_apply_dispatch": {
            "auto_applied_count": dispatch_res["auto_applied_count"],
            "auto_applied": dispatch_res["auto_applied"],
            "rolled_back_count": dispatch_res["rolled_back_count"],
            "rolled_back": dispatch_res["rolled_back"],
            "pending_hitl_count": dispatch_res["pending_hitl_count"],
            "policy_decisions": dispatch_res["policy_decisions"],
        },
        "next_ask_question_payload": dispatch_res["next_ask_question_payload"],
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
    parser.add_argument(
        "--emit-next-hitl-question",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Auto-apply eligible Tier A updates and attach next single ask_question payload (default: enabled).",
    )
    parser.add_argument("--harvest-borderline", action="store_true", help="Harvest <=3 topic-diverse borderline runs/day.")
    parser.add_argument("--daily-harvest-cap", type=int, default=3)
    parser.add_argument(
        "--fail-on-pending-action",
        action="store_true",
        help="Return exit code 3 when pending HITL or auto-applied proposals exist so preflight does not fast-exit.",
    )
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
                    emit_next_hitl_question=args.emit_next_hitl_question,
                    harvest_borderline=args.harvest_borderline,
                    daily_harvest_cap=args.daily_harvest_cap,
                    fail_on_pending_action=args.fail_on_pending_action,
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
                emit_next_hitl_question=args.emit_next_hitl_question,
                harvest_borderline=args.harvest_borderline,
                daily_harvest_cap=args.daily_harvest_cap,
                fail_on_pending_action=args.fail_on_pending_action,
            )
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "HARD_FAIL", "error": str(exc)}, indent=2))
        return 1

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        dispatch = receipt.get("auto_apply_dispatch") or {}
        has_q = receipt.get("next_ask_question_payload") is not None
        print(
            f"[eval-flywheel-cycle] exit={code} traces={receipt['trace_count']} "
            f"findings={receipt['findings_consolidation']['total_findings']} "
            f"golden={receipt['golden_promotion']['total_cases']} "
            f"proposals={receipt['synthesized_proposals_count']} "
            f"auto_applied={dispatch.get('auto_applied_count', 0)} "
            f"pending_hitl={dispatch.get('pending_hitl_count', 0)} "
            f"next_hitl_question={'1' if has_q else '0'} "
            f"drift_alerts={len(receipt['drift_alerts'])}"
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
