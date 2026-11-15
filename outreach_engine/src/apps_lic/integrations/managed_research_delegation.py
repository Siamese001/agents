"""Managed apps_research delegation for outreach_engine briefing.

Pure re-export facade delegating to `apps_lic.integrations.managed_research_pkg`.
"""

from __future__ import annotations

from apps_lic.integrations.apps_research_bridge import ResearchResult
from apps_lic.integrations.managed_research_pkg.contracts import (
    OutreachBriefingReady,
    RequestForOutreachBriefing,
    ResearchDispatchFailure,
    ResearchFailureReason,
    _is_within,
    _utc_ms,
    _validate_persisted_research_artifacts,
)
from apps_lic.integrations.managed_research_pkg.dispatcher import (
    _log,
    dispatch_outreach_research_briefing,
    execute_managed_research,
)

__all__ = [
    "OutreachBriefingReady",
    "RequestForOutreachBriefing",
    "ResearchDispatchFailure",
    "ResearchFailureReason",
    "ResearchResult",
    "_is_within",
    "_log",
    "_utc_ms",
    "_validate_persisted_research_artifacts",
    "dispatch_outreach_research_briefing",
    "execute_managed_research",
]
