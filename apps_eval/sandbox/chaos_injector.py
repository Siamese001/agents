"""Deterministic chaos fault injector for resilience and recovery testing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Literal, TypeVar

T = TypeVar("T")

FaultKind = Literal[
    "timeout",
    "rate_limit",
    "server_error",
    "truncated_payload",
    "malformed_output",
]


class InjectedChaosError(RuntimeError):
    """Error raised by ChaosInjector during deterministic resilience testing."""

    def __init__(self, fault_kind: FaultKind, message: str) -> None:
        super().__init__(message)
        self.fault_kind = fault_kind


@dataclass(frozen=True)
class ChaosFaultSpec:
    fault_kind: FaultKind
    trigger_count: int = 1
    message: str = "Injected deterministic chaos fault"


@dataclass
class ChaosMetrics:
    total_calls: int = 0
    faults_injected: int = 0
    recovered_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChaosInjector:
    """Wraps a callable and injects a deterministic fault for trigger_count calls before recovery."""

    def __init__(self, spec: ChaosFaultSpec) -> None:
        if spec.trigger_count < 0:
            raise ValueError("trigger_count must be >= 0")
        self.spec = spec
        self.metrics = ChaosMetrics()

    def wrap(self, fn: Callable[..., T]) -> Callable[..., Any]:
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            self.metrics.total_calls += 1
            if self.metrics.faults_injected < self.spec.trigger_count:
                self.metrics.faults_injected += 1
                if self.spec.fault_kind == "timeout":
                    raise TimeoutError(self.spec.message)
                if self.spec.fault_kind in {"rate_limit", "server_error"}:
                    raise InjectedChaosError(self.spec.fault_kind, self.spec.message)
                if self.spec.fault_kind == "truncated_payload":
                    return '{"truncated": true'
                if self.spec.fault_kind == "malformed_output":
                    return {"__malformed__": True, "payload": None}
            result = fn(*args, **kwargs)
            self.metrics.recovered_calls += 1
            return result

        return _wrapped
