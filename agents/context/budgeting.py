"""Token Budgeting and Allocation Contracts.

Manages token allocations across prompt context categories, enforcing model
limits and preventing unbounded context bloat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from agents.context.provenance import ContextItem, ContextSnapshot, ContextSourceType


class TokenBudgetExceededError(ValueError):
    """Raised when context compilation exceeds allocated token budget."""


# Default priority ordering for context sources (higher index = preserved first)
_SOURCE_PRIORITY: dict[ContextSourceType, int] = {
    ContextSourceType.EPHEMERAL_SCRATCH: 1,
    ContextSourceType.CONFIGURATION: 2,
    ContextSourceType.GENERATED_INTERMEDIATE: 3,
    ContextSourceType.REQUEST: 4,
    ContextSourceType.RETRIEVED_EVIDENCE: 5,
    ContextSourceType.USER_DOCUMENT: 6,
}


@dataclass(slots=True)
class TokenBudget:
    """Allocated token budget for a single model call or stage."""

    max_total_tokens: int
    reserved_output_tokens: int = 1500
    source_allocations: Mapping[ContextSourceType, int] = field(default_factory=dict)

    @property
    def max_context_tokens(self) -> int:
        return max(0, self.max_total_tokens - self.reserved_output_tokens)

    def validate_snapshot(self, snapshot: ContextSnapshot) -> None:
        """Validate that a ContextSnapshot satisfies the token budget."""
        if snapshot.total_estimated_tokens > self.max_context_tokens:
            raise TokenBudgetExceededError(
                f"ContextSnapshot {snapshot.snapshot_id} has {snapshot.total_estimated_tokens} tokens, "
                f"exceeding budget limit of {self.max_context_tokens} tokens."
            )

    def fit_items_to_budget(
        self,
        items: list[ContextItem],
        snapshot_id: str = "budgeted_snapshot",
    ) -> ContextSnapshot:
        """Filter and select context items by priority to strictly fit within budget."""
        # Sort items: descending by source priority, then descending by relevance score
        sorted_items = sorted(
            items,
            key=lambda item: (
                _SOURCE_PRIORITY.get(item.source_type, 0),
                item.relevance_score,
            ),
            reverse=True,
        )

        selected: list[ContextItem] = []
        accumulated_tokens = 0
        limit = self.max_context_tokens

        for item in sorted_items:
            if accumulated_tokens + item.estimated_tokens <= limit:
                selected.append(item)
                accumulated_tokens += item.estimated_tokens

        # Return in original stable order
        selected_set = set(selected)
        final_items = tuple(item for item in items if item in selected_set)

        return ContextSnapshot(
            snapshot_id=snapshot_id,
            items=final_items,
            max_token_budget=self.max_context_tokens,
        )


__all__ = [
    "TokenBudget",
    "TokenBudgetExceededError",
]
