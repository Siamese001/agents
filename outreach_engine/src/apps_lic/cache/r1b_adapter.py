"""R1B opt-in semantic cache adapter for outreach_engine (apps_lic).

Controlled strictly via ``infrastructure.config.env_loader.get_apps_lic_enable_r1b_semantic_cache()``
(zero direct ``os.environ`` reads in ``outreach_engine``).
Requires BOTH cosine similarity ``>= 0.95`` on the query/prompt embedding vector AND exact equality on
``(allocation_plan_digest, candidate_graph_db_sha256, model_id)`` so a semantic near-match can NEVER
return cached text across different candidate graphs or C0 fact allocations.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from infrastructure.candidate_evidence.quad_hybrid_retriever import (
    project_text_bge_m3_heads,
)
from infrastructure.config.env_loader import (
    get_apps_lic_enable_r1b_semantic_cache,
)

R1B_SCHEMA_VERSION: str = "apps_lic.r1b_semantic_cache.v1"
R1B_DEFAULT_COSINE_THRESHOLD: float = 0.95
R1B_MIN_COSINE_THRESHOLD: float = 0.95
DEFAULT_R1B_TTL_SECONDS: float = 86400.0


def compute_cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Compute cosine similarity between two numeric vectors, failing closed to 0.0 on invalid inputs."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a_raw, b_raw in zip(vec_a, vec_b):
        a = float(a_raw)
        b = float(b_raw)
        if math.isnan(a) or math.isnan(b) or math.isinf(a) or math.isinf(b):
            return 0.0
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return 0.0
    sim = dot / (math.sqrt(norm_a) * math.sqrt(norm_b))
    return max(-1.0, min(1.0, sim))


def embed_prompt_for_r1b(text: str) -> tuple[float, ...]:
    """Deterministically project prompt/query text to a 1024-d BGE-M3 dense vector."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ()
    dense_vec, _, _ = project_text_bge_m3_heads(cleaned)
    return tuple(float(x) for x in dense_vec)


@dataclass(frozen=True, slots=True)
class R1BSemanticEntry:
    """Immutable semantic cache entry bound to C0 fact allocation and candidate graph digests."""

    prompt_hash: str
    model_id: str
    allocation_plan_digest: str
    candidate_graph_db_sha256: str
    embedding: tuple[float, ...]
    payload: Any = None
    query_text: str = ""
    schema_version: str = R1B_SCHEMA_VERSION
    entry_id: str = ""
    similarity_score: float = 1.0
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = DEFAULT_R1B_TTL_SECONDS
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.embedding, tuple):
            object.__setattr__(self, "embedding", tuple(float(x) for x in self.embedding))
        if not self.entry_id:
            identity_payload = {
                "prompt_hash": str(self.prompt_hash or "").strip(),
                "model_id": str(self.model_id or "").strip(),
                "allocation_plan_digest": str(self.allocation_plan_digest or "").strip(),
                "candidate_graph_db_sha256": str(self.candidate_graph_db_sha256 or "").strip(),
                "schema_version": str(self.schema_version or R1B_SCHEMA_VERSION).strip(),
            }
            digest = hashlib.sha256(
                json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            object.__setattr__(self, "entry_id", digest)

    @property
    def value(self) -> Any:
        """Alias for payload."""
        return self.payload

    @property
    def response(self) -> Any:
        """Alias for payload."""
        return self.payload

    def is_valid_guard(self) -> bool:
        """Return True iff mandatory exact-equality guard fields and embedding are non-empty."""
        return bool(
            self.model_id.strip()
            and self.allocation_plan_digest.strip()
            and self.candidate_graph_db_sha256.strip()
            and len(self.embedding) > 0
        )

    def is_expired(self, now: float | None = None) -> bool:
        """Return True if the semantic entry has exceeded its TTL."""
        if self.ttl_seconds <= 0:
            return True
        current = time.time() if now is None else float(now)
        return (current - self.created_at) > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        """Serialize R1BSemanticEntry to a JSON-compatible dictionary."""
        return {
            "entry_id": self.entry_id,
            "prompt_hash": self.prompt_hash,
            "model_id": self.model_id,
            "allocation_plan_digest": self.allocation_plan_digest,
            "candidate_graph_db_sha256": self.candidate_graph_db_sha256,
            "embedding": list(self.embedding),
            "payload": self.payload,
            "query_text": self.query_text,
            "schema_version": self.schema_version,
            "similarity_score": round(float(self.similarity_score), 6),
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
            "metadata": dict(self.metadata),
        }


class R1BSemanticCacheAdapter:
    """Opt-in R1B semantic cache adapter enforcing >=0.95 cosine AND exact graph/C0 guard equality."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        no_cache: bool = False,
        similarity_threshold: float = R1B_DEFAULT_COSINE_THRESHOLD,
        default_ttl_seconds: float = DEFAULT_R1B_TTL_SECONDS,
        cache_dir: Path | str | None = None,
    ) -> None:
        self._explicit_enabled: bool | None = enabled
        self.no_cache: bool = bool(no_cache)
        self.similarity_threshold: float = max(float(similarity_threshold), R1B_MIN_COSINE_THRESHOLD)
        self.default_ttl_seconds: float = float(default_ttl_seconds)
        self.cache_dir: Path | None = Path(cache_dir).resolve() if cache_dir is not None else None
        self._entries: list[R1BSemanticEntry] = []
        self.hits: int = 0
        self.misses: int = 0
        self.bypasses: int = 0
        self.disabled_misses: int = 0
        self.guard_rejections: int = 0
        self.below_threshold_rejections: int = 0
        self.writes: int = 0

    def is_enabled(self) -> bool:
        """Check whether R1B semantic caching is enabled via env_loader or explicit override."""
        env_enabled = get_apps_lic_enable_r1b_semantic_cache(default=False)
        if self._explicit_enabled is not None:
            return bool(self._explicit_enabled)
        return env_enabled

    def _resolve_embedding(
        self,
        embedding: Sequence[float] | None,
        query_text: str,
    ) -> tuple[float, ...]:
        if embedding is not None:
            return tuple(float(x) for x in embedding)
        if query_text.strip():
            return embed_prompt_for_r1b(query_text)
        return ()

    def get(
        self,
        *,
        embedding: Sequence[float] | None = None,
        query_text: str = "",
        allocation_plan_digest: str = "",
        candidate_graph_db_sha256: str = "",
        model_id: str = "",
        no_cache: bool | None = None,
        similarity_threshold: float | None = None,
    ) -> R1BSemanticEntry | None:
        """Look up a semantic match; fails closed when disabled, bypassed, <0.95 cosine, or guard mismatch."""
        effective_no_cache = self.no_cache if no_cache is None else bool(no_cache)
        if effective_no_cache:
            self.bypasses += 1
            return None

        if not self.is_enabled():
            self.disabled_misses += 1
            self.misses += 1
            return None

        req_alloc = str(allocation_plan_digest or "").strip()
        req_graph = str(candidate_graph_db_sha256 or "").strip()
        req_model = str(model_id or "").strip()
        if not req_alloc or not req_graph or not req_model:
            self.misses += 1
            return None

        q_vec = self._resolve_embedding(embedding, query_text)
        if not q_vec:
            self.misses += 1
            return None

        threshold = max(
            float(self.similarity_threshold if similarity_threshold is None else similarity_threshold),
            R1B_MIN_COSINE_THRESHOLD,
        )

        best_entry: R1BSemanticEntry | None = None
        best_sim: float = -1.0

        for entry in self._entries:
            if entry.is_expired():
                continue
            if (
                entry.allocation_plan_digest != req_alloc
                or entry.candidate_graph_db_sha256 != req_graph
                or entry.model_id != req_model
            ):
                self.guard_rejections += 1
                continue

            sim = compute_cosine_similarity(q_vec, entry.embedding)
            if sim < threshold:
                self.below_threshold_rejections += 1
                continue

            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is None:
            self.misses += 1
            return None

        self.hits += 1
        return replace(best_entry, similarity_score=round(best_sim, 6))

    def lookup(self, **kwargs: Any) -> R1BSemanticEntry | None:
        """Alias for get()."""
        return self.get(**kwargs)

    def put(
        self,
        entry: R1BSemanticEntry | None = None,
        *,
        prompt_hash: str = "",
        model_id: str = "",
        allocation_plan_digest: str = "",
        candidate_graph_db_sha256: str = "",
        embedding: Sequence[float] | None = None,
        query_text: str = "",
        payload: Any = None,
        metadata: Mapping[str, Any] | None = None,
        ttl_seconds: float | None = None,
        no_cache: bool | None = None,
    ) -> R1BSemanticEntry | None:
        """Store a semantic cache entry when enabled and not bypassed; fails closed otherwise."""
        effective_no_cache = self.no_cache if no_cache is None else bool(no_cache)
        if effective_no_cache:
            self.bypasses += 1
            return None

        if not self.is_enabled():
            self.disabled_misses += 1
            return None

        if isinstance(entry, R1BSemanticEntry):
            resolved = entry
        else:
            vec = self._resolve_embedding(embedding, query_text)
            resolved = R1BSemanticEntry(
                prompt_hash=prompt_hash or hashlib.sha256(query_text.encode("utf-8")).hexdigest(),
                model_id=model_id,
                allocation_plan_digest=allocation_plan_digest,
                candidate_graph_db_sha256=candidate_graph_db_sha256,
                embedding=vec,
                payload=payload,
                query_text=query_text,
                ttl_seconds=self.default_ttl_seconds if ttl_seconds is None else float(ttl_seconds),
                metadata=dict(metadata or {}),
            )

        if not resolved.is_valid_guard():
            return None

        self._entries.append(resolved)
        self.writes += 1
        return resolved

    def store(self, *args: Any, **kwargs: Any) -> R1BSemanticEntry | None:
        """Alias for put()."""
        return self.put(*args, **kwargs)

    def telemetry(self) -> dict[str, Any]:
        """Return deterministic telemetry counters for R1B semantic caching."""
        return {
            "cache_tier": "R1B_SEMANTIC",
            "schema_version": R1B_SCHEMA_VERSION,
            "enabled": self.is_enabled(),
            "no_cache": self.no_cache,
            "similarity_threshold": self.similarity_threshold,
            "hits": self.hits,
            "misses": self.misses,
            "bypasses": self.bypasses,
            "disabled_misses": self.disabled_misses,
            "guard_rejections": self.guard_rejections,
            "below_threshold_rejections": self.below_threshold_rejections,
            "writes": self.writes,
            "entries": len(self._entries),
        }

    def get_telemetry(self) -> dict[str, Any]:
        """Alias for telemetry()."""
        return self.telemetry()

    def clear(self) -> None:
        """Clear in-memory semantic cache entries and reset telemetry counters."""
        self._entries.clear()
        self.hits = 0
        self.misses = 0
        self.bypasses = 0
        self.disabled_misses = 0
        self.guard_rejections = 0
        self.below_threshold_rejections = 0
        self.writes = 0


__all__ = [
    "DEFAULT_R1B_TTL_SECONDS",
    "R1BSemanticCacheAdapter",
    "R1BSemanticEntry",
    "R1B_DEFAULT_COSINE_THRESHOLD",
    "R1B_MIN_COSINE_THRESHOLD",
    "R1B_SCHEMA_VERSION",
    "compute_cosine_similarity",
    "embed_prompt_for_r1b",
]
