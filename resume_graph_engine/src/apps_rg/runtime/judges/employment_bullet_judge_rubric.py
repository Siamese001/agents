"""Domain-General Employment Bullet Judge v3 Contract (`<= 95L`, zero employer hardcoding)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from apps_rg.runtime.judges.v3_section_judge import (
    get_apps_rg_v3_profile,
    render_section_v3_rubric,
)

FORBIDDEN_EXEC_SUMMARY_DIMENSION_IDS: Final[frozenset[str]] = frozenset(
    {
        "executive_signal",
        "synthesis_quality",
        "resume_voice",
        "evidence_utilization",
        "deterministic_alignment",
        "executive_strategy_thesis",
        "executive_summary_quality",
        "executive_presence",
        "executive_brevity",
        "north_star_alignment",
        "complementarity_vs_bullets",
        "why_role_mattered",
    }
)

EMPLOYMENT_BULLET_RUBRIC_VERSION: Final[str] = "employment_bullet_judge_v3"


@dataclass(frozen=True, slots=True)
class BulletJudgeDimension:
    dimension_id: str
    criterion: str


SHARED_EMPLOYMENT_BULLET_DIMENSIONS: Final[tuple[BulletJudgeDimension, ...]] = tuple(
    BulletJudgeDimension(c.id, c.question)
    for c in get_apps_rg_v3_profile("employment_bullets").checks
)


def employment_bullet_dimensions(section_id: str) -> tuple[BulletJudgeDimension, ...]:
    _ = section_id
    return SHARED_EMPLOYMENT_BULLET_DIMENSIONS


def pool_selector_dimension_ids(section_id: str) -> tuple[str, ...]:
    return tuple(d.dimension_id for d in employment_bullet_dimensions(section_id))


def pool_selector_scoring_instruction(section_id: str) -> str:
    dims = ", ".join(pool_selector_dimension_ids(section_id))
    return (
        f"Evaluate candidate bullet variants strictly on atomic bullet checks ({dims}). "
        "Require verified episode fact grounding, active human ownership, and non-duplicate outcomes."
    )


def grade_only_rubric_text(section_id: str, *, bullet_count: int = 0, bullet_id_range: str = "") -> str:
    _ = (bullet_count, bullet_id_range)
    return render_section_v3_rubric(section_id or "employment_bullets")


def assert_no_exec_summary_dimensions(section_id: str) -> None:
    ids = {d.dimension_id for d in employment_bullet_dimensions(section_id)}
    overlap = ids & FORBIDDEN_EXEC_SUMMARY_DIMENSION_IDS
    if overlap:
        raise ValueError(f"{section_id}: bullet rubric must not reuse exec-summary dimensions: {sorted(overlap)}")


__all__ = [
    "BulletJudgeDimension",
    "EMPLOYMENT_BULLET_RUBRIC_VERSION",
    "FORBIDDEN_EXEC_SUMMARY_DIMENSION_IDS",
    "SHARED_EMPLOYMENT_BULLET_DIMENSIONS",
    "assert_no_exec_summary_dimensions",
    "employment_bullet_dimensions",
    "grade_only_rubric_text",
    "pool_selector_dimension_ids",
    "pool_selector_scoring_instruction",
]
