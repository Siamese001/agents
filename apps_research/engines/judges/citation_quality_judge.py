"""Clean-Slate Judge v3 Adapter for `citation_quality` (`IS_STUB=True`, `IS_CALIBRATED=False` until human gold exists)."""
from __future__ import annotations

from apps_research.engines.judges.base import BaseResearchJudge, JudgeEvidence

IS_STUB: bool = True
IS_CALIBRATED: bool = False
GRADER_ID: str = 'research::citation_quality_judge::v1'


class CitationQualityJudge(BaseResearchJudge):
    judge_id: str = GRADER_ID
    dimension: str = 'citation_quality'
    version: str = "v3.0.0"
    IS_STUB: bool = True
    IS_CALIBRATED: bool = False
    is_stub: bool = True
    grader_id: str = GRADER_ID
    v3_profile_token: str = 'company_research_brief:company_brief_synthesis'


__all__ = ['CitationQualityJudge', "GRADER_ID", "IS_CALIBRATED", "IS_STUB", "JudgeEvidence"]
