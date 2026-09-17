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


class TrajectoryExemplarIndex:
    """Index of mined golden trajectory exemplars that converts to prompt ContextItems."""

    def __init__(self) -> None:
        self._exemplars: list[Any] = []

    def add_exemplar(self, exemplar: Any) -> None:
        self._exemplars.append(exemplar)

    def to_context_items(self, task_type: str = "general", max_items: int = 2) -> list[ContextItem]:
        """Convert matching exemplars to ContextItem records for token budgeted context compilation."""
        from agents.context.provenance import ContextItem, ContextSourceType

        items: list[ContextItem] = []
        matching = [
            e
            for e in self._exemplars
            if getattr(e, "task_type", "general") == task_type or task_type == "general"
        ]
        sorted_matching = sorted(
            matching, key=lambda e: getattr(e, "efficiency_score", 0.0), reverse=True
        )

        for ex in sorted_matching[:max_items]:
            cid = getattr(ex, "exemplar_id", f"ex_{len(items)}")
            content = (
                f"[Golden Trajectory Exemplar: {cid}]\n"
                f"Task: {getattr(ex, 'task_type', 'general')}\n"
                f"Summary: {getattr(ex, 'summary_text', '')}\n"
                f"Steps: {' -> '.join(getattr(ex, 'step_sequence', ()))}"
            )
            items.append(
                ContextItem(
                    source_id=f"trajectory_exemplar_{cid}",
                    source_type=ContextSourceType.RETRIEVED_EVIDENCE,
                    content=content,
                    authority="verified",
                    relevance_score=float(getattr(ex, "efficiency_score", 0.90)),
                )
            )
        return items


__all__ = [
    "TokenBudget",
    "TokenBudgetExceededError",
    "TrajectoryExemplarIndex",
]
