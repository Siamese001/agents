"""Dynamic bridge to the centralized `core-governance` Judge v3 Rigor Engine & Studio Session Contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

CORE_GOVERNANCE_MCP_DIR = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp"
CORE_GOVERNANCE_UI_HTML_PATH = CORE_GOVERNANCE_MCP_DIR / "ui" / "studio_app.html"


def _load_core_gov_module(module_name: str, filename: str) -> ModuleType:
    if module_name in sys.modules:
        return sys.modules[module_name]
    target = CORE_GOVERNANCE_MCP_DIR / filename
    if not target.is_file():
        raise FileNotFoundError(f"Centralized core-governance module missing at '{target}'.")
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load spec for '{target}'.")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def get_judge_v3_rigor_engine() -> ModuleType:
    return _load_core_gov_module("judge_v3_rigor_engine", "judge_v3_rigor_engine.py")


def get_studio_session_contract() -> ModuleType:
    get_judge_v3_rigor_engine()
    return _load_core_gov_module("session_contract", "session_contract.py")


__all__ = [
    "CORE_GOVERNANCE_MCP_DIR",
    "CORE_GOVERNANCE_UI_HTML_PATH",
    "get_judge_v3_rigor_engine",
    "get_studio_session_contract",
]
