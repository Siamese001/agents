"""Authoritative Workflow Execution Engine.

Executes declared workflow steps with:
- Formal state transitions enforced by WorkflowStateMachine.
- Explicit retry (ExecutionRetry) vs. repair (SemanticRepair) vs. cognitive replan (Replan).
- Structured artifact persistence to workflow_state.json.
- Fail-closed execution semantics.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Callable

from agents.orchestration.failure_taxonomy import (
    FailureKind,
    RecoveryAction,
    classify_failure,
    derive_recovery_action,
)
from agents.orchestration.primitives import (
    ExecutionRetry,
    OrchestrationPrimitive,
    Replan,
    SemanticRepair,
    WorkflowStatus,
    WorkflowStep,
)
from agents.orchestration.state_contracts import (
    RecoveryBudget,
    RecoveryCounters,
    RunCheckpoint,
    StepExecutionResult,
    WorkflowExecutionReport,
    _safe_serialize,
)
from agents.orchestration.state_machine import WorkflowStateMachine
from agents.telemetry.correlation import CorrelationContext, get_current_correlation
from agents.telemetry.events import TelemetryEmitter, TelemetryEventType


class WorkflowExecutionEngine:
    """Engine executing declared multi-agent workflow plans."""

    def __init__(
        self,
        workflow_id: str,
        *,
        artifact_dir: Path | str | None = None,
        correlation: CorrelationContext | None = None,
        emitter: TelemetryEmitter | None = None,
        budget: RecoveryBudget | None = None,
        default_step_timeout: float = 30.0,
    ) -> None:
        self.workflow_id = workflow_id
        self.state_machine = WorkflowStateMachine(workflow_id)
        self.artifact_dir = Path(artifact_dir).resolve() if artifact_dir else None
        if self.artifact_dir:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.correlation = (
            correlation
            or get_current_correlation()
            or CorrelationContext(run_id=workflow_id, workflow_id=workflow_id)
        )
        self.emitter = emitter or TelemetryEmitter(artifact_dir=self.artifact_dir)
        self.budget: RecoveryBudget = budget or RecoveryBudget()
        self.counters: RecoveryCounters = RecoveryCounters()
        self.default_step_timeout: float = default_step_timeout
        self._checkpoints: list[RunCheckpoint] = []

    def _persist_checkpoint(
        self,
        step_results: dict[str, StepExecutionResult],
        *,
        overall_success: bool | None = None,
        failure_diagnostics: dict[str, Any] | None = None,
    ) -> str | None:
        """Incrementally persist workflow state checkpoint to workflow_state.json."""
        if not self.artifact_dir:
            return None
        out_file = self.artifact_dir / "workflow_state.json"
        chk = self.state_machine.checkpoint()
        self._checkpoints.append(chk)
        success_val = (
            overall_success
            if overall_success is not None
            else (self.state_machine.current_status == WorkflowStatus.COMPLETED)
        )
        report_dict = {
            "workflow_id": self.workflow_id,
            "correlation": self.correlation.to_dict(),
            "final_status": self.state_machine.current_status.value,
            "final_phase": self.state_machine.current_phase.value,
            "checkpoint": chk.as_dict(),
            "checkpoints_count": len(self._checkpoints),
            "success": success_val,
            "telemetry_events_count": len(self.emitter.events),
            "recovery_counters": {
                "transport_retries": self.counters.transport_retries,
                "schema_repairs": self.counters.schema_repairs,
                "semantic_revisions": self.counters.semantic_revisions,
                "cognitive_replans": self.counters.cognitive_replans,
            },
            "budget": {
                "max_transport_retries": self.budget.max_transport_retries,
                "max_schema_repairs": self.budget.max_schema_repairs,
                "max_semantic_revisions": self.budget.max_semantic_revisions,
                "max_cognitive_replans": self.budget.max_cognitive_replans,
            },
            "steps": {k: v.as_dict() for k, v in step_results.items()},
            "state_machine": self.state_machine.as_dict(),
            "failure_diagnostics": failure_diagnostics or {},
        }
        out_file.write_text(
            json.dumps(report_dict, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return str(out_file)

    def _execute_step_handler(
        self,
        handler: Callable[..., Any],
        ctx: dict[str, Any],
        timeout_sec: float | None,
    ) -> Any:
        """Execute step handler within a bounded execution deadline."""
        effective_timeout = timeout_sec if timeout_sec is not None else self.default_step_timeout
        if effective_timeout is not None and effective_timeout > 0:
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(handler, ctx)
                return future.result(timeout=effective_timeout)
            except FuturesTimeoutError:
                raise TimeoutError(f"Step execution exceeded bounded timeout of {effective_timeout}s")
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        return handler(ctx)

    @staticmethod
    def _is_step_idempotent(step: WorkflowStep) -> bool:
        """Determine whether a step is safe to retry on transient failure."""
        if step.idempotent is not None:
            return bool(step.idempotent)
        if "idempotent" in step.metadata:
            return bool(step.metadata["idempotent"])
        if step.is_product_stage or step.metadata.get("is_product_stage", False):
            return False
        return True

    def execute_plan(
        self,
        steps: list[WorkflowStep],
        *,
        context: dict[str, Any] | None = None,
    ) -> WorkflowExecutionReport:
        """Execute a sequence of workflow steps under strict state machine governance."""
        ctx = dict(context or {})
        step_results: dict[str, StepExecutionResult] = {}

        self.emitter.emit(
            TelemetryEventType.WORKFLOW_START,
            self.correlation,
            {"step_count": len(steps), "steps": [s.step_id for s in steps]},
        )
        self.state_machine.transition_to(
            WorkflowStatus.PLANNED,
            reason=f"Plan assembled with {len(steps)} steps",
            metadata={"step_ids": [s.step_id for s in steps]},
        )
        self.state_machine.transition_to(
            WorkflowStatus.RUNNING,
            reason="Starting workflow execution loop",
        )

        overall_success = True
        fatal_error_msg = ""
        top_failure_diagnostics: dict[str, Any] = {}

        for step in steps:
            step_id = step.step_id
            primitive = step.primitive
            step_corr = self.correlation.new_child(
                step_name=step_id,
                metadata={"primitive": primitive.value},
            )
            self.emitter.emit(
                TelemetryEventType.STEP_START,
                step_corr,
                {"step_id": step_id, "optional": step.optional, "primitive": primitive.value},
            )

            # Check if optional step is explicitly disabled
            if step.optional and step.metadata.get("disabled", False):
                step_results[step_id] = StepExecutionResult(
                    step_id=step_id,
                    status="SKIPPED",
                    primitive=primitive.value,
                    metadata={"reason": "Step marked disabled/optional"},
                )
                self.emitter.emit(
                    TelemetryEventType.STEP_COMPLETE,
                    step_corr,
                    {"step_id": step_id, "status": "SKIPPED", "reason": "disabled/optional"},
                )
                continue

            # Invariant: Never re-execute or retry completed product stages from prior context/checkpoint
            is_product_stage = bool(step.is_product_stage or step.metadata.get("is_product_stage", False))
            is_idempotent = self._is_step_idempotent(step)
            existing_stage_output = ctx.get(f"step_{step_id}")
            if (
                is_product_stage
                and isinstance(existing_stage_output, dict)
                and existing_stage_output.get("status") in ("PASSED", "SUCCESS")
            ):
                step_results[step_id] = StepExecutionResult(
                    step_id=step_id,
                    status="PASSED",
                    primitive=primitive.value,
                    output=existing_stage_output,
                    metadata={"preserved_completed_product_stage": True},
                )
                self.emitter.emit(
                    TelemetryEventType.STEP_COMPLETE,
                    step_corr,
                    {"step_id": step_id, "status": "PASSED", "preserved": True},
                )
                self._persist_checkpoint(step_results)
                continue

            # Check prerequisite dependencies
            deps_missing = [dep for dep in step.depends_on if dep not in step_results]
            deps_failed = [
                dep for dep in step.depends_on
                if dep in step_results and (
                    step_results[dep].status == "FAILED"
                    or (step_results[dep].status == "SKIPPED" and step_results[dep].error)
                )
            ]
            if deps_missing or deps_failed:
                err_parts = []
                if deps_missing:
                    err_parts.append(f"Prerequisite steps missing or unexecuted: {deps_missing}")
                if deps_failed:
                    err_parts.append(f"Prerequisite steps failed: {deps_failed}")
                dep_err = "; ".join(err_parts)
                step_results[step_id] = StepExecutionResult(
                    step_id=step_id,
                    status="SKIPPED",
                    primitive=primitive.value,
                    error=dep_err,
                )
                self.emitter.emit(
                    TelemetryEventType.STEP_COMPLETE,
                    step_corr,
                    {"step_id": step_id, "status": "SKIPPED", "error": dep_err},
                )
                if not step.optional:
                    overall_success = False
                    fatal_error_msg = f"Prerequisites unsatisfied for mandatory step {step_id}: {dep_err}"
                    top_failure_diagnostics = {
                        "failed_step_id": step_id,
                        "error": dep_err,
                        "failure_kind": FailureKind.PLANNING.value,
                        "recovery_action": RecoveryAction.COGNITIVE_REPLAN.value,
                        "diagnostics": {"deps_missing": deps_missing, "deps_failed": deps_failed},
                    }
                    self._persist_checkpoint(
                        step_results,
                        overall_success=False,
                        failure_diagnostics=top_failure_diagnostics,
                    )
                    break
                continue

            # Execute step with bounded technical retry and semantic repair
            retries = 0
            replans = 0
            step_passed = False
            step_output = None
            step_err = ""
            is_skipped = False
            skip_reason = ""
            step_diagnostics: dict[str, Any] = {}
            step_failure_kind: FailureKind | None = None
            step_recovery_action: RecoveryAction = RecoveryAction.TERMINAL_ESCALATION

            max_retries = int(step.metadata.get("max_retries", self.budget.max_transport_retries))
            effective_max_retries = min(max_retries, self.budget.max_transport_retries)
            t_step_start = time.perf_counter()

            while retries <= effective_max_retries:
                is_exc = False
                exc_obj: Exception | None = None
                try:
                    step_output = self._execute_step_handler(step.handler, ctx, step.timeout)
                    failed, failure_reason = self._detect_output_failure(step_output)
                    if failed:
                        step_err = failure_reason
                        step_failure_kind = classify_failure(Exception(failure_reason))
                    else:
                        skipped, reason = self._detect_output_skip(step_output)
                        if skipped:
                            is_skipped, skip_reason, step_passed, step_err = True, reason, False, ""
                            break
                        step_passed, step_err = True, ""
                        break
                except Exception as exc:
                    is_exc = True
                    exc_obj = exc
                    step_err = str(exc)
                    is_timeout = isinstance(exc, TimeoutError) or "timed out" in step_err.lower()
                    step_failure_kind = FailureKind.TRANSPORT if is_timeout else classify_failure(exc)

                step_passed = False
                recovery = derive_recovery_action(step_failure_kind, retries, effective_max_retries)
                step_recovery_action = recovery
                is_transient = (
                    recovery == RecoveryAction.TRANSPORT_RETRY
                    or step_failure_kind == FailureKind.TRANSPORT
                    or (self._is_transient_error(exc_obj) if is_exc else self._is_transient_error_str(step_err))
                )

                if not is_transient:
                    step_diagnostics = {
                        "retry_blocked": "deterministic_failure",
                        "reason": f"Failure is not transient/transport: {step_failure_kind.value}",
                        "failure_kind": step_failure_kind.value,
                        "error": step_err,
                    }
                    break

                if not is_idempotent:
                    step_recovery_action = RecoveryAction.TERMINAL_ESCALATION
                    step_diagnostics = {
                        "retry_blocked": "non_idempotent_operation",
                        "reason": "Transport retry blocked: operation is non-idempotent to prevent redundant provider calls or duplicate side-effects",
                        "is_idempotent": False,
                        "error": step_err,
                    }
                    break

                if self.counters.transport_retries >= self.budget.max_transport_retries or retries >= effective_max_retries:
                    step_recovery_action = RecoveryAction.TERMINAL_ESCALATION
                    step_diagnostics = {
                        "retry_blocked": "budget_exhausted",
                        "reason": f"Transport retry budget exhausted ({self.counters.transport_retries}/{self.budget.max_transport_retries} attempts)",
                        "counters": self.counters.transport_retries,
                        "budget": self.budget.max_transport_retries,
                        "error": step_err,
                    }
                    break

                retries += 1
                self.counters = self.counters.with_increment(RecoveryAction.TRANSPORT_RETRY)
                self.emitter.emit(
                    TelemetryEventType.STEP_RECOVERY,
                    step_corr,
                    {
                        "step_id": step_id,
                        "retry_count": retries,
                        "error": step_err,
                        "failure_kind": step_failure_kind.value,
                        "recovery_action": recovery.value,
                        "idempotent": True,
                    },
                )
                time.sleep(min(0.05 * (2 ** (retries - 1)), 1.0))

            # Record review status
            self.state_machine.transition_to(
                WorkflowStatus.REVIEWING,
                reason=f"Reviewing outcome for step {step_id}",
                metadata={"step_id": step_id, "passed": step_passed, "skipped": is_skipped},
            )
            step_duration_ms = round((time.perf_counter() - t_step_start) * 1000, 2)

            if is_skipped:
                step_results[step_id] = StepExecutionResult(
                    step_id=step_id,
                    status="SKIPPED",
                    primitive=primitive.value,
                    output=step_output,
                    diagnostics={"duration_ms": step_duration_ms},
                    metadata={"reason": skip_reason or "Step handler indicated SKIPPED"},
                )
                self.emitter.emit(
                    TelemetryEventType.STEP_COMPLETE,
                    step_corr,
                    {"step_id": step_id, "status": "SKIPPED", "reason": skip_reason},
                )
                if isinstance(step_output, dict):
                    ctx[f"step_{step_id}"] = step_output
                if not step.optional:
                    overall_success = False
                    fatal_error_msg = f"Mandatory step {step_id} skipped: {skip_reason}"
                    top_failure_diagnostics = {
                        "failed_step_id": step_id,
                        "error": fatal_error_msg,
                        "failure_kind": FailureKind.PLANNING.value,
                        "recovery_action": RecoveryAction.TERMINAL_ESCALATION.value,
                        "diagnostics": {"reason": skip_reason},
                    }
                    self._persist_checkpoint(
                        step_results,
                        overall_success=False,
                        failure_diagnostics=top_failure_diagnostics,
                    )
                    break
                else:
                    self.state_machine.transition_to(
                        WorkflowStatus.RUNNING,
                        reason=f"Optional step {step_id} skipped; continuing pipeline",
                    )
            elif step_passed:
                step_results[step_id] = StepExecutionResult(
                    step_id=step_id,
                    status="PASSED",
                    primitive=primitive.value,
                    output=step_output,
                    retry_count=retries,
                    replan_count=replans,
                    diagnostics={"duration_ms": step_duration_ms},
                )
                self.emitter.emit(
                    TelemetryEventType.STEP_COMPLETE,
                    step_corr,
                    {"step_id": step_id, "status": "PASSED", "retries": retries},
                )
                if isinstance(step_output, dict):
                    ctx[f"step_{step_id}"] = step_output
                self.state_machine.transition_to(
                    WorkflowStatus.RUNNING,
                    reason=f"Step {step_id} completed successfully",
                )
                self._persist_checkpoint(step_results)
            else:
                final_diag = {
                    "step_id": step_id,
                    "error": step_err,
                    "failure_kind": step_failure_kind.value if step_failure_kind else "UNKNOWN",
                    "recovery_action": step_recovery_action.value if hasattr(step_recovery_action, "value") else str(step_recovery_action),
                    "is_idempotent": is_idempotent,
                    "is_product_stage": is_product_stage,
                    "retries": retries,
                    "counters": {"transport_retries": self.counters.transport_retries},
                    "duration_ms": step_duration_ms,
                }
                final_diag.update(step_diagnostics)

                step_results[step_id] = StepExecutionResult(
                    step_id=step_id,
                    status="FAILED",
                    primitive=primitive.value,
                    output=step_output,
                    error=step_err,
                    retry_count=retries,
                    replan_count=replans,
                    failure_kind=step_failure_kind.value if step_failure_kind else "",
                    recovery_action=step_recovery_action.value if hasattr(step_recovery_action, "value") else str(step_recovery_action),
                    diagnostics=final_diag,
                )
                self.emitter.emit(
                    TelemetryEventType.STEP_FAILED,
                    step_corr,
                    {"step_id": step_id, "status": "FAILED", "error": step_err, "retries": retries, "diagnostics": final_diag},
                )
                if not step.optional:
                    overall_success = False
                    fatal_error_msg = f"Step {step_id} failed: {step_err}"
                    top_failure_diagnostics = {
                        "failed_step_id": step_id,
                        "error": step_err,
                        "failure_kind": step_failure_kind.value if step_failure_kind else "",
                        "recovery_action": step_recovery_action.value if hasattr(step_recovery_action, "value") else str(step_recovery_action),
                        "diagnostics": final_diag,
                        "transport_retries": self.counters.transport_retries,
                        "budget": {"max_transport_retries": self.budget.max_transport_retries},
                    }
                    self._persist_checkpoint(
                        step_results,
                        overall_success=False,
                        failure_diagnostics=top_failure_diagnostics,
                    )
                    break
                else:
                    self.state_machine.transition_to(
                        WorkflowStatus.RUNNING,
                        reason=f"Optional step {step_id} failed; continuing pipeline",
                    )

        # Final terminal transition
        if overall_success:
            self.state_machine.transition_to(
                WorkflowStatus.COMPLETED,
                reason="All required steps completed successfully",
            )
            self.emitter.emit(
                TelemetryEventType.WORKFLOW_COMPLETE,
                self.correlation,
                {"success": True, "step_count": len(steps)},
            )
        else:
            self.state_machine.transition_to(
                WorkflowStatus.FAILED,
                reason=fatal_error_msg or "One or more required steps failed",
            )
            self.emitter.emit(
                TelemetryEventType.WORKFLOW_FAILED,
                self.correlation,
                {"success": False, "error": fatal_error_msg, "diagnostics": top_failure_diagnostics},
            )

        artifact_path_str = self._persist_checkpoint(
            step_results,
            overall_success=overall_success,
            failure_diagnostics=top_failure_diagnostics,
        )

        return WorkflowExecutionReport(
            workflow_id=self.workflow_id,
            final_status=self.state_machine.current_status,
            success=overall_success,
            step_results=step_results,
            state_machine_audit=self.state_machine.as_dict(),
            artifact_path=artifact_path_str,
            failure_diagnostics=top_failure_diagnostics,
        )

    @staticmethod
    def _is_transient_error(exc: Exception | None) -> bool:
        """Identify transient exceptions eligible for technical retry."""
        return WorkflowExecutionEngine._is_transient_error_str(str(exc or ""))

    @staticmethod
    def _is_transient_error_str(msg: str) -> bool:
        """Identify transient error messages eligible for technical retry."""
        lower_msg = str(msg).lower()
        transient_tokens = (
            "timeout", "rate limit", "connection reset", "connection refused",
            "broken pipe", "socket error", "503", "504", "502", "transient", "econnreset"
        )
        return any(t in lower_msg for t in transient_tokens)

    @staticmethod
    def _detect_output_failure(output: Any) -> tuple[bool, str]:
        """Detect if step output signals a failure."""
        if output is None:
            return False, ""
        getter = (lambda k: output.get(k)) if isinstance(output, dict) else (lambda k: getattr(output, k, None))
        status = str(getter("status") or "").upper()
        err = getter("error") or getter("message")
        if status in ("FAILED", "FAILURE", "ERROR"):
            return True, str(err or f"Step handler returned status={status}")
        if getter("success") is False or getter("is_successful") is False or getter("is_valid") is False:
            return True, str(err or "Step handler returned failure status")
        exit_code = getter("exit_code")
        if exit_code is not None and exit_code != 0:
            return True, str(err or f"Step handler returned non-zero exit code: {exit_code}")
        if getter("failed") is True:
            return True, str(err or "Step handler returned failed=True")
        return False, ""

    @staticmethod
    def _detect_output_skip(output: Any) -> tuple[bool, str]:
        """Detect if step output signals a clean skip."""
        if output is None:
            return False, ""
        getter = (lambda k: output.get(k)) if isinstance(output, dict) else (lambda k: getattr(output, k, None))
        status = str(getter("status") or "").upper()
        if status == "SKIPPED" or getter("skipped") is True:
            return True, str(getter("reason") or getter("message") or "Step handler returned status=SKIPPED")
        return False, ""


__all__ = [
    "StepExecutionResult",
    "WorkflowExecutionEngine",
    "WorkflowExecutionReport",
    "_safe_serialize",
]
