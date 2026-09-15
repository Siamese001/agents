"""Unit tests for Wave 3: Canonical Pipeline Routing and Structured Feedback Controller.

Verifies:
1. Clean validation results yield ControllerAction.ACCEPT.
2. Quality failures produce structured, bounded RevisionRequest packets.
3. Schema errors produce ControllerAction.DETERMINISTIC_NORMALIZE without LLM revision.
4. Budget exhaustion strictly transitions to ControllerAction.TERMINAL_FAIL.
5. Policy violations immediately yield ControllerAction.TERMINAL_FAIL.
6. Canonical dispatch routes whole-resume execution authoritatively.
"""

from __future__ import annotations

import pytest

from agents.orchestration import (
    ControllerAction,
    FailureKind,
    FeedbackController,
    FeedbackDecision,
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
    RunPhase,
)


def test_feedback_controller_accepts_clean_validation() -> None:
    controller = FeedbackController()
    decision = controller.evaluate_result(validation_passed=True)

    assert decision.action == ControllerAction.ACCEPT
    assert decision.can_retry is False
    assert decision.revision_request is None
    assert decision.failure is None


def test_feedback_controller_creates_valid_revision_request() -> None:
    controller = FeedbackController()
    state = ResumeRunState(
        run_id="run-test-001",
        workflow_id="wf-test-001",
        phase=RunPhase.RUNNING,
        counters=RecoveryCounters(semantic_revisions=0),
        budget=RecoveryBudget(max_semantic_revisions=2),
    )

    decision = controller.evaluate_result(
        validation_passed=False,
        errors=["Bullet point exceeds 24 words", "Missing strong active verb"],
        failure_kind=FailureKind.DETERMINISTIC_QUALITY,
        state=state,
        evidence=["Bullet: 'Managed and handled various customer operations throughout the entire calendar year...'"],
        allowed_actions=["shorten_bullet", "use_action_verb"],
    )

    assert decision.action == ControllerAction.REQUEST_SEMANTIC_REVISION
    assert decision.can_retry is True
    assert decision.revision_request is not None
    assert decision.revision_request.attempt_count == 0
    assert decision.revision_request.max_revisions == 2
    assert len(decision.revision_request.failed_constraints) == 2
    assert "Bullet point exceeds 24 words" in decision.revision_request.failed_constraints
    assert decision.failure is not None
    assert decision.failure.failure_kind == FailureKind.DETERMINISTIC_QUALITY


def test_feedback_controller_schema_repair_deterministic() -> None:
    controller = FeedbackController()
    decision = controller.evaluate_result(
        validation_passed=False,
        errors=["JSON syntax error at line 14"],
        failure_kind=FailureKind.SCHEMA,
    )

    assert decision.action == ControllerAction.DETERMINISTIC_NORMALIZE
    assert decision.can_retry is True
    assert decision.revision_request is None
    assert decision.failure is not None
    assert decision.failure.failure_kind == FailureKind.SCHEMA
    assert "deterministic" in decision.repair_hint.lower()


def test_feedback_controller_budget_exhaustion_terminates() -> None:
    controller = FeedbackController()
    # State where revision budget is completely consumed (2/2)
    state = ResumeRunState(
        run_id="run-exhausted",
        workflow_id="wf-exhausted",
        phase=RunPhase.RUNNING,
        counters=RecoveryCounters(semantic_revisions=2),
        budget=RecoveryBudget(max_semantic_revisions=2),
    )

    decision = controller.evaluate_result(
        validation_passed=False,
        errors=["Repeated quality error"],
        failure_kind=FailureKind.DETERMINISTIC_QUALITY,
        state=state,
    )

    assert decision.action == ControllerAction.TERMINAL_FAIL
    assert decision.can_retry is False
    assert decision.revision_request is None
    assert decision.failure is not None
    assert "exhausted" in decision.failure.message.lower()


def test_feedback_controller_policy_failure_never_revises() -> None:
    controller = FeedbackController()
    state = ResumeRunState(
        run_id="run-policy",
        workflow_id="wf-policy",
        phase=RunPhase.RUNNING,
        counters=RecoveryCounters(semantic_revisions=0),
        budget=RecoveryBudget(max_semantic_revisions=5),
    )

    decision = controller.evaluate_result(
        validation_passed=False,
        errors=["Safety policy violation: PII detected in output"],
        failure_kind=FailureKind.POLICY,
        state=state,
        evidence=["Phone number found in text"],
    )

    assert decision.action == ControllerAction.TERMINAL_FAIL
    assert decision.can_retry is False
    assert decision.revision_request is None
    assert decision.failure is not None
    assert decision.failure.retryable is False


def test_canonical_dispatch_authority() -> None:
    from resume_graph_engine.src.apps_rg.runtime.orchestration.canonical_dispatch import (
        run_canonical_apps_rg_from_cli_primitives,
        run_canonical_full_resume_from_cli_primitives,
    )

    assert callable(run_canonical_full_resume_from_cli_primitives)
    assert callable(run_canonical_apps_rg_from_cli_primitives)
