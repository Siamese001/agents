"""Alias and backward-compatibility re-export for L15StrategicFitAgent."""

from apps_rg.runtime.reasoning.L15StrategicFitAgent import (
    L15_STRATEGIC_FIT_FILENAME,
    L15_STRATEGIC_FIT_SCHEMA,
    CareerThesis,
    EvidenceGapMitigation,
    L15StrategicFitAgent,
    L15StrategicFitPlan,
    ThematicAllocation,
    execute_l15_strategic_fit,
)

__all__ = [
    "L15StrategicFitAgent",
    "L15StrategicFitPlan",
    "CareerThesis",
    "EvidenceGapMitigation",
    "ThematicAllocation",
    "execute_l15_strategic_fit",
    "L15_STRATEGIC_FIT_SCHEMA",
    "L15_STRATEGIC_FIT_FILENAME",
]
