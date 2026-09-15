"""Structured telemetry events and event streaming for agentic workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any
import uuid

from agents.telemetry.correlation import CorrelationContext


class TelemetryEventType(str, Enum):
    """Canonical event types for structured telemetry emission."""

    WORKFLOW_START = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_FAILED = "workflow_failed"
    STEP_START = "step_start"
    STEP_COMPLETE = "step_complete"
    STEP_FAILED = "step_failed"
    STEP_RECOVERY = "step_recovery"
    MODEL_INVOCATION = "model_invocation"
    EVALUATION_VERDICT = "evaluation_verdict"
    CALIBRATION_CHECK = "calibration_check"


@dataclass(frozen=True)
class TelemetryEvent:
    """A single structured, correlated telemetry record."""

    event_id: str
    event_type: TelemetryEventType
    timestamp: str
    correlation: CorrelationContext
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary representation."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "correlation": self.correlation.to_dict(),
            "payload": dict(self.payload),
        }

    def to_agent_event_envelope(
        self,
        sequence: int = 1,
        producer: str = "telemetry_emitter",
        previous_event_digest: str | None = None,
    ) -> Any:
        """Convert to canonical AgentEventEnvelope."""
        from agents.observability.events import AgentEventType, create_event_envelope

        event_type_map = {
            TelemetryEventType.WORKFLOW_START: AgentEventType.PHASE_TRANSITION,
            TelemetryEventType.WORKFLOW_COMPLETE: AgentEventType.PHASE_TRANSITION,
            TelemetryEventType.WORKFLOW_FAILED: AgentEventType.PHASE_TRANSITION,
            TelemetryEventType.STEP_START: AgentEventType.PHASE_TRANSITION,
            TelemetryEventType.STEP_COMPLETE: AgentEventType.PHASE_TRANSITION,
            TelemetryEventType.STEP_FAILED: AgentEventType.PHASE_TRANSITION,
            TelemetryEventType.STEP_RECOVERY: AgentEventType.FEEDBACK_DECISION,
            TelemetryEventType.EVALUATION_VERDICT: AgentEventType.FEEDBACK_DECISION,
        }
        canonical_type = event_type_map.get(self.event_type, AgentEventType.FEEDBACK_DECISION)
        corr_id = getattr(self.correlation, "correlation_id", None) or getattr(self.correlation, "span_id", self.correlation.run_id)
        return create_event_envelope(
            event_type=canonical_type,
            run_id=self.correlation.run_id,
            correlation_id=corr_id,
            sequence=sequence,
            producer=producer,
            payload={
                "telemetry_event_type": self.event_type.value,
                **self.payload,
            },
            previous_event_digest=previous_event_digest,
            event_id=self.event_id,
            occurred_at=self.timestamp,
        )


class TelemetryEmitter:
    """Emits structured telemetry events to in-memory audit logs and persistent JSONL."""

    def __init__(self, artifact_dir: Path | str | None = None) -> None:
        self.artifact_dir = Path(artifact_dir) if artifact_dir is not None else None
        self._events: list[TelemetryEvent] = []
        if self.artifact_dir is not None:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)

    @property
    def events(self) -> list[TelemetryEvent]:
        """Return shallow copy of recorded events."""
        return list(self._events)

    def emit(
        self,
        event_type: TelemetryEventType,
        correlation: CorrelationContext,
        payload: dict[str, Any] | None = None,
    ) -> TelemetryEvent:
        """Create, record, and persist a telemetry event."""
        event = TelemetryEvent(
            event_id=f"evt_{uuid.uuid4().hex[:10]}",
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            correlation=correlation,
            payload=dict(payload or {}),
        )
        self._events.append(event)

        if self.artifact_dir is not None:
            jsonl_path = self.artifact_dir / "telemetry.jsonl"
            with jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.to_dict()) + "\n")

        return event

    def get_events(
        self,
        event_type: TelemetryEventType | str | None = None,
        run_id: str | None = None,
    ) -> list[TelemetryEvent]:
        """Filter recorded events by type or run_id."""
        matched = self._events
        if event_type is not None:
            target = event_type.value if isinstance(event_type, TelemetryEventType) else str(event_type)
            matched = [e for e in matched if e.event_type.value == target]
        if run_id is not None:
            matched = [e for e in matched if e.correlation.run_id == run_id]
        return matched


__all__ = [
    "TelemetryEmitter",
    "TelemetryEvent",
    "TelemetryEventType",
]
