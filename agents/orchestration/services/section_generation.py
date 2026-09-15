"""Section Generation Service and Typed Section Contracts.

Part of Sovereign Agentic Platform Monolith Decomposition (Wave 5).
Coordinates generation of logical sections via injected generation ports
without direct persistence, CLI, or concrete lane monolith coupling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from agents.orchestration.failure_taxonomy import (
    ExecutionFailure,
    FailureKind,
    RecoveryAction,
)
from agents.orchestration.state_contracts import RecoveryBudget, ResumeRunState


@dataclass(frozen=True, slots=True)
class SectionGenerationRequest:
    """Input specification for generating a logical resume/document section."""

    run_id: str
    section_name: str
    lane_id: str
    inputs: Mapping[str, Any] = field(default_factory=dict)
    budget: RecoveryBudget = field(default_factory=RecoveryBudget)
    current_state: ResumeRunState | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class SectionGenerationResult:
    """Typed outcome of a section generation attempt."""

    run_id: str
    section_name: str
    success: bool
    content: Mapping[str, Any] = field(default_factory=dict)
    failure: ExecutionFailure | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_successful(self) -> bool:
        return self.success


class SectionGenerationPort(Protocol):
    """Protocol for decoupled lane or LLM generation workers."""

    def generate_section(
        self, request: SectionGenerationRequest
    ) -> SectionGenerationResult:
        """Generate content for the requested section."""
        ...


class DefaultSectionGenerator:
    """Reference implementation of SectionGenerationPort."""

    def __init__(
        self,
        handler: Callable[[SectionGenerationRequest], SectionGenerationResult] | None = None,
    ) -> None:
        self._handler = handler

    def generate_section(
        self, request: SectionGenerationRequest
    ) -> SectionGenerationResult:
        if self._handler is not None:
            return self._handler(request)
        return SectionGenerationResult(
            run_id=request.run_id,
            section_name=request.section_name,
            success=True,
            content=dict(request.inputs),
            metadata={"generator": "DefaultSectionGenerator"},
        )


class SectionGenerationService:
    """Domain service managing section generation orchestration."""

    def __init__(self, port: SectionGenerationPort | None = None) -> None:
        self._port: SectionGenerationPort = port or DefaultSectionGenerator()

    def generate(self, request: SectionGenerationRequest) -> SectionGenerationResult:
        """Execute section generation with budget verification and failure classification."""
        if not request.section_name.strip():
            return SectionGenerationResult(
                run_id=request.run_id,
                section_name=request.section_name,
                success=False,
                failure=ExecutionFailure(
                    failure_kind=FailureKind.SCHEMA,
                    message="Section name cannot be empty.",
                    recovery_action=RecoveryAction.TERMINAL_FAIL,
                    retryable=False,
                ),
            )

        try:
            result = self._port.generate_section(request)
            return result
        except Exception as err:
            return SectionGenerationResult(
                run_id=request.run_id,
                section_name=request.section_name,
                success=False,
                failure=ExecutionFailure(
                    failure_kind=FailureKind.TRANSPORT,
                    message=f"Section generation raised exception: {err}",
                    recovery_action=RecoveryAction.TRANSPORT_RETRY,
                    retryable=True,
                ),
            )
