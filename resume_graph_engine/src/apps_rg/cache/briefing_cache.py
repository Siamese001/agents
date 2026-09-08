"""First-class R1A briefing cache for apps_rg.

Caches resolved sealed briefings by (company_name, jd_hash) to provide
instant (0ms) replayability across runs targeting the same position.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BRIEFING_TTL_SECONDS = 30 * 24 * 3600  # 30 days


@dataclass(frozen=True, slots=True)
class CachedBriefing:
    company_name: str
    target_role: str
    briefing_text: str
    digest: str
    source: str
    created_at: float
    ttl_seconds: float = DEFAULT_BRIEFING_TTL_SECONDS
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds


def compute_briefing_cache_key(*, company_name: str, jd_hash: str) -> str:
    norm_co = company_name.strip().lower()
    norm_jd = jd_hash.strip().lower()
    combined = f"{norm_co}::{norm_jd}".encode("utf-8")
    return "r1a_brief:" + hashlib.sha256(combined).hexdigest()[:24]


class BriefingCache:
    """In-memory and filesystem-backed cache for sealed briefings."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._memory: dict[str, CachedBriefing] = {}
        self._cache_dir = cache_dir

    def get(self, key: str) -> CachedBriefing | None:
        # Check memory first
        item = self._memory.get(key)
        if item is not None:
            if not item.is_expired:
                return item
            self._memory.pop(key, None)

        # Check disk if configured
        if self._cache_dir is not None:
            safe_key = key.replace(":", "_")
            path = self._cache_dir / f"{safe_key}.json"
            if path.is_file():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    cached = CachedBriefing(
                        company_name=payload.get("company_name", ""),
                        target_role=payload.get("target_role", ""),
                        briefing_text=payload.get("briefing_text", ""),
                        digest=payload.get("digest", ""),
                        source=payload.get("source", ""),
                        created_at=float(payload.get("created_at", 0.0)),
                        ttl_seconds=float(payload.get("ttl_seconds", DEFAULT_BRIEFING_TTL_SECONDS)),
                        metadata=dict(payload.get("metadata", {})),
                    )
                    if not cached.is_expired:
                        self._memory[key] = cached
                        return cached
                    path.unlink(missing_ok=True)
                except (OSError, ValueError, TypeError):
                    pass
        return None

    def put(self, key: str, briefing: CachedBriefing) -> None:
        self._memory[key] = briefing
        if self._cache_dir is not None:
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                safe_key = key.replace(":", "_")
                path = self._cache_dir / f"{safe_key}.json"
                tmp = path.with_name(f".{path.name}.tmp")
                tmp.write_text(json.dumps(asdict(briefing), indent=2), encoding="utf-8")
                tmp.replace(path)
            except OSError:
                pass

    def clear(self) -> None:
        self._memory.clear()


_GLOBAL_BRIEFING_CACHE = BriefingCache()


def get_global_briefing_cache(cache_dir: Path | None = None) -> BriefingCache:
    global _GLOBAL_BRIEFING_CACHE
    if cache_dir is not None and _GLOBAL_BRIEFING_CACHE._cache_dir != cache_dir:
        _GLOBAL_BRIEFING_CACHE = BriefingCache(cache_dir=cache_dir)
    return _GLOBAL_BRIEFING_CACHE


__all__ = [
    "BriefingCache",
    "CachedBriefing",
    "compute_briefing_cache_key",
    "get_global_briefing_cache",
]
