"""Unit tests verifying hardening invariants for WorkflowExecutionEngine and agents health checks.

Invariants verified:
1. Never retry completed product stages for transport failures.
2. Retry only failed idempotent operations within existing SSOT budgets.
3. Enforce bounded timeouts, preventing unbounded execution.
4. Incrementally persist and preserve successful checkpoints on disk.
5. Emit exact failure diagnostics.
6. Verify no redundant provider calls on non-idempotent steps or completed stages.
7. Verify health check per-domain isolation, bounded timeouts, and diagnostic extraction.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.health import _extract_failures_from_output, _resolve_pytest_cmd, run_health_checks
from agents.orchestration.engine import (
    StepExecutionResult,
    WorkflowExecutionEngine,
    WorkflowExecutionReport,
)
from agents.orchestration.failure_taxonomy import FailureKind, RecoveryAction
from agents.orchestration.primitives import (
    OrchestrationPrimitive,
    WorkflowStatus,
    WorkflowStep,
)
from agents.orchestration.state_contracts import RecoveryBudget


# =========================================================================
# 1. NEVER RETRY COMPLETED PRODUCT STAGES FOR TRANSPORT FAILURES
# =========================================================================

def test_never_retry_completed_product_stages_for_transport_failures(tmp_path: Path):
    """Completed product stages must never be retried or re-executed when downstream fails."""
    engine = WorkflowExecutionEngine("wf_completed_stage_001", artifact_dir=tmp_path)

    stage1_calls = 0
    stage2_calls = 0

    def stage1_product_handler(ctx: dict) -> dict:
        nonlocal stage1_calls
        stage1_calls += 1
        return {"status": "PASSED", "deliverable": "tailored_resume.pdf"}

    def stage2_downstream_transport_failure(ctx: dict) -> dict:
        nonlocal stage2_calls
        stage2_calls += 1
        raise ConnectionResetError("503 Service Unavailable: upstream connection reset")

    steps = [
        WorkflowStep(
            step_id="resume_tailoring",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=stage1_product_handler,
            is_product_stage=True,
            idempotent=False,
        ),
        WorkflowStep(
            step_id="executive_outreach",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=stage2_downstream_transport_failure,
            depends_on=("resume_tailoring",),
            is_product_stage=True,
            idempotent=False,
        ),
    ]

    report = engine.execute_plan(steps)

    # Stage 1 succeeded and was called exactly once
    assert stage1_calls == 1
    assert report.step_results["resume_tailoring"].status == "PASSED"

    # Stage 2 failed on transport, but being a non-idempotent product stage, was NOT retried
    assert stage2_calls == 1
    assert report.step_results["executive_outreach"].status == "FAILED"
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED

    # Checkpoint preservation: workflow_state.json contains Stage 1 output intact
    state_file = tmp_path / "workflow_state.json"
    assert state_file.is_file()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["steps"]["resume_tailoring"]["status"] == "PASSED"
    assert state_data["steps"]["resume_tailoring"]["output"]["deliverable"] == "tailored_resume.pdf"
    assert state_data["steps"]["executive_outreach"]["status"] == "FAILED"

    # Now verify re-execution / resumption with pre-existing completed stage in context:
    # Stage 1 handler must NOT be called again
    resumed_ctx = {"step_resume_tailoring": {"status": "PASSED", "deliverable": "tailored_resume.pdf"}}
    stage1_calls_before = stage1_calls

    engine2 = WorkflowExecutionEngine("wf_completed_stage_001_resumed", artifact_dir=tmp_path)
    report2 = engine2.execute_plan(steps, context=resumed_ctx)
    assert stage1_calls == stage1_calls_before  # 0 additional invocations!
    assert report2.step_results["resume_tailoring"].status == "PASSED"


# =========================================================================
# 2. RETRY ONLY FAILED IDEMPOTENT OPERATIONS WITHIN EXISTING SSOT BUDGETS
# =========================================================================

def test_non_idempotent_operation_never_retries_on_transport_failure(tmp_path: Path):
    """Non-idempotent steps must fail-closed immediately without retrying (0 extra calls)."""
    engine = WorkflowExecutionEngine("wf_non_idem_001", artifact_dir=tmp_path)

    provider_calls = 0

    def non_idempotent_provider_mutation(ctx: dict) -> dict:
        nonlocal provider_calls
        provider_calls += 1
        raise TimeoutError("504 Gateway Timeout while submitting campaign dispatch")

    steps = [
        WorkflowStep(
            step_id="campaign_dispatch",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=non_idempotent_provider_mutation,
            idempotent=False,
            metadata={"max_retries": 3},
        ),
    ]

    report = engine.execute_plan(steps)

    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    assert provider_calls == 1  # Exactly 1 call; no retries attempted
    step_res = report.step_results["campaign_dispatch"]
    assert step_res.status == "FAILED"
    assert step_res.retry_count == 0
    assert step_res.diagnostics["retry_blocked"] == "non_idempotent_operation"


def test_idempotent_operation_retries_and_succeeds_within_ssot_budget(tmp_path: Path):
    """Idempotent step retries transient failure up to SSOT budget and succeeds."""
    custom_budget = RecoveryBudget(max_transport_retries=3)
    engine = WorkflowExecutionEngine(
        "wf_idem_success_001",
        artifact_dir=tmp_path,
        budget=custom_budget,
    )

    invocations = 0

    def idempotent_read_handler(ctx: dict) -> dict:
        nonlocal invocations
        invocations += 1
        if invocations < 3:
            raise ConnectionResetError("503 Transient socket disconnect")
        return {"data": "verified_research_evidence"}

    steps = [
        WorkflowStep(
            step_id="research_retrieval",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=idempotent_read_handler,
            idempotent=True,
            metadata={"max_retries": 3},
        ),
    ]

    report = engine.execute_plan(steps)

    assert report.success is True
    assert report.final_status == WorkflowStatus.COMPLETED
    assert invocations == 3  # Initial + 2 retries
    step_res = report.step_results["research_retrieval"]
    assert step_res.status == "PASSED"
    assert step_res.retry_count == 2
    assert engine.counters.transport_retries == 2


def test_idempotent_operation_exhausts_budget_and_fails_closed(tmp_path: Path):
    """Persistent transport failure on idempotent step halts at exact SSOT budget limit."""
    budget = RecoveryBudget(max_transport_retries=2)
    engine = WorkflowExecutionEngine("wf_idem_exhaust_001", artifact_dir=tmp_path, budget=budget)

    invocations = 0

    def persistent_failing_handler(ctx: dict) -> dict:
        nonlocal invocations
        invocations += 1
        raise TimeoutError("504 Gateway Timeout")

    steps = [
        WorkflowStep(
            step_id="failing_fetch",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=persistent_failing_handler,
            idempotent=True,
            metadata={"max_retries": 5},  # Requested 5, but SSOT budget is 2
        ),
    ]

    report = engine.execute_plan(steps)

    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    # Initial attempt (1) + retries capped at budget.max_transport_retries (2) = 3 total invocations
    assert invocations == 3
    step_res = report.step_results["failing_fetch"]
    assert step_res.retry_count == 2
    assert step_res.diagnostics["retry_blocked"] == "budget_exhausted"


# =========================================================================
# 3. ENFORCE BOUNDED TIMEOUTS
# =========================================================================

def test_enforce_bounded_timeouts_prevents_unbounded_execution(tmp_path: Path):
    """Step execution exceeding timeout is cancelled cleanly without hanging."""
    engine = WorkflowExecutionEngine("wf_timeout_001", artifact_dir=tmp_path, default_step_timeout=0.2)

    def slow_hanging_step(ctx: dict) -> dict:
        time.sleep(1.0)
        return {"done": True}

    steps = [
        WorkflowStep(
            step_id="slow_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=slow_hanging_step,
            idempotent=False,
            timeout=0.15,
        ),
    ]

    t0 = time.perf_counter()
    report = engine.execute_plan(steps)
    elapsed = time.perf_counter() - t0

    # Must complete near the 0.15s deadline, not 1.0s
    assert elapsed < 0.8
    assert report.success is False
    assert report.final_status == WorkflowStatus.FAILED
    step_res = report.step_results["slow_step"]
    assert step_res.status == "FAILED"
    assert "bounded timeout" in step_res.error


# =========================================================================
# 4. PRESERVE SUCCESSFUL CHECKPOINTS ON FAILURE
# =========================================================================

def test_preserve_successful_checkpoints_on_failure(tmp_path: Path):
    """Successful intermediate checkpoints are written to disk before downstream failure."""
    engine = WorkflowExecutionEngine("wf_checkpoint_001", artifact_dir=tmp_path)

    steps = [
        WorkflowStep(
            step_id="step_a_success",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=lambda ctx: {"status": "PASSED", "token": "secret_abc"},
            is_product_stage=True,
            idempotent=False,
        ),
        WorkflowStep(
            step_id="step_b_failure",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=lambda ctx: {"status": "FAILED", "error": "Fatal format violation"},
            depends_on=("step_a_success",),
            idempotent=False,
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False

    state_file = tmp_path / "workflow_state.json"
    assert state_file.is_file()
    state_data = json.loads(state_file.read_text(encoding="utf-8"))

    # Step A must be preserved with full output
    assert state_data["steps"]["step_a_success"]["status"] == "PASSED"
    assert state_data["steps"]["step_a_success"]["output"]["token"] == "secret_abc"
    # Step B must record exact failure
    assert state_data["steps"]["step_b_failure"]["status"] == "FAILED"
    assert state_data["final_status"] == "FAILED"
    assert state_data["success"] is False
    assert state_data["checkpoints_count"] >= 2


# =========================================================================
# 5. EMIT EXACT FAILURE DIAGNOSTICS
# =========================================================================

def test_emit_exact_failure_diagnostics(tmp_path: Path):
    """Execution report and step results emit comprehensive failure diagnostics."""
    engine = WorkflowExecutionEngine("wf_diag_001", artifact_dir=tmp_path)

    steps = [
        WorkflowStep(
            step_id="syntax_failure_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=lambda ctx: (_ for _ in ()).throw(ValueError("Invalid schema field 'resume_version'")),
            idempotent=False,
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    step_res = report.step_results["syntax_failure_step"]

    assert step_res.failure_kind == FailureKind.SCHEMA.value
    assert step_res.recovery_action == RecoveryAction.SCHEMA_REPAIR.value
    assert "resume_version" in step_res.error
    assert "duration_ms" in step_res.diagnostics

    # Top-level failure diagnostics on report
    assert report.failure_diagnostics["failed_step_id"] == "syntax_failure_step"
    assert report.failure_diagnostics["failure_kind"] == FailureKind.SCHEMA.value
    assert "diagnostics" in report.failure_diagnostics


# =========================================================================
# 6. VERIFY NO REDUNDANT PROVIDER CALLS
# =========================================================================

def test_verify_no_redundant_provider_calls(tmp_path: Path):
    """Verify that non-idempotent provider calls are invoked exactly once on failure."""
    mock_provider = MagicMock(side_effect=RuntimeError("502 Bad Gateway from Model Provider"))
    engine = WorkflowExecutionEngine("wf_zero_redundant_001", artifact_dir=tmp_path)

    steps = [
        WorkflowStep(
            step_id="llm_generation_step",
            primitive=OrchestrationPrimitive.SEQUENCE,
            handler=lambda ctx: mock_provider(model="gpt-4o"),
            idempotent=False,  # Non-idempotent provider generation
            metadata={"max_retries": 3},
        ),
    ]

    report = engine.execute_plan(steps)
    assert report.success is False
    # Provider must be invoked exactly once: zero redundant calls
    assert mock_provider.call_count == 1


# =========================================================================
# 7. AGENTS HEALTH CHECK HARDENING: RESOLUTION, TIMEOUT, ISOLATION, DIAGNOSTICS
# =========================================================================

def test_health_check_pytest_command_resolution():
    """_resolve_pytest_cmd reliably locates pytest in worktree or returns fallback."""
    cmd = _resolve_pytest_cmd()
    assert isinstance(cmd, list)
    assert len(cmd) >= 1
    assert "pytest" in cmd[0] or "python" in cmd[0]


def test_health_check_failure_extraction():
    """_extract_failures_from_output correctly parses pytest failure text."""
    sample_stdout = """
=================================== FAILURES ===================================
___________________________ test_broken_component ___________________________
tests/unit/test_foo.py:42: in test_broken_component
    assert result == 42
E   AssertionError: assert 10 == 42
=========================== short test summary info ============================
FAILED tests/unit/test_foo.py::test_broken_component - AssertionError: assert 10 == 42
========================= 1 failed, 5 passed in 0.5s ===========================
"""
    failures = _extract_failures_from_output(sample_stdout, "")
    assert len(failures) == 1
    assert "test_broken_component" in failures[0]["target"]
    assert "assert 10 == 42" in failures[0]["error"]


def test_health_check_domain_isolation(monkeypatch):
    """Health check runner isolates domain results without marking healthy domains failed."""
    # Run only Orchestration domain
    report = run_health_checks(domain_filter="Orchestration")
    assert report["domains_count"] == 1
    assert report["domains"][0]["domain"] == "Orchestration"
    assert report["domains"][0]["status"] == "PASSED"
    assert report["status"] == "HEALTHY"
    assert report["exit_code"] == 0
