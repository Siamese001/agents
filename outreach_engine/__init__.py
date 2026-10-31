"""outreach_engine - Autonomous Lifecycle Intelligence & Grounded Executive Outreach Engine.

Top-level package root shim ensuring src-layout packages and shared libraries are discoverable
while loading heavy pipeline and judge modules lazily on demand.
"""

from __future__ import annotations

import importlib
import site
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parent
site.addsitedir(str(_PKG_ROOT / "src"))
site.addsitedir(str(_PKG_ROOT.parent))
site.addsitedir(str(_PKG_ROOT.parent / "resume_graph_engine" / "src"))

# Level 0 domain models exported directly
from apps_lic.domain.models import (
    AudiencePersona,
    AuthoritativeVerdict,
    CandidateFact,
    CandidateProfile,
    CandidateProfileLoader,
    ChannelType,
    OutreachMessageDraft,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
    TouchPoint,
    TouchSequence,
    ValidationResult,
)

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "ForbiddenClaimsValidator": ("apps_lic.domain.validators", "ForbiddenClaimsValidator"),
    "OutboundPrivacyValidator": ("apps_lic.domain.validators", "OutboundPrivacyValidator"),
    "AppsResearchBridge": ("apps_lic.integrations.apps_research_bridge", "AppsResearchBridge"),
    "EvidenceItem": ("apps_lic.integrations.apps_research_bridge", "EvidenceItem"),
    "ResearchResult": ("apps_lic.integrations.apps_research_bridge", "ResearchResult"),
    "EvaluationReport": ("apps_lic.judges.evaluator", "EvaluationReport"),
    "ExecutiveOutreachJudgePanel": ("apps_lic.judges.evaluator", "ExecutiveOutreachJudgePanel"),
    "RubricJudgeEvaluator": ("apps_lic.judges.evaluator", "RubricJudgeEvaluator"),
    "GovernedBriefingResolver": ("apps_lic.pipeline.briefing_resolver", "GovernedBriefingResolver"),
    "SealedBriefingResolution": ("apps_lic.pipeline.briefing_resolver", "SealedBriefingResolution"),
    "PromptCompiler": ("apps_lic.pipeline.compiler", "PromptCompiler"),
    "get_executive_signature_block": ("apps_lic.pipeline.compiler", "get_executive_signature_block"),
    "get_recruiter_signature_block": ("apps_lic.pipeline.compiler", "get_recruiter_signature_block"),
    "MissionLoader": ("apps_lic.pipeline.mission_loader", "MissionLoader"),
    "OutreachOrchestrator": ("apps_lic.pipeline.orchestrator", "OutreachOrchestrator"),
    "TouchSequencePlanner": ("apps_lic.pipeline.touch_sequence", "TouchSequencePlanner"),
    "OutreachModelPin": ("apps_lic.runtime.model_registry", "OutreachModelPin"),
    "OutreachModelRegistry": ("apps_lic.runtime.model_registry", "OutreachModelRegistry"),
    "OutreachModelRegistryError": ("apps_lic.runtime.model_registry", "OutreachModelRegistryError"),
    "main": ("apps_lic.__main__", "main"),
}

__all__ = [
    "AudiencePersona",
    "AuthoritativeVerdict",
    "CandidateFact",
    "CandidateProfile",
    "CandidateProfileLoader",
    "ChannelType",
    "OutreachMessageDraft",
    "RecipientClass",
    "RelationshipDistance",
    "TargetOpportunity",
    "TouchPoint",
    "TouchSequence",
    "ValidationResult",
    "ForbiddenClaimsValidator",
    "OutboundPrivacyValidator",
    "AppsResearchBridge",
    "EvidenceItem",
    "ResearchResult",
    "EvaluationReport",
    "ExecutiveOutreachJudgePanel",
    "RubricJudgeEvaluator",
    "GovernedBriefingResolver",
    "SealedBriefingResolution",
    "MissionLoader",
    "OutreachOrchestrator",
    "PromptCompiler",
    "TouchSequencePlanner",
    "OutreachModelPin",
    "OutreachModelRegistry",
    "OutreachModelRegistryError",
    "get_executive_signature_block",
    "get_recruiter_signature_block",
    "main",
]


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
