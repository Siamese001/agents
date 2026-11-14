"""Dynamic parent-module symbol resolver for monkeypatch compatibility."""
from __future__ import annotations

import sys
from typing import Any

_PARENT_MOD = "apps_rg.runtime.sections.executive_summary_voice_repair"


def _p(name: str, default: Any) -> Any:
    mod = sys.modules.get(_PARENT_MOD)
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return default
