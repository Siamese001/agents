"""Deterministic Stage A coverage-depth helper & Judge v3 adapter (decoupled from `apps_rg`)."""
from __future__ import annotations

from typing import Any, Mapping

from apps_research.engines.judges.base import BaseResearchJudge

IS_STUB: bool = False
IS_CALIBRATED: bool = False
GRADER_ID: str = "research::coverage_depth_judge::v3"
GRADER_UNKNOWN_SENTINEL: int = -1


def grade(dim: str, run_context: object) -> tuple[float | int, list[str]]:
    """Deterministic Stage A structural coverage ratio (never masquerades as calibrated LLM)."""
    _ = dim
    if not isinstance(run_context, Mapping):
        return GRADER_UNKNOWN_SENTINEL, []
    output = run_context.get("output")
    if not isinstance(output, Mapping) or not output:
        return GRADER_UNKNOWN_SENTINEL, []
    priorities = output.get("strategic_priorities") or output.get("sections") or []
    sources = output.get("retrieval_sources") or output.get("citations") or []
    if not priorities and not sources:
        return GRADER_UNKNOWN_SENTINEL, []
    p_cov = min(1.0, len(priorities) / 3.0) if isinstance(priorities, list) else 0.5
    s_cov = min(1.0, len(sources) / 3.0) if isinstance(sources, list) else 0.5
    refs = [str(s) for s in (sources[:5] if isinstance(sources, list) else [])]
    return round(0.6 * p_cov + 0.4 * s_cov, 4), refs


class CoverageDepthJudge(BaseResearchJudge):
    judge_id: str = GRADER_ID
    dimension: str = "coverage_depth"
    IS_STUB: bool = False
    IS_CALIBRATED: bool = False
    is_stub: bool = False
    grader_id: str = GRADER_ID

    def __call__(self, dim: str, run_context: object) -> Any:
        return grade(dim, run_context)


__all__ = ["CoverageDepthJudge", "GRADER_ID", "IS_CALIBRATED", "IS_STUB", "grade"]
