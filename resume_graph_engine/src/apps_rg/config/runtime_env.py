"""Centralized process environment accessors for apps_rg runtime & cache controls.

All environment lookups across apps_rg cache, orchestration, provider, closeout,
and section policy modules route through this approved config boundary rather than
reading ``os.environ`` directly across domain and runtime modules.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping


def get_runtime_environ() -> MutableMapping[str, str]:
    """Return the active process environment mapping from the approved config boundary."""
    return os.environ


def get_runtime_env_str(key: str, default: str | None = None) -> str | None:
    """Return an optional environment variable string from the approved config boundary."""
    return os.environ.get(key, default)


def get_runtime_env_flag(key: str, default: bool = False) -> bool:
    """Resolve a boolean toggle environment variable with explicit truthy/falsy parsing."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    norm = raw.strip().lower()
    if norm in ("1", "true", "yes", "on"):
        return True
    if norm in ("0", "false", "no", "off"):
        return False
    return default


__all__ = [
    "get_runtime_env_flag",
    "get_runtime_env_str",
    "get_runtime_environ",
]
