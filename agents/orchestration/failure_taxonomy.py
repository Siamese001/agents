"""Authoritative Failure Taxonomy and Structured Revision Contracts.

Part of Sovereign Agentic Platform Orchestration Governance (Wave 2).
Categorizes runtime failures into orthogonal classes and defines structured,
evidence-based revision requests for bounded self-correction loops.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FailureKind(str, Enum):
    """Authoritative classifications for all execution and agentic failures."""

    TRANSPORT = "TRANSPORT"                      # Network timeouts, HTTP 5xx, socket errors, transient RPC failures
    PROVIDER = "PROVIDER"                        # Model provider auth, quota exceeded, context length exceeded, rate limit
    SCHEMA = "SCHEMA"                            # JSON parse failures, missing required fields, pydantic/type mismatches
    DETERMINISTIC_QUALITY = "DETERMINISTIC_QUALITY"  # Regex checks, word count limits, formatting, bullet constraint rules
    FACTUAL_CONFLICT = "FACTUAL_CONFLICT"        # Hallucinations, fact graph violations, date inconsistencies
    PLANNING = "PLANNING"                        # Subgoal failure, missing prerequisite, unexecutable plan sequence
    POLICY = "POLICY"                            # Safety block, HITL rejection, compliance gate denial, security guard


class RecoveryAction(str, Enum):
    """Deterministic recovery mechanisms governed by independent budgets."""

    TRANSPORT_RETRY = "TRANSPORT_RETRY"          # Transient retry with exponential backoff; identical request
    SCHEMA_REPAIR = "SCHEMA_REPAIR"              # Deterministic patch or targeted re-parse; no model re-prompt
    SEMANTIC_REVISION = "SEMANTIC_REVISION"      # Multi-turn model turn with structured RevisionRequest feedback
    COGNITIVE_REPLAN = "COGNITIVE_REPLAN"        # Plan-level redesign or strategy alternation
    TERMINAL_FAIL = "TERMINAL_FAIL"              # Escalation to fatal run status; unrecoverable failure


@dataclass(frozen=True, slots=True)
class ExecutionFailure:
    """Immutable, typed descriptor of a runtime or quality failure."""

    failure_kind: FailureKind
    message: str
    recovery_action: RecoveryAction
    retryable: bool = True
    error_code: str = ""
    evidence: tuple[str, ...] = field(default_factory=tuple)
    details: Mapping[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.message:
            raise ValueError("ExecutionFailure must have a non-empty message.")


@dataclass(frozen=True, slots=True)
class RevisionRequest:
    """Structured, evidence-based feedback packet passed to model for semantic revision."""

    failure_kind: FailureKind
    failed_constraints: tuple[str, ...]
    evidence: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    attempt_count: int
    max_revisions: int = 2
    context_diff: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.attempt_count < 0:
            raise ValueError(f"attempt_count cannot be negative: {self.attempt_count}")
        if self.max_revisions < 1:
            raise ValueError(f"max_revisions must be at least 1: {self.max_revisions}")
        if not self.failed_constraints:
            raise ValueError("RevisionRequest requires at least one failed constraint description.")

    @property
    def can_revise(self) -> bool:
        """Check if revision budget remains available."""
        return self.attempt_count < self.max_revisions


def derive_recovery_action(kind: FailureKind, attempt: int, max_limit: int) -> RecoveryAction:
    """Deterministically map a failure kind to its corresponding recovery action.

    Enforces strict precedence:
    - Transport -> TRANSPORT_RETRY
    - Schema -> SCHEMA_REPAIR
    - Deterministic Quality & Factual Conflict -> SEMANTIC_REVISION
    - Planning -> COGNITIVE_REPLAN
    - Policy -> TERMINAL_FAIL (Policy denials are never auto-revised)
    """
    if attempt >= max_limit:
        return RecoveryAction.TERMINAL_FAIL

    match kind:
        case FailureKind.TRANSPORT:
            return RecoveryAction.TRANSPORT_RETRY
        case FailureKind.SCHEMA:
            return RecoveryAction.SCHEMA_REPAIR
        case FailureKind.DETERMINISTIC_QUALITY | FailureKind.FACTUAL_CONFLICT:
            return RecoveryAction.SEMANTIC_REVISION
        case FailureKind.PLANNING:
            return RecoveryAction.COGNITIVE_REPLAN
        case _:
            return RecoveryAction.TERMINAL_FAIL


def classify_failure(exc: Exception) -> FailureKind:
    """Classify an exception into an authoritative FailureKind."""
    msg = str(exc).lower()
    if any(token in msg for token in ("timeout", "rate limit", "connection reset", "503", "504", "transient")):
        return FailureKind.TRANSPORT
    if any(token in msg for token in ("json", "schema", "validation", "pydantic", "missing key")):
        return FailureKind.SCHEMA
    if any(token in msg for token in ("policy", "denied", "prohibited", "forbidden", "unauthorized")):
        return FailureKind.POLICY
    if any(token in msg for token in ("replan", "goal", "strategy", "task plan")):
        return FailureKind.PLANNING
    return FailureKind.PROVIDER


__all__ = [
    "ExecutionFailure",
    "FailureKind",
    "RecoveryAction",
    "RevisionRequest",
    "classify_failure",
    "derive_recovery_action",
]
