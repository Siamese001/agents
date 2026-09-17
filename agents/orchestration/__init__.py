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
from agents.orchestration.feedback_controller import (
    ControllerAction,
    FeedbackController,
    FeedbackDecision,
)
from agents.orchestration.learning_store import (
    FeedbackLearningStore,
    compute_failure_signature,
    normalize_constraint_key,
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
    "ControllerAction",
    "ExecutionFailure",
    "ExecutionRetry",
    "FailureKind",
    "FeedbackController",
    "FeedbackDecision",
    "FeedbackLearningStore",
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
    "compute_failure_signature",
    "derive_recovery_action",
    "normalize_constraint_key",
    "validate_and_transition",
]
