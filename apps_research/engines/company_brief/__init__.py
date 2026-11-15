"""Decomposed mixin submodules for CompanyBriefEngine."""
from __future__ import annotations

from apps_research.engines.company_brief.c0_bundle import _CompanyBriefC0BundleMixin
from apps_research.engines.company_brief.retrieval_legacy import _CompanyBriefRetrievalLegacyMixin
from apps_research.engines.company_brief.retrieval_v2 import _CompanyBriefRetrievalV2Mixin
from apps_research.engines.company_brief.synthesis import _CompanyBriefSynthesisMixin
from apps_research.engines.company_brief.targeting_brief import _CompanyBriefTargetingBriefMixin

__all__ = [
    "_CompanyBriefC0BundleMixin",
    "_CompanyBriefRetrievalLegacyMixin",
    "_CompanyBriefRetrievalV2Mixin",
    "_CompanyBriefSynthesisMixin",
    "_CompanyBriefTargetingBriefMixin",
]
