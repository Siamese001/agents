"""Typed State Contracts, Run Phases, and Checkpoint Integrity Governance.

Part of Sovereign Agentic Platform Orchestration Governance (Wave 2).
Provides immutable state containers, monotonic checkpointing, explicit legal
phase transitions, and independent recovery budget tracking.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from agents.orchestration.failure_taxonomy import ExecutionFailure, RecoveryAction


class RunPhase(str, Enum):
    """Authoritative execution phases for governed agentic workflows."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    REPAIRING = "REPAIRING"
    REVISING = "REVISING"
    REPLANNING = "REPLANNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        """Return True if the phase is an immutable terminal end-state."""
        return self in (RunPhase.COMPLETED, RunPhase.FAILED, RunPhase.CANCELLED)

    @property
    def is_active(self) -> bool:
        """Return True if the workflow is in an active in-flight or recovery phase."""
        return self in (
            RunPhase.RUNNING,
            RunPhase.WAITING,
            RunPhase.REPAIRING,
            RunPhase.REVISING,
            RunPhase.REPLANNING,
        )


LEGAL_PHASE_TRANSITIONS: dict[RunPhase, set[RunPhase]] = {
    RunPhase.CREATED: {
        RunPhase.RUNNING,
        RunPhase.CANCELLED,
        RunPhase.FAILED,
    },
    RunPhase.RUNNING: {
        RunPhase.WAITING,
        RunPhase.REPAIRING,
        RunPhase.REVISING,
        RunPhase.REPLANNING,
        RunPhase.COMPLETED,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.WAITING: {
        RunPhase.RUNNING,
        RunPhase.REPAIRING,
        RunPhase.REVISING,
        RunPhase.REPLANNING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.REPAIRING: {
        RunPhase.RUNNING,
        RunPhase.REVISING,
        RunPhase.REPLANNING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.REVISING: {
        RunPhase.RUNNING,
        RunPhase.REPLANNING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.REPLANNING: {
        RunPhase.RUNNING,
        RunPhase.FAILED,
        RunPhase.CANCELLED,
    },
    RunPhase.COMPLETED: set(),
    RunPhase.FAILED: set(),
    RunPhase.CANCELLED: set(),
}


@dataclass(frozen=True, slots=True)
class RecoveryBudget:
    """Configured limits for each independent recovery mechanism."""

    max_transport_retries: int = 3
    max_schema_repairs: int = 2
    max_semantic_revisions: int = 2
    max_cognitive_replans: int = 1

    def limit_for(self, action: RecoveryAction) -> int:
        match action:
            case RecoveryAction.TRANSPORT_RETRY:
                return self.max_transport_retries
            case RecoveryAction.SCHEMA_REPAIR:
                return self.max_schema_repairs
            case RecoveryAction.SEMANTIC_REVISION:
                return self.max_semantic_revisions
            case RecoveryAction.COGNITIVE_REPLAN:
                return self.max_cognitive_replans
            case _:
                return 0


@dataclass(frozen=True, slots=True)
class RecoveryCounters:
    """Immutable tracker of recovery actions attempted during a workflow execution."""

    transport_retries: int = 0
    schema_repairs: int = 0
    semantic_revisions: int = 0
    cognitive_replans: int = 0

    def current_count(self, action: RecoveryAction) -> int:
        match action:
            case RecoveryAction.TRANSPORT_RETRY:
                return self.transport_retries
            case RecoveryAction.SCHEMA_REPAIR:
                return self.schema_repairs
            case RecoveryAction.SEMANTIC_REVISION:
                return self.semantic_revisions
            case RecoveryAction.COGNITIVE_REPLAN:
                return self.cognitive_replans
            case _:
                return 0

    def is_exhausted(self, budget: RecoveryBudget, action: RecoveryAction) -> bool:
        """Check whether budget for a specific recovery mechanism is reached."""
        return self.current_count(action) >= budget.limit_for(action)

    def with_increment(self, action: RecoveryAction) -> RecoveryCounters:
        """Return a new RecoveryCounters with the target action incremented."""
        match action:
            case RecoveryAction.TRANSPORT_RETRY:
                return RecoveryCounters(
                    transport_retries=self.transport_retries + 1,
                    schema_repairs=self.schema_repairs,
                    semantic_revisions=self.semantic_revisions,
                    cognitive_replans=self.cognitive_replans,
                )
            case RecoveryAction.SCHEMA_REPAIR:
                return RecoveryCounters(
                    transport_retries=self.transport_retries,
                    schema_repairs=self.schema_repairs + 1,
                    semantic_revisions=self.semantic_revisions,
                    cognitive_replans=self.cognitive_replans,
                )
            case RecoveryAction.SEMANTIC_REVISION:
                return RecoveryCounters(
                    transport_retries=self.transport_retries,
                    schema_repairs=self.schema_repairs,
                    semantic_revisions=self.semantic_revisions + 1,
                    cognitive_replans=self.cognitive_replans,
                )
            case RecoveryAction.COGNITIVE_REPLAN:
                return RecoveryCounters(
                    transport_retries=self.transport_retries,
                    schema_repairs=self.schema_repairs,
                    semantic_revisions=self.semantic_revisions,
                    cognitive_replans=self.cognitive_replans + 1,
                )
            case _:
                return self


@dataclass(frozen=True, slots=True)
class ResumeRunState:
    """Immutable, typed workflow execution state container."""

    run_id: str
    workflow_id: str
    phase: RunPhase
    step_index: int = 0
    payload: Mapping[str, Any] = field(default_factory=dict)
    counters: RecoveryCounters = field(default_factory=RecoveryCounters)
    budget: RecoveryBudget = field(default_factory=RecoveryBudget)
    context_digest: str = ""
    last_failure: ExecutionFailure | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def compute_digest(self) -> str:
        """Compute SHA-256 state integrity digest."""
        components = [
            f"run:{self.run_id}",
            f"workflow:{self.workflow_id}",
            f"phase:{self.phase.value}",
            f"step:{self.step_index}",
            f"retries:{self.counters.transport_retries}",
            f"repairs:{self.counters.schema_repairs}",
            f"revisions:{self.counters.semantic_revisions}",
            f"replans:{self.counters.cognitive_replans}",
            f"context:{self.context_digest}",
        ]
        return hashlib.sha256(";".join(components).encode("utf-8")).hexdigest()

    def create_checkpoint(self, sequence: int = 0) -> RunCheckpoint:
        """Generate a tamper-evident, monotonically sequenced checkpoint."""
        digest = self.compute_digest()
        checkpoint_id = f"chk-{self.run_id[:8]}-{sequence:04d}"
        return RunCheckpoint(
            checkpoint_id=checkpoint_id,
            sequence=sequence,
            state=self,
            state_digest=digest,
            timestamp=time.time(),
        )

    def to_checkpoint(self, sequence: int = 0) -> RunCheckpoint:
        """Alias for create_checkpoint."""
        return self.create_checkpoint(sequence=sequence)


@dataclass(frozen=True, slots=True)
class RunCheckpoint:
    """Tamper-evident, serialized checkpoint for safe persistence and deterministic resume."""

    checkpoint_id: str
    sequence: int
    state: ResumeRunState
    state_digest: str
    timestamp: float = field(default_factory=time.time)

    @property
    def digest(self) -> str:
        return self.state_digest

    def verify_integrity(self) -> bool:
        """Verify that state payload matches the recorded SHA-256 digest."""
        computed = self.state.compute_digest()
        return computed == self.state_digest

    def as_dict(self) -> dict[str, Any]:
        """Serialize checkpoint metadata for telemetry persistence."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "sequence": self.sequence,
            "phase": self.state.phase.value,
            "step_index": self.state.step_index,
            "state_digest": self.state_digest,
            "timestamp": self.timestamp,
        }


class IllegalPhaseTransitionError(Exception):
    """Raised when an illegal state machine phase transition is attempted."""

    def __init__(self, from_phase: RunPhase, to_phase: RunPhase) -> None:
        super().__init__(
            f"Illegal workflow phase transition: cannot move from {from_phase.value} to {to_phase.value}."
        )
        self.from_phase = from_phase
        self.to_phase = to_phase


def validate_and_transition(
    current: ResumeRunState,
    target_phase: RunPhase,
    *,
    payload_updates: Mapping[str, Any] | None = None,
    recovery_action: RecoveryAction | None = None,
    failure: ExecutionFailure | None = None,
    context_digest: str | None = None,
) -> ResumeRunState:
    """Validate legal state progression and return a new immutable ResumeRunState.

    Enforces:
    - Phase transition table invariants.
    - Terminal state immutability (cannot transition out of terminal state).
    - Recovery budget bounds when a recovery action is specified.
    """
    if current.phase.is_terminal:
        raise IllegalPhaseTransitionError(current.phase, target_phase)

    allowed = LEGAL_PHASE_TRANSITIONS.get(current.phase, set())
    if target_phase not in allowed:
        raise IllegalPhaseTransitionError(current.phase, target_phase)

    new_counters = current.counters
    if recovery_action and recovery_action not in (RecoveryAction.TERMINAL_ESCALATION, RecoveryAction.TERMINAL_FAIL):
        if current.counters.is_exhausted(current.budget, recovery_action):
            raise ValueError(
                f"Recovery budget exhausted for {recovery_action.value}: limit {current.budget.limit_for(recovery_action)} reached."
            )
        new_counters = current.counters.with_increment(recovery_action)

    merged_payload = dict(current.payload)
    if payload_updates:
        merged_payload.update(payload_updates)

    new_step = current.step_index + 1 if target_phase != current.phase else current.step_index
    new_context = context_digest if context_digest is not None else current.context_digest

    return ResumeRunState(
        run_id=current.run_id,
        workflow_id=current.workflow_id,
        phase=target_phase,
        step_index=new_step,
        payload=merged_payload,
        counters=new_counters,
        budget=current.budget,
        context_digest=new_context,
        last_failure=failure or current.last_failure,
        created_at=current.created_at,
        updated_at=time.time(),
    )


def workflow_status_to_run_phase(status: Any) -> RunPhase:
    """Convert a WorkflowStatus or status string to its corresponding RunPhase."""
    val = status.value if hasattr(status, "value") else str(status)
    mapping = {
        "CREATED": RunPhase.CREATED,
        "PLANNED": RunPhase.CREATED,
        "RUNNING": RunPhase.RUNNING,
        "WAITING": RunPhase.WAITING,
        "REVIEWING": RunPhase.RUNNING,
        "REPAIRING": RunPhase.REPAIRING,
        "REVISING": RunPhase.REVISING,
        "REPLANNING": RunPhase.REPLANNING,
        "PAUSED": RunPhase.WAITING,
        "CANCELLED": RunPhase.CANCELLED,
        "FAILED": RunPhase.FAILED,
        "COMPLETED": RunPhase.COMPLETED,
    }
    return mapping.get(val, RunPhase.RUNNING)
