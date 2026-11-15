"""apps_research bridge for outreach_engine briefing delegation.

Pure re-export facade delegating to `apps_lic.integrations.research_bridge_pkg`.
"""

from __future__ import annotations

from apps_lic.integrations.research_boundary_policy import (
    ResearchBoundaryPolicy,
    _build_canonical_sidecar,
    _extract_priorities_from_text,
    _find_valid_persisted_artifact_bundle,
    _read_candidate_brief,
    _resolve_canonical_targeting_brief,
    build_cost_limit_exceeded_result,
    build_timeout_result,
    execute_bounded_live_research,
)
from apps_lic.integrations.research_bridge_pkg.bridge import AppsResearchBridge
from apps_lic.integrations.research_bridge_pkg.models import EvidenceItem, ResearchResult
from apps_lic.integrations.research_bridge_pkg.persistence import (
    build_hermetic_fallback_result,
    translate_and_persist_research_result,
)
from apps_lic.integrations.research_bridge_support import (
    MockAppsResearchBridge,
    _CANONICAL_MOCK_BRIEF,
)

__all__ = [
    "AppsResearchBridge",
    "EvidenceItem",
    "MockAppsResearchBridge",
    "ResearchBoundaryPolicy",
    "ResearchResult",
    "_CANONICAL_MOCK_BRIEF",
    "_build_canonical_sidecar",
    "_extract_priorities_from_text",
    "_find_valid_persisted_artifact_bundle",
    "_read_candidate_brief",
    "_resolve_canonical_targeting_brief",
    "build_cost_limit_exceeded_result",
    "build_timeout_result",
    "execute_bounded_live_research",
]
