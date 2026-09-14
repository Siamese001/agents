"""Normalized Agentic Orchestration Primitives and Workflow Status Contracts.

Defines the core vocabulary for control-flow, state transitions, and recovery
lifecycles across the Sovereign Agentic Platform.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping


class OrchestrationPrimitive(str, Enum):
    """Authoritative primitive operations for multi-agent workflows."""

    SEQUENCE = "SEQUENCE"
    BRANCH = "BRANCH"
    PARALLEL = "PARALLEL"
    JOIN = "JOIN"
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    FAIL = "FAIL"
    COMPLETE = "COMPLETE"


class WorkflowStatus(str, Enum):
    """Authoritative workflow execution lifecycle statuses."""

    CREATED = "CREATED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    REVIEWING = "REVIEWING"
    REPAIRING = "REPAIRING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"

    @property
    def is_terminal(self) -> bool:
        """Indicate whether status is an immutable terminal state."""
        return self in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        )

    @property
    def is_active(self) -> bool:
        """Indicate whether status represents active in-flight processing."""
        return self in (
            WorkflowStatus.RUNNING,
            WorkflowStatus.REVIEWING,
            WorkflowStatus.REPAIRING,
            WorkflowStatus.WAITING,
        )


@dataclass(frozen=True, slots=True)
class ExecutionRetry:
    """Transient technical retry instruction (e.g. rate limit, network timeout, 5xx).

    Repeats the identical execution request with bounded exponential backoff.
    Does NOT modify reasoning, prompt, constraints, or subgoals.
    """

    attempt: int
    max_attempts: int = 3
    backoff_seconds: float = 1.0
    cause: str = ""

    @property
    def can_retry(self) -> bool:
        return self.attempt < self.max_attempts


@dataclass(frozen=True, slots=True)
class SemanticRepair:
    """Deterministic, targeted repair of localized field or format imperfections.

    Applies deterministic patch operations or targeted formatting adjustments
    without re-invoking full cognitive re-planning.
    """

    target_fields: tuple[str, ...] = ()
    validation_errors: tuple[str, ...] = ()
    repair_action: str = ""
    repaired_payload: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Replan:
    """Cognitive feedback loop modifying plan, goals, or constraints.

    Triggered when an observation or review verdict reveals semantic
    insufficiency or unfulfilled subgoals. Modifies the L1 task plan and
    initiates a new bounded execution cycle.
    """

    cycle: int
    max_cycles: int = 2
    critique: str = ""
    unfulfilled_subgoals: tuple[str, ...] = ()
    adapted_constraints: Mapping[str, Any] = field(default_factory=dict)

    @property
    def can_replan(self) -> bool:
        return self.cycle < self.max_cycles


@dataclass(slots=True)
class WorkflowStep:
    """A declarative step within an orchestrated workflow plan."""

    step_id: str
    primitive: OrchestrationPrimitive
    handler: Callable[..., Any]
    depends_on: tuple[str, ...] = ()
    optional: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ExecutionRetry",
    "OrchestrationPrimitive",
    "Replan",
    "SemanticRepair",
    "WorkflowStatus",
    "WorkflowStep",
]
