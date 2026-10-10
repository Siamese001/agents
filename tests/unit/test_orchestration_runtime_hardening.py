"""tests/unit/test_orchestration_runtime_hardening.py

Comprehensive test suite verifying runtime behavior, state transitions,
step dependencies, retries, routing, error propagation, terminal statuses,
and prevention of false-success conditions across agents/orchestration.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.orchestration import (
    ControllerAction,
    ExecutionFailure,
    FailureKind,
    FeedbackController,
    FeedbackDecision,
    IllegalPhaseTransitionError,
    InvalidStateTransitionError,
    OrchestrationPrimitive,
    RecoveryAction,
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
    RunPhase,
    WorkflowExecutionEngine,
    WorkflowStateMachine,
    WorkflowStatus,
    WorkflowStep,
)
from agents.orchestration.services import PipelineCoordinator
from agents.orchestration.services.artifact_assembly import ArtifactAssembler, AssemblyRequest
from agents.orchestration.services.evaluation import (
    EvaluationRequest,
    EvaluationResult,
    EvaluationService,
)
from agents.orchestration.services.pipeline_coordinator import PipelineExecutionRequest
from agents.orchestration.services.release_policy import ReleaseDecision, ReleasePolicy
from agents.orchestration.services.section_generation import (
    SectionGenerationRequest,
    SectionGenerationResult,
    SectionGenerationService,
)


@dataclass
class CustomStepOutcome:
    """Mock domain outcome object with typed status and success flags."""
    status: str
    success: bool
    is_successful: bool
    error: str = ""
    exit_code: int = 0


# =========================================================================
# 1. POSITIVE TESTS: Standard Execution & Dependencies
# =========================================================================

def test_workflow_execution_engine_positive_dag(tmp_path: Path):
    """Verify standard multi-step execution with shared context passing and clean terminal status."""
    engine = WorkflowExecutionEngine("wf_pos_001", artifact_dir=tmp_path)

    def step1(ctx: dict) -> dict:
        return {"value": 42, "status": "PASSED"}

    def step2(ctx: dict) -> dict:
        # Relies on step1 output in context
        val = ctx.get("step_step1", {}).get("value", 0)
        return {"doubled": val * 2}

    steps = [
        WorkflowStep(step_id="step1", primitive=OrchestrationPrimitive.SEQUENCE, handler=step1),
        WorkflowStep(step_id="step2", primitive=OrchestrationPrimitive.SEQUENCE, handler=step2, depends_on=("step1",)),
    ]

    report = engine.execute_plan(steps)
    assert report.success is True
    assert report.final_status == WorkflowStatus.COMPLETED
    assert report.step_results["step1"].status == "PASSED"
    assert report.step_results["step2"].status == "PASSED"
    assert report.step_results["step2"].output["doubled"] == 84

    # Verify state machine audit trail
    state_file = tmp_path / "workflow_state.json"
    assert state_file.is_file()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["final_status"] == "COMPLETED"
    assert data["success"] is True


# =========================================================================
# 2. FALSE-SUCCESS PREVENTION TESTS
# =========================================================================

def test_false_success_prevention_dict_status_failed(tmp_path: Path):
    """Handler returning {'status': 'FAILED'} must be marked FAILED, not PASSED."""
    engine = WorkflowExecutionEngine("wf_false_succ_001", artifact_dir=tmp_path)

    def failed_handler(ctx: dict) -> dict:
        return {"status": "FAILED", "error": "Upstream service returned error payload"}

    steps = [
        WorkflowStep(step_id="step_failing_dict", primitive=OrchestrationPrimitive.SEQUENCE, handler=failed_handler),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert report.step_results["step_failing_dict"].status == "FAILED"
    assert "Upstream service returned error payload" in report.step_results["step_failing_dict"].error


def test_false_success_prevention_dict_status_failed_no_message(tmp_path: Path):
    """Handler returning {'status': 'FAILED'} without message must fall back to status description."""
    engine = WorkflowExecutionEngine("wf_false_succ_001b", artifact_dir=tmp_path)

    def failed_handler(ctx: dict) -> dict:
        return {"status": "FAILED"}

    steps = [
        WorkflowStep(step_id="step_failing_no_msg", primitive=OrchestrationPrimitive.SEQUENCE, handler=failed_handler),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert report.step_results["step_failing_no_msg"].status == "FAILED"
    assert "status=FAILED" in report.step_results["step_failing_no_msg"].error


def test_false_success_prevention_dict_exit_code_non_zero(tmp_path: Path):
    """Handler returning non-zero exit_code must fail-closed."""
    engine = WorkflowExecutionEngine("wf_false_succ_002", artifact_dir=tmp_path)

    def exit_code_handler(ctx: dict) -> dict:
        return {"status": "FAILED", "exit_code": 137}

    steps = [
        WorkflowStep(step_id="step_exit_code", primitive=OrchestrationPrimitive.SEQUENCE, handler=exit_code_handler),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert report.step_results["step_exit_code"].status == "FAILED"
    assert report.step_results["step_exit_code"].error != ""


def test_false_success_prevention_dict_success_false(tmp_path: Path):
    """Handler returning {'success': False} must be marked FAILED."""
    engine = WorkflowExecutionEngine("wf_false_succ_003", artifact_dir=tmp_path)

    def success_false_handler(ctx: dict) -> dict:
        return {"success": False, "message": "Validation rule check violated"}

    steps = [
        WorkflowStep(step_id="step_succ_false", primitive=OrchestrationPrimitive.SEQUENCE, handler=success_false_handler),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert report.step_results["step_succ_false"].status == "FAILED"


def test_false_success_prevention_object_outcome(tmp_path: Path):
    """Handler returning an object with success=False or is_successful=False must fail-closed."""
    engine = WorkflowExecutionEngine("wf_false_succ_004", artifact_dir=tmp_path)

    def object_handler(ctx: dict) -> CustomStepOutcome:
        return CustomStepOutcome(
            status="FAILED",
            success=False,
            is_successful=False,
            error="Domain logic rejection",
            exit_code=1,
        )

    steps = [
        WorkflowStep(step_id="step_obj", primitive=OrchestrationPrimitive.SEQUENCE, handler=object_handler),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert report.step_results["step_obj"].status == "FAILED"
    assert "Domain logic rejection" in report.step_results["step_obj"].error


def test_truthful_skip_recording_not_passed(tmp_path: Path):
    """Handler returning {'status': 'SKIPPED'} must be recorded as SKIPPED, never PASSED."""
    engine = WorkflowExecutionEngine("wf_skip_truth_001", artifact_dir=tmp_path)

    def skip_handler(ctx: dict) -> dict:
        return {"status": "SKIPPED", "reason": "Preconditions not applicable"}

    steps = [
        WorkflowStep(
            step_id="optional_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=skip_handler,
            optional=True,
        ),
        WorkflowStep(
            step_id="mandatory_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=lambda ctx: {"ok": True},
            depends_on=("optional_step",),
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is True
    assert report.final_status == WorkflowStatus.COMPLETED
    assert report.step_results["optional_step"].status == "SKIPPED"
    assert report.step_results["mandatory_step"].status == "PASSED"


# =========================================================================
# 3. STEP DEPENDENCY & ROUTING HARDENING TESTS
# =========================================================================

def test_missing_dependency_fails_closed(tmp_path: Path):
    """Step depending on a missing/unexecuted prerequisite must not run and must fail-closed."""
    engine = WorkflowExecutionEngine("wf_missing_dep_001", artifact_dir=tmp_path)

    executed = []

    def orphan_handler(ctx: dict) -> dict:
        executed.append("orphan")
        return {"data": "should_not_run"}

    steps = [
        WorkflowStep(
            step_id="step_with_missing_dep",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=orphan_handler,
            depends_on=("non_existent_step_abc",),
            optional=False,
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert executed == []
    assert report.step_results["step_with_missing_dep"].status == "SKIPPED"
    assert "missing or unexecuted" in report.step_results["step_with_missing_dep"].error


def test_transitive_prerequisite_failure_propagation(tmp_path: Path):
    """Step 1 failure causes Step 2 (optional) to skip due to prerequisite failure,
    which in turn causes Step 3 (mandatory) depending on Step 2 to skip and fail the workflow.
    """
    engine = WorkflowExecutionEngine("wf_transitive_001", artifact_dir=tmp_path)

    def failing_step1(ctx: dict) -> dict:
        raise RuntimeError("Fatal root error")

    def intermediate_step2(ctx: dict) -> dict:
        return {"ok": True}

    def downstream_step3(ctx: dict) -> dict:
        return {"ok": True}

    steps = [
        WorkflowStep(
            step_id="step1",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=failing_step1,
            optional=True,  # Optional step fails
        ),
        WorkflowStep(
            step_id="step2",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=intermediate_step2,
            depends_on=("step1",),
            optional=True,  # Optional step skipped because step1 failed
        ),
        WorkflowStep(
            step_id="step3",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=downstream_step3,
            depends_on=("step2",),  # Depends on step2 which was skipped due to failure
            optional=False,  # Mandatory step
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert report.step_results["step1"].status == "FAILED"
    assert report.step_results["step2"].status == "SKIPPED"
    assert "Prerequisite steps failed" in report.step_results["step2"].error
    assert report.step_results["step3"].status == "SKIPPED"
    assert "Prerequisite steps failed" in report.step_results["step3"].error


# =========================================================================
# 4. RETRIES AND ERROR PROPAGATION TESTS
# =========================================================================

def test_transient_retry_success_after_failure(tmp_path: Path):
    """Transient network error retries and succeeds within max_retries limit."""
    engine = WorkflowExecutionEngine("wf_retry_001", artifact_dir=tmp_path)

    attempts = 0

    def flaky_network_handler(ctx: dict) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise ConnectionResetError("Connection reset by peer (503 transient)")
        return {"network": "recovered"}

    steps = [
        WorkflowStep(
            step_id="flaky_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=flaky_network_handler,
            metadata={"max_retries": 2},
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is True
    assert report.final_status == WorkflowStatus.COMPLETED
    assert report.step_results["flaky_step"].status == "PASSED"
    assert report.step_results["flaky_step"].retry_count == 1
    assert attempts == 2


def test_retry_budget_exhaustion_terminates_failed(tmp_path: Path):
    """Persistent transient error exhausts retries and halts workflow as FAILED."""
    engine = WorkflowExecutionEngine("wf_retry_exhaust_001", artifact_dir=tmp_path)

    attempts = 0

    def permanently_broken(ctx: dict) -> dict:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("Gateway timeout (504)")

    steps = [
        WorkflowStep(
            step_id="timeout_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=permanently_broken,
            metadata={"max_retries": 2},
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert report.step_results["timeout_step"].status == "FAILED"
    assert report.step_results["timeout_step"].retry_count == 2
    assert attempts == 3  # initial + 2 retries


def test_non_transient_error_does_not_waste_retries(tmp_path: Path):
    """Deterministic policy or syntax errors should fail immediately without retrying."""
    engine = WorkflowExecutionEngine("wf_policy_fail_001", artifact_dir=tmp_path)

    attempts = 0

    def policy_violating_step(ctx: dict) -> dict:
        nonlocal attempts
        attempts += 1
        raise PermissionError("Access forbidden: policy prohibited action")

    steps = [
        WorkflowStep(
            step_id="forbidden_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=policy_violating_step,
            metadata={"max_retries": 3},
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert report.step_results["forbidden_step"].retry_count == 0
    assert attempts == 1


# =========================================================================
# 5. TERMINAL STATUSES & STATE TRANSITIONS TESTS
# =========================================================================

def test_terminal_statuses_immutability():
    """State machine strictly blocks transitions out of terminal statuses."""
    for terminal_status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED):
        sm = WorkflowStateMachine(f"wf_term_{terminal_status.value}")
        sm.transition_to(WorkflowStatus.PLANNED)
        sm.transition_to(WorkflowStatus.RUNNING)
        sm.transition_to(terminal_status)
        assert sm.current_status.is_terminal is True

        for target in (WorkflowStatus.CREATED, WorkflowStatus.PLANNED, WorkflowStatus.RUNNING, WorkflowStatus.REVIEWING):
            with pytest.raises(InvalidStateTransitionError):
                sm.transition_to(target)


# =========================================================================
# 6. PIPELINE COORDINATOR HARDENING TESTS
# =========================================================================

def test_pipeline_coordinator_release_rejection_sets_failed_phase():
    """PipelineCoordinator must set state.phase to FAILED and is_successful=False
    when release policy rejects release, avoiding false-success COMPLETED.
    """
    class RejectingReleasePolicy(ReleasePolicy):
        def evaluate_release(self, state, evaluation_results=(), assembly_result=None):
            return ReleaseDecision(
                run_id=state.run_id,
                is_releasable=False,
                reasons=("Quality gate 11 failed",),
                blocking_failures=("Blocking gate failure",),
            )

    coord = PipelineCoordinator(release_policy=RejectingReleasePolicy())
    req = PipelineExecutionRequest(
        run_id="run_pc_reject_001",
        workflow_id="wf_pc_reject_001",
        section_specs={"header": {"title": "Executive Summary"}},
    )

    result = coord.run(req)
    assert result.is_successful is False
    assert result.state.phase == RunPhase.FAILED
    assert result.state.phase.is_terminal is True
    assert "Blocking gate failure" in result.errors


def test_pipeline_coordinator_empty_specs_fails_closed():
    """PipelineCoordinator must fail-closed if empty section specs are passed."""
    coord = PipelineCoordinator()
    req = PipelineExecutionRequest(
        run_id="run_pc_empty_001",
        workflow_id="wf_pc_empty_001",
        section_specs={},
    )

    result = coord.run(req)
    assert result.is_successful is False
    assert result.state.phase == RunPhase.FAILED
    assert any("No section specifications" in e for e in result.errors)


# =========================================================================
# 7. FEEDBACK CONTROLLER PARAMETER & FALLBACK TESTS
# =========================================================================

def test_feedback_controller_step_name_and_none_kind():
    """FeedbackController handles step_name and None failure_kind without raising TypeError."""
    controller = FeedbackController()

    # Clean validation with step_name
    pass_decision = controller.evaluate_result(
        validation_passed=True,
        step_name="section_executive_summary",
    )
    assert pass_decision.action == ControllerAction.ACCEPT
    assert "section_executive_summary" in pass_decision.diagnostic

    # Failed validation with None failure_kind
    fail_decision = controller.evaluate_result(
        validation_passed=False,
        failure_kind=None,
        errors=["Generic quality imperfection"],
        step_name="section_skills",
    )
    assert fail_decision.action == ControllerAction.REQUEST_SEMANTIC_REVISION
    assert fail_decision.failure is not None
    assert fail_decision.failure.failure_kind == FailureKind.DETERMINISTIC_QUALITY
