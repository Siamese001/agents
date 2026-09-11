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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import airlock sanitizer from apps_research with fallback
try:
    from apps_research.airlocks.briefing_injection_airlock import (
        AirlockBriefingReceipt,
        sanitize_briefing_content,
    )
except ImportError:
    @dataclass(frozen=True, slots=True)
    class AirlockBriefingReceipt:
        original_digest: str
        clean_digest: str
        sanitized: bool
        injection_signals_detected: tuple[str, ...]
        char_count: int
        bullet_count: int
        clean_briefing_text: str
        audit_metadata: dict[str, Any] = field(default_factory=dict)

    def sanitize_briefing_content(raw_text: str, *, trace_id: str = "") -> tuple[str, AirlockBriefingReceipt]:
        clean = (raw_text or "").strip()
        orig_sha = "sha256:" + hashlib.sha256(clean.encode("utf-8")).hexdigest()
        return clean, AirlockBriefingReceipt(
            original_digest=orig_sha,
            clean_digest=orig_sha,
            sanitized=False,
            injection_signals_detected=(),
            char_count=len(clean),
            bullet_count=len(clean.splitlines()),
            clean_briefing_text=clean,
        )


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
            "metadata": self.metadata,
        }


class GovernedBriefingResolver:
    """Resolves briefing context for outreach through governed multi-path resolution."""

    _cache: dict[str, dict[str, Any]] = {}

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

            # Sanitize all manual input through the Adversarial Injection Airlock
            clean_brief, receipt = sanitize_briefing_content(raw_content, trace_id=trace_id)

            return SealedBriefingResolution(
                briefing_text=clean_brief,
                digest=receipt.clean_digest,
                resolution_source="MANUAL",
                company_name=company_name,
                target_role=target_role,
                confidence_score=1.0,
                evidence_count=len(priorities) or 1,
                airlock_sanitized=receipt.sanitized,
                strategic_priorities=priorities,
                metadata={
                    "source": "manual_fixture",
                    "signals_flagged": list(receipt.injection_signals_detected),
                },
            )

        # Compute cache key
        cache_key = hashlib.sha256(
            f"{company_name}::{target_role}::{job_description_text}".encode("utf-8")
        ).hexdigest()

        # PATH B: Cache Hit
        if cache_key in cls._cache:
            cached = cls._cache[cache_key]
            return SealedBriefingResolution(
                briefing_text=cached["briefing_text"],
                digest=cached["digest"],
                resolution_source="CACHE_HIT",
                company_name=company_name,
                target_role=target_role,
                confidence_score=0.90,
                evidence_count=cached.get("evidence_count", 1),
                airlock_sanitized=cached.get("airlock_sanitized", False),
                strategic_priorities=tuple(cached.get("strategic_priorities", ())),
                research_artifact_dir=cached.get("research_artifact_dir", ""),
                briefing_artifact_path=cached.get("briefing_artifact_path", ""),
                metadata={"cache_key": cache_key},
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
                clean_brief, receipt = sanitize_briefing_content(
                    dispatch_res.briefing_text, trace_id=trace_id
                )
                priorities = dispatch_res.strategic_priorities or ()
                cls._cache[cache_key] = {
                    "briefing_text": clean_brief,
                    "digest": receipt.clean_digest,
                    "evidence_count": dispatch_res.research_evidence_count,
                    "airlock_sanitized": receipt.sanitized,
                    "strategic_priorities": priorities,
                    "research_artifact_dir": dispatch_res.research_artifact_dir,
                    "briefing_artifact_path": dispatch_res.research_briefing_path,
                }
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
                    metadata={
                        "signals_flagged": list(receipt.injection_signals_detected),
                        "duration_ms": dispatch_res.dispatch_duration_ms,
                    },
                )
            else:
                _log.warning(
                    "Autonomous research path failed: %s; falling back to hermetic",
                    dispatch_res.detail,
                )

        # PATH D: Hermetic Offline Fallback
        fallback_priorities = (
            f"Core platform modernization at {company_name}",
            f"Strategic initiatives in {target_role or 'enterprise engineering'}",
        )
        fallback_text = f"Hermetic fallback brief for {company_name} - {target_role}"
        digest = "sha256:" + hashlib.sha256(fallback_text.encode("utf-8")).hexdigest()
        return SealedBriefingResolution(
            briefing_text=fallback_text,
            digest=digest,
            resolution_source="HERMETIC_FALLBACK",
            company_name=company_name,
            target_role=target_role,
            confidence_score=0.85,
            evidence_count=len(fallback_priorities),
            airlock_sanitized=False,
            strategic_priorities=fallback_priorities,
            fallback_reason="AUTO_RESEARCH_UNAVAILABLE_OR_OFFLINE",
        )


__all__ = ["GovernedBriefingResolver", "SealedBriefingResolution"]
