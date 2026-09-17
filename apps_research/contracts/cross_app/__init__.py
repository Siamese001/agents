"""apps_research cross-app contracts."""

from __future__ import annotations

from apps_research.contracts.cross_app.base import (
    CrossAppEnvelope,
    EnvelopeExpiredError,
    EnvelopeHashMismatchError,
    EnvelopeLoadError,
    EnvelopeSchemaError,
    compute_sha256,
)
from apps_research.contracts.cross_app.research_brief import (
    ResearchBriefEnvelope,
    ResearchBriefPayload,
    ResearchClaimRow,
)

__all__ = [
    "CrossAppEnvelope",
    "EnvelopeExpiredError",
    "EnvelopeHashMismatchError",
    "EnvelopeLoadError",
    "EnvelopeSchemaError",
    "ResearchBriefEnvelope",
    "ResearchBriefPayload",
    "ResearchClaimRow",
    "compute_sha256",
]
