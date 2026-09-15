"""Authoritative Request, Response, and Model Invocation Provenance Contracts.

Part of Sovereign Agentic Platform Observability & Persistence Governance (Wave 4).
Records provenance metadata and execution lineage while strictly prohibiting
the persistence of credentials, bearer tokens, or raw proprietary secrets.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from agents.observability.events import canonical_json_dumps, compute_digest


PROHIBITED_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "token",
    "password",
    "secret",
    "client_secret",
}


def sanitize_provenance_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize metadata by redacting any sensitive or credential keys."""
    sanitized: dict[str, Any] = {}
    for k, v in metadata.items():
        key_lower = str(k).lower()
        if any(secret in key_lower for secret in PROHIBITED_SECRET_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, Mapping):
            sanitized[k] = sanitize_provenance_metadata(v)
        else:
            sanitized[k] = v
    return sanitized


@dataclass(frozen=True, slots=True)
class RequestProvenance:
    """Tamper-evident record of an inbound request or workflow trigger."""

    request_id: str
    run_id: str
    correlation_id: str
    source: str
    operation: str
    input_digest: str
    received_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "source": self.source,
            "operation": self.operation,
            "input_digest": self.input_digest,
            "received_at": self.received_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ResponseProvenance:
    """Tamper-evident record of an outbound result, model turn, or section output."""

    response_id: str
    run_id: str
    correlation_id: str
    output_digest: str
    generated_at: str
    model_provider: str | None = None
    model_name: str | None = None
    latency_ms: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "output_digest": self.output_digest,
            "generated_at": self.generated_at,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "latency_ms": self.latency_ms,
            "metadata": dict(self.metadata),
        }


def create_request_provenance(
    request_id: str,
    run_id: str,
    correlation_id: str,
    source: str,
    operation: str,
    raw_input: Any,
    metadata: Mapping[str, Any] | None = None,
) -> RequestProvenance:
    """Construct a sanitized, digest-bound RequestProvenance descriptor."""
    serialized = canonical_json_dumps(raw_input) if not isinstance(raw_input, (str, bytes)) else raw_input
    digest = compute_digest(serialized)
    sanitized_meta = sanitize_provenance_metadata(metadata or {})
    return RequestProvenance(
        request_id=request_id,
        run_id=run_id,
        correlation_id=correlation_id,
        source=source,
        operation=operation,
        input_digest=digest,
        received_at=datetime.now(timezone.utc).isoformat(),
        metadata=sanitized_meta,
    )


def create_response_provenance(
    response_id: str,
    run_id: str,
    correlation_id: str,
    raw_output: Any,
    model_provider: str | None = None,
    model_name: str | None = None,
    latency_ms: float = 0.0,
    metadata: Mapping[str, Any] | None = None,
) -> ResponseProvenance:
    """Construct a sanitized, digest-bound ResponseProvenance descriptor."""
    serialized = canonical_json_dumps(raw_output) if not isinstance(raw_output, (str, bytes)) else raw_output
    digest = compute_digest(serialized)
    sanitized_meta = sanitize_provenance_metadata(metadata or {})
    return ResponseProvenance(
        response_id=response_id,
        run_id=run_id,
        correlation_id=correlation_id,
        output_digest=digest,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_provider=model_provider,
        model_name=model_name,
        latency_ms=latency_ms,
        metadata=sanitized_meta,
    )
