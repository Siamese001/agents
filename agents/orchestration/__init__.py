"""Agents Orchestration Package.

Exports authoritative primitives, state machine, execution engine, typed state contracts,
and failure taxonomy for governed multi-agent workflows.
"""

from agents.orchestration.engine import (
    StepExecutionResult,
    WorkflowExecutionEngine,
    WorkflowExecutionReport,
)
from agents.orchestration.failure_taxonomy import (
    ExecutionFailure,
    FailureKind,
    RecoveryAction,
    RevisionRequest,
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
    IllegalPhaseTransitionError,
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
    RunCheckpoint,
    RunPhase,
    validate_and_transition,
)
from agents.orchestration.state_machine import (
    InvalidStateTransitionError,
    StateTransitionRecord,
    WorkflowStateMachine,
)

__all__ = [
    "ExecutionFailure",
    "ExecutionRetry",
    "FailureKind",
    "IllegalPhaseTransitionError",
    "InvalidStateTransitionError",
    "OrchestrationPrimitive",
    "RecoveryAction",
    "RecoveryBudget",
    "RecoveryCounters",
    "Replan",
    "ResumeRunState",
    "RevisionRequest",
    "RunCheckpoint",
    "RunPhase",
    "SemanticRepair",
    "StateTransitionRecord",
    "StepExecutionResult",
    "WorkflowExecutionEngine",
    "WorkflowExecutionReport",
    "WorkflowStateMachine",
    "WorkflowStatus",
    "WorkflowStep",
    "derive_recovery_action",
    "validate_and_transition",
]
