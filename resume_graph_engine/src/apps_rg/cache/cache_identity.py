"""Canonical cache identity and key computation for apps_rg caching layers.

Milestone Wave 6 (P18, P17):
- The key strictly covers: resolved snapshot, registry digest, prompt template hash,
  generation params, schema version, and input digests.
- Empty or 'unknown' critical values are treated as non-cacheable misses.
- Briefing cache keys incorporate target role, model pin, and schema version.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from apps_rg.runtime.model_registry import get_registry_digest

CACHE_IDENTITY_SCHEMA_VERSION = "2026-10-cache-id-v1"
BRIEFING_CACHE_SCHEMA_VERSION = "2026-10-briefing-v2"
INVALID_CACHE_VALUES = frozenset({"", "unknown", "none", "null", "undefined"})


@dataclass(frozen=True, slots=True)
class CacheIdentity:
    """Immutable cache identity descriptor for model outputs."""

    resolved_model_snapshot: str
    registry_digest: str
    prompt_template_hash: str
    generation_params: dict[str, Any]
    schema_version: str = CACHE_IDENTITY_SCHEMA_VERSION
    input_digests: dict[str, str] | None = None
    role: str = ""

    def is_cacheable(self) -> bool:
        """Return True if all mandatory identity fields are valid non-sentinel values."""
        if str(self.resolved_model_snapshot or "").strip().lower() in INVALID_CACHE_VALUES:
            return False
        if str(self.registry_digest or "").strip().lower() in INVALID_CACHE_VALUES:
            return False
        if str(self.prompt_template_hash or "").strip().lower() in INVALID_CACHE_VALUES:
            return False
        return True

    def compute_key(self) -> str:
        """Return a deterministic 64-hex SHA-256 fingerprint, or empty string if uncacheable."""
        if not self.is_cacheable():
            return ""
        params_items = sorted((str(k), str(v)) for k, v in (self.generation_params or {}).items())
        inputs_items = sorted((str(k), str(v)) for k, v in (self.input_digests or {}).items())
        payload = {
            "model_snapshot": self.resolved_model_snapshot.strip(),
            "registry_digest": self.registry_digest.strip(),
            "template_hash": self.prompt_template_hash.strip(),
            "params": params_items,
            "schema_version": self.schema_version,
            "inputs": inputs_items,
            "role": self.role.strip(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def compute_cache_identity_key(
    *,
    resolved_model_snapshot: str,
    prompt_template_hash: str,
    generation_params: dict[str, Any] | None = None,
    registry_digest: str | None = None,
    schema_version: str = CACHE_IDENTITY_SCHEMA_VERSION,
    input_digests: dict[str, str] | None = None,
    role: str = "",
) -> str:
    """Helper to compute a canonical cache key with registry SSOT digest."""
    digest = registry_digest or get_registry_digest()
    identity = CacheIdentity(
        resolved_model_snapshot=resolved_model_snapshot,
        registry_digest=digest,
        prompt_template_hash=prompt_template_hash,
        generation_params=generation_params or {},
        schema_version=schema_version,
        input_digests=input_digests,
        role=role,
    )
    return identity.compute_key()


def compute_briefing_cache_key(
    *,
    company_name: str,
    jd_hash: str,
    target_role: str = "",
    model_pin: str = "",
    schema_version: str = BRIEFING_CACHE_SCHEMA_VERSION,
) -> str:
    """Deterministic SHA-256 fingerprint for resolved briefing caching.

    Incorporates company, role, jd_hash, model_pin, and schema_version.
    """
    corp = str(company_name or "").strip().lower()
    role = str(target_role or "").strip().lower()
    jdh = str(jd_hash or "").strip().lower()
    pin = str(model_pin or "").strip().lower()
    envelope = f"apps_rg|briefing|{schema_version}|{corp}|{role}|{jdh}|{pin}"
    return hashlib.sha256(envelope.encode("utf-8")).hexdigest()


__all__ = [
    "BRIEFING_CACHE_SCHEMA_VERSION",
    "CACHE_IDENTITY_SCHEMA_VERSION",
    "CacheIdentity",
    "compute_briefing_cache_key",
    "compute_cache_identity_key",
]
