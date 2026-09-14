"""apps_rg Prompt Assembly Segment & Scope Contracts.

Defines prompt segment classifications, scope boundaries, and canonical serialization
for OpenAI prefix caching and Anthropic prompt caching optimization.

Self-contained for apps_rg local prompt assembly use.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class PromptScope(str, Enum):
    """Lifecycle scope and caching boundary of a prompt segment."""

    GLOBAL_STATIC = "global_static"      # Identical across all runs/roles (laws, schemas, rubrics)
    JOB_SCOPED = "job_scoped"            # Stable for one target role/company (JD pack, research brief)
    CANDIDATE_SCOPED = "candidate_scoped"# Stable for one candidate (facts, profile spine)
    REQUEST_SCOPED = "request_scoped"    # Dynamic per call/attempt (gate summary, candidate text, hints)


@dataclass(frozen=True)
class PromptSegment:
    """A distinct semantic segment of a prompt with lifecycle and caching metadata."""

    name: str
    scope: PromptScope
    text: str
    content_hash: str = ""
    cache_breakpoint: bool = False
    token_estimate: int = 0

    def __post_init__(self) -> None:
        computed_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]
        if not self.content_hash:
            object.__setattr__(self, "content_hash", computed_hash)
        if self.token_estimate <= 0 and self.text:
            # Conservative local character estimate: 3 chars/token * 1.12 safety
            raw_tokens = max(1, (len(self.text) + 2) // 3)
            object.__setattr__(self, "token_estimate", int(raw_tokens * 1.12 + 0.999999))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scope": self.scope.value,
            "text": self.text,
            "content_hash": self.content_hash,
            "cache_breakpoint": self.cache_breakpoint,
            "token_estimate": self.token_estimate,
        }

    def to_anthropic_block(self, *, cache_override: bool | None = None) -> dict[str, Any]:
        """Format as an Anthropic content block with optional ephemeral cache breakpoint."""
        should_cache = self.cache_breakpoint if cache_override is None else cache_override
        block: dict[str, Any] = {
            "type": "text",
            "text": self.text,
        }
        if should_cache:
            block["cache_control"] = {"type": "ephemeral"}
        return block


def classify_slot_scope(slot_id: str) -> PromptScope:
    """Classify canonical slot IDs into their caching scope boundary."""
    sid = str(slot_id or "").strip().upper()
    if sid in {"S0", "D0", "I0", "E0", "Y0", "R0", "M0"}:
        return PromptScope.GLOBAL_STATIC
    if sid == "C0":
        return PromptScope.JOB_SCOPED
    if sid in {"U0", "H0"}:
        return PromptScope.REQUEST_SCOPED
    return PromptScope.REQUEST_SCOPED


def canonical_prompt_json(value: Any) -> str:
    """Serialize data structures to canonical JSON with sorted keys and tight separators.

    Guarantees 100% byte-for-byte reproducibility across runtime invocations,
    preventing spurious prefix cache invalidations.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_stable_prefix_hash(segments: Sequence[PromptSegment], *, max_scope: PromptScope = PromptScope.GLOBAL_STATIC) -> str:
    """Compute deterministic SHA256 digest of segments within or up to the specified scope.

    Segments with scopes broader than max_scope are excluded.
    """
    allowed_scopes: set[PromptScope] = {PromptScope.GLOBAL_STATIC}
    if max_scope == PromptScope.JOB_SCOPED:
        allowed_scopes.add(PromptScope.JOB_SCOPED)
    elif max_scope == PromptScope.CANDIDATE_SCOPED:
        allowed_scopes.add(PromptScope.JOB_SCOPED)
        allowed_scopes.add(PromptScope.CANDIDATE_SCOPED)
    elif max_scope == PromptScope.REQUEST_SCOPED:
        allowed_scopes.update(PromptScope)

    prefix_parts: list[str] = []
    for seg in segments:
        if seg.scope in allowed_scopes:
            prefix_parts.append(f"{seg.name}:{seg.content_hash}")
        else:
            break

    joined = "|".join(prefix_parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "PromptScope",
    "PromptSegment",
    "canonical_prompt_json",
    "classify_slot_scope",
    "compute_stable_prefix_hash",
]
