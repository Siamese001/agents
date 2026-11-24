"""Wave 2 tests: Unified flywheel post-run sync hook and live longitudinal drift ledger wiring."""

from __future__ import annotations

import json
import time
from pathlib import Path

from agents.observability.flywheel_sync_hook import (
    record_manifest_to_longitudinal_ledger,
    sync_flywheel_after_run,
)
from agents.observability.trace_collector import emit_post_run_trace_safe
from apps_eval.longitudinal import LongitudinalEvaluationTracker
from tools.run_eval_flywheel_cycle import run_eval_flywheel_cycle


def test_sync_flywheel_after_run_drains_traces_and_consolidates_under_one_second(tmp_path: Path) -> None:
    rt_root = tmp_path / "learning"
    traces_file = rt_root / "run_traces.jsonl"

    for i in range(4):
        emit_post_run_trace_safe(
            app_id="apps_rg",
            run_id=f"rg-sync-fail-{i}",
            session_id=f"sess-{i % 2}",
            terminal_status="FAIL",
            raw_input={"company": "Anthropic", "role": "Applied AI"},
            gate_outcomes={"x2_gates": {"c0_valid": True, "x2_narrative": False}},
            telemetry={"latency_ms": 120.0},
            traces_path=traces_file,
        )

    t0 = time.perf_counter()
    res = sync_flywheel_after_run(
        runtime_root=rt_root,
        force_in_pytest=True,
    )
    elapsed_s = time.perf_counter() - t0
    assert res is not None
    assert elapsed_s < 1.0
    assert res["new_traces_drained"] == 4
    assert res["online_backfill"]["graded_count"] == 4
    assert res["total_findings"] >= 1
    assert (rt_root / "online_eval_ledger.jsonl").is_file()
    assert (rt_root / "remediation_queue_snapshot.json").is_file()
    assert (rt_root / "golden_eval_cases.json").is_file()


def test_longitudinal_manifest_recording_and_cumulative_anchor_peak_drift_alert(tmp_path: Path) -> None:
    rt_root = tmp_path / "learning"
    rt_root.mkdir(parents=True, exist_ok=True)
    long_ledger = rt_root / "longitudinal_eval_ledger.json"

    scores = (0.980, 0.972, 0.964, 0.956, 0.948)
    for idx, sc in enumerate(scores):
        manifest = {
            "generated_at": f"2026-11-2{idx}T12:00:00Z",
            "git_sha": f"{idx + 1:040x}",
            "rubric_version": "rubric.v1",
            "suite_receipts": {
                "apps_lic.dev.outreach_message": {
                    "record_id": f"rec-lic-{idx}",
                    "finding_count": 100,
                    "passed_findings": int(round(sc * 100)),
                    "score": sc,
                    "suite_passed": True,
                }
            },
            "apps_lic_g5_g6_receipt": {
                "status": "PASS",
                "g6": {
                    "passed": True,
                    "spearman_rho": 0.92,
                    "cohens_kappa": 0.88,
                    "fpr": 0.0,
                    "tpr": 1.0,
                },
                "g5": {
                    "passed": True,
                    "max_std": 0.002,
                },
            },
        }
        rec_res = record_manifest_to_longitudinal_ledger(
            manifest,
            ledger_path=long_ledger,
            active_rubric_version="rubric.v1",
        )
        assert rec_res["recorded_entries"] == 2

    tracker = LongitudinalEvaluationTracker(long_ledger)
    assert len(tracker.entries) == 10

    # Cumulative drop from 0.980 to 0.948 is -3.27% (> 2.0% threshold) -> triggers DRIFT_ALERT (exit_code == 2)
    code, receipt = run_eval_flywheel_cycle(
        repo_root=Path(".").resolve(),
        source_root=rt_root,
        output_root=rt_root,
        sandbox=False,
        active_rubric_version="rubric.v1",
    )
    assert code == 2
    assert any(a["detector"] == "cumulative_anchor_peak" for a in receipt["drift_alerts"])
