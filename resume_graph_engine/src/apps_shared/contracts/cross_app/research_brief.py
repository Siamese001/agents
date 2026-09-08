"""ResearchBriefEnvelope — apps_research -> apps_rg / apps_qna."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps_shared.contracts.cross_app.base import CrossAppEnvelope


class ResearchClaimRow(BaseModel):
    """One claim from a research source register (typed projection)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim: str
    claim_type: Literal[
        "direct_evidence", "interpretation", "analyst_inference", "assumption"
    ] = "analyst_inference"
    source_id: str = "SRC-000"
    section_id: str = ""


class ResearchBriefPayload(BaseModel):
    """Typed projection of research_brief_<trace>.md + source_register."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brief_path: str = Field(description="Relative path to the markdown brief.")
    register_path: str | None = None
    company_brief: str | None = None
    role_areas_of_focus: list[str] = Field(default_factory=list)
    industry_trends: list[str] = Field(default_factory=list)
    source_register: list[ResearchClaimRow] = Field(default_factory=list)


class ResearchBriefEnvelope(CrossAppEnvelope):
    """apps_research -> downstream apps research brief handoff envelope."""

    SCHEMA_NAME: ClassVar[str] = "cross_app.research_brief"
    COMPATIBLE_MAJOR: ClassVar[int] = 1

    payload: ResearchBriefPayload


__all__ = [
    "ResearchBriefEnvelope",
    "ResearchBriefPayload",
    "ResearchClaimRow",
]
