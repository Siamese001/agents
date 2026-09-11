"""outreach_engine - Autonomous Lifecycle Intelligence & Grounded Executive Outreach Engine.

Top-level package root shim ensuring src-layout packages and shared libraries are discoverable.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_SRC_ROOT = _PKG_ROOT / "src"
_REPO_ROOT = _PKG_ROOT.parent

# Ensure src-layout packages under outreach_engine/src are discoverable
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

# Ensure repo root and apps_shared (under resume_graph_engine/src) are discoverable
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SHARED_SRC = _REPO_ROOT / "resume_graph_engine" / "src"
if _SHARED_SRC.is_dir() and str(_SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(_SHARED_SRC))

# Re-export canonical domain and pipeline models
from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
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
from apps_lic.judges.evaluator import EvaluationReport, RubricJudgeEvaluator
from apps_lic.pipeline.briefing_resolver import GovernedBriefingResolver, SealedBriefingResolution
from apps_lic.pipeline.compiler import PromptCompiler
from apps_lic.pipeline.mission_loader import MissionLoader
from apps_lic.pipeline.orchestrator import OutreachOrchestrator
from apps_lic.pipeline.touch_sequence import TouchSequencePlanner

__all__ = [
    "CandidateFact",
    "CandidateProfile",
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
    "RubricJudgeEvaluator",
    "GovernedBriefingResolver",
    "SealedBriefingResolution",
    "MissionLoader",
    "OutreachOrchestrator",
    "PromptCompiler",
    "TouchSequencePlanner",
]
