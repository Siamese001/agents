"""Authoritative Workflow State Machine for Multi-Agent Execution.

Enforces valid lifecycle transitions, guards against illegal state jumps,
and records an immutable chronological audit trail.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents.orchestration.primitives import WorkflowStatus
from agents.orchestration.state_contracts import (
    ResumeRunState,
    RunCheckpoint,
    RunPhase,
    validate_and_transition,
    workflow_status_to_run_phase,
)


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal workflow state transition is attempted."""


# Valid transition graph: source_status -> allowed_target_statuses
_VALID_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.CREATED: frozenset({
        WorkflowStatus.PLANNED,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.PLANNED: frozenset({
        WorkflowStatus.RUNNING,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.RUNNING: frozenset({
        WorkflowStatus.WAITING,
        WorkflowStatus.REVIEWING,
        WorkflowStatus.PAUSED,
        WorkflowStatus.FAILED,
        WorkflowStatus.COMPLETED,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.WAITING: frozenset({
        WorkflowStatus.RUNNING,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.REVIEWING: frozenset({
        WorkflowStatus.REPAIRING,
        WorkflowStatus.RUNNING,
        WorkflowStatus.FAILED,
        WorkflowStatus.COMPLETED,
    }),
    WorkflowStatus.REPAIRING: frozenset({
        WorkflowStatus.RUNNING,
        WorkflowStatus.FAILED,
    }),
    WorkflowStatus.PAUSED: frozenset({
        WorkflowStatus.RUNNING,
        WorkflowStatus.CANCELLED,
    }),
    WorkflowStatus.CANCELLED: frozenset(),
    WorkflowStatus.FAILED: frozenset(),
    WorkflowStatus.COMPLETED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class StateTransitionRecord:
    """Immutable record of an individual workflow state transition."""

    from_status: WorkflowStatus
    to_status: WorkflowStatus
    timestamp_utc: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class WorkflowStateMachine:
    """State machine governing workflow lifecycle transitions and audit logging."""

    def __init__(
        self,
        workflow_id: str,
        *,
        initial_status: WorkflowStatus = WorkflowStatus.CREATED,
        run_state: ResumeRunState | None = None,
    ) -> None:
        self.workflow_id = workflow_id
        self._current_status = initial_status
        self._history: list[StateTransitionRecord] = []
        self._created_at_utc = datetime.now(timezone.utc).isoformat()
        self._run_state: ResumeRunState = run_state or ResumeRunState(
            run_id=workflow_id,
            workflow_id=workflow_id,
            phase=workflow_status_to_run_phase(initial_status),
        )
        self._checkpoint_seq: int = 0

    @property
    def current_status(self) -> WorkflowStatus:
        return self._current_status

    @property
    def current_phase(self) -> RunPhase:
        return self._run_state.phase

    @property
    def run_state(self) -> ResumeRunState:
        return self._run_state

    def checkpoint(self) -> RunCheckpoint:
        """Return an immutable cryptographic checkpoint of current run state."""
        self._checkpoint_seq += 1
        return self._run_state.create_checkpoint(sequence=self._checkpoint_seq)

    @property
    def history(self) -> tuple[StateTransitionRecord, ...]:
        return tuple(self._history)

    def transition_to(
        self,
        target_status: WorkflowStatus,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StateTransitionRecord:
        """Attempt to transition the workflow to a new status."""
        if target_status == self._current_status:
            return StateTransitionRecord(
                from_status=self._current_status,
                to_status=target_status,
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                reason=reason or "idempotent_reaffirmation",
                metadata=metadata or {},
            )

        allowed = _VALID_TRANSITIONS.get(self._current_status, frozenset())
        if target_status not in allowed:
            raise InvalidStateTransitionError(
                f"Illegal transition for workflow {self.workflow_id}: "
                f"{self._current_status.value} -> {target_status.value}. "
                f"Allowed target statuses: {[s.value for s in allowed]}"
            )

        now = datetime.now(timezone.utc).isoformat()
        record = StateTransitionRecord(
            from_status=self._current_status,
            to_status=target_status,
            timestamp_utc=now,
            reason=reason,
            metadata=dict(metadata or {}),
        )
        self._history.append(record)
        self._current_status = target_status

        # Synchronize typed RunPhase if it changes
        target_phase = workflow_status_to_run_phase(target_status)
        if target_phase != self._run_state.phase:
            try:
                self._run_state = validate_and_transition(
                    self._run_state,
                    target_phase,
                    payload_updates={"last_reason": reason} if reason else None,
                )
            except Exception:
                # Direct jump allowed at state machine level (e.g. from WAITING)
                self._run_state = ResumeRunState(
                    run_id=self._run_state.run_id,
                    workflow_id=self._run_state.workflow_id,
                    phase=target_phase,
                    step_index=self._run_state.step_index + 1,
                    payload=self._run_state.payload,
                    counters=self._run_state.counters,
                    budget=self._run_state.budget,
                    context_digest=self._run_state.context_digest,
                    last_failure=self._run_state.last_failure,
                )

        return record

    def as_dict(self) -> dict[str, Any]:
        """Serialize state machine and audit log for telemetry persistence."""
        return {
            "workflow_id": self.workflow_id,
            "current_status": self._current_status.value,
            "current_phase": self.current_phase.value,
            "checkpoint_digest": self._run_state.compute_digest(),
            "created_at_utc": self._created_at_utc,
            "updated_at_utc": self._history[-1].timestamp_utc if self._history else self._created_at_utc,
            "is_terminal": self._current_status.is_terminal,
            "transition_count": len(self._history),
            "history": [
                {
                    "from_status": r.from_status.value,
                    "to_status": r.to_status.value,
                    "timestamp_utc": r.timestamp_utc,
                    "reason": r.reason,
                    "metadata": r.metadata,
                }
                for r in self._history
            ],
        }


__all__ = [
    "InvalidStateTransitionError",
    "StateTransitionRecord",
    "WorkflowStateMachine",
]
