"""Canonical Agent Event Types, Envelopes, and Tamper-Evident Chaining.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Provides an immutable, versioned, cryptographic event envelope with predecessor
SHA-256 hash chaining to guarantee auditability and tamper evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
import uuid


class AgentEventType(str, Enum):
    """Canonical event types for sovereign agentic workflow observability."""

    PHASE_TRANSITION = "phase_transition"       # Workflow state machine transitions between RunPhases
    FEEDBACK_DECISION = "feedback_decision"     # FeedbackController produces an evaluation decision
    ARTIFACT_COMMITTED = "artifact_committed"   # An artifact has been durably stored with verified digest
    CHECKPOINT_STORED = "checkpoint_stored"     # State checkpoint durably persisted for resume/recovery


def canonical_json_dumps(obj: Any) -> str:
    """Serialize object to deterministic, sorted canonical UTF-8 JSON."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_digest(data: str | bytes) -> str:
    """Compute standard lowercase SHA-256 hex digest."""
    b = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(b).hexdigest()


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Tamper-evidence verification result for an event or event chain."""

    is_valid: bool
    verified_count: int
    error_message: str = ""
    tampered_event_id: str | None = None
    expected_digest: str | None = None
    actual_digest: str | None = None


@dataclass(frozen=True, slots=True)
class AgentEventEnvelope:
    """Authoritative, tamper-evident envelope for all agentic events."""

    event_id: str
    event_type: AgentEventType
    schema_version: int
    run_id: str
    correlation_id: str
    sequence: int
    occurred_at: str
    producer: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    previous_event_digest: str | None = None
    event_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize envelope to standard dictionary representation."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at,
            "producer": self.producer,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
            "previous_event_digest": self.previous_event_digest,
            "event_digest": self.event_digest,
        }

    def compute_canonical_digest(self) -> str:
        """Compute the deterministic SHA-256 digest over envelope contents excluding event_digest."""
        preimage = {
            "correlation_id": self.correlation_id,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "metadata": self.metadata,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
            "previous_event_digest": self.previous_event_digest,
            "producer": self.producer,
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "sequence": self.sequence,
        }
        return compute_digest(canonical_json_dumps(preimage))

    def verify_integrity(self) -> bool:
        """Verify that envelope contents match the recorded event_digest."""
        if not self.event_digest:
            return False
        return self.compute_canonical_digest() == self.event_digest

    @classmethod
    def create(
        cls,
        event_type: AgentEventType,
        run_id: str,
        correlation_id: str,
        sequence: int,
        producer: str,
        payload: Mapping[str, Any],
        previous_event_digest: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        event_id: str | None = None,
        occurred_at: str | None = None,
        schema_version: int = 1,
    ) -> AgentEventEnvelope:
        return create_event_envelope(
            event_type=event_type,
            run_id=run_id,
            correlation_id=correlation_id,
            sequence=sequence,
            producer=producer,
            payload=payload,
            previous_event_digest=previous_event_digest,
            metadata=metadata,
            event_id=event_id,
            occurred_at=occurred_at,
            schema_version=schema_version,
        )


def create_event_envelope(
    event_type: AgentEventType,
    run_id: str,
    correlation_id: str,
    sequence: int,
    producer: str,
    payload: Mapping[str, Any],
    previous_event_digest: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    event_id: str | None = None,
    occurred_at: str | None = None,
    schema_version: int = 1,
) -> AgentEventEnvelope:
    """Factory helper to construct a sealed, cryptographically signed event envelope."""
    eid = event_id or f"evt_{uuid.uuid4().hex[:12]}"
    ts = occurred_at or datetime.now(timezone.utc).isoformat()
    meta = dict(metadata or {})
    pay = dict(payload)

    # Initial draft without digest
    draft = AgentEventEnvelope(
        event_id=eid,
        event_type=event_type,
        schema_version=schema_version,
        run_id=run_id,
        correlation_id=correlation_id,
        sequence=sequence,
        occurred_at=ts,
        producer=producer,
        payload=pay,
        metadata=meta,
        previous_event_digest=previous_event_digest,
        event_digest="",
    )
    digest = draft.compute_canonical_digest()

    return AgentEventEnvelope(
        event_id=eid,
        event_type=event_type,
        schema_version=schema_version,
        run_id=run_id,
        correlation_id=correlation_id,
        sequence=sequence,
        occurred_at=ts,
        producer=producer,
        payload=pay,
        metadata=meta,
        previous_event_digest=previous_event_digest,
        event_digest=digest,
    )


def verify_event_chain(events: Sequence[AgentEventEnvelope]) -> VerificationResult:
    """Verify that a sequence of event envelopes forms an unbroken, untampered chain."""
    if not events:
        return VerificationResult(is_valid=True, verified_count=0)

    expected_prev_digest: str | None = None

    for idx, event in enumerate(events):
        # 1. Verify sequence monotonicity
        if idx > 0 and event.sequence <= events[idx - 1].sequence:
            return VerificationResult(
                is_valid=False,
                verified_count=idx,
                error_message=f"Event {event.event_id} broke monotonic sequence: {event.sequence} <= {events[idx - 1].sequence}",
                tampered_event_id=event.event_id,
            )

        # 2. Verify previous event link
        if event.previous_event_digest != expected_prev_digest:
            return VerificationResult(
                is_valid=False,
                verified_count=idx,
                error_message=(
                    f"Event {event.event_id} has invalid previous_event_digest: "
                    f"expected {expected_prev_digest}, got {event.previous_event_digest}"
                ),
                tampered_event_id=event.event_id,
                expected_digest=expected_prev_digest,
                actual_digest=event.previous_event_digest,
            )

        # 3. Verify internal payload digest
        if not event.verify_integrity():
            return VerificationResult(
                is_valid=False,
                verified_count=idx,
                error_message=f"Event {event.event_id} digest mismatch; payload was tampered.",
                tampered_event_id=event.event_id,
                expected_digest=event.compute_canonical_digest(),
                actual_digest=event.event_digest,
            )

        expected_prev_digest = event.event_digest

    return VerificationResult(is_valid=True, verified_count=len(events))
