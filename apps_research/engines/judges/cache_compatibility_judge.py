"""Clean-Slate Judge v3 Adapter for `cache_compatibility` (`IS_STUB=True`, `IS_CALIBRATED=False` until human gold exists)."""
from __future__ import annotations

from apps_research.engines.judges.base import BaseResearchJudge, JudgeEvidence

IS_STUB: bool = True
IS_CALIBRATED: bool = False
GRADER_ID: str = 'apps_research_cache_compatibility'


class CacheCompatibilityJudge(BaseResearchJudge):
    judge_id: str = GRADER_ID
    dimension: str = 'cache_compatibility'
    version: str = "v3.0.0"
    IS_STUB: bool = True
    IS_CALIBRATED: bool = False
    is_stub: bool = True
    grader_id: str = GRADER_ID
    v3_profile_token: str = 'company_research_brief:targeting_brief_handoff'


__all__ = ['CacheCompatibilityJudge', "GRADER_ID", "IS_CALIBRATED", "IS_STUB", "JudgeEvidence"]
