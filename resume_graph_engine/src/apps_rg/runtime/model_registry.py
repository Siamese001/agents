"""Typed Model Registry v2 Resolver for apps_rg.

Provides typed, frozen, fail-closed resolution of model roles from the single
canonical registry SSOT at `resume_graph_engine/config/models/registry.yaml`.

Enforces:
1. Pinned-only model snapshots (no floating aliases, no env overrides).
2. Fail-closed on missing roles, unknown models, or retired models.
3. RFC 8259 canonical digest computation for audit receipts.
4. Mtime-based in-memory caching.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from apps_rg.config_root import get_models_registry_path


class ModelResolutionError(ValueError):
    """Raised when a model role or snapshot cannot be resolved."""


@dataclass(frozen=True)
class ResolvedModel:
    role: str
    model: str
    provider: str
    snapshot_id: str
    tier: str
    proof_eligible: bool
    owner: str
    review_after: str
    backup_role: str | None
    params: dict[str, Any]
    capabilities: tuple[str, ...]
    context_window: int
    tokenizer_family: str
    pricing: dict[str, Any]
    hf_revision: str | None = None
    artifact_sha256: str | None = None

    @property
    def pinned_model_id(self) -> str:
        return self.snapshot_id or self.model

    @property
    def model_id(self) -> str:
        return self.model


_CACHED_REGISTRY_MTIME: float | None = None
_CACHED_REGISTRY_DATA: dict[str, Any] | None = None
_CACHED_DIGEST: str | None = None


def _load_registry_data(registry_path: Path | None = None) -> tuple[dict[str, Any], str]:
    global _CACHED_REGISTRY_MTIME, _CACHED_REGISTRY_DATA, _CACHED_DIGEST

    path = registry_path or get_models_registry_path()
    if not path.is_file():
        raise ModelResolutionError(f"Model registry SSOT not found at {path}")

    current_mtime = path.stat().st_mtime
    if (
        _CACHED_REGISTRY_DATA is not None
        and _CACHED_REGISTRY_MTIME == current_mtime
        and _CACHED_DIGEST is not None
        and registry_path is None
    ):
        return _CACHED_REGISTRY_DATA, _CACHED_DIGEST

    try:
        raw_text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except Exception as exc:
        raise ModelResolutionError(f"Failed to read model registry YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise ModelResolutionError(f"Model registry at {path} must be a dictionary")

    # Policy checks
    policy = data.get("policy", {})
    if policy.get("environment_model_override_allowed") is True:
        raise ModelResolutionError("Registry policy violation: environment_model_override_allowed must be false")
    if policy.get("aliases_allowed") is True:
        raise ModelResolutionError("Registry policy violation: aliases_allowed must be false")

    # Compute RFC 8259 canonical SHA256 digest
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    if registry_path is None:
        _CACHED_REGISTRY_MTIME = current_mtime
        _CACHED_REGISTRY_DATA = data
        _CACHED_DIGEST = digest

    return data, digest


def registry_digest(registry_path: Path | None = None) -> str:
    """Return the RFC 8259 canonical SHA256 digest of the model registry SSOT."""
    _, digest = _load_registry_data(registry_path)
    return digest


get_registry_digest = registry_digest


def get_runtime_limits(registry_path: Path | None = None) -> dict[str, Any]:
    """Return the runtime limits dictionary from the model registry."""
    data, _ = _load_registry_data(registry_path)
    limits = data.get("runtime_limits")
    if not isinstance(limits, dict):
        raise ModelResolutionError("runtime_limits missing from model registry")
    return limits


def list_roles(registry_path: Path | None = None) -> list[str]:
    """Return sorted list of all defined roles in the registry."""
    data, _ = _load_registry_data(registry_path)
    roles = data.get("roles", {})
    return sorted(roles.keys())


def list_models(registry_path: Path | None = None) -> list[str]:
    """Return sorted list of all model IDs defined in the registry."""
    data, _ = _load_registry_data(registry_path)
    models = data.get("models", {})
    return sorted(models.keys())


def resolve(role: str, registry_path: Path | None = None) -> ResolvedModel:
    """Resolve a logical role to a typed, frozen ResolvedModel.

    Fails closed if the role is not defined, references an unknown model,
    or references a retired model. Environment overrides are strictly ignored.
    """
    if not role or not isinstance(role, str):
        raise ModelResolutionError(f"Role must be a non-empty string, got {role!r}")

    data, _ = _load_registry_data(registry_path)
    roles: dict[str, Any] = data.get("roles", {})
    models: dict[str, Any] = data.get("models", {})

    # Candidate keys for role lookup
    candidates = [role]
    if not role.startswith("generation.") and not role.startswith("proof_judge.") and not role.startswith("selector."):
        candidates.append(f"generation.{role}")
        candidates.append(f"proof_judge.{role}")
        candidates.append(f"selector.{role}")

    role_spec = None
    resolved_role_key = role
    for candidate in candidates:
        if candidate in roles:
            role_spec = roles[candidate]
            resolved_role_key = candidate
            break

    if role_spec is None:
        raise ModelResolutionError(
            f"Unknown role {role!r}. Available roles: {', '.join(sorted(roles.keys()))}"
        )

    model_id = role_spec.get("model")
    if not model_id or model_id not in models:
        raise ModelResolutionError(
            f"Role {resolved_role_key!r} references unknown model {model_id!r}"
        )

    model_spec: dict[str, Any] = models[model_id]
    status = model_spec.get("status", "active")
    if status == "retired":
        replacement = model_spec.get("replacement") or "none"
        raise ModelResolutionError(
            f"Model {model_id!r} referenced by role {resolved_role_key!r} is retired. Replacement: {replacement}"
        )

    return ResolvedModel(
        role=resolved_role_key,
        model=model_id,
        provider=role_spec.get("provider", model_spec.get("provider", "")),
        snapshot_id=model_spec.get("snapshot_id", model_id),
        tier=role_spec.get("tier", "frontier"),
        proof_eligible=bool(role_spec.get("proof_eligible", False)),
        owner=role_spec.get("owner", ""),
        review_after=role_spec.get("review_after", ""),
        backup_role=role_spec.get("backup_role"),
        params=dict(role_spec.get("params", {})),
        capabilities=tuple(model_spec.get("capabilities", [])),
        context_window=int(model_spec.get("context_window", 131072)),
        tokenizer_family=str(model_spec.get("tokenizer_family", "")),
        pricing=dict(model_spec.get("pricing", {})),
        hf_revision=model_spec.get("hf_revision"),
        artifact_sha256=model_spec.get("artifact_sha256"),
    )


resolve_model_role = resolve
