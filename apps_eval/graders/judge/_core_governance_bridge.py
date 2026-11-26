"""Dynamic bridge to centralized `core-governance` Judge v3 Engine, IDE Router, Blind Protocol, Jury & Studio."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType

from infrastructure.config.env_loader import get_env_optional_path

_DEFAULT_CORE_GOVERNANCE_MCP_DIR = Path.home() / ".gemini" / "config" / "plugins" / "core-governance" / "mcp"
CORE_GOVERNANCE_MCP_DIR = (
    get_env_optional_path("CORE_GOVERNANCE_MCP_DIR") or _DEFAULT_CORE_GOVERNANCE_MCP_DIR
).resolve()
CORE_GOVERNANCE_UI_HTML_PATH = CORE_GOVERNANCE_MCP_DIR / "ui" / "studio_app.html"


def get_core_governance_mcp_dir() -> Path:
    override = get_env_optional_path("CORE_GOVERNANCE_MCP_DIR")
    return override if override is not None else CORE_GOVERNANCE_MCP_DIR


def _load_core_gov_module(module_name: str, filename: str) -> ModuleType:
    mcp_dir = get_core_governance_mcp_dir()
    target = mcp_dir / filename
    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_file = getattr(existing, "__file__", None)
        if existing_file and Path(existing_file).resolve() == target.resolve():
            return existing
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


def get_judge_ide_router_v3() -> ModuleType:
    return _load_core_gov_module("judge_ide_router_v3", "judge_ide_router_v3.py")


def get_judge_blind_protocol_v3() -> ModuleType:
    get_judge_v3_rigor_engine()
    get_judge_ide_router_v3()
    return _load_core_gov_module("judge_blind_protocol_v3", "judge_blind_protocol_v3.py")


def get_judge_disjoint_jury_v3() -> ModuleType:
    get_judge_blind_protocol_v3()
    return _load_core_gov_module("judge_disjoint_jury_v3", "judge_disjoint_jury_v3.py")


def get_studio_session_contract() -> ModuleType:
    _load_core_gov_module("atomic_concurrency", "atomic_concurrency.py")
    get_judge_v3_rigor_engine()
    return _load_core_gov_module("session_contract", "session_contract.py")


__all__ = [
    "CORE_GOVERNANCE_MCP_DIR",
    "CORE_GOVERNANCE_UI_HTML_PATH",
    "get_core_governance_mcp_dir",
    "get_judge_blind_protocol_v3",
    "get_judge_disjoint_jury_v3",
    "get_judge_ide_router_v3",
    "get_judge_v3_rigor_engine",
    "get_studio_session_contract",
]
