"""Shared dynamic parent-module resolution for CompanyBriefEngine mixins."""
from __future__ import annotations

import sys
from typing import Any

_PARENT_MODULE = "apps_research.engines.company_brief_engine"


def _cbe(name: str, fallback: Any = None) -> Any:
    """Resolve an attribute on ``company_brief_engine`` dynamically so monkeypatches apply."""
    mod = sys.modules.get(_PARENT_MODULE)
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return fallback


__all__ = ["_cbe"]
