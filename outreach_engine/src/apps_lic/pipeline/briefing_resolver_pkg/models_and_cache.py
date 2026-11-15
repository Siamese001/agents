"""Data models, airlock sanitization, and bounded FIFO/disk cache for GovernedBriefingResolver."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Import airlock sanitizer from apps_research with availability enforcement
try:
    from apps_research.airlocks.briefing_injection_airlock import (
        AirlockBriefingReceipt,
        sanitize_briefing_content,
    )
    _AIRLOCK_AVAILABLE = True
except ImportError:
    _AIRLOCK_AVAILABLE = False
    AirlockBriefingReceipt = None  # type: ignore
    sanitize_briefing_content = None  # type: ignore

OUTREACH_MAX_CACHE_SIZE: int = 128


def _sanitize_briefing_content(raw_text: str, *, trace_id: str = "") -> tuple[str, Any]:
    """Sanitize research briefing text and enforce injection-airlock availability."""
    facade_mod = sys.modules.get("apps_lic.pipeline.briefing_resolver")
    airlock_avail = getattr(facade_mod, "_AIRLOCK_AVAILABLE", _AIRLOCK_AVAILABLE) if facade_mod is not None else _AIRLOCK_AVAILABLE
    sanitize_fn = getattr(facade_mod, "sanitize_briefing_content", sanitize_briefing_content) if facade_mod is not None else sanitize_briefing_content
    if not airlock_avail or sanitize_fn is None:
        raise RuntimeError(
            "AIRLOCK_UNAVAILABLE: apps_research briefing injection airlock must be available. "
            "All briefings must pass through injection-airlock validation."
        )
    try:
        return sanitize_fn(raw_text, trace_id=trace_id)
    except Exception as exc:
        raise RuntimeError(f"AIRLOCK_UNAVAILABLE: airlock execution failed: {exc}") from exc


@dataclass(frozen=True, slots=True)
class SealedBriefingResolution:
    briefing_text: str
    digest: str
    resolution_source: str  # MANUAL, CACHE_HIT, WEB_RESEARCH, CANONICAL_FIXTURE, HERMETIC_FALLBACK
    company_name: str
    target_role: str
    confidence_score: float
    evidence_count: int
    airlock_sanitized: bool
    strategic_priorities: tuple[str, ...] = ()
    fallback_reason: str = ""
    producer_handoff_ref: str = ""
    research_artifact_dir: str = ""
    briefing_artifact_path: str = ""
    is_verified: bool = True
    never_treated_as_candidate_proof: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "outreach.sealed_briefing_resolution.v1",
            "digest": self.digest,
            "resolution_source": self.resolution_source,
            "company_name": self.company_name,
            "target_role": self.target_role,
            "confidence_score": self.confidence_score,
            "evidence_count": self.evidence_count,
            "airlock_sanitized": self.airlock_sanitized,
            "strategic_priorities": list(self.strategic_priorities),
            "fallback_reason": self.fallback_reason,
            "producer_handoff_ref": self.producer_handoff_ref,
            "research_artifact_dir": self.research_artifact_dir,
            "briefing_artifact_path": self.briefing_artifact_path,
            "is_verified": self.is_verified,
            "never_treated_as_candidate_proof": self.never_treated_as_candidate_proof,
            "metadata": self.metadata,
        }


class BriefingCacheStoreBase:
    """In-memory FIFO and atomic disk cache storage for GovernedBriefingResolver."""

    MAX_CACHE_SIZE: int = OUTREACH_MAX_CACHE_SIZE
    DEFAULT_CACHE_TTL_SECONDS: float = 30 * 86400.0  # Unified 30-day cross-engine freshness window
    SHARED_DISK_CACHE_DIR: Path | None = None
    _cache: dict[str, dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def _save_to_cache(cls, key: str, value: dict[str, Any], *, disk_cache_dir: Path | None = None) -> None:
        """Stores entry in cache with bounded FIFO eviction, timestamp, and optional atomic disk persistence."""
        now_ts = time.time()
        with cls._lock:
            if len(cls._cache) >= cls.MAX_CACHE_SIZE:
                oldest_key = next(iter(cls._cache))
                cls._cache.pop(oldest_key, None)
            val = dict(value)
            val.setdefault("timestamp", now_ts)
            cls._cache[key] = val

        target_dir = disk_cache_dir or cls.SHARED_DISK_CACHE_DIR
        if target_dir is not None and bool(value.get("is_verified", True)):
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                safe_key = key.replace(":", "_")
                path = target_dir / f"{safe_key}.json"
                tmp = path.with_name(f".{path.name}.tmp")
                disk_payload = {
                    "company_name": str(value.get("company_name") or ""),
                    "target_role": str(value.get("target_role") or ""),
                    "briefing_text": str(value.get("briefing_text") or ""),
                    "digest": str(value.get("digest") or ""),
                    "source": str(value.get("resolution_source") or "OUTREACH_CACHE"),
                    "created_at": float(val["timestamp"]),
                    "ttl_seconds": float(cls.DEFAULT_CACHE_TTL_SECONDS),
                    "metadata": {
                        "confidence_score": float(value.get("confidence_score", 1.0)),
                        "evidence_count": int(value.get("evidence_count", 1)),
                        "airlock_sanitized": bool(value.get("airlock_sanitized", True)),
                        "strategic_priorities": list(value.get("strategic_priorities") or ()),
                        "is_verified": True,
                    },
                }
                tmp.write_text(
                    json.dumps(disk_payload, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )
                tmp.replace(path)
            except OSError:
                pass

    @classmethod
    def _load_from_shared_disk(cls, key: str, *, disk_cache_dir: Path | None = None) -> dict[str, Any] | None:
        target_dir = disk_cache_dir or cls.SHARED_DISK_CACHE_DIR
        if target_dir is None:
            return None
        safe_key = key.replace(":", "_")
        path = target_dir / f"{safe_key}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            created_at = float(payload.get("created_at") or 0.0)
            ttl = float(payload.get("ttl_seconds") or cls.DEFAULT_CACHE_TTL_SECONDS)
            if created_at <= 0.0 or (time.time() - created_at) > ttl:
                path.unlink(missing_ok=True)
                return None
            meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            if meta.get("is_verified") is not True:
                return None
            briefing_text = str(payload.get("briefing_text") or "").strip()
            digest = str(payload.get("digest") or "").strip()
            if not briefing_text or not digest.startswith("sha256:") or len(digest) != 71:
                return None
            computed = "sha256:" + hashlib.sha256(briefing_text.encode("utf-8")).hexdigest()
            if digest != computed:
                clean_b, receipt = _sanitize_briefing_content(briefing_text)
                if digest != receipt.clean_digest:
                    return None
                briefing_text = clean_b
            confidence = float(meta.get("confidence_score", 0.0))
            evidence_count = int(meta.get("evidence_count", 0))
            if confidence <= 0.0 or evidence_count <= 0:
                return None
            return {
                "briefing_text": briefing_text,
                "digest": digest,
                "confidence_score": confidence,
                "evidence_count": evidence_count,
                "airlock_sanitized": bool(meta.get("airlock_sanitized", True)),
                "strategic_priorities": tuple(meta.get("strategic_priorities") or ()),
                "is_verified": True,
                "timestamp": created_at,
            }
        except (OSError, ValueError, TypeError, RuntimeError):
            return None

    @classmethod
    def clear_cache(cls) -> None:
        """Clears in-memory resolution cache for testing or memory isolation."""
        with cls._lock:
            cls._cache.clear()


__all__ = [
    "AirlockBriefingReceipt",
    "BriefingCacheStoreBase",
    "OUTREACH_MAX_CACHE_SIZE",
    "SealedBriefingResolution",
    "_AIRLOCK_AVAILABLE",
    "_sanitize_briefing_content",
    "sanitize_briefing_content",
]
