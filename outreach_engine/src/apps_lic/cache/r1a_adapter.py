"""R1A deterministic exact-match cache adapter for outreach_engine (apps_lic).

Keyed strictly by the canonical SHA-256 digest of:
``(prompt_hash, model_id, allocation_plan_digest, candidate_graph_db_sha256, schema_version)``.
Supports ``--no-cache`` bypass (`no_cache: bool = False`) and tracks hit/miss/bypass telemetry.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

R1A_SCHEMA_VERSION: str = "apps_lic.r1a_exact_cache.v1"
DEFAULT_R1A_TTL_SECONDS: float = 86400.0


def _compute_canonical_key_sha256(
    *,
    prompt_hash: str,
    model_id: str,
    allocation_plan_digest: str,
    candidate_graph_db_sha256: str,
    schema_version: str = R1A_SCHEMA_VERSION,
) -> str:
    """Compute canonical SHA-256 over the 5-tuple exact cache identity."""
    canonical_tuple = {
        "prompt_hash": str(prompt_hash or "").strip(),
        "model_id": str(model_id or "").strip(),
        "allocation_plan_digest": str(allocation_plan_digest or "").strip(),
        "candidate_graph_db_sha256": str(candidate_graph_db_sha256 or "").strip(),
        "schema_version": str(schema_version or R1A_SCHEMA_VERSION).strip(),
    }
    encoded = json.dumps(canonical_tuple, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class R1ACacheKey:
    """Frozen 5-tuple identity key for R1A exact-match outreach response caching."""

    prompt_hash: str
    model_id: str
    allocation_plan_digest: str
    candidate_graph_db_sha256: str
    schema_version: str = R1A_SCHEMA_VERSION
    key_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.key_sha256:
            digest = _compute_canonical_key_sha256(
                prompt_hash=self.prompt_hash,
                model_id=self.model_id,
                allocation_plan_digest=self.allocation_plan_digest,
                candidate_graph_db_sha256=self.candidate_graph_db_sha256,
                schema_version=self.schema_version,
            )
            object.__setattr__(self, "key_sha256", digest)

    @property
    def digest(self) -> str:
        """Return the 64-hex SHA-256 key digest."""
        return self.key_sha256

    def is_valid(self) -> bool:
        """Return True iff all 5 constituent fields are non-empty."""
        return all(
            (
                self.prompt_hash.strip(),
                self.model_id.strip(),
                self.allocation_plan_digest.strip(),
                self.candidate_graph_db_sha256.strip(),
                self.schema_version.strip(),
            )
        )

    def matches_components(self, other: R1ACacheKey) -> bool:
        """Verify exact equality across all 5 identity fields plus key_sha256."""
        return (
            self.key_sha256 == other.key_sha256
            and self.prompt_hash == other.prompt_hash
            and self.model_id == other.model_id
            and self.allocation_plan_digest == other.allocation_plan_digest
            and self.candidate_graph_db_sha256 == other.candidate_graph_db_sha256
            and self.schema_version == other.schema_version
        )

    def to_dict(self) -> dict[str, str]:
        """Serialize R1ACacheKey to a dictionary."""
        return {
            "prompt_hash": self.prompt_hash,
            "model_id": self.model_id,
            "allocation_plan_digest": self.allocation_plan_digest,
            "candidate_graph_db_sha256": self.candidate_graph_db_sha256,
            "schema_version": self.schema_version,
            "key_sha256": self.key_sha256,
        }

    def __str__(self) -> str:
        return self.key_sha256


def compute_r1a_cache_key(
    *,
    prompt_hash: str,
    model_id: str,
    allocation_plan_digest: str,
    candidate_graph_db_sha256: str,
    schema_version: str = R1A_SCHEMA_VERSION,
) -> R1ACacheKey:
    """Build a canonical R1ACacheKey from its 5 constituent digests."""
    return R1ACacheKey(
        prompt_hash=prompt_hash,
        model_id=model_id,
        allocation_plan_digest=allocation_plan_digest,
        candidate_graph_db_sha256=candidate_graph_db_sha256,
        schema_version=schema_version,
    )


@dataclass(frozen=True, slots=True)
class R1ACacheEntry:
    """Immutable cache entry stored by R1AExactCacheAdapter."""

    cache_key: R1ACacheKey
    payload: Any
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = DEFAULT_R1A_TTL_SECONDS
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key_sha256(self) -> str:
        """Return the entry's 64-hex SHA-256 cache key."""
        return self.cache_key.key_sha256

    @property
    def prompt_hash(self) -> str:
        """Return the prompt_hash bound to this cache entry."""
        return self.cache_key.prompt_hash

    @property
    def model_id(self) -> str:
        """Return the model_id bound to this cache entry."""
        return self.cache_key.model_id

    @property
    def allocation_plan_digest(self) -> str:
        """Return the C0 allocation_plan_digest bound to this cache entry."""
        return self.cache_key.allocation_plan_digest

    @property
    def candidate_graph_db_sha256(self) -> str:
        """Return the candidate_graph_db_sha256 bound to this cache entry."""
        return self.cache_key.candidate_graph_db_sha256

    @property
    def schema_version(self) -> str:
        """Return the schema_version bound to this cache entry."""
        return self.cache_key.schema_version

    @property
    def value(self) -> Any:
        """Alias for payload."""
        return self.payload

    @property
    def response(self) -> Any:
        """Alias for payload."""
        return self.payload

    def is_expired(self, now: float | None = None) -> bool:
        """Return True if the entry has exceeded its TTL."""
        if self.ttl_seconds <= 0:
            return True
        current = time.time() if now is None else float(now)
        return (current - self.created_at) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        """Serialize R1ACacheEntry to a JSON-compatible dictionary."""
        return {
            "cache_key": self.cache_key.to_dict(),
            "payload": self.payload,
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
            "metadata": dict(self.metadata),
        }


class R1AExactCacheAdapter:
    """Deterministic exact-match cache adapter with `--no-cache` bypass and telemetry."""

    def __init__(
        self,
        *,
        cache_dir: Path | str | None = None,
        no_cache: bool = False,
        default_ttl_seconds: float = DEFAULT_R1A_TTL_SECONDS,
        schema_version: str = R1A_SCHEMA_VERSION,
    ) -> None:
        self.cache_dir: Path | None = Path(cache_dir).resolve() if cache_dir is not None else None
        self.no_cache: bool = bool(no_cache)
        self.default_ttl_seconds: float = float(default_ttl_seconds)
        self.schema_version: str = str(schema_version)
        self._entries: dict[str, R1ACacheEntry] = {}
        self.hits: int = 0
        self.misses: int = 0
        self.bypasses: int = 0
        self.writes: int = 0

    def build_key(
        self,
        *,
        prompt_hash: str,
        model_id: str,
        allocation_plan_digest: str,
        candidate_graph_db_sha256: str,
        schema_version: str | None = None,
    ) -> R1ACacheKey:
        """Construct an R1ACacheKey using the adapter's default schema_version unless overridden."""
        return R1ACacheKey(
            prompt_hash=prompt_hash,
            model_id=model_id,
            allocation_plan_digest=allocation_plan_digest,
            candidate_graph_db_sha256=candidate_graph_db_sha256,
            schema_version=schema_version if schema_version is not None else self.schema_version,
        )

    def _resolve_key(
        self,
        key: R1ACacheKey | None,
        *,
        prompt_hash: str,
        model_id: str,
        allocation_plan_digest: str,
        candidate_graph_db_sha256: str,
        schema_version: str | None,
    ) -> R1ACacheKey | None:
        if isinstance(key, R1ACacheKey):
            return key if key.is_valid() else None
        built = self.build_key(
            prompt_hash=prompt_hash,
            model_id=model_id,
            allocation_plan_digest=allocation_plan_digest,
            candidate_graph_db_sha256=candidate_graph_db_sha256,
            schema_version=schema_version,
        )
        return built if built.is_valid() else None

    def get(
        self,
        key: R1ACacheKey | None = None,
        *,
        prompt_hash: str = "",
        model_id: str = "",
        allocation_plan_digest: str = "",
        candidate_graph_db_sha256: str = "",
        schema_version: str | None = None,
        no_cache: bool | None = None,
    ) -> R1ACacheEntry | None:
        """Look up an exact-match entry; returns None and increments bypasses when no_cache is True."""
        effective_no_cache = self.no_cache if no_cache is None else bool(no_cache)
        if effective_no_cache:
            self.bypasses += 1
            return None

        resolved_key = self._resolve_key(
            key,
            prompt_hash=prompt_hash,
            model_id=model_id,
            allocation_plan_digest=allocation_plan_digest,
            candidate_graph_db_sha256=candidate_graph_db_sha256,
            schema_version=schema_version,
        )
        if resolved_key is None:
            self.misses += 1
            return None

        entry = self._entries.get(resolved_key.key_sha256)
        if entry is None and self.cache_dir is not None:
            entry = self._load_from_disk(resolved_key.key_sha256)
            if entry is not None:
                self._entries[resolved_key.key_sha256] = entry

        if entry is None or entry.is_expired() or not entry.cache_key.matches_components(resolved_key):
            self.misses += 1
            return None

        self.hits += 1
        return entry

    def lookup(
        self,
        key: R1ACacheKey | None = None,
        *,
        prompt_hash: str = "",
        model_id: str = "",
        allocation_plan_digest: str = "",
        candidate_graph_db_sha256: str = "",
        schema_version: str | None = None,
        no_cache: bool | None = None,
    ) -> R1ACacheEntry | None:
        """Alias for get()."""
        return self.get(
            key,
            prompt_hash=prompt_hash,
            model_id=model_id,
            allocation_plan_digest=allocation_plan_digest,
            candidate_graph_db_sha256=candidate_graph_db_sha256,
            schema_version=schema_version,
            no_cache=no_cache,
        )

    def put(
        self,
        key: R1ACacheKey | R1ACacheEntry | None = None,
        payload: Any = None,
        *,
        prompt_hash: str = "",
        model_id: str = "",
        allocation_plan_digest: str = "",
        candidate_graph_db_sha256: str = "",
        schema_version: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        ttl_seconds: float | None = None,
        no_cache: bool | None = None,
    ) -> R1ACacheEntry | None:
        """Store an exact-match entry; returns None and increments bypasses when no_cache is True."""
        effective_no_cache = self.no_cache if no_cache is None else bool(no_cache)
        if effective_no_cache:
            self.bypasses += 1
            return None

        if isinstance(key, R1ACacheEntry):
            entry = key
            if not entry.cache_key.is_valid():
                return None
        else:
            resolved_key = self._resolve_key(
                key,
                prompt_hash=prompt_hash,
                model_id=model_id,
                allocation_plan_digest=allocation_plan_digest,
                candidate_graph_db_sha256=candidate_graph_db_sha256,
                schema_version=schema_version,
            )
            if resolved_key is None:
                return None
            entry = R1ACacheEntry(
                cache_key=resolved_key,
                payload=payload,
                ttl_seconds=self.default_ttl_seconds if ttl_seconds is None else float(ttl_seconds),
                metadata=dict(metadata or {}),
            )

        self._entries[entry.key_sha256] = entry
        if self.cache_dir is not None:
            self._persist_to_disk(entry)
        self.writes += 1
        return entry

    def store(self, *args: Any, **kwargs: Any) -> R1ACacheEntry | None:
        """Alias for put()."""
        return self.put(*args, **kwargs)

    def _persist_to_disk(self, entry: R1ACacheEntry) -> None:
        if self.cache_dir is None:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            target = self.cache_dir / f"{entry.key_sha256}.json"
            target.write_text(
                json.dumps(entry.to_dict(), sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        except OSError:
            return

    def _load_from_disk(self, key_sha256: str) -> R1ACacheEntry | None:
        if self.cache_dir is None:
            return None
        target = self.cache_dir / f"{key_sha256}.json"
        if not target.is_file():
            return None
        try:
            doc = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(doc, Mapping) or not isinstance(doc.get("cache_key"), Mapping):
                return None
            ck_raw = doc["cache_key"]
            ck = R1ACacheKey(
                prompt_hash=str(ck_raw.get("prompt_hash") or ""),
                model_id=str(ck_raw.get("model_id") or ""),
                allocation_plan_digest=str(ck_raw.get("allocation_plan_digest") or ""),
                candidate_graph_db_sha256=str(ck_raw.get("candidate_graph_db_sha256") or ""),
                schema_version=str(ck_raw.get("schema_version") or R1A_SCHEMA_VERSION),
            )
            return R1ACacheEntry(
                cache_key=ck,
                payload=doc.get("payload"),
                created_at=float(doc.get("created_at") or time.time()),
                ttl_seconds=float(doc.get("ttl_seconds") or self.default_ttl_seconds),
                metadata=dict(doc.get("metadata") or {}),
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def telemetry(self) -> dict[str, Any]:
        """Return deterministic telemetry counters for R1A exact caching."""
        return {
            "cache_tier": "R1A_EXACT",
            "schema_version": self.schema_version,
            "no_cache": self.no_cache,
            "hits": self.hits,
            "misses": self.misses,
            "bypasses": self.bypasses,
            "writes": self.writes,
            "entries": len(self._entries),
        }

    def get_telemetry(self) -> dict[str, Any]:
        """Alias for telemetry()."""
        return self.telemetry()

    def clear(self) -> None:
        """Clear in-memory entries and reset telemetry counters."""
        self._entries.clear()
        self.hits = 0
        self.misses = 0
        self.bypasses = 0
        self.writes = 0


__all__ = [
    "DEFAULT_R1A_TTL_SECONDS",
    "R1ACacheEntry",
    "R1ACacheKey",
    "R1AExactCacheAdapter",
    "R1A_SCHEMA_VERSION",
    "compute_r1a_cache_key",
]
