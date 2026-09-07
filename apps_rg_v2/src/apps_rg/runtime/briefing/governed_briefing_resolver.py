"""Governed Multi-Path Briefing Resolver.

Coordinates resolution across 4 paths:
1. Manual explicit brief (if provided by user)
2. R1A cached brief (if company + JD was previously resolved)
3. Live autonomous research (via apps_research + Adversarial Injection Airlock)
4. Hermetic Tier-1 JD extractor fallback (when SearXNG is offline or research blocks)

Guarantees that downstream apps_rg ALWAYS receives a valid, sealed briefing artifact
without crashing when external network dependencies are unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from apps_rg.cache.briefing_cache import (
    CachedBriefing,
    compute_briefing_cache_key,
    get_global_briefing_cache,
)
from apps_rg.runtime.briefing.jd_context_briefing_engine import extract_jd_briefing
from apps_research.airlocks.briefing_injection_airlock import sanitize_briefing_content

_log = logging.getLogger(__name__)


class BriefingResolutionError(RuntimeError):
    """Raised when briefing resolution fails and fallback is forbidden."""
    pass


@dataclass(frozen=True, slots=True)
class SealedBriefingResolution:
    briefing_text: str
    digest: str
    resolution_source: str
    company_name: str
    target_role: str
    confidence_score: float
    evidence_count: int
    airlock_sanitized: bool
    fallback_reason: str = ""
    producer_handoff_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "apps_rg.sealed_briefing_resolution.v1",
            "digest": self.digest,
            "resolution_source": self.resolution_source,
            "company_name": self.company_name,
            "target_role": self.target_role,
            "confidence_score": self.confidence_score,
            "evidence_count": self.evidence_count,
            "airlock_sanitized": self.airlock_sanitized,
            "fallback_reason": self.fallback_reason,
            "producer_handoff_ref": self.producer_handoff_ref,
            "metadata": self.metadata,
        }


def _searxng_available() -> bool:
    url = os.environ.get("SEARXNG_BASE_URL", "").strip()
    return bool(url and url != "disabled")


class GovernedBriefingResolver:
    def __init__(self, *, cache_dir: Path | None = None) -> None:
        self._cache = get_global_briefing_cache(cache_dir=cache_dir)

    @staticmethod
    def resolve(
        *,
        company_name: str,
        target_role: str,
        jd_text: str,
        jd_ref: str = "",
        manual_brief_path_or_text: str = "",
        auto_research: bool = True,
        research_bridge: Any | None = None,
        artifact_dir: Path | None = None,
        trace_id: str = "",
        allow_offline_fallback: bool = False,
    ) -> SealedBriefingResolution:
        # PATH A: Explicit Manual Brief
        manual_candidate = (manual_brief_path_or_text or "").strip()
        if manual_candidate:
            content = ""
            try:
                p = Path(manual_candidate)
                if p.is_file():
                    content = p.read_text(encoding="utf-8").strip()
            except OSError:
                content = ""
            if not content:
                content = manual_candidate

            if content:
                content_bytes = content.encode("utf-8")
                digest = "sha256:" + hashlib.sha256(content_bytes).hexdigest()
                return SealedBriefingResolution(
                    briefing_text=content,
                    digest=digest,
                    resolution_source="MANUAL",
                    company_name=company_name,
                    target_role=target_role,
                    confidence_score=1.0,
                    evidence_count=1,
                    airlock_sanitized=False,
                    metadata={"source_ref": manual_candidate[:120]},
                )

        # Compute JD Hash for cache and targeting
        jd_hash = "sha256:" + hashlib.sha256((jd_text or "").strip().encode("utf-8")).hexdigest()
        cache_key = compute_briefing_cache_key(company_name=company_name, jd_hash=jd_hash)
        cache = get_global_briefing_cache()

        # PATH B: R1A Briefing Cache Hit
        cached = cache.get(cache_key)
        if cached is not None:
            return SealedBriefingResolution(
                briefing_text=cached.briefing_text,
                digest=cached.digest,
                resolution_source="CACHE_HIT",
                company_name=company_name,
                target_role=target_role,
                confidence_score=0.90,
                evidence_count=1,
                airlock_sanitized=False,
                metadata={"cache_key": cache_key, "original_source": cached.source},
            )

        # PATH C: Live Autonomous Web Research (if requested & bridge available)
        fallback_reason = ""
        if auto_research and research_bridge is not None:
            try:
                raw_result = research_bridge.fetch(
                    company_name=company_name,
                    job_title=target_role,
                    capability_ref="apps_research.v1",
                    request_id=f"req-{trace_id[:8]}",
                    run_id=f"run-{trace_id[:8]}",
                    trace_id=trace_id or "trace-resolver",
                    job_description_ref=jd_ref,
                    job_description_text=jd_text,
                )
                if (
                    raw_result is not None
                    and not getattr(raw_result, "is_blocked", False)
                    and str(getattr(raw_result, "company_brief_text", "") or "").strip()
                ):
                    raw_brief = str(raw_result.company_brief_text).strip()
                    # Sanitize through Adversarial Injection Airlock
                    clean_brief, airlock_receipt = sanitize_briefing_content(
                        raw_brief, trace_id=trace_id
                    )
                    # Cache in R1A
                    cache.put(
                        cache_key,
                        CachedBriefing(
                            company_name=company_name,
                            target_role=target_role,
                            briefing_text=clean_brief,
                            digest=airlock_receipt.clean_digest,
                            source="WEB_RESEARCH",
                            created_at=time.time(),
                        ),
                    )
                    return SealedBriefingResolution(
                        briefing_text=clean_brief,
                        digest=airlock_receipt.clean_digest,
                        resolution_source="WEB_RESEARCH",
                        company_name=company_name,
                        target_role=target_role,
                        confidence_score=float(getattr(raw_result, "confidence_score", 0.88) or 0.88),
                        evidence_count=len(getattr(raw_result, "evidence_items", ()) or ()),
                        airlock_sanitized=airlock_receipt.sanitized,
                        producer_handoff_ref=str(getattr(raw_result, "briefing_artifact_path", "") or ""),
                        metadata={
                            "airlock_signals_flagged": list(airlock_receipt.injection_signals_detected),
                            "original_digest": airlock_receipt.original_digest,
                        },
                    )
                else:
                    block_msg = getattr(raw_result, "block_reason", "unknown_research_block")
                    fallback_reason = f"RESEARCH_BLOCKED: {block_msg}"
            except Exception as exc:  # noqa: BLE001
                fallback_reason = f"RESEARCH_EXCEPTION: {type(exc).__name__}: {exc}"
        else:
            if not auto_research:
                fallback_reason = "AUTO_RESEARCH_DISABLED"
            elif research_bridge is None:
                fallback_reason = "RESEARCH_BRIDGE_UNAVAILABLE"

        if not allow_offline_fallback:
            raise BriefingResolutionError(
                f"Briefing resolution failed ({fallback_reason}). Offline fallback is strictly forbidden."
            )

        # PATH D: Tier-1 Hermetic JD Context Fallback (Only when explicitly permitted)
        offline_result = extract_jd_briefing(
            company_name=company_name,
            target_role=target_role,
            jd_text=jd_text,
            jd_ref=jd_ref,
        )
        return SealedBriefingResolution(
            briefing_text=offline_result.briefing_text,
            digest=offline_result.digest,
            resolution_source="JD_OFFLINE_FALLBACK",
            company_name=company_name,
            target_role=target_role,
            confidence_score=offline_result.confidence_score,
            evidence_count=offline_result.evidence_count,
            airlock_sanitized=False,
            fallback_reason=fallback_reason,
            metadata=dict(offline_result.metadata),
        )


__all__ = [
    "BriefingResolutionError",
    "GovernedBriefingResolver",
    "SealedBriefingResolution",
]
