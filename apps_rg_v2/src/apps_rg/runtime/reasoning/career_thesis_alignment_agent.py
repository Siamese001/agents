"""Alias and backward-compatibility re-export for CareerThesisAlignmentAgent."""

from apps_rg.runtime.reasoning.CareerThesisAlignmentAgent import (
    CAREER_THESIS_ALIGNMENT_FILENAME,
    CAREER_THESIS_ALIGNMENT_SCHEMA,
    CareerThesis,
    CareerThesisAlignmentAgent,
    CareerThesisAlignmentPlan,
    EvidenceGapMitigation,
    L15_STRATEGIC_FIT_FILENAME,
    L15_STRATEGIC_FIT_SCHEMA,
    L15StrategicFitAgent,
    L15StrategicFitPlan,
    ThematicAllocation,
    execute_career_thesis_alignment,
    execute_l15_strategic_fit,
)

__all__ = [
    "CareerThesisAlignmentAgent",
    "CareerThesisAlignmentPlan",
    "CareerThesis",
    "EvidenceGapMitigation",
    "ThematicAllocation",
    "execute_career_thesis_alignment",
    "CAREER_THESIS_ALIGNMENT_SCHEMA",
    "CAREER_THESIS_ALIGNMENT_FILENAME",
    "L15StrategicFitAgent",
    "L15StrategicFitPlan",
    "execute_l15_strategic_fit",
    "L15_STRATEGIC_FIT_SCHEMA",
    "L15_STRATEGIC_FIT_FILENAME",
]
