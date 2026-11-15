"""Governed Multi-Path Briefing Resolver for outreach_engine.

Coordinates resolution across 4 paths matching resume_graph_engine:
1. Manual explicit brief / mission fixture (Path A)
2. Local cached brief hit (Path B)
3. Live autonomous research via apps_research + Adversarial Injection Airlock (Path C)
4. Hermetic Tier-1 context fallback (Path D)
"""

from __future__ import annotations

from apps_lic.pipeline.briefing_resolver_pkg.models_and_cache import (
    AirlockBriefingReceipt,
    BriefingCacheStoreBase,
    OUTREACH_MAX_CACHE_SIZE,
    SealedBriefingResolution,
    _AIRLOCK_AVAILABLE,
    _sanitize_briefing_content,
    sanitize_briefing_content,
)
from apps_lic.pipeline.briefing_resolver_pkg.resolver import GovernedBriefingResolver

__all__ = [
    "AirlockBriefingReceipt",
    "BriefingCacheStoreBase",
    "GovernedBriefingResolver",
    "OUTREACH_MAX_CACHE_SIZE",
    "SealedBriefingResolution",
    "_AIRLOCK_AVAILABLE",
    "_sanitize_briefing_content",
    "sanitize_briefing_content",
]
