"""Wave 5 architecture unit tests: Telemetry, Correlation, Calibration & Final Closeout."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.cli import _build_parser, run_e2e
from agents.orchestration.engine import WorkflowExecutionEngine
from agents.orchestration.primitives import OrchestrationPrimitive, WorkflowStep
from agents.telemetry.calibration import (
    CalibrationProfile,
    EvaluationTelemetry,
    EvaluationVerdict,
    JudgeCalibrator,
)
from agents.telemetry.correlation import (
    CorrelationContext,
    get_current_correlation,
    set_current_correlation,
)
from agents.telemetry.events import (
    TelemetryEmitter,
    TelemetryEvent,
    TelemetryEventType,
)


def test_correlation_context_creation_and_child_derivation() -> None:
    """AC-5.1: CorrelationContext creates child spans with provenance and serializes to dict."""
    root = CorrelationContext(
        run_id="run_root_001",
        workflow_id="wf_root_001",
        attempt_id=1,
        provenance_digest="sha256:abcd1234efgh5678",
        metadata={"env": "test"},
    )

    assert root.run_id == "run_root_001"
    assert root.workflow_id == "wf_root_001"
    assert root.parent_span_id is None
    assert root.provenance_digest == "sha256:abcd1234efgh5678"

    # Derive child span
    child = root.new_child("step_resume", metadata={"stage": 1})
    assert child.run_id == root.run_id
    assert child.workflow_id == root.workflow_id
    assert child.parent_span_id == root.span_id
    assert child.span_id != root.span_id
    assert child.metadata["env"] == "test"
    assert child.metadata["step_name"] == "step_resume"
    assert child.metadata["stage"] == 1

    # Round-trip serialization
    payload = child.to_dict()
    restored = CorrelationContext.from_dict(payload)
    assert restored.run_id == child.run_id
    assert restored.span_id == child.span_id
    assert restored.parent_span_id == child.parent_span_id
    assert restored.provenance_digest == child.provenance_digest
    assert restored.metadata == child.metadata


def test_correlation_context_var_binding() -> None:
    """AC-5.1: Correlation context can be bound and retrieved via contextvars."""
    assert get_current_correlation() is None
    ctx = CorrelationContext(run_id="test_run", workflow_id="test_wf")
    token = set_current_correlation(ctx)
    try:
        assert get_current_correlation() is ctx
    finally:
        set_current_correlation(None)
    assert get_current_correlation() is None


def test_telemetry_emitter_event_emission_and_filtering(tmp_path: Path) -> None:
    """AC-5.1: TelemetryEmitter records events in-memory and persists JSONL to disk."""
    emitter = TelemetryEmitter(artifact_dir=tmp_path)
    ctx = CorrelationContext(run_id="run_alpha", workflow_id="wf_alpha")

    # Emit events
    evt1 = emitter.emit(TelemetryEventType.WORKFLOW_START, ctx, {"detail": "init"})
    evt2 = emitter.emit(TelemetryEventType.STEP_START, ctx, {"step": "s1"})

    assert len(emitter.events) == 2
    assert evt1.event_type == TelemetryEventType.WORKFLOW_START
    assert evt2.event_type == TelemetryEventType.STEP_START

    # Filter events
    wf_events = emitter.get_events(TelemetryEventType.WORKFLOW_START)
    assert len(wf_events) == 1
    assert wf_events[0].event_id == evt1.event_id

    alpha_events = emitter.get_events(run_id="run_alpha")
    assert len(alpha_events) == 2

    # Check JSONL persistence
    jsonl_file = tmp_path / "telemetry.jsonl"
    assert jsonl_file.exists()
    lines = [json.loads(line) for line in jsonl_file.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    assert lines[0]["event_type"] == "workflow_start"
    assert lines[0]["correlation"]["run_id"] == "run_alpha"


def test_evaluation_telemetry_and_judge_calibrator() -> None:
    """AC-5.3: JudgeCalibrator evaluates scores against calibrated thresholds and audits drift."""
    profile = CalibrationProfile(
        criterion_thresholds={
            "groundedness": 0.80,
            "relevance": 0.70,
        }
    )
    calibrator = JudgeCalibrator(profile)

    # Pass verdict
    rec_pass = calibrator.evaluate_score(
        evaluator_id="judge_x1",
        criterion="groundedness",
        score=0.92,
        reasoning="Strong empirical groundings",
        latency_ms=124.5,
    )
    assert rec_pass.verdict == EvaluationVerdict.PASS
    assert rec_pass.score == 0.92
    assert rec_pass.threshold == 0.80

    # Warn verdict (within 0.15 margin below threshold)
    rec_warn = calibrator.evaluate_score(
        evaluator_id="judge_x1",
        criterion="groundedness",
        score=0.72,
        reasoning="Borderline citations",
    )
    assert rec_warn.verdict == EvaluationVerdict.WARN

    # Fail verdict
    rec_fail = calibrator.evaluate_score(
        evaluator_id="judge_x1",
        criterion="groundedness",
        score=0.50,
        reasoning="Missing critical citations",
    )
    assert rec_fail.verdict == EvaluationVerdict.FAIL

    # Audit drift calculation
    audit_clean = calibrator.audit_evaluations([rec_pass, rec_pass, rec_warn])
    assert audit_clean["total_records"] == 3
    assert audit_clean["pass_count"] == 2
    assert audit_clean["fail_count"] == 0
    assert audit_clean["drift_detected"] is False

    audit_drift = calibrator.audit_evaluations([rec_pass, rec_fail, rec_fail])
    assert audit_drift["fail_count"] == 2
    assert audit_drift["drift_detected"] is True


def test_workflow_execution_engine_telemetry_integration(tmp_path: Path) -> None:
    """AC-5.2: WorkflowExecutionEngine seamlessly emits correlated events and updates workflow_state.json."""
    engine = WorkflowExecutionEngine("test_corr_wf", artifact_dir=tmp_path)

    step = WorkflowStep(
        step_id="unit_task",
        primitive=OrchestrationPrimitive.SEQUENCE,
        handler=lambda ctx: {"processed": True},
    )

    report = engine.execute_plan([step])
    assert report.success is True

    # Validate workflow_state.json
    state_file = tmp_path / "workflow_state.json"
    assert state_file.exists()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert "correlation" in state_data
    assert state_data["correlation"]["workflow_id"] == "test_corr_wf"
    assert state_data["telemetry_events_count"] >= 4

    # Validate telemetry.jsonl
    telemetry_file = tmp_path / "telemetry.jsonl"
    assert telemetry_file.exists()
    records = [json.loads(line) for line in telemetry_file.read_text(encoding="utf-8").splitlines() if line]
    event_types = [r["event_type"] for r in records]
    assert "workflow_start" in event_types
    assert "step_start" in event_types
    assert "step_complete" in event_types
    assert "workflow_complete" in event_types


def test_cli_e2e_emits_correlated_telemetry_and_manifest(tmp_path: Path) -> None:
    """AC-5.2: agents e2e emits unified correlation metadata in summary manifest and telemetry stream."""
    parser = _build_parser()
    args = parser.parse_args([
        "e2e",
        "--company", "TestCorp",
        "--role", "Lead AI Engineer",
        "--artifact-dir", str(tmp_path),
        "--skip-resume",
        "--demo",
    ])

    with patch("apps_lic.__main__.main", return_value=0) as mock_outreach:
        code = run_e2e(args)
        assert code == 0
        assert mock_outreach.called

    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    assert summary_file.exists()
    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))

    assert "correlation" in summary_data
    assert summary_data["correlation"]["run_id"] == summary_data["run_id"]
    assert summary_data["telemetry_ref"] == "telemetry.jsonl"
    assert summary_data["telemetry_events_count"] > 0

    telemetry_file = tmp_path / "telemetry.jsonl"
    assert telemetry_file.exists()
    records = [json.loads(line) for line in telemetry_file.read_text(encoding="utf-8").splitlines() if line]
    assert len(records) == summary_data["telemetry_events_count"]
