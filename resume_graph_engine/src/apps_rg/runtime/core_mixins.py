"""Small Apps RG-owned behavior mixins.

The two consumers only need component identity and a stable marker base class;
neither needs an external runtime policy or initialization side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class _CircuitBreaker:
    """Small local circuit breaker for app-owned executor helpers."""

    name: str
    failure_threshold: int
    reset_after_s: int
    failure_count: int = 0
    is_open: bool = False

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        self.failure_count += 1
        self.is_open = self.failure_count >= self.failure_threshold


@dataclass(frozen=True)
class _ErrorRecovery:
    """Explicit retry policy retained by local hardened executors."""

    max_retries: int
    base_backoff_ms: int
    jitter_ms: int
    enable_circuit_breaker: bool


@dataclass(frozen=True)
class _Telemetry:
    """Minimal component-scoped telemetry identity with no external side effect."""

    component_name: str


class HardeningMixin:
    """Provide local resilience state for hardened app executors."""

    def __init__(
        self,
        *,
        component_name: str = "",
        failure_threshold: int = 5,
        reset_timeout_s: int = 30,
        max_retries: int = 3,
        base_backoff_ms: int = 200,
        jitter_ms: int = 100,
        telemetry: _Telemetry | None = None,
        **_kwargs: object,
    ) -> None:
        self.component_name = str(component_name)
        self.circuit_breaker = _CircuitBreaker(
            name=f"{self.component_name}_breaker",
            failure_threshold=max(1, int(failure_threshold)),
            reset_after_s=max(0, int(reset_timeout_s)),
        )
        self.error_recovery = _ErrorRecovery(
            max_retries=max(0, int(max_retries)),
            base_backoff_ms=max(0, int(base_backoff_ms)),
            jitter_ms=max(0, int(jitter_ms)),
            enable_circuit_breaker=True,
        )
        self.telemetry = telemetry or _Telemetry(self.component_name)

    async def execute_hardened(
        self,
        _operation: str,
        fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Run one operation with local breaker state and bounded retries."""

        if self.circuit_breaker.is_open:
            raise RuntimeError(f"circuit breaker is open: {self.circuit_breaker.name}")
        last_error: Exception | None = None
        for _attempt in range(self.error_recovery.max_retries + 1):
            try:
                result = await fn()
            except Exception as exc:
                last_error = exc
                self.circuit_breaker.record_failure()
                if self.circuit_breaker.is_open:
                    break
            else:
                self.circuit_breaker.record_success()
                return result
        assert last_error is not None
        raise last_error


class SubatomicTestingMixin:
    """Marker base for Apps RG probe-oriented helper types."""

__all__ = ["HardeningMixin", "SubatomicTestingMixin"]
