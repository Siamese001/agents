"""Wave 1 tests: Full-fidelity RunTrace provenance, scenario fingerprinting, and scoped failure resolution."""

from __future__ import annotations

import json
import time
from pathlib import Path

from agents.observability.eval_flywheel import EvalFlywheelEngine
from agents.observability.trace_collector import (
    RunTraceCollector,
    build_run_trace,
    compute_scenario_fingerprint,
    emit_post_run_trace_safe,
    resolve_live_config_digest,
    resolve_live_git_sha,
)
from apps_eval.online_grader import grade_run_trace


def test_build_run_trace_populates_live_git_sha_config_digest_and_latency(tmp_path: Path) -> None:
    t0 = time.perf_counter()
    trace = build_run_trace(
        app_id="apps_rg",
        run_id="run-prov-001",
        terminal_status="PASS",
        raw_input={"company": "Anthropic", "role": "Manager, Applied AI Architecture"},
        gate_outcomes={"checks": {"c0_valid": True, "x2_clean": True}},
        telemetry={"elapsed_ms": 142.5},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 200.0
    assert len(trace.git_sha) == 40
    assert trace.git_sha != "0" * 40
    assert trace.git_sha == resolve_live_git_sha()
    assert len(trace.config_digest) == 64
    assert trace.config_digest != "0" * 64
    assert trace.config_digest == resolve_live_config_digest()
    assert trace.telemetry["latency_ms"] == 142.5
    assert trace.gate_outcomes["x2_gates"] == {"c0_valid": True, "x2_clean": True}
    scen_fp = trace.output_summary["scenario_fingerprint"]
    assert scen_fp.startswith("apps_rg::anthropic_")

    graded = grade_run_trace(trace)
    assert graded.passed is True
    assert graded.git_sha == trace.git_sha
    assert graded.metrics["latency_ms"] == 142.5
    assert graded.metrics["x2_pass_rate"] == 1.0


def test_emit_post_run_trace_safe_writes_full_provenance_to_isolated_ledger(tmp_path: Path) -> None:
    traces_file = tmp_path / "run_traces.jsonl"
    emitted = emit_post_run_trace_safe(
        app_id="apps_lic",
        run_id="lic-run-99",
        terminal_status="PASS",
        raw_input={"company": "Truist", "role": "Head of FDE", "channel": "email"},
        output_summary={"status": "PASSED"},
        gate_outcomes={"x2_gates": {"validation_passed": True, "evaluation_passed": True}},
        telemetry={"latency_ms": 88.4},
        traces_path=traces_file,
    )
    assert emitted is not None
    assert traces_file.is_file()
    collector = RunTraceCollector(traces_path=traces_file, cursor_path=tmp_path / "cursor.json")
    drained = collector.drain_new_traces()
    assert len(drained) == 1
    assert drained[0].git_sha != "0" * 40
    assert drained[0].telemetry["latency_ms"] == 88.4
    assert drained[0].gate_outcomes["x2_gates"]["validation_passed"] is True


def test_scoped_resolution_preserves_other_scenarios_and_blocks_smoke_resolution(tmp_path: Path) -> None:
    fw = EvalFlywheelEngine(
        learning_db_path=tmp_path / "learning" / "feedback.sqlite",
        trajectory_store_path=tmp_path / "learning" / "traj.json",
        calibration_history_path=tmp_path / "learning" / "cal.json",
        graduation_state_path=tmp_path / "learning" / "grad.json",
        triage_root=tmp_path / "triage",
    )

    anthropic_fp = compute_scenario_fingerprint(
        app_id="apps_rg",
        raw_input={"company": "Anthropic", "role": "Applied AI"},
    )
    truist_fp = compute_scenario_fingerprint(
        app_id="apps_rg",
        raw_input={"company": "Truist", "role": "Head of FDE"},
    )
    smoke_fp = compute_scenario_fingerprint(
        app_id="apps_rg",
        raw_input={"company": "Anthropic"},
        is_smoke_or_demo=True,
    )

    # 1. Record an Anthropic failure
    fw.ingest_product_run(
        app_id="apps_rg",
        run_id="run-anthropic-fail-1",
        x3_disposition="X3A_DENY_REROUTE",
        passed=False,
        failure_reasons=["section:ibm_narrative:x2_block"],
        score=0.0,
        scenario_fingerprint=anthropic_fp,
    )
    pending_before = fw.list_triage_candidates(app_filter="apps_rg", pending_only=True)
    assert len(pending_before) == 1

    # 2. A passing Truist run MUST NOT resolve the open Anthropic failure or triage packet
    fw.ingest_product_run(
        app_id="apps_rg",
        run_id="run-truist-pass-1",
        x3_disposition="X3D_ALLOW_FINISH",
        passed=True,
        score=1.0,
        scenario_fingerprint=truist_fp,
    )
    pending_after_truist = fw.list_triage_candidates(app_filter="apps_rg", pending_only=True)
    assert len(pending_after_truist) == 1

    fb_store = fw._open_feedback_store()
    try:
        unresolved = [r for r in fb_store.get_failure_statistics() if float(r.get("success_rate") or 0.0) < 1.0]
        assert len(unresolved) == 1
    finally:
        fb_store.close()

    # 3. A passing smoke/demo run MUST NOT resolve the open Anthropic failure either
    fw.ingest_product_run(
        app_id="apps_rg",
        run_id="run-smoke-pass-1",
        x3_disposition="X3D_ALLOW_FINISH",
        passed=True,
        score=1.0,
        scenario_fingerprint=smoke_fp,
        is_smoke_or_demo=True,
    )
    assert len(fw.list_triage_candidates(app_filter="apps_rg", pending_only=True)) == 1

    # 4. A passing non-smoke Anthropic run with matching scenario_fingerprint DOES resolve it
    fw.ingest_product_run(
        app_id="apps_rg",
        run_id="run-anthropic-pass-2",
        x3_disposition="X3D_ALLOW_FINISH",
        passed=True,
        score=1.0,
        scenario_fingerprint=anthropic_fp,
    )
    assert len(fw.list_triage_candidates(app_filter="apps_rg", pending_only=True)) == 0
    fb_store = fw._open_feedback_store()
    try:
        unresolved_after = [r for r in fb_store.get_failure_statistics() if float(r.get("success_rate") or 0.0) < 1.0]
        assert len(unresolved_after) == 0
    finally:
        fb_store.close()
