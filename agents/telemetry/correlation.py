"""Authoritative correlation context for multi-agent executions.

Provides immutable propagation of correlation identifiers:
- ``run_id``: Identifier for the top-level execution run.
- ``workflow_id``: Identifier for the workflow state machine.
- ``attempt_id``: Attempt counter for retries/replans.
- ``span_id``: Unique identifier for the active execution span.
- ``parent_span_id``: Identifier for the parent span in the call hierarchy.
- ``provenance_digest``: SHA-256 digest of input context snapshot.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from typing import Any
import uuid


@dataclass(frozen=True)
class CorrelationContext:
    """Immutable correlation context passed through agentic pipelines."""

    run_id: str
    workflow_id: str
    attempt_id: int = 1
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_span_id: str | None = None
    provenance_digest: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def new_child(
        self,
        step_name: str = "",
        *,
        attempt_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CorrelationContext:
        """Create a child correlation span linked to this context."""
        merged_meta = dict(self.metadata)
        if step_name:
            merged_meta["step_name"] = step_name
        if metadata:
            merged_meta.update(metadata)

        return CorrelationContext(
            run_id=self.run_id,
            workflow_id=self.workflow_id,
            attempt_id=self.attempt_id if attempt_id is None else attempt_id,
            span_id=uuid.uuid4().hex[:12],
            parent_span_id=self.span_id,
            provenance_digest=self.provenance_digest,
            metadata=merged_meta,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize context to standard correlation dictionary."""
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "attempt_id": self.attempt_id,
            "span_id": self.span_id,
        }
        if self.parent_span_id is not None:
            payload["parent_span_id"] = self.parent_span_id
        if self.provenance_digest is not None:
            payload["provenance_digest"] = self.provenance_digest
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorrelationContext:
        """Construct a CorrelationContext from dictionary."""
        return cls(
            run_id=str(data.get("run_id", "")),
            workflow_id=str(data.get("workflow_id", "")),
            attempt_id=int(data.get("attempt_id", 1)),
            span_id=str(data.get("span_id", uuid.uuid4().hex[:12])),
            parent_span_id=data.get("parent_span_id"),
            provenance_digest=data.get("provenance_digest"),
            metadata=dict(data.get("metadata") or {}),
        )


_CURRENT_CORRELATION: contextvars.ContextVar[CorrelationContext | None] = (
    contextvars.ContextVar("current_correlation", default=None)
)


def get_current_correlation() -> CorrelationContext | None:
    """Return the currently bound correlation context, if any."""
    return _CURRENT_CORRELATION.get()


def set_current_correlation(
    ctx: CorrelationContext | None,
) -> contextvars.Token[CorrelationContext | None]:
    """Bind a correlation context to the current task/thread."""
    return _CURRENT_CORRELATION.set(ctx)


__all__ = [
    "CorrelationContext",
    "get_current_correlation",
    "set_current_correlation",
]
