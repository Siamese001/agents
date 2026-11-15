"""Dynamic parent-module attribute resolver preserving test monkeypatches."""
from __future__ import annotations

import sys
from typing import Any

PARENT_MODULE = "apps_rg.runtime.sections.ibm_bullets_lane"


def parent_attr(name: str, default: Any) -> Any:
    mod = sys.modules.get(PARENT_MODULE)
    return getattr(mod, name, default) if mod is not None else default
