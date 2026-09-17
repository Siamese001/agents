"""Authoritative Structured Agentic Feedback Controller.

Part of Sovereign Agentic Platform Orchestration Governance (Wave 3).
Translates validation failures and judge feedback into typed, policy-governed
revision requests, separating deterministic schema/format repair from semantic
model revision loops while strictly enforcing recovery budgets.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from agents.orchestration.failure_taxonomy import (
    ExecutionFailure,
    FailureKind,
    RecoveryAction,
    RevisionRequest,
    derive_recovery_action,
)
from agents.orchestration.state_contracts import (
    RecoveryBudget,
    RecoveryCounters,
    ResumeRunState,
)


class ControllerAction(str, Enum):
    """Authoritative actions emitted by the FeedbackController."""

    ACCEPT = "ACCEPT"                                   # Validation passed cleanly; workflow continues
    DETERMINISTIC_NORMALIZE = "DETERMINISTIC_NORMALIZE" # Local deterministic fix applied; no LLM call
    REQUEST_SEMANTIC_REVISION = "REQUEST_SEMANTIC_REVISION" # Structured revision packet sent to model
    COGNITIVE_REPLAN = "COGNITIVE_REPLAN"               # Plan-level redesign or routing alternative
    TERMINAL_ESCALATION = "TERMINAL_ESCALATION"         # Budget exhausted or unrecoverable policy failure
    TERMINAL_FAIL = "TERMINAL_ESCALATION"               # Backward-compatible terminal alias


@dataclass(frozen=True, slots=True)
class FeedbackDecision:
    """Immutable decision artifact produced by the FeedbackController."""

    action: ControllerAction
    revision_request: RevisionRequest | None = None
    failure: ExecutionFailure | None = None
    diagnostic: str = ""
    can_retry: bool = False
    repair_hint: str = ""
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        """Serialize feedback decision to telemetry payload."""
        return {
            "action": self.action.value,
            "diagnostic": self.diagnostic,
            "can_retry": self.can_retry,
            "repair_hint": self.repair_hint,
            "has_revision_request": self.revision_request is not None,
            "timestamp": self.timestamp,
        }


class FeedbackController:
    """Policy-governed feedback controller for agentic validation loops.

    Invariants:
    1. Clean validations always yield ControllerAction.ACCEPT.
    2. Policy violations immediately yield ControllerAction.TERMINAL_FAIL.
    3. Schema errors yield ControllerAction.DETERMINISTIC_NORMALIZE before any model revision.
    4. Quality and factual conflicts yield structured RevisionRequest packets until budget exhaustion.
    5. Exceeded recovery budgets strictly yield ControllerAction.TERMINAL_FAIL.
    """

    def __init__(
        self,
        default_budget: RecoveryBudget | None = None,
        learning_store: Any | None = None,
    ) -> None:
        self.default_budget = default_budget or RecoveryBudget()
        self.learning_store = learning_store

    def evaluate_result(
        self,
        validation_passed: bool,
        *,
        errors: Sequence[str] = (),
        failure_kind: FailureKind = FailureKind.DETERMINISTIC_QUALITY,
        state: ResumeRunState | None = None,
        evidence: Sequence[str] = (),
        allowed_actions: Sequence[str] = ("revise_content", "fix_constraint"),
        context_diff: Mapping[str, Any] | None = None,
    ) -> FeedbackDecision:
        """Evaluate a validation or judge outcome and decide next orchestration action."""
        if validation_passed and not errors:
            return FeedbackDecision(
                action=ControllerAction.ACCEPT,
                diagnostic="Validation passed cleanly; output satisfies all constraints.",
                can_retry=False,
            )

        # Policy failures never auto-retry or auto-revise
        if failure_kind == FailureKind.POLICY:
            fail_desc = "; ".join(errors) or "Policy validation check failed."
            failure = ExecutionFailure(
                failure_kind=FailureKind.POLICY,
                message=f"Policy violation: {fail_desc}",
                recovery_action=RecoveryAction.TERMINAL_FAIL,
                retryable=False,
                evidence=tuple(evidence),
            )
            return FeedbackDecision(
                action=ControllerAction.TERMINAL_FAIL,
                failure=failure,
                diagnostic=f"Policy violation fatal: {fail_desc}",
                can_retry=False,
            )

        # Schema errors are deterministically repaired locally
        if failure_kind == FailureKind.SCHEMA:
            schema_err = "; ".join(errors) or "Schema mismatch."
            failure = ExecutionFailure(
                failure_kind=FailureKind.SCHEMA,
                message=f"Schema violation: {schema_err}",
                recovery_action=RecoveryAction.SCHEMA_REPAIR,
                retryable=True,
                evidence=tuple(evidence),
            )
            return FeedbackDecision(
                action=ControllerAction.DETERMINISTIC_NORMALIZE,
                failure=failure,
                diagnostic=f"Schema normalization indicated: {schema_err}",
                can_retry=True,
                repair_hint="Apply deterministic JSON/schema repair function.",
            )

        # Retrieve counters and budgets
        counters = state.counters if state else RecoveryCounters()
        budget = state.budget if state else self.default_budget

        # Quality and factual conflicts trigger semantic revision
        if failure_kind in (FailureKind.DETERMINISTIC_QUALITY, FailureKind.FACTUAL_CONFLICT):
            current_revisions = counters.semantic_revisions
            max_revisions = budget.max_semantic_revisions
            recovery = derive_recovery_action(failure_kind, current_revisions, max_revisions)

            if recovery == RecoveryAction.TERMINAL_FAIL or current_revisions >= max_revisions:
                failure = ExecutionFailure(
                    failure_kind=failure_kind,
                    message=f"Semantic revision budget exhausted ({current_revisions}/{max_revisions}).",
                    recovery_action=RecoveryAction.TERMINAL_FAIL,
                    retryable=False,
                    evidence=tuple(evidence),
                )
                return FeedbackDecision(
                    action=ControllerAction.TERMINAL_FAIL,
                    failure=failure,
                    diagnostic=f"Quality revision budget exhausted: {current_revisions}/{max_revisions}.",
                    can_retry=False,
                )

            # Create structured, evidence-based RevisionRequest
            req = RevisionRequest(
                failure_kind=failure_kind,
                failed_constraints=tuple(errors) or ("Unspecified quality constraint violation",),
                evidence=tuple(evidence),
                allowed_actions=tuple(allowed_actions),
                attempt_count=current_revisions,
                max_revisions=max_revisions,
                context_diff=dict(context_diff or {}),
            )
            failure = ExecutionFailure(
                failure_kind=failure_kind,
                message=f"Quality check failed: {'; '.join(errors)}",
                recovery_action=RecoveryAction.SEMANTIC_REVISION,
                retryable=True,
                evidence=tuple(evidence),
            )
            # Query empirical repair hints from persistent learning store
            empirical_hint = ""
            if self.learning_store:
                try:
                    for err in errors:
                        self.learning_store.record_failure(
                            failure_kind, err, run_id=state.run_id if state else ""
                        )
                    hints: list[str] = []
                    for err in errors:
                        hints.extend(self.learning_store.get_repair_hints(failure_kind, err))
                    if hints:
                        empirical_hint = f"Empirical hint from prior runs: {'; '.join(hints[:3])}"
                except Exception:
                    pass

            return FeedbackDecision(
                action=ControllerAction.REQUEST_SEMANTIC_REVISION,
                revision_request=req,
                failure=failure,
                diagnostic=f"Semantic revision requested (attempt {current_revisions + 1}/{max_revisions}).",
                can_retry=True,
                repair_hint=empirical_hint,
            )

        # Planning failures trigger cognitive replanning
        if failure_kind == FailureKind.PLANNING:
            current_replans = counters.cognitive_replans
            max_replans = budget.max_cognitive_replans
            if current_replans >= max_replans:
                failure = ExecutionFailure(
                    failure_kind=FailureKind.PLANNING,
                    message=f"Cognitive replan budget exhausted ({current_replans}/{max_replans}).",
                    recovery_action=RecoveryAction.TERMINAL_FAIL,
                    retryable=False,
                    evidence=tuple(evidence),
                )
                return FeedbackDecision(
                    action=ControllerAction.TERMINAL_FAIL,
                    failure=failure,
                    diagnostic="Cognitive replan budget exhausted.",
                    can_retry=False,
                )

            failure = ExecutionFailure(
                failure_kind=FailureKind.PLANNING,
                message=f"Plan execution failed: {'; '.join(errors)}",
                recovery_action=RecoveryAction.COGNITIVE_REPLAN,
                retryable=True,
                evidence=tuple(evidence),
            )
            return FeedbackDecision(
                action=ControllerAction.COGNITIVE_REPLAN,
                failure=failure,
                diagnostic=f"Cognitive replanning requested (replan {current_replans + 1}/{max_replans}).",
                can_retry=True,
            )

        # Transport failures
        current_retries = counters.transport_retries
        max_retries = budget.max_transport_retries
        if current_retries >= max_retries:
            failure = ExecutionFailure(
                failure_kind=FailureKind.TRANSPORT,
                message=f"Transport retry budget exhausted ({current_retries}/{max_retries}).",
                recovery_action=RecoveryAction.TERMINAL_FAIL,
                retryable=False,
            )
            return FeedbackDecision(
                action=ControllerAction.TERMINAL_FAIL,
                failure=failure,
                diagnostic="Transport retry budget exhausted.",
                can_retry=False,
            )

        failure = ExecutionFailure(
            failure_kind=FailureKind.TRANSPORT,
            message=f"Transport error: {'; '.join(errors)}",
            recovery_action=RecoveryAction.TRANSPORT_RETRY,
            retryable=True,
        )
        return FeedbackDecision(
            action=ControllerAction.DETERMINISTIC_NORMALIZE,
            failure=failure,
            diagnostic=f"Transport retry eligible ({current_retries + 1}/{max_retries}).",
            can_retry=True,
        )

    def record_resolution_outcome(
        self,
        failure_kind: FailureKind,
        constraint: str,
        *,
        run_id: str = "",
        action_taken: str = "SEMANTIC_REVISION",
        repair_hint: str = "",
        outcome: str = "SUCCESS",
    ) -> None:
        """Record resolution efficacy into learning store if configured."""
        if self.learning_store:
            try:
                from agents.orchestration.learning_store import compute_failure_signature

                sig_hash = compute_failure_signature(failure_kind, constraint)
                self.learning_store.record_resolution(
                    sig_hash,
                    run_id=run_id,
                    action_taken=action_taken,
                    repair_hint=repair_hint,
                    outcome=outcome,
                )
            except Exception:
                pass
