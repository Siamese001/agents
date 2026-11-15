"""Dynamic lookup helper preserving monkeypatches on executive_summary_lane."""
from __future__ import annotations

import sys
from typing import Any

_PARENT_MOD = "apps_rg.runtime.sections.executive_summary_lane"


def _lane_attr(name: str, default: Any) -> Any:
    mod = sys.modules.get(_PARENT_MOD)
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return default
