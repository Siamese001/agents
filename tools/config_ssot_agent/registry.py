"""Authoritative SSOT domain registry and configuration ownership mappings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Pattern, Sequence


class ConfigDomain(str, Enum):
    """Governed configuration domain."""

    MODEL_IDENTITY = "model_identity"
    PROVIDER_PROFILES = "provider_profiles"
    RUNTIME_LIMITS = "runtime_limits"
    ROUTE_IDENTITY = "route_identity"
    ENVIRONMENT_NAMES = "environment_names"
    CREDENTIAL_LOCATIONS = "credential_locations"
    EMBEDDING_SETTINGS = "embedding_settings"

    # Aliases
    MODELS = MODEL_IDENTITY
    TIMEOUTS = RUNTIME_LIMITS
    ENV_VARS = ENVIRONMENT_NAMES
    EMBEDDINGS = EMBEDDING_SETTINGS


@dataclass(frozen=True)
class DomainOwner:
    """Ownership definition for a configuration domain."""

    domain: ConfigDomain
    owner_relative_path: str
    format: str  # json, yaml, python
    canonical_reader: str
    description: str
    target_keys: tuple[str, ...] = field(default_factory=tuple)


DEFAULT_OWNERS: dict[ConfigDomain, DomainOwner] = {
    ConfigDomain.MODEL_IDENTITY: DomainOwner(
        domain=ConfigDomain.MODEL_IDENTITY,
        owner_relative_path="resume_graph_engine/config/model_catalog.json",
        format="json",
        canonical_reader="apps_rg.runtime.model_capabilities.model_capabilities",
        description="Catalog of approved LLM model IDs, endpoint bindings, and capability classes.",
        target_keys=("model", "model_id", "model_actual", "model_name", "model_ref"),
    ),
    ConfigDomain.PROVIDER_PROFILES: DomainOwner(
        domain=ConfigDomain.PROVIDER_PROFILES,
        owner_relative_path="resume_graph_engine/src/apps_rg/config/provider_profiles.yaml",
        format="yaml",
        canonical_reader="apps_rg.runtime.section_model_limits.resolve_section_generation_model",
        description="Per-section model and provider selection mappings.",
        target_keys=("provider", "provider_profile", "provider_key"),
    ),
    ConfigDomain.RUNTIME_LIMITS: DomainOwner(
        domain=ConfigDomain.RUNTIME_LIMITS,
        owner_relative_path="resume_graph_engine/src/apps_rg/config/provider_profiles.yaml",
        format="yaml",
        canonical_reader="apps_rg.runtime.section_model_limits.runtime_limit_int",
        description="Timeout thresholds, output token caps, and retry parameters.",
        target_keys=("timeout", "timeout_s", "max_tokens", "max_output_tokens", "max_completion_tokens"),
    ),
    ConfigDomain.ROUTE_IDENTITY: DomainOwner(
        domain=ConfigDomain.ROUTE_IDENTITY,
        owner_relative_path="resume_graph_engine/src/apps_rg/config/route_registry.yaml",
        format="yaml",
        canonical_reader="apps_rg.runtime.orchestration.integrated_spine_runner._load_apps_rg_route_id",
        description="Canonical route and pipeline identifiers.",
        target_keys=("route_id", "route"),
    ),
    ConfigDomain.ENVIRONMENT_NAMES: DomainOwner(
        domain=ConfigDomain.ENVIRONMENT_NAMES,
        owner_relative_path="resume_graph_engine/src/apps_rg/runtime/env_bootstrap.py",
        format="python",
        canonical_reader="apps_rg.runtime.env_bootstrap.bootstrap_apps_rg_env",
        description="SSOT for discovering and loading runtime credentials into process environment.",
        target_keys=(),
    ),
    ConfigDomain.EMBEDDING_SETTINGS: DomainOwner(
        domain=ConfigDomain.EMBEDDING_SETTINGS,
        owner_relative_path="resume_graph_engine/src/apps_rg/runtime/embedding_settings.py",
        format="python",
        canonical_reader="apps_rg.runtime.embedding_settings.resolve_apps_rg_embedding_settings",
        description="SSOT for embedding models, Chroma vector-DB paths, and BGE settings.",
        target_keys=("CHROMA_PERSIST_DIR", "APPS_RG_EMBEDDING_MODEL_PATH", "EMBEDDING_MODEL_ID"),
    ),
}

KNOWN_MODEL_PATTERN: Pattern[str] = re.compile(
    r"^(?:gpt-[456]\.[0-9](?:-[a-z0-9]+)?|claude-[a-z0-9-]+|gemini-[0-9]\.[0-9](?:-[a-z0-9]+)?|o[13](?:-[a-z0-9]+)?)$",
    re.IGNORECASE,
)

CORE_KNOWN_MODELS: tuple[str, ...] = (
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "claude-sonnet-5",
    "claude-sonnet-4-5",
    "claude-3-7-sonnet",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
)


class SSOTRegistry:
    """Registry providing fast lookup of configuration owners and model catalogs."""

    def __init__(
        self,
        repo_root: Path | None = None,
        owners: Mapping[ConfigDomain, DomainOwner] | None = None,
    ) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.owners = dict(owners or DEFAULT_OWNERS)
        self._known_models: set[str] = set(CORE_KNOWN_MODELS)
        self._load_catalog_models()

    def _load_catalog_models(self) -> None:
        owner = self.owners.get(ConfigDomain.MODEL_IDENTITY)
        if not owner:
            return
        catalog_path = self.repo_root / owner.owner_relative_path
        if catalog_path.is_file():
            try:
                data = json.loads(catalog_path.read_text(encoding="utf-8"))
                models = data.get("models") if isinstance(data, dict) else None
                if isinstance(models, dict):
                    for mid in models.keys():
                        self._known_models.add(str(mid).strip().lower())
            except Exception:
                pass

    @property
    def domains(self) -> set[ConfigDomain]:
        return set(self.owners.keys())

    @property
    def known_models(self) -> frozenset[str]:
        return frozenset(self._known_models)

    def is_known_model_literal(self, value: str) -> bool:
        norm = str(value or "").strip().lower()
        if norm in self._known_models:
            return True
        return bool(KNOWN_MODEL_PATTERN.match(norm))

    def get_owner(self, domain: ConfigDomain) -> DomainOwner:
        return self.owners[domain]
