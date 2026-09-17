"""outreach_engine - Autonomous Lifecycle Intelligence & Grounded Executive Outreach Engine."""

from __future__ import annotations

from apps_lic.domain.models import (
    AudiencePersona,
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
from apps_lic.integrations.apps_research_bridge import AppsResearchBridge, EvidenceItem, ResearchResult
from apps_lic.judges.evaluator import (
    EvaluationReport,
    ExecutiveOutreachJudgePanel,
    RubricJudgeEvaluator,
)
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver, SealedBriefingResolution
from apps_lic.pipeline.compiler import (
    PromptCompiler,
    get_executive_signature_block,
    get_recruiter_signature_block,
)
from apps_lic.pipeline.mission_loader import MissionLoader
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.pipeline.touch_sequence import TouchSequencePlanner
from apps_lic.runtime.model_registry import (
    OutreachModelPin,
    OutreachModelRegistry,
    OutreachModelRegistryError,
)

__all__ = [
    "AudiencePersona",
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
]
