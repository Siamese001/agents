"""C0 sequence fact-slot allocator and whole-sequence graph allocation facade.

Re-exports public contracts and solver functions for outreach multi-touch sequence allocation.
"""

from __future__ import annotations

from apps_lic.runtime.c0.sequence_allocation import (
    C0_ALLOCATION_PLAN_SCHEMA_VERSION,
    INV_LIC_C0_DISJOINT_TOUCH_FACTS,
    OutreachSequenceAllocationPlan,
    SequenceAllocationError,
    TouchAllocationAssignment,
    TouchSlotSpec,
    compute_allocation_plan_digest,
    normalize_metric_token,
    solve_sequence_allocation,
    validate_disjoint_allocation,
)

__all__ = [
    "C0_ALLOCATION_PLAN_SCHEMA_VERSION",
    "INV_LIC_C0_DISJOINT_TOUCH_FACTS",
    "OutreachSequenceAllocationPlan",
    "SequenceAllocationError",
    "TouchAllocationAssignment",
    "TouchSlotSpec",
    "compute_allocation_plan_digest",
    "normalize_metric_token",
    "solve_sequence_allocation",
    "validate_disjoint_allocation",
]
