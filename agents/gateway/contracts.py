"""Capability Gateway Data Contracts.

Standardizes all model invocations and tool dispatches behind typed,
audited request and response structures.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.context.provenance import ContextSnapshot


class ModelTier(str, Enum):
    """Normalized performance / latency tier."""

    FAST = "fast"
    REASONING = "reasoning"
    FRONTIER = "frontier"


def sha256_hex(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    """Standardized request envelope for all model / tool capability invocations."""

    capability_name: str
    prompt_snapshot: ContextSnapshot
    model_tier: ModelTier = ModelTier.REASONING
    temperature: float = 0.0
    max_output_tokens: int = 1500
    timeout_seconds: float = 30.0
    allowed_providers: tuple[str, ...] = ("openai", "anthropic", "google")
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def request_digest(self) -> str:
        body = {
            "capability_name": self.capability_name,
            "provenance_digest": self.prompt_snapshot.provenance_digest,
            "model_tier": self.model_tier.value,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        return sha256_hex(body)


@dataclass(frozen=True, slots=True)
class CapabilityResponse:
    """Standardized response envelope returned by the capability gateway."""

    content: str
    provider: str
    model_id: str
    status: str = "SUCCESS"  # "SUCCESS", "ERROR", "TIMEOUT", "REJECTED"
    prompt_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    error_message: str = ""
    observation_digest: str = ""

    def __post_init__(self) -> None:
        if not self.observation_digest:
            body = {
                "content": self.content,
                "provider": self.provider,
                "model_id": self.model_id,
                "status": self.status,
                "error_message": self.error_message,
            }
            object.__setattr__(self, "observation_digest", sha256_hex(body))

    @property
    def is_success(self) -> bool:
        return self.status == "SUCCESS"


__all__ = [
    "CapabilityRequest",
    "CapabilityResponse",
    "ModelTier",
]
