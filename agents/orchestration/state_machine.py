"""Authoritative Workflow State Machine for Multi-Agent Execution.

Enforces valid lifecycle transitions, guards against illegal state jumps,
and records an immutable chronological audit trail.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents.orchestration.primitives import WorkflowStatus


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

    def __init__(self, workflow_id: str, *, initial_status: WorkflowStatus = WorkflowStatus.CREATED) -> None:
        self.workflow_id = workflow_id
        self._current_status = initial_status
        self._history: list[StateTransitionRecord] = []
        self._created_at_utc = datetime.now(timezone.utc).isoformat()

    @property
    def current_status(self) -> WorkflowStatus:
        return self._current_status

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
        return record

    def as_dict(self) -> dict[str, Any]:
        """Serialize state machine and audit log for telemetry persistence."""
        return {
            "workflow_id": self.workflow_id,
            "current_status": self._current_status.value,
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
