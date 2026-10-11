"""Governed Multi-Path Briefing Resolver for outreach_engine.

Coordinates resolution across 4 paths matching resume_graph_engine:
1. Manual explicit brief / mission fixture (Path A)
2. Local cached brief hit (Path B)
3. Live autonomous research via apps_research + Adversarial Injection Airlock (Path C)
4. Hermetic Tier-1 context fallback (Path D)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

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


def _sanitize_briefing_content(raw_text: str, *, trace_id: str = "") -> tuple[str, Any]:
    """Sanitize research briefing text and enforce injection-airlock availability."""
    if not _AIRLOCK_AVAILABLE or sanitize_briefing_content is None:
        raise RuntimeError(
            "AIRLOCK_UNAVAILABLE: apps_research briefing injection airlock must be available. "
            "All briefings must pass through injection-airlock validation."
        )
    try:
        return sanitize_briefing_content(raw_text, trace_id=trace_id)
    except Exception as exc:
        raise RuntimeError(f"AIRLOCK_UNAVAILABLE: airlock execution failed: {exc}") from exc


_log = logging.getLogger(__name__)


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
            "metadata": self.metadata,
        }


class GovernedBriefingResolver:
    """Resolves briefing context for outreach through governed multi-path resolution."""

    MAX_CACHE_SIZE: int = 128
    DEFAULT_CACHE_TTL_SECONDS: float = 7 * 86400.0  # 7 days freshness window
    _cache: dict[str, dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def _save_to_cache(cls, key: str, value: dict[str, Any]) -> None:
        """Stores entry in cache with bounded FIFO eviction and freshness timestamp."""
        with cls._lock:
            if len(cls._cache) >= cls.MAX_CACHE_SIZE:
                oldest_key = next(iter(cls._cache))
                cls._cache.pop(oldest_key, None)
            val = dict(value)
            val.setdefault("timestamp", time.time())
            cls._cache[key] = val

    @classmethod
    def clear_cache(cls) -> None:
        """Clears in-memory resolution cache for testing or memory isolation."""
        with cls._lock:
            cls._cache.clear()

    @classmethod
    def resolve(
        cls,
        *,
        company_name: str,
        target_role: str = "",
        manual_brief_or_fixture: str = "",
        strategic_priorities: list[str] | tuple[str, ...] = (),
        job_description_text: str = "",
        auto_research: bool = True,
        research_bridge: Any | None = None,
        artifact_runs_root: Path | None = None,
        trace_id: str = "",
    ) -> SealedBriefingResolution:
        # PATH A: Explicit Manual Brief or Mission Fixture context
        if manual_brief_or_fixture or strategic_priorities:
            raw_content = str(manual_brief_or_fixture or "").strip()
            priorities = tuple(strategic_priorities)
            if not raw_content and priorities:
                raw_content = (
                    f"Target Company: {company_name}\n"
                    f"Strategic Priorities:\n"
                    + "\n".join(f"- {p}" for p in priorities)
                )

            # Check if manual_brief_or_fixture is a local file path to capture mtime
            mtime = 0.0
            if len(raw_content) < 300 and "\n" not in raw_content and "\0" not in raw_content:
                try:
                    p = Path(raw_content)
                    if p.is_file():
                        mtime = p.stat().st_mtime
                        raw_content = p.read_text(encoding="utf-8").strip()
                except (OSError, ValueError):
                    pass

            manual_cache_key = hashlib.sha256(
                f"MANUAL::{company_name}::{target_role}::{mtime}::{raw_content}::{priorities}".encode("utf-8")
            ).hexdigest()

            with cls._lock:
                if manual_cache_key in cls._cache:
                    cached = cls._cache[manual_cache_key]
                    cached_time = cached.get("timestamp", 0.0)
                    if time.time() - cached_time <= cls.DEFAULT_CACHE_TTL_SECONDS:
                        return SealedBriefingResolution(
                            briefing_text=cached["briefing_text"],
                            digest=cached["digest"],
                            resolution_source="MANUAL",
                            company_name=company_name,
                            target_role=target_role,
                            confidence_score=float(cached.get("confidence_score", 1.0)),
                            evidence_count=int(cached.get("evidence_count", 1)),
                            airlock_sanitized=cached["airlock_sanitized"],
                            strategic_priorities=priorities,
                            is_verified=bool(cached.get("is_verified", True)),
                            metadata=dict(cached.get("metadata", {})),
                        )
                    cls._cache.pop(manual_cache_key, None)

            # Sanitize all manual input through the Adversarial Injection Airlock
            clean_brief, receipt = _sanitize_briefing_content(raw_content, trace_id=trace_id)
            is_verified = bool(clean_brief)

            res = SealedBriefingResolution(
                briefing_text=clean_brief,
                digest=receipt.clean_digest,
                resolution_source="MANUAL",
                company_name=company_name,
                target_role=target_role,
                confidence_score=1.0 if is_verified else 0.0,
                evidence_count=len(priorities) if priorities else (1 if is_verified else 0),
                airlock_sanitized=receipt.sanitized,
                strategic_priorities=priorities,
                is_verified=is_verified,
                metadata={
                    "source": "manual_fixture",
                    "signals_flagged": list(receipt.injection_signals_detected),
                    "is_verified": is_verified,
                },
            )
            cls._save_to_cache(
                manual_cache_key,
                {
                    "briefing_text": clean_brief,
                    "digest": receipt.clean_digest,
                    "confidence_score": res.confidence_score,
                    "evidence_count": res.evidence_count,
                    "airlock_sanitized": receipt.sanitized,
                    "strategic_priorities": priorities,
                    "is_verified": is_verified,
                    "metadata": res.metadata,
                },
            )
            return res

        # Compute cache key
        cache_key = hashlib.sha256(
            f"{company_name}::{target_role}::{job_description_text}".encode("utf-8")
        ).hexdigest()

        # PATH B: Cache Hit with TTL Freshness Verification
        with cls._lock:
            if cache_key in cls._cache:
                cached = cls._cache[cache_key]
                cached_time = cached.get("timestamp", 0.0)
                if time.time() - cached_time > cls.DEFAULT_CACHE_TTL_SECONDS:
                    cls._cache.pop(cache_key, None)
                else:
                    return SealedBriefingResolution(
                        briefing_text=cached["briefing_text"],
                        digest=cached["digest"],
                        resolution_source="CACHE_HIT",
                        company_name=company_name,
                        target_role=target_role,
                        confidence_score=float(cached.get("confidence_score", 0.0)),
                        evidence_count=int(cached.get("evidence_count", 0)),
                        airlock_sanitized=cached.get("airlock_sanitized", False),
                        strategic_priorities=tuple(cached.get("strategic_priorities", ())),
                        research_artifact_dir=cached.get("research_artifact_dir", ""),
                        briefing_artifact_path=cached.get("briefing_artifact_path", ""),
                        is_verified=bool(cached.get("is_verified", True)),
                        metadata={"cache_key": cache_key, "cached_at": cached_time},
                    )

        # PATH C: Autonomous Research via AppsResearchBridge
        if auto_research:
            from apps_lic.integrations.apps_research_bridge import AppsResearchBridge
            from apps_lic.integrations.managed_research_delegation import (
                OutreachBriefingReady,
                RequestForOutreachBriefing,
                dispatch_outreach_research_briefing,
            )

            bridge = research_bridge or AppsResearchBridge(artifact_runs_root=artifact_runs_root)
            req = RequestForOutreachBriefing(
                request_id=f"req-brief-{trace_id[:8] or 'default'}",
                run_id=f"run-{trace_id[:8] or 'default'}",
                trace_id=trace_id or "trace-default",
                company_name=company_name,
                job_title=target_role,
                job_description_text=job_description_text,
                artifact_runs_root=artifact_runs_root,
            )

            dispatch_res = dispatch_outreach_research_briefing(req, bridge=bridge)
            if isinstance(dispatch_res, OutreachBriefingReady):
                clean_brief, receipt = _sanitize_briefing_content(
                    dispatch_res.briefing_text, trace_id=trace_id
                )
                priorities = dispatch_res.strategic_priorities or ()
                is_verified = (
                    dispatch_res.resolution_source != "HERMETIC_FALLBACK"
                    and dispatch_res.confidence_score > 0.0
                )
                cls._save_to_cache(
                    cache_key,
                    {
                        "briefing_text": clean_brief,
                        "digest": receipt.clean_digest,
                        "confidence_score": dispatch_res.confidence_score,
                        "evidence_count": dispatch_res.research_evidence_count,
                        "airlock_sanitized": receipt.sanitized,
                        "strategic_priorities": priorities,
                        "research_artifact_dir": dispatch_res.research_artifact_dir,
                        "briefing_artifact_path": dispatch_res.research_briefing_path,
                        "is_verified": is_verified,
                    },
                )
                return SealedBriefingResolution(
                    briefing_text=clean_brief,
                    digest=receipt.clean_digest,
                    resolution_source=dispatch_res.resolution_source,
                    company_name=company_name,
                    target_role=target_role,
                    confidence_score=dispatch_res.confidence_score,
                    evidence_count=dispatch_res.research_evidence_count,
                    airlock_sanitized=receipt.sanitized,
                    strategic_priorities=priorities,
                    producer_handoff_ref=dispatch_res.result_hash,
                    research_artifact_dir=dispatch_res.research_artifact_dir,
                    briefing_artifact_path=dispatch_res.research_briefing_path,
                    is_verified=is_verified,
                    metadata={
                        "signals_flagged": list(receipt.injection_signals_detected),
                        "duration_ms": dispatch_res.dispatch_duration_ms,
                        "is_verified": is_verified,
                    },
                )
            else:
                _log.warning(
                    "Autonomous research path failed: %s; falling back to unverified hermetic",
                    dispatch_res.detail,
                )

        # PATH D: Hermetic Offline Fallback (Explicitly Marked Unverified, Zero Invented Priorities)
        fallback_text = (
            f"# Research Briefing: {company_name}\n\n"
            f"## Status\n"
            f"Unverified offline fallback brief for {company_name} - {target_role}\n\n"
            f"## Governance\n"
            f"- Provenance: apps_research hermetic fallback (unverified)\n"
        )
        digest = "sha256:" + hashlib.sha256(fallback_text.encode("utf-8")).hexdigest()
        return SealedBriefingResolution(
            briefing_text=fallback_text,
            digest=digest,
            resolution_source="HERMETIC_FALLBACK",
            company_name=company_name,
            target_role=target_role,
            confidence_score=0.0,
            evidence_count=0,
            airlock_sanitized=False,
            strategic_priorities=(),
            fallback_reason="AUTO_RESEARCH_UNAVAILABLE_OR_OFFLINE",
            is_verified=False,
            metadata={"status": "UNVERIFIED", "is_verified": False},
        )


__all__ = ["GovernedBriefingResolver", "SealedBriefingResolution"]
