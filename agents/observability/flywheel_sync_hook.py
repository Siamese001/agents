"""Fast (<1s, $0.00 API cost) stage-only observer hook unifying post-run trace grading, consolidation, and longitudinal sync."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from agents.observability.findings_consolidator import (
    build_failure_clusters,
    consolidate_all_findings,
)
from agents.observability.trace_collector import (
    RunTraceCollector,
    resolve_live_config_digest,
    resolve_live_git_sha,
)
from apps_eval.contracts.digests import canonical_sha256, stable_id
from apps_eval.contracts.schemas import RunTrace, utc_now_iso
from apps_eval.longitudinal import LongitudinalEvalEntry, LongitudinalEvaluationTracker
from apps_eval.online_grader import backfill_online_grades, load_online_eval_records
from apps_eval.triage_promoter import promote_golden_cases
from infrastructure.config.env_loader import get_env_str

logger = logging.getLogger(__name__)
_SYNC_LOCK = threading.Lock()


def record_manifest_to_longitudinal_ledger(
    manifest: Mapping[str, Any] | Path | str,
    *,
    ledger_path: Path,
    repo_root: Path | None = None,
    active_rubric_version: str = "rubric.v1",
) -> dict[str, Any]:
    """Append suite receipts and G5/G6 calibration metrics from evidence_manifest.json into longitudinal_eval_ledger.json."""
    if isinstance(manifest, (str, Path)):
        mp = Path(manifest).resolve()
        if not mp.is_file():
            return {"recorded_entries": 0, "ledger_path": ledger_path.as_posix()}
        data = json.loads(mp.read_text(encoding="utf-8"))
    else:
        data = dict(manifest)

    if not isinstance(data, dict):
        return {"recorded_entries": 0, "ledger_path": ledger_path.as_posix()}

    tracker = LongitudinalEvaluationTracker(ledger_path)
    existing_ids = {e.run_id for e in tracker.entries}
    git_sha = str(data.get("git_sha") or resolve_live_git_sha(repo_root))
    cfg_digest = resolve_live_config_digest(repo_root)[:12]
    pipeline_ver = str(data.get("pipeline_version") or f"git:{git_sha[:12]}:{cfg_digest}")
    rubric_ver = str(data.get("rubric_version") or active_rubric_version)
    gen_at = str(data.get("generated_at") or utc_now_iso())

    recorded = 0
    suite_receipts = data.get("suite_receipts") or {}
    if isinstance(suite_receipts, Mapping):
        for suite_id, rec in sorted(suite_receipts.items()):
            if not isinstance(rec, Mapping):
                continue
            rec_id = str(rec.get("record_id") or "")
            entry_id = rec_id or stable_id("long", suite_id, gen_at, str(rec.get("score", 0.0)), length=16)
            if entry_id in existing_ids:
                continue
            finding_count = int(rec.get("finding_count", 0))
            passed_findings = int(rec.get("passed_findings", 0))
            pass_rate = (passed_findings / float(finding_count)) if finding_count > 0 else 0.0
            score_val = float(rec.get("score", 0.0))
            suite_passed = bool(rec.get("suite_passed", False))
            entry = LongitudinalEvalEntry(
                run_id=entry_id,
                timestamp=gen_at,
                pipeline_version=pipeline_ver,
                rubric_version=rubric_ver,
                benchmark_suite=str(suite_id),
                model_id=str(rec.get("model_id") or "local-deterministic"),
                reasoning_effort=str(rec.get("reasoning_effort") or "low"),
                metrics={
                    "score": round(score_val, 6),
                    "grader_pass_rate": round(pass_rate, 6),
                },
                gates={"suite_passed": suite_passed},
                git_commit=git_sha,
            )
            tracker.record_entry(entry)
            existing_ids.add(entry_id)
            recorded += 1

    g56 = data.get("apps_lic_g5_g6_receipt")
    if isinstance(g56, Mapping) and isinstance(g56.get("g6"), Mapping):
        g6 = g56["g6"]
        g5 = g56.get("g5") if isinstance(g56.get("g5"), Mapping) else {}
        g_entry_id = stable_id("long_g56", gen_at, canonical_sha256(dict(g6))[:12], length=16)
        if g_entry_id not in existing_ids:
            entry = LongitudinalEvalEntry(
                run_id=g_entry_id,
                timestamp=gen_at,
                pipeline_version=pipeline_ver,
                rubric_version=rubric_ver,
                benchmark_suite="apps_lic.g5_g6_calibration",
                model_id="local-deterministic",
                reasoning_effort="low",
                metrics={
                    "spearman_rho": float(g6.get("spearman_rho", 0.0)),
                    "cohens_kappa": float(g6.get("cohens_kappa", 0.0)),
                    "clean_fpr": float(g6.get("fpr", 0.0)),
                    "defect_tpr": float(g6.get("tpr", 0.0)),
                    "g5_max_std": float(g5.get("max_std", 0.0)),
                },
                gates={
                    "g6_passed": bool(g6.get("passed", False)),
                    "g5_passed": bool(g5.get("passed", True)),
                },
                git_commit=git_sha,
            )
            tracker.record_entry(entry)
            existing_ids.add(g_entry_id)
            recorded += 1

    return {
        "recorded_entries": recorded,
        "total_entries": len(tracker.entries),
        "ledger_path": ledger_path.as_posix(),
    }


def sync_flywheel_after_run(
    *,
    repo_root: Path | None = None,
    runtime_root: Path | None = None,
    manifest_payload: Mapping[str, Any] | Path | str | None = None,
    active_rubric_version: str = "rubric.v1",
    force_in_pytest: bool = False,
) -> dict[str, Any] | None:
    """Execute fast (<1s, $0.00) stage-only flywheel sync without mutating git-tracked files inline."""
    if not force_in_pytest and (
        "pytest" in sys.modules or get_env_str("PYTEST_CURRENT_TEST")
    ) and get_env_str("AGENTS_TRACE_IN_PYTEST") != "1":
        return None

    t0 = time.perf_counter()
    base = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[2]
    rt_root = Path(runtime_root).resolve() if runtime_root is not None else (base / "artifacts" / "learning")
    if "output" in [p.lower() for p in rt_root.parts]:
        raise ValueError(f"Refusing to sync flywheel under production output/: {rt_root}")

    with _SYNC_LOCK:
        rt_root.mkdir(parents=True, exist_ok=True)
        from agents.learning.proposal_generator import synthesize_proposals_from_clusters
        from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore

        traces_path = rt_root / "run_traces.jsonl"
        collector = RunTraceCollector(
            traces_path=traces_path,
            cursor_path=rt_root / "run_traces_cursor.json",
            repo_root=base,
        )
        new_traces = collector.drain_new_traces()
        online_ledger = rt_root / "online_eval_ledger.jsonl"
        backfill_res = backfill_online_grades(new_traces, online_ledger)

        all_traces: list[RunTrace] = []
        if traces_path.is_file():
            for line in traces_path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                try:
                    all_traces.append(RunTrace.from_dict(json.loads(s)))
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

        failed_online_ids = [
            str(r.get("trace_id") or "")
            for r in load_online_eval_records(online_ledger)
            if r.get("passed") is False and r.get("trace_id")
        ]

        hitl_db = base / "artifacts" / "governance" / "hitl_decisions.sqlite"
        consol_res = consolidate_all_findings(
            source_root=rt_root,
            output_root=rt_root,
            online_ledger_path=online_ledger,
            hitl_db_path=hitl_db if hitl_db.is_file() else None,
            feedback_db_path=rt_root / "feedback_learning.sqlite",
            triage_root=base / "data" / "eval" / "triage",
        )

        q = SqliteFindingsQueueStore(rt_root / "remediation_queue.sqlite")
        try:
            clusters = build_failure_clusters(q.list_findings(limit=5000))
            golden_res = promote_golden_cases(
                output_dataset_path=rt_root / "golden_eval_cases.json",
                traces=all_traces,
                eligible_clusters=clusters,
                failed_trace_ids=failed_online_ids,
                repo_root=base,
            )
            proposals = synthesize_proposals_from_clusters(
                clusters,
                repo_root=base,
                graduation_state_path=rt_root / "capability_graduation_state.json",
            )
            snapshot = q.export_snapshot(rt_root / "remediation_queue_snapshot.json")
        finally:
            q.close()

        long_ledger_path = rt_root / "longitudinal_eval_ledger.json"
        long_res = {"recorded_entries": 0, "total_entries": 0, "ledger_path": long_ledger_path.as_posix()}
        if manifest_payload is not None:
            long_res = record_manifest_to_longitudinal_ledger(
                manifest_payload,
                ledger_path=long_ledger_path,
                repo_root=base,
                active_rubric_version=active_rubric_version,
            )

        drift_alerts: list[dict[str, Any]] = []
        if long_ledger_path.is_file():
            tracker = LongitudinalEvaluationTracker(long_ledger_path)
            for suite_name in sorted({e.benchmark_suite for e in tracker.entries}):
                suite_entries = [e for e in tracker.entries if e.benchmark_suite == suite_name]
                for mk in sorted({k for e in suite_entries for k in e.metrics.keys()}):
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

        elapsed_s = round(time.perf_counter() - t0, 4)
        summary = {
            "status": "DRIFT_ALERT" if drift_alerts else "SYNCED",
            "exit_code": 2 if drift_alerts else 0,
            "elapsed_s": elapsed_s,
            "marginal_api_cost_usd": 0.0,
            "new_traces_drained": len(new_traces),
            "online_backfill": backfill_res,
            "total_findings": snapshot["total_findings"],
            "cluster_count": consol_res["cluster_count"],
            "golden_cases_total": golden_res["total_cases"],
            "staged_proposals_count": len(proposals),
            "longitudinal": long_res,
            "drift_alerts": drift_alerts,
        }
        return summary
