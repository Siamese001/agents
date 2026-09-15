"""Immutable Context Snapshots and Provenance Contracts.

Provides typed classification, provenance hashing, and token accounting
for all context items assembled into agent prompts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence


class ContextSourceType(str, Enum):
    """Categorical source classification for prompt context elements."""

    REQUEST = "REQUEST"
    USER_DOCUMENT = "USER_DOCUMENT"
    RETRIEVED_EVIDENCE = "RETRIEVED_EVIDENCE"
    GENERATED_INTERMEDIATE = "GENERATED_INTERMEDIATE"
    CONFIGURATION = "CONFIGURATION"
    EPHEMERAL_SCRATCH = "EPHEMERAL_SCRATCH"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_hex(value: Any) -> str:
    raw = _canonical_json(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ContextItem:
    """Individual provenance-bearing context element."""

    source_id: str
    source_type: ContextSourceType
    content: str
    authority: str = "advisory"  # "canonical", "verified", "advisory", "untrusted"
    version: str = "v1"
    relevance_score: float = 1.0
    estimated_tokens: int = 0
    retrieved_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, ContextSourceType):
            raise TypeError(f"ContextItem source_type must be ContextSourceType, got {type(self.source_type)}")
        if self.estimated_tokens == 0 and self.content:
            # Heuristic token approximation: ~4 characters per token
            object.__setattr__(self, "estimated_tokens", max(1, len(self.content) // 4))

    @property
    def item_digest(self) -> str:
        payload = {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "content": self.content,
            "version": self.version,
            "authority": self.authority,
        }
        return sha256_hex(payload)


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    """Immutable, audited snapshot of all context passed to a model or tool."""

    snapshot_id: str
    items: tuple[ContextItem, ...]
    max_token_budget: int = 8000
    created_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def total_estimated_tokens(self) -> int:
        return sum(item.estimated_tokens for item in self.items)

    @property
    def is_within_budget(self) -> bool:
        return self.total_estimated_tokens <= self.max_token_budget

    @property
    def provenance_digest(self) -> str:
        digests = [item.item_digest for item in self.items]
        return sha256_hex({"snapshot_id": self.snapshot_id, "items": digests})

    def get_items_by_source(self, source_type: ContextSourceType) -> tuple[ContextItem, ...]:
        return tuple(item for item in self.items if item.source_type == source_type)

    def assemble_text(self, separator: str = "\n\n") -> str:
        """Assemble all context items into an ordered prompt text stream."""
        return separator.join(item.content for item in self.items if item.content.strip())

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "total_estimated_tokens": self.total_estimated_tokens,
            "max_token_budget": self.max_token_budget,
            "is_within_budget": self.is_within_budget,
            "provenance_digest": self.provenance_digest,
            "created_at_utc": self.created_at_utc,
            "item_count": len(self.items),
            "items": [
                {
                    "source_id": item.source_id,
                    "source_type": item.source_type.value,
                    "authority": item.authority,
                    "version": item.version,
                    "estimated_tokens": item.estimated_tokens,
                    "relevance_score": item.relevance_score,
                    "item_digest": item.item_digest,
                }
                for item in self.items
            ],
        }


__all__ = [
    "ContextItem",
    "ContextSnapshot",
    "ContextSourceType",
]
