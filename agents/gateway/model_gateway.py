"""Unified Model and Tool Capability Gateway.

Hides provider infrastructure, prompt caching idiosyncrasies, and limit handling
behind a single pre-commit validated gateway contract.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from agents.gateway.contracts import CapabilityRequest, CapabilityResponse, ModelTier


class GatewayPreCommitValidationError(ValueError):
    """Raised when a capability request fails pre-commit validation."""


class ModelCapabilityGateway:
    """Unified gateway routing requests to model providers and tools."""

    def __init__(self) -> None:
        self._adapters: dict[str, Callable[[CapabilityRequest], CapabilityResponse]] = {}

    def register_adapter(
        self,
        capability_name: str,
        adapter: Callable[[CapabilityRequest], CapabilityResponse],
    ) -> None:
        """Register a handler adapter for a specific capability."""
        self._adapters[capability_name] = adapter

    def validate_pre_commit(self, request: CapabilityRequest) -> None:
        """Enforce pre-commit validation before sending to model/tool."""
        if not request.capability_name.strip():
            raise GatewayPreCommitValidationError("Capability request must specify non-empty capability_name")

        if not request.prompt_snapshot.is_within_budget:
            raise GatewayPreCommitValidationError(
                f"ContextSnapshot exceeds token budget: "
                f"{request.prompt_snapshot.total_estimated_tokens} > {request.prompt_snapshot.max_token_budget}"
            )

        if request.timeout_seconds <= 0:
            raise GatewayPreCommitValidationError("timeout_seconds must be strictly positive")

        if request.max_output_tokens <= 0:
            raise GatewayPreCommitValidationError("max_output_tokens must be strictly positive")

    def execute(self, request: CapabilityRequest) -> CapabilityResponse:
        """Validate and dispatch capability request with latency and audit tracking."""
        self.validate_pre_commit(request)

        adapter = self._adapters.get(request.capability_name)
        if adapter is None:
            # Fallback default adapter for registered mock/generic invocation
            adapter = self._default_adapter

        start_time = time.perf_counter()
        try:
            response = adapter(request)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return CapabilityResponse(
                content=response.content,
                provider=response.provider,
                model_id=response.model_id,
                status=response.status,
                prompt_tokens=response.prompt_tokens or request.prompt_snapshot.total_estimated_tokens,
                output_tokens=response.output_tokens or max(1, len(response.content) // 4),
                latency_ms=elapsed_ms,
                error_message=response.error_message,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return CapabilityResponse(
                content="",
                provider="gateway",
                model_id="none",
                status="ERROR",
                prompt_tokens=request.prompt_snapshot.total_estimated_tokens,
                output_tokens=0,
                latency_ms=elapsed_ms,
                error_message=str(exc),
            )

    @staticmethod
    def _default_adapter(request: CapabilityRequest) -> CapabilityResponse:
        """Default simulated execution adapter when no external provider is registered."""
        prompt_text = request.prompt_snapshot.assemble_text()
        return CapabilityResponse(
            content=f"Simulated execution for capability '{request.capability_name}' on prompt length {len(prompt_text)} chars.",
            provider="simulated_default",
            model_id="simulated-v1",
            status="SUCCESS",
            prompt_tokens=request.prompt_snapshot.total_estimated_tokens,
            output_tokens=25,
        )


__all__ = [
    "GatewayPreCommitValidationError",
    "ModelCapabilityGateway",
]
