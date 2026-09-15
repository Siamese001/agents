"""Evaluation Service and Structured Validation Contracts.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Validates generated outputs and classifies failures into typed FailureKinds
without directly modifying run state, persisting files, or performing revisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from agents.orchestration.failure_taxonomy import FailureKind
from agents.orchestration.feedback_controller import FeedbackController, FeedbackDecision


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    """Request to evaluate a generated section or workflow artifact."""

    run_id: str
    section_name: str
    content: Mapping[str, Any] = field(default_factory=dict)
    criteria: Mapping[str, Any] = field(default_factory=dict)
    required_keys: tuple[str, ...] = ()
    max_word_count: int | None = None
    policy_checks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Outcome of evaluating a generated section."""

    run_id: str
    section_name: str
    is_valid: bool
    failure_kind: FailureKind | None = None
    errors: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.is_valid


class EvaluationService:
    """Domain service evaluating section outputs and classifying failures."""

    def __init__(self, feedback_controller: FeedbackController | None = None) -> None:
        self._controller = feedback_controller or FeedbackController()

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        """Evaluate section content against structural and semantic requirements."""
        errors: list[str] = []
        diagnostics: dict[str, Any] = {}

        # 1. Structural / Schema Verification
        missing_keys = [k for k in request.required_keys if k not in request.content]
        if missing_keys:
            errors.append(f"Missing required keys: {', '.join(missing_keys)}")
            return EvaluationResult(
                run_id=request.run_id,
                section_name=request.section_name,
                is_valid=False,
                failure_kind=FailureKind.SCHEMA,
                errors=tuple(errors),
                diagnostics={"missing_keys": missing_keys},
            )

        # 2. Word Count / Density Bounds
        if request.max_word_count is not None:
            text_corpus = " ".join(str(v) for v in request.content.values())
            words = text_corpus.split()
            word_count = len(words)
            diagnostics["word_count"] = word_count
            if word_count > request.max_word_count:
                errors.append(
                    f"Word count {word_count} exceeds limit of {request.max_word_count}"
                )
                return EvaluationResult(
                    run_id=request.run_id,
                    section_name=request.section_name,
                    is_valid=False,
                    failure_kind=FailureKind.DETERMINISTIC_QUALITY,
                    errors=tuple(errors),
                    diagnostics=diagnostics,
                )

        # 3. Policy Rule Checks
        for check in request.policy_checks:
            if check == "no_empty_fields":
                empty_fields = [k for k, v in request.content.items() if not str(v).strip()]
                if empty_fields:
                    errors.append(f"Empty fields detected: {', '.join(empty_fields)}")
                    return EvaluationResult(
                        run_id=request.run_id,
                        section_name=request.section_name,
                        is_valid=False,
                        failure_kind=FailureKind.POLICY,
                        errors=tuple(errors),
                        diagnostics={"empty_fields": empty_fields},
                    )

        return EvaluationResult(
            run_id=request.run_id,
            section_name=request.section_name,
            is_valid=True,
            failure_kind=None,
            errors=(),
            diagnostics=diagnostics,
        )

    def evaluate_and_decide(
        self, request: EvaluationRequest
    ) -> tuple[EvaluationResult, FeedbackDecision]:
        """Evaluate request and derive structured FeedbackDecision."""
        eval_res = self.evaluate(request)
        decision = self._controller.evaluate_result(
            validation_passed=eval_res.is_valid,
            failure_kind=eval_res.failure_kind,
            errors=eval_res.errors,
            evidence=(),
            step_name=request.section_name,
        )
        return eval_res, decision
