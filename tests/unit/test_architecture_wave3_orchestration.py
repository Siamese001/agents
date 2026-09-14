"""tests/unit/test_architecture_wave3_orchestration.py

Wave 3 Orchestration & Agentic Feedback Verification Test Suite:
Validates that:
1. Canonical orchestration primitives and workflow status contracts are strictly typed.
2. Recovery descriptors (ExecutionRetry, SemanticRepair, Replan) are cleanly separated.
3. WorkflowStateMachine enforces valid transitions and rejects illegal state jumps.
4. WorkflowExecutionEngine executes declarative steps, manages dependency flow, and enforces fail-closed behavior.
5. agents.cli.run_e2e executes through WorkflowExecutionEngine and persists workflow_state.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import agents.cli as agents_cli
from agents.orchestration.engine import WorkflowExecutionEngine
from agents.orchestration.primitives import (
    ExecutionRetry,
    OrchestrationPrimitive,
    Replan,
    SemanticRepair,
    WorkflowStatus,
    WorkflowStep,
)
from agents.orchestration.state_machine import (
    InvalidStateTransitionError,
    WorkflowStateMachine,
)


def test_primitives_and_status_contracts():
    """Verify all 10 orchestration primitives and 10 workflow statuses are defined."""
    expected_primitives = {
        "SEQUENCE",
        "BRANCH",
        "PARALLEL",
        "JOIN",
        "RETRY",
        "REPLAN",
        "PAUSE",
        "RESUME",
        "FAIL",
        "COMPLETE",
    }
    assert set(p.value for p in OrchestrationPrimitive) == expected_primitives

    expected_statuses = {
        "CREATED",
        "PLANNED",
        "RUNNING",
        "WAITING",
        "REVIEWING",
        "REPAIRING",
        "PAUSED",
        "CANCELLED",
        "FAILED",
        "COMPLETED",
    }
    assert set(s.value for s in WorkflowStatus) == expected_statuses

    # Terminal vs active checks
    assert WorkflowStatus.COMPLETED.is_terminal is True
    assert WorkflowStatus.FAILED.is_terminal is True
    assert WorkflowStatus.CANCELLED.is_terminal is True
    assert WorkflowStatus.RUNNING.is_terminal is False

    assert WorkflowStatus.RUNNING.is_active is True
    assert WorkflowStatus.REVIEWING.is_active is True
    assert WorkflowStatus.REPAIRING.is_active is True
    assert WorkflowStatus.COMPLETED.is_active is False


def test_recovery_descriptors_distinction():
    """Verify clean separation between technical retry, semantic repair, and cognitive replan."""
    # 1. ExecutionRetry: transient backoff, no reasoning mutation
    retry = ExecutionRetry(attempt=1, max_attempts=3, backoff_seconds=2.0, cause="rate_limit")
    assert retry.can_retry is True
    exhausted_retry = ExecutionRetry(attempt=3, max_attempts=3)
    assert exhausted_retry.can_retry is False

    # 2. SemanticRepair: localized formatting/field patch
    repair = SemanticRepair(
        target_fields=("metrics", "keywords"),
        validation_errors=("missing_percentage",),
        repair_action="format_metrics",
    )
    assert "metrics" in repair.target_fields

    # 3. Replan: cognitive re-evaluation updating plan and subgoals
    replan = Replan(
        cycle=1,
        max_cycles=2,
        critique="Lack of evidence for distributed systems leadership",
        unfulfilled_subgoals=("cite_cluster_scale_metrics",),
        adapted_constraints={"min_bullet_metrics": 3},
    )
    assert replan.can_replan is True
    assert replan.adapted_constraints["min_bullet_metrics"] == 3
    exhausted_replan = Replan(cycle=2, max_cycles=2)
    assert exhausted_replan.can_replan is False


def test_state_machine_valid_and_invalid_transitions():
    """Verify WorkflowStateMachine permits legal flows and raises on illegal state jumps."""
    sm = WorkflowStateMachine("wf_test_001")
    assert sm.current_status == WorkflowStatus.CREATED

    # Legal flow
    sm.transition_to(WorkflowStatus.PLANNED, reason="Plan compiled")
    sm.transition_to(WorkflowStatus.RUNNING, reason="Starting execution")
    sm.transition_to(WorkflowStatus.REVIEWING, reason="Post-execution review")
    sm.transition_to(WorkflowStatus.REPAIRING, reason="Fixing fields")
    sm.transition_to(WorkflowStatus.RUNNING, reason="Re-evaluating")
    sm.transition_to(WorkflowStatus.COMPLETED, reason="All goals satisfied")
    assert sm.current_status == WorkflowStatus.COMPLETED
    assert len(sm.history) == 6

    # Attempting to move out of terminal state raises InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        sm.transition_to(WorkflowStatus.RUNNING)

    # Illegal jump from initial state
    sm2 = WorkflowStateMachine("wf_test_002")
    with pytest.raises(InvalidStateTransitionError):
        sm2.transition_to(WorkflowStatus.REPAIRING)


def test_workflow_execution_engine_sequential_success(tmp_path: Path):
    """Verify WorkflowExecutionEngine executes declarative steps and persists state."""
    engine = WorkflowExecutionEngine("wf_success_001", artifact_dir=tmp_path)

    calls = []

    def step1_handler(ctx: dict) -> dict:
        calls.append("step1")
        return {"data": "step1_ok"}

    def step2_handler(ctx: dict) -> dict:
        calls.append("step2")
        return {"data": "step2_ok"}

    steps = [
        WorkflowStep(
            step_id="first_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=step1_handler,
        ),
        WorkflowStep(
            step_id="second_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=step2_handler,
            depends_on=("first_step",),
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is True
    assert report.final_status == WorkflowStatus.COMPLETED
    assert calls == ["step1", "step2"]

    # Verify workflow_state.json
    state_file = tmp_path / "workflow_state.json"
    assert state_file.is_file()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["final_status"] == "COMPLETED"
    assert state_data["success"] is True
    assert "first_step" in state_data["steps"]
    assert "second_step" in state_data["steps"]


def test_workflow_execution_engine_fail_closed(tmp_path: Path):
    """Verify WorkflowExecutionEngine halts remaining steps on mandatory step failure."""
    engine = WorkflowExecutionEngine("wf_fail_001", artifact_dir=tmp_path)

    calls = []

    def step1_failing(ctx: dict) -> dict:
        calls.append("step1_fail")
        raise RuntimeError("Service unavailable")

    def step2_unreachable(ctx: dict) -> dict:
        calls.append("step2_never")
        return {"data": "should_not_run"}

    steps = [
        WorkflowStep(
            step_id="failing_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=step1_failing,
            metadata={"max_retries": 1},
        ),
        WorkflowStep(
            step_id="downstream_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=step2_unreachable,
            depends_on=("failing_step",),
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert calls == ["step1_fail"]

    state_file = tmp_path / "workflow_state.json"
    assert state_file.is_file()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["final_status"] == "FAILED"
    assert state_data["steps"]["failing_step"]["status"] == "FAILED"


def test_e2e_cli_runs_through_workflow_engine(tmp_path: Path):
    """Verify that agents e2e executes through the workflow engine and writes workflow_state.json."""
    parser = agents_cli._build_parser()
    args = parser.parse_args(["e2e", "--skip-resume", "--demo", "--artifact-dir", str(tmp_path)])

    with patch("apps_lic.__main__.main", return_value=0):
        code = agents_cli.run_e2e(args)
        assert code == 0

    # Verify e2e_lifecycle_summary.json has workflow telemetry
    summary_file = tmp_path / "e2e_lifecycle_summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary["workflow_status"] == "COMPLETED"
    assert summary["workflow_state_ref"] == "workflow_state.json"

    # Verify workflow_state.json
    state_file = tmp_path / "workflow_state.json"
    assert state_file.is_file()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["final_status"] == "COMPLETED"
    assert state_data["success"] is True
    assert "company_research" in state_data["steps"]
    assert "resume_tailoring" in state_data["steps"]
    assert "executive_outreach" in state_data["steps"]


def test_e2e_cli_with_research_fails_closed_through_engine(tmp_path: Path):
    """Verify that enabled research failure causes engine to mark status FAILED."""
    parser = agents_cli._build_parser()
    args = parser.parse_args(["e2e", "--with-research", "--skip-resume", "--artifact-dir", str(tmp_path)])

    code = agents_cli.run_e2e(args)
    assert code != 0

    state_file = tmp_path / "workflow_state.json"
    assert state_file.is_file()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["final_status"] == "FAILED"
    assert state_data["success"] is False
    assert state_data["steps"]["company_research"]["status"] == "FAILED"
