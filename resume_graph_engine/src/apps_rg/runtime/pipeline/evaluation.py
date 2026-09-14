"""Evaluation Service.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Applies validators, quality checks, and judges to section outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from agents.orchestration.failure_taxonomy import FailureKind
from agents.orchestration.feedback_controller import (
    ControllerAction,
    FeedbackController,
    FeedbackDecision,
)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Outcome of an evaluation pass over a section output."""

    section_id: str
    passed: bool
    score: float
    violations: tuple[str, ...]
    decision: FeedbackDecision


class EvaluationService:
    """Service evaluating generated sections and generating structured feedback decisions."""

    def __init__(self, controller: FeedbackController | None = None) -> None:
        self.controller = controller or FeedbackController()
        self._validators: dict[str, list[Callable[[str], list[str]]]] = {}

    def register_validator(
        self,
        section_id: str,
        validator: Callable[[str], list[str]],
    ) -> None:
        """Register a validation rule function for a section."""
        self._validators.setdefault(section_id, []).append(validator)

    def evaluate(
        self,
        section_id: str,
        content: str,
    ) -> EvaluationReport:
        """Evaluate section content and return structured evaluation report."""
        violations: list[str] = []
        for v in self._validators.get(section_id, []):
            errs = v(content)
            violations.extend(errs)

        passed = len(violations) == 0
        score = 1.0 if passed else max(0.0, 1.0 - (0.2 * len(violations)))

        decision = self.controller.evaluate_result(
            validation_passed=passed,
            errors=violations,
            failure_kind=FailureKind.DETERMINISTIC_QUALITY if not passed else FailureKind.PROVIDER,
        )

        return EvaluationReport(
            section_id=section_id,
            passed=passed,
            score=score,
            violations=tuple(violations),
            decision=decision,
        )
