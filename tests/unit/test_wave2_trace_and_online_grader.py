"""Wave 2 unit tests for RunTraceCollector, PII scrubbing, byte-offset cursor, and deterministic OnlineGrader."""

from __future__ import annotations

from pathlib import Path

from agents.observability.trace_collector import (
    RunTraceCollector,
    build_run_trace,
    scrub_pii,
)
from apps_eval.online_grader import (
    backfill_online_grades,
    grade_run_trace,
    load_online_eval_records,
)


def test_pii_scrubbing_removes_emails_phones_ssns_and_tokens() -> None:
    fake_api_token = "sk-" + "1234567890" + "abcdef1234"
    raw = {
        "user_email": "alice.smith@example.com",
        "phone": "555-867-5309",
        "ssn": "123-45-6789",
        "note": f"Use Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 or {fake_api_token}",
        "api_key": "super-secret-value",
    }
    cleaned = scrub_pii(raw)
    serialized = str(cleaned)
    assert "alice.smith@example.com" not in serialized
    assert "555-867-5309" not in serialized
    assert "123-45-6789" not in serialized
    assert fake_api_token not in serialized
    assert "super-secret-value" not in serialized
    assert cleaned["api_key"] == "[REDACTED_SECRET]"


def test_trace_collector_byte_offset_cursor_is_idempotent_across_restarts(tmp_path: Path) -> None:
    traces_file = tmp_path / "run_traces.jsonl"
    cursor_file = tmp_path / "run_traces_cursor.json"

    collector = RunTraceCollector(traces_path=traces_file, cursor_path=cursor_file)
    t1 = build_run_trace(
        app_id="apps_rg",
        run_id="run-01",
        terminal_status="PASS",
        raw_input={"email": "bob@example.com", "role": "VP Engineering"},
        telemetry={"latency_ms": 1200.0, "cost_usd": 0.02},
    )
    t2 = build_run_trace(
        app_id="apps_research",
        run_id="run-02",
        terminal_status="FAIL",
        raw_input={"company": "Acme Corp"},
        gate_outcomes={"x2_gates": {"grounding": False, "schema": True}},
        telemetry={"latency_ms": 4500.0, "cost_usd": 0.01},
    )
    collector.emit(t1)
    collector.emit(t2)

    batch1 = collector.drain_new_traces()
    assert len(batch1) == 2
    assert "bob@example.com" not in str(batch1[0].to_dict())

    # Restarting a fresh collector instance at the same cursor drains 0 duplicates.
    collector2 = RunTraceCollector(traces_path=traces_file, cursor_path=cursor_file)
    assert collector2.drain_new_traces() == []

    # Appending a duplicate of t2 and a brand-new t3 yields only t3.
    t3 = build_run_trace(
        app_id="apps_lic",
        run_id="run-03",
        terminal_status="PASS",
        raw_input={"channel": "linkedin"},
    )
    collector2.emit(t2)
    collector2.emit(t3)
    batch2 = collector2.drain_new_traces()
    assert [t.trace_id for t in batch2] == [t3.trace_id]


def test_online_grader_and_chronological_backfill_zero_api_cost(tmp_path: Path) -> None:
    passing_trace = build_run_trace(
        app_id="apps_rg",
        run_id="r-pass",
        terminal_status="PASS",
        gate_outcomes={"x2_gates": {"g1": True, "g2": True}},
        telemetry={"latency_ms": 1500.0, "cost_usd": 0.01},
        finished_at_utc="2026-11-21T01:00:00Z",
    )
    failing_trace = build_run_trace(
        app_id="apps_lic",
        run_id="r-fail",
        terminal_status="FAIL",
        gate_outcomes={"x2_gates": {"g1": False}},
        telemetry={"latency_ms": 99000.0, "cost_usd": 0.03},
        user_feedback={"hitl_override": True},
        finished_at_utc="2026-11-21T02:00:00Z",
    )

    rec_pass = grade_run_trace(passing_trace)
    assert rec_pass.passed is True
    assert rec_pass.marginal_api_cost_usd == 0.0
    assert rec_pass.verify_digest()

    rec_fail = grade_run_trace(failing_trace)
    assert rec_fail.passed is False
    assert "terminal_success" in rec_fail.failed_gates
    assert "latency_sla" in rec_fail.failed_gates
    assert "no_hitl_override" in rec_fail.failed_gates

    ledger = tmp_path / "online_eval_ledger.jsonl"
    res1 = backfill_online_grades([failing_trace, passing_trace], ledger)
    assert res1["graded_count"] == 2
    assert res1["failed_count"] == 1
    assert res1["marginal_api_cost_usd"] == 0.0

    # Re-running backfill is 100% idempotent.
    res2 = backfill_online_grades([failing_trace, passing_trace], ledger)
    assert res2["graded_count"] == 0
    assert res2["skipped_existing"] == 2
    assert len(load_online_eval_records(ledger)) == 2
