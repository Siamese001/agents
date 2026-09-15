"""Unit tests verifying Wave 2 invariants: typed state contracts, failure taxonomy, and recovery budgets."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from agents.orchestration import (
    ExecutionFailure,
    FailureKind,
    IllegalPhaseTransitionError,
    RecoveryAction,
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
    RevisionRequest,
    RunCheckpoint,
    RunPhase,
    derive_recovery_action,
    validate_and_transition,
)


def test_run_phase_lifecycle_transitions() -> None:
    """Ensure legal phase transitions succeed while illegal transitions fail closed."""
    state = ResumeRunState(
        run_id="run-001",
        workflow_id="wf-test",
        phase=RunPhase.CREATED,
    )

    # Legal: CREATED -> RUNNING
    running_state = validate_and_transition(state, RunPhase.RUNNING)
    assert running_state.phase == RunPhase.RUNNING
    assert running_state.step_index == 1

    # Legal: RUNNING -> REPAIRING
    repairing_state = validate_and_transition(running_state, RunPhase.REPAIRING)
    assert repairing_state.phase == RunPhase.REPAIRING

    # Legal: REPAIRING -> REVISING
    revising_state = validate_and_transition(repairing_state, RunPhase.REVISING)
    assert revising_state.phase == RunPhase.REVISING

    # Legal: REVISING -> RUNNING -> COMPLETED
    resumed_state = validate_and_transition(revising_state, RunPhase.RUNNING)
    completed_state = validate_and_transition(resumed_state, RunPhase.COMPLETED)
    assert completed_state.phase == RunPhase.COMPLETED
    assert completed_state.phase.is_terminal is True

    # Illegal: cannot transition out of COMPLETED terminal state
    with pytest.raises(IllegalPhaseTransitionError):
        validate_and_transition(completed_state, RunPhase.RUNNING)

    # Illegal direct jump: CREATED -> COMPLETED
    with pytest.raises(IllegalPhaseTransitionError):
        validate_and_transition(state, RunPhase.COMPLETED)


def test_independent_recovery_budgets() -> None:
    """Ensure recovery counters track independent limits without cross-contamination."""
    budget = RecoveryBudget(
        max_transport_retries=2,
        max_schema_repairs=1,
        max_semantic_revisions=2,
        max_cognitive_replans=1,
    )
    counters = RecoveryCounters()

    assert counters.is_exhausted(budget, RecoveryAction.TRANSPORT_RETRY) is False
    assert counters.is_exhausted(budget, RecoveryAction.SCHEMA_REPAIR) is False

    # Increment transport retry
    c1 = counters.with_increment(RecoveryAction.TRANSPORT_RETRY)
    assert c1.transport_retries == 1
    assert c1.schema_repairs == 0  # schema repair remains 0

    c2 = c1.with_increment(RecoveryAction.TRANSPORT_RETRY)
    assert c2.transport_retries == 2
    assert c2.is_exhausted(budget, RecoveryAction.TRANSPORT_RETRY) is True
    # Schema repair still available
    assert c2.is_exhausted(budget, RecoveryAction.SCHEMA_REPAIR) is False

    # Exceeding budget via validate_and_transition raises ValueError
    state = ResumeRunState(
        run_id="run-002",
        workflow_id="wf-test",
        phase=RunPhase.RUNNING,
        budget=budget,
        counters=c2,
    )
    with pytest.raises(ValueError, match="Recovery budget exhausted for TRANSPORT_RETRY"):
        validate_and_transition(
            state,
            RunPhase.WAITING,
            recovery_action=RecoveryAction.TRANSPORT_RETRY,
        )


def test_failure_taxonomy_and_recovery_derivation() -> None:
    """Ensure failure kinds map deterministically to appropriate recovery actions."""
    # Transport failure maps to TRANSPORT_RETRY
    action_transport = derive_recovery_action(FailureKind.TRANSPORT, attempt=0, max_limit=3)
    assert action_transport == RecoveryAction.TRANSPORT_RETRY

    # Schema error maps to SCHEMA_REPAIR
    action_schema = derive_recovery_action(FailureKind.SCHEMA, attempt=0, max_limit=2)
    assert action_schema == RecoveryAction.SCHEMA_REPAIR

    # Deterministic quality failure maps to SEMANTIC_REVISION
    action_quality = derive_recovery_action(FailureKind.DETERMINISTIC_QUALITY, attempt=0, max_limit=2)
    assert action_quality == RecoveryAction.SEMANTIC_REVISION

    # Planning failure maps to COGNITIVE_REPLAN
    action_plan = derive_recovery_action(FailureKind.PLANNING, attempt=0, max_limit=1)
    assert action_plan == RecoveryAction.COGNITIVE_REPLAN

    # Policy denial ALWAYS maps to TERMINAL_ESCALATION
    action_policy = derive_recovery_action(FailureKind.POLICY, attempt=0, max_limit=5)
    assert action_policy == RecoveryAction.TERMINAL_ESCALATION
    assert action_policy == RecoveryAction.TERMINAL_FAIL

    # Limit reached maps to TERMINAL_ESCALATION
    action_exhausted = derive_recovery_action(FailureKind.TRANSPORT, attempt=3, max_limit=3)
    assert action_exhausted == RecoveryAction.TERMINAL_ESCALATION
    assert action_exhausted == RecoveryAction.TERMINAL_FAIL


def test_revision_request_validation() -> None:
    """Ensure RevisionRequest validates required feedback attributes and constraints."""
    req = RevisionRequest(
        failure_kind=FailureKind.DETERMINISTIC_QUALITY,
        failed_constraints=("bullet_word_count_exceeded", "missing_metric_quantification"),
        evidence=("Bullet 1 contains 42 words (limit: 30)",),
        allowed_actions=("compress_verbiage", "inject_metrics"),
        attempt_count=1,
        max_revisions=2,
    )
    assert req.can_revise is True

    # Negative attempt count rejected
    with pytest.raises(ValueError, match="attempt_count cannot be negative"):
        RevisionRequest(
            failure_kind=FailureKind.DETERMINISTIC_QUALITY,
            failed_constraints=("constraint",),
            evidence=(),
            allowed_actions=(),
            attempt_count=-1,
        )

    # Empty failed constraints rejected
    with pytest.raises(ValueError, match="requires at least one failed constraint"):
        RevisionRequest(
            failure_kind=FailureKind.SCHEMA,
            failed_constraints=(),
            evidence=(),
            allowed_actions=(),
            attempt_count=0,
        )


def test_checkpoint_integrity_and_tamper_detection() -> None:
    """Ensure RunCheckpoint enforces SHA-256 integrity verification."""
    state = ResumeRunState(
        run_id="run-chk-1",
        workflow_id="wf-chk",
        phase=RunPhase.RUNNING,
        step_index=2,
        context_digest="abc123sha256",
    )
    checkpoint = state.create_checkpoint(sequence=1)
    assert checkpoint.verify_integrity() is True

    # Tampered state fails verification
    tampered_state = ResumeRunState(
        run_id="run-chk-1",
        workflow_id="wf-chk",
        phase=RunPhase.COMPLETED,  # modified phase without updating digest
        step_index=2,
        context_digest="abc123sha256",
    )
    tampered_checkpoint = RunCheckpoint(
        checkpoint_id=checkpoint.checkpoint_id,
        sequence=checkpoint.sequence,
        state=tampered_state,
        state_digest=checkpoint.state_digest,  # original digest
    )
    assert tampered_checkpoint.verify_integrity() is False


def test_resume_run_state_immutability() -> None:
    """Ensure ResumeRunState is strictly immutable and cannot be mutated in-place."""
    state = ResumeRunState(
        run_id="run-imm-1",
        workflow_id="wf-imm",
        phase=RunPhase.CREATED,
    )
    with pytest.raises(FrozenInstanceError):
        state.phase = RunPhase.RUNNING  # type: ignore[misc]


def test_state_machine_and_engine_wave2_integration(tmp_path) -> None:
    """Verify state machine and engine integration with RunPhase and checkpoints."""
    from agents.orchestration.primitives import (
        ExecutionRetry,
        OrchestrationPrimitive,
        Replan,
        SemanticRepair,
        WorkflowStatus,
        WorkflowStep,
    )
    from agents.orchestration.state_machine import WorkflowStateMachine
    from agents.orchestration.engine import WorkflowExecutionEngine

    # 1. Primitives recovery action mapping
    assert ExecutionRetry(attempt=0).recovery_action == "TRANSPORT_RETRY"
    assert SemanticRepair().recovery_action == "SCHEMA_REPAIR"
    assert Replan(cycle=0).recovery_action == "COGNITIVE_REPLAN"

    # 2. State machine RunPhase and checkpoint
    sm = WorkflowStateMachine("wf-integration-001")
    assert sm.current_phase == RunPhase.CREATED
    chk = sm.checkpoint()
    assert chk.state_digest != ""

    sm.transition_to(WorkflowStatus.PLANNED)
    sm.transition_to(WorkflowStatus.RUNNING)
    assert sm.current_phase == RunPhase.RUNNING
    chk2 = sm.checkpoint()
    assert chk2.sequence >= chk.sequence

    # 3. Engine execution and state persistence
    engine = WorkflowExecutionEngine(
        "wf-integration-002",
        artifact_dir=tmp_path,
    )
    step = WorkflowStep(
        step_id="step-1",
        primitive=OrchestrationPrimitive.SEQUENCE,
        handler=lambda ctx: {"data": "ok"},
    )
    report = engine.execute_plan([step])
    assert report.success is True
    assert report.final_status == WorkflowStatus.COMPLETED

    # Checkpoint exists in persisted artifact
    import json
    saved = json.loads((tmp_path / "workflow_state.json").read_text())
    assert "checkpoint" in saved
    assert saved["final_phase"] == "COMPLETED"
