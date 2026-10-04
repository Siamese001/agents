"""SSOT Configuration Root and Path Resolvers for apps_rg and resume_graph_engine.

Eliminates fragile `Path(__file__).parents[N] / 'config'` expressions across the
engine source tree and establishes `resume_graph_engine/config` as the single pipeline
configuration root.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_engine_root() -> Path:
    """Return the absolute path to the resume_graph_engine root directory."""
    # When running from installed package or editable worktree
    # resume_graph_engine/src/apps_rg/config_root.py -> parents[2] is resume_graph_engine
    return Path(__file__).resolve().parents[2]


def get_engine_config_root() -> Path:
    """Return the SSOT pipeline configuration root (resume_graph_engine/config)."""
    return get_engine_root() / "config"


def get_apps_rg_config_root() -> Path:
    """Return the app-level config root (resume_graph_engine/src/apps_rg/config)."""
    return Path(__file__).resolve().parent / "config"


def get_models_registry_path() -> Path:
    """Return the path to the canonical model_registry.v2 SSOT file."""
    return get_engine_config_root() / "models" / "registry.yaml"


def get_model_catalog_path() -> Path:
    """Return the path to model_catalog.json."""
    return get_engine_config_root() / "model_catalog.json"


def get_provider_profiles_path() -> Path:
    """Return the path to provider_profiles.yaml."""
    return get_apps_rg_config_root() / "provider_profiles.yaml"


def get_default_briefing_path() -> Path:
    """Return the path to default_targeting_briefing.txt."""
    return get_apps_rg_config_root() / "default_targeting_briefing.txt"
