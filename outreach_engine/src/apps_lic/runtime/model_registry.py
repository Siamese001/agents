"""Authoritative Model & Provider Registry SSOT for outreach_engine."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


class OutreachModelRegistryError(RuntimeError):
    """Raised when model registry configuration is missing, corrupt, or unapproved."""


@dataclass(frozen=True)
class OutreachModelPin:
    """An immutable, governed model pin definition."""
    role: str
    provider: str
    model: str
    reasoning_effort: str = "low"
    backup_provider: str = ""
    backup_model: str = ""
    description: str = ""


class OutreachModelRegistry:
    """Thread-safe, mtime-cached runtime model registry for outreach_engine."""

    _lock = threading.Lock()
    _cached_data: Optional[Dict[str, Any]] = None
    _cached_mtime: float = -1.0
    _cached_path: Optional[Path] = None

    @classmethod
    def _resolve_config_path(cls, explicit_path: Path | str | None = None) -> Path:
        if explicit_path is not None:
            return Path(explicit_path).resolve()
        env_override = os.environ.get("OUTREACH_PROVIDER_PROFILES_PATH")
        if env_override:
            p = Path(env_override).resolve()
            if p.is_file():
                return p
        # Default: outreach_engine/config/provider_profiles.yaml
        pkg_root = Path(__file__).resolve().parent.parent.parent.parent
        default_path = pkg_root / "config" / "provider_profiles.yaml"
        if default_path.is_file():
            return default_path
        # Repo root fallback
        repo_root = pkg_root.parent
        repo_config = repo_root / "config" / "provider_profiles.yaml"
        if repo_config.is_file():
            return repo_config
        return default_path

    @classmethod
    def get_profiles(cls, config_path: Path | str | None = None) -> Dict[str, Any]:
        """Loads provider profiles with thread-safe, mtime-aware memoization."""
        resolved = cls._resolve_config_path(config_path)
        if not resolved.is_file():
            raise OutreachModelRegistryError(f"Model registry profile not found: {resolved}")

        current_mtime = resolved.stat().st_mtime
        with cls._lock:
            if (
                cls._cached_data is not None
                and cls._cached_path == resolved
                and cls._cached_mtime == current_mtime
            ):
                return cls._cached_data

            try:
                data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                raise OutreachModelRegistryError(
                    f"Failed to parse model registry YAML from {resolved}: {exc}"
                ) from exc

            if not isinstance(data, dict):
                raise OutreachModelRegistryError(
                    f"Invalid model registry format in {resolved}; expected dict."
                )

            cls._cached_data = data
            cls._cached_mtime = current_mtime
            cls._cached_path = resolved
            return data

    @classmethod
    def get_model_pin(cls, role: str, config_path: Path | str | None = None) -> OutreachModelPin:
        """Resolves the authoritative OutreachModelPin for a given functional role."""
        profiles_doc = cls.get_profiles(config_path)
        profiles = profiles_doc.get("profiles", {})
        entry = profiles.get(role)
        if not entry or not isinstance(entry, dict):
            raise OutreachModelRegistryError(f"Role '{role}' is not registered in outreach model registry SSOT.")

        return OutreachModelPin(
            role=role,
            provider=str(entry.get("provider", "")).strip(),
            model=str(entry.get("model", "")).strip(),
            reasoning_effort=str(entry.get("reasoning_effort", "low")).strip(),
            backup_provider=str(entry.get("backup_provider", "")).strip(),
            backup_model=str(entry.get("backup_model", "")).strip(),
            description=str(entry.get("description", "")).strip(),
        )

    @classmethod
    def get_model_for_role(cls, role: str, default: str = "", config_path: Path | str | None = None) -> str:
        """Convenience accessor returning the pinned model ID for a role."""
        try:
            pin = cls.get_model_pin(role, config_path)
            return pin.model or default
        except OutreachModelRegistryError:
            if default:
                return default
            raise

    @classmethod
    def get_provider_for_role(cls, role: str, default: str = "", config_path: Path | str | None = None) -> str:
        """Convenience accessor returning the provider name for a role."""
        try:
            pin = cls.get_model_pin(role, config_path)
            return pin.provider or default
        except OutreachModelRegistryError:
            if default:
                return default
            raise

    @classmethod
    def get_effort_for_role(cls, role: str, default: str = "low", config_path: Path | str | None = None) -> str:
        """Convenience accessor returning reasoning effort for a role."""
        try:
            pin = cls.get_model_pin(role, config_path)
            return pin.reasoning_effort or default
        except OutreachModelRegistryError:
            return default

    @classmethod
    def list_active_models(cls, config_path: Path | str | None = None) -> Dict[str, str]:
        """Returns a mapping of role -> model for all registered profiles."""
        profiles_doc = cls.get_profiles(config_path)
        profiles = profiles_doc.get("profiles", {})
        result: Dict[str, str] = {}
        for role, entry in profiles.items():
            if isinstance(entry, dict) and "model" in entry:
                result[role] = str(entry["model"])
        return result

    @classmethod
    def list_approved_models(cls, config_path: Path | str | None = None) -> set[str]:
        """Returns the complete set of approved primary and backup model names."""
        profiles_doc = cls.get_profiles(config_path)
        profiles = profiles_doc.get("profiles", {})
        approved: set[str] = set()
        for _, entry in profiles.items():
            if isinstance(entry, dict):
                if "model" in entry and entry["model"]:
                    approved.add(str(entry["model"]))
                if "backup_model" in entry and entry["backup_model"]:
                    approved.add(str(entry["backup_model"]))
        return approved

    @classmethod
    def validate_model(cls, model_name: str, config_path: Path | str | None = None) -> bool:
        """Validates that a model ID is registered in the SSOT (primary or backup)."""
        approved = cls.list_approved_models(config_path)
        return model_name in approved

    @classmethod
    def is_env_override_allowed(cls, config_path: Path | str | None = None) -> bool:
        """Checks if provider profiles allows environment variable model overrides."""
        profiles_doc = cls.get_profiles(config_path)
        return bool(profiles_doc.get("environment_model_override_allowed", False))

    @classmethod
    def clear_cache(cls) -> None:
        """Clears the cached registry for testing or reloading."""
        with cls._lock:
            cls._cached_data = None
            cls._cached_mtime = -1.0
            cls._cached_path = None


__all__ = [
    "OutreachModelPin",
    "OutreachModelRegistry",
    "OutreachModelRegistryError",
]
