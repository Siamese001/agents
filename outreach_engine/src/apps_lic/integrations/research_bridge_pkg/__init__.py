"""apps_research_bridge implementation package."""

from __future__ import annotations

from apps_lic.integrations.research_bridge_pkg.bridge import AppsResearchBridge
from apps_lic.integrations.research_bridge_pkg.models import EvidenceItem, ResearchResult
from apps_lic.integrations.research_bridge_pkg.persistence import (
    build_hermetic_fallback_result,
    translate_and_persist_research_result,
)

__all__ = [
    "AppsResearchBridge",
    "EvidenceItem",
    "ResearchResult",
    "build_hermetic_fallback_result",
    "translate_and_persist_research_result",
]
