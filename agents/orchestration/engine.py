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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from agents.orchestration.failure_taxonomy import (
    ExecutionFailure,
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
from agents.orchestration.state_machine import WorkflowStateMachine
from agents.telemetry.correlation import CorrelationContext, get_current_correlation
from agents.telemetry.events import TelemetryEmitter, TelemetryEventType


@dataclass(slots=True)
class StepExecutionResult:
    """Outcome of an individual executed workflow step."""

    step_id: str
    status: str  # "PASSED", "FAILED", "SKIPPED"
    primitive: str
    output: Any = None
    error: str = ""
    retry_count: int = 0
    replan_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status,
            "primitive": self.primitive,
            "error": self.error,
            "retry_count": self.retry_count,
            "replan_count": self.replan_count,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class WorkflowExecutionReport:
    """Consolidated report of workflow execution."""

    workflow_id: str
    final_status: WorkflowStatus
    success: bool
    step_results: dict[str, StepExecutionResult]
    state_machine_audit: dict[str, Any]
    artifact_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "final_status": self.final_status.value,
            "success": self.success,
            "step_results": {k: v.as_dict() for k, v in self.step_results.items()},
            "state_machine": self.state_machine_audit,
            "artifact_path": self.artifact_path,
        }


class WorkflowExecutionEngine:
    """Engine executing declared multi-agent workflow plans."""

    def __init__(
        self,
        workflow_id: str,
        *,
        artifact_dir: Path | str | None = None,
        correlation: CorrelationContext | None = None,
        emitter: TelemetryEmitter | None = None,
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

    def execute_plan(
        self,
        steps: list[WorkflowStep],
        *,
        context: dict[str, Any] | None = None,
    ) -> WorkflowExecutionReport:
        """Execute a sequence of workflow steps under strict state machine governance."""
        ctx = dict(context or {})
        step_results: dict[str, StepExecutionResult] = {}

        # Telemetry: Workflow Start
        self.emitter.emit(
            TelemetryEventType.WORKFLOW_START,
            self.correlation,
            {"step_count": len(steps), "steps": [s.step_id for s in steps]},
        )

        # 1. State: PLANNED
        self.state_machine.transition_to(
            WorkflowStatus.PLANNED,
            reason=f"Plan assembled with {len(steps)} steps",
            metadata={"step_ids": [s.step_id for s in steps]},
        )

        # 2. State: RUNNING
        self.state_machine.transition_to(
            WorkflowStatus.RUNNING,
            reason="Starting workflow execution loop",
        )

        overall_success = True
        fatal_error_msg = ""

        for step in steps:
            step_id = step.step_id
            primitive = step.primitive
            step_corr = self.correlation.new_child(
                step_name=step_id,
                metadata={"primitive": primitive.value},
            )

            # Telemetry: Step Start
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

            max_retries = int(step.metadata.get("max_retries", 2))

            while retries <= max_retries:
                try:
                    step_output = step.handler(ctx)

                    # Check if step output signals failure
                    failed, failure_reason = self._detect_output_failure(step_output)
                    if failed:
                        step_err = failure_reason
                        step_passed = False
                        failure_kind = classify_failure(Exception(failure_reason))
                        recovery = derive_recovery_action(failure_kind, retries, max_retries)
                        if retries < max_retries and (
                            recovery == RecoveryAction.TRANSPORT_RETRY
                            or self._is_transient_error_str(failure_reason)
                        ):
                            retries += 1
                            self.emitter.emit(
                                TelemetryEventType.STEP_RECOVERY,
                                step_corr,
                                {
                                    "step_id": step_id,
                                    "retry_count": retries,
                                    "error": step_err,
                                    "failure_kind": failure_kind.value,
                                    "recovery_action": recovery.value,
                                },
                            )
                            time.sleep(0.05 * retries)
                            continue
                        else:
                            break

                    # Check if step output signals a clean skip
                    skipped, reason = self._detect_output_skip(step_output)
                    if skipped:
                        is_skipped = True
                        skip_reason = reason
                        step_passed = False
                        step_err = ""
                        break

                    step_passed = True
                    step_err = ""
                    break
                except Exception as exc:
                    step_err = str(exc)
                    step_passed = False
                    failure_kind = classify_failure(exc)
                    recovery = derive_recovery_action(failure_kind, retries, max_retries)
                    # Check if error is transient technical retry
                    if retries < max_retries and (
                        recovery == RecoveryAction.TRANSPORT_RETRY or self._is_transient_error(exc)
                    ):
                        retries += 1
                        self.emitter.emit(
                            TelemetryEventType.STEP_RECOVERY,
                            step_corr,
                            {
                                "step_id": step_id,
                                "retry_count": retries,
                                "error": step_err,
                                "failure_kind": failure_kind.value,
                                "recovery_action": recovery.value,
                            },
                        )
                        time.sleep(0.05 * retries)
                        continue
                    else:
                        break

            # Record review status
            self.state_machine.transition_to(
                WorkflowStatus.REVIEWING,
                reason=f"Reviewing outcome for step {step_id}",
                metadata={"step_id": step_id, "passed": step_passed, "skipped": is_skipped},
            )

            if is_skipped:
                step_results[step_id] = StepExecutionResult(
                    step_id=step_id,
                    status="SKIPPED",
                    primitive=primitive.value,
                    output=step_output,
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
                )
                self.emitter.emit(
                    TelemetryEventType.STEP_COMPLETE,
                    step_corr,
                    {"step_id": step_id, "status": "PASSED", "retries": retries},
                )
                # Store step output into shared context if dict
                if isinstance(step_output, dict):
                    ctx[f"step_{step_id}"] = step_output
                self.state_machine.transition_to(
                    WorkflowStatus.RUNNING,
                    reason=f"Step {step_id} completed successfully",
                )
            else:
                step_results[step_id] = StepExecutionResult(
                    step_id=step_id,
                    status="FAILED",
                    primitive=primitive.value,
                    output=step_output,
                    error=step_err,
                    retry_count=retries,
                    replan_count=replans,
                )
                self.emitter.emit(
                    TelemetryEventType.STEP_FAILED,
                    step_corr,
                    {"step_id": step_id, "status": "FAILED", "error": step_err, "retries": retries},
                )
                if not step.optional:
                    overall_success = False
                    fatal_error_msg = f"Step {step_id} failed: {step_err}"
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
                {"success": False, "error": fatal_error_msg},
            )

        # Persist workflow_state.json if artifact directory is provided
        artifact_path_str: str | None = None
        if self.artifact_dir:
            out_file = self.artifact_dir / "workflow_state.json"
            report_dict = {
                "workflow_id": self.workflow_id,
                "correlation": self.correlation.to_dict(),
                "final_status": self.state_machine.current_status.value,
                "final_phase": self.state_machine.current_phase.value,
                "checkpoint": self.state_machine.checkpoint().as_dict(),
                "success": overall_success,
                "telemetry_events_count": len(self.emitter.events),
                "steps": {k: v.as_dict() for k, v in step_results.items()},
                "state_machine": self.state_machine.as_dict(),
            }
            out_file.write_text(
                json.dumps(report_dict, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            artifact_path_str = str(out_file)

        return WorkflowExecutionReport(
            workflow_id=self.workflow_id,
            final_status=self.state_machine.current_status,
            success=overall_success,
            step_results=step_results,
            state_machine_audit=self.state_machine.as_dict(),
            artifact_path=artifact_path_str,
        )

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        """Identify transient exceptions eligible for technical retry."""
        return WorkflowExecutionEngine._is_transient_error_str(str(exc))

    @staticmethod
    def _is_transient_error_str(msg: str) -> bool:
        """Identify transient error messages eligible for technical retry."""
        lower_msg = str(msg).lower()
        return any(
            token in lower_msg
            for token in (
                "timeout",
                "rate limit",
                "connection reset",
                "connection refused",
                "broken pipe",
                "socket error",
                "503",
                "504",
                "502",
                "transient",
                "econnreset",
            )
        )

    @staticmethod
    def _detect_output_failure(output: Any) -> tuple[bool, str]:
        """Detect if step output signals a failure."""
        if output is None:
            return False, ""
        if isinstance(output, dict):
            status = str(output.get("status", "")).upper()
            if status in ("FAILED", "FAILURE", "ERROR"):
                err = output.get("error") or output.get("message") or f"Step handler returned status={status}"
                return True, str(err)
            if output.get("success") is False:
                err = output.get("error") or output.get("message") or "Step handler returned success=False"
                return True, str(err)
            if output.get("is_successful") is False:
                err = output.get("error") or output.get("message") or "Step handler returned is_successful=False"
                return True, str(err)
            if output.get("is_valid") is False:
                err = output.get("error") or output.get("message") or "Step handler returned is_valid=False"
                return True, str(err)
            exit_code = output.get("exit_code")
            if exit_code is not None and exit_code != 0:
                err = output.get("error") or output.get("message") or f"Step handler returned non-zero exit code: {exit_code}"
                return True, str(err)
            if output.get("failed") is True:
                err = output.get("error") or output.get("message") or "Step handler returned failed=True"
                return True, str(err)
        else:
            status = str(getattr(output, "status", "")).upper()
            if status in ("FAILED", "FAILURE", "ERROR"):
                err = getattr(output, "error", "") or getattr(output, "message", "") or f"Step handler returned status={status}"
                return True, str(err)
            if getattr(output, "success", None) is False:
                err = getattr(output, "error", "") or getattr(output, "message", "") or "Step handler returned success=False"
                return True, str(err)
            if getattr(output, "is_successful", None) is False:
                err = getattr(output, "error", "") or getattr(output, "message", "") or "Step handler returned is_successful=False"
                return True, str(err)
            if getattr(output, "is_valid", None) is False:
                err = getattr(output, "error", "") or getattr(output, "message", "") or "Step handler returned is_valid=False"
                return True, str(err)
            exit_code = getattr(output, "exit_code", None)
            if exit_code is not None and exit_code != 0:
                err = getattr(output, "error", "") or getattr(output, "message", "") or f"Step handler returned non-zero exit code: {exit_code}"
                return True, str(err)
            if getattr(output, "failed", None) is True:
                err = getattr(output, "error", "") or getattr(output, "message", "") or "Step handler returned failed=True"
                return True, str(err)
        return False, ""

    @staticmethod
    def _detect_output_skip(output: Any) -> tuple[bool, str]:
        """Detect if step output signals a clean skip."""
        if output is None:
            return False, ""
        if isinstance(output, dict):
            status = str(output.get("status", "")).upper()
            if status == "SKIPPED":
                reason = output.get("reason") or output.get("message") or "Step handler returned status=SKIPPED"
                return True, str(reason)
            if output.get("skipped") is True:
                reason = output.get("reason") or output.get("message") or "Step handler returned skipped=True"
                return True, str(reason)
        else:
            status = str(getattr(output, "status", "")).upper()
            if status == "SKIPPED":
                reason = getattr(output, "reason", "") or getattr(output, "message", "") or "Step handler returned status=SKIPPED"
                return True, str(reason)
            if getattr(output, "skipped", None) is True:
                reason = getattr(output, "reason", "") or getattr(output, "message", "") or "Step handler returned skipped=True"
                return True, str(reason)
        return False, ""


__all__ = [
    "StepExecutionResult",
    "WorkflowExecutionEngine",
    "WorkflowExecutionReport",
]
