"""Multi-path briefing resolution engine for GovernedBriefingResolver."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from apps_lic.pipeline.briefing_resolver_pkg.models_and_cache import (
    BriefingCacheStoreBase,
    SealedBriefingResolution,
    _sanitize_briefing_content,
)

_log = logging.getLogger(__name__)


class GovernedBriefingResolver(BriefingCacheStoreBase):
    """Resolves briefing context for outreach through governed multi-path resolution."""

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
        force_fresh: bool = False,
    ) -> SealedBriefingResolution:
        # PATH A: Explicit Manual Brief or Mission Fixture context
        if manual_brief_or_fixture or strategic_priorities:
            raw_content = str(manual_brief_or_fixture or "").strip()
            if isinstance(strategic_priorities, str):
                priorities = (strategic_priorities.strip(),) if strategic_priorities.strip() else ()
            elif isinstance(strategic_priorities, (list, tuple, set)):
                priorities = tuple(str(p).strip() for p in strategic_priorities if str(p).strip())
            else:
                priorities = ()
            if not raw_content and priorities:
                raw_content = (
                    f"Target Company: {company_name}\n"
                    f"Strategic Priorities:\n"
                    + "\n".join(f"- {p}" for p in priorities)
                )

            mtime = 0.0
            has_sep = "/" in raw_content or "\\" in raw_content
            is_path_like = (
                len(raw_content) < 300
                and "\n" not in raw_content
                and "\0" not in raw_content
                and (
                    any(raw_content.endswith(ext) for ext in (".txt", ".md", ".json", ".yaml", ".yml"))
                    or has_sep
                )
            )
            if is_path_like:
                p = Path(raw_content)
                if p.is_file():
                    mtime = p.stat().st_mtime
                    raw_content = p.read_text(encoding="utf-8").strip()
                elif has_sep:
                    raise FileNotFoundError(f"Briefing file not found: {raw_content}")

            manual_cache_key = hashlib.sha256(
                f"MANUAL::{company_name}::{target_role}::{mtime}::{raw_content}::{priorities}".encode("utf-8")
            ).hexdigest()

            if not force_fresh:
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
                                strategic_priorities=tuple(cached.get("strategic_priorities", priorities)),
                                is_verified=bool(cached.get("is_verified", True)),
                                metadata=dict(cached.get("metadata", {})),
                            )
                        cls._cache.pop(manual_cache_key, None)

            clean_brief, receipt = _sanitize_briefing_content(raw_content, trace_id=trace_id)
            extracted_from_raw = False
            if not priorities and clean_brief:
                from apps_lic.integrations.research_boundary_policy import _extract_priorities_from_text

                priorities = tuple(_extract_priorities_from_text(clean_brief))
                extracted_from_raw = bool(priorities)
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
                    "source": "RAW_TEXT_EXTRACTION" if extracted_from_raw else "manual_fixture",
                    "extraction_mode": "RAW_TEXT_EXTRACTION" if extracted_from_raw else "EXPLICIT_FIXTURE",
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

        cache_key = hashlib.sha256(
            f"{company_name}::{target_role}::{job_description_text}".encode("utf-8")
        ).hexdigest()

        # PATH B: Cache Hit with TTL Freshness Verification (In-memory + Persisted Artifacts)
        if not force_fresh:
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

            disk_hit = cls._load_from_shared_disk(cache_key)
            if disk_hit is not None:
                cls._save_to_cache(cache_key, disk_hit)
                return SealedBriefingResolution(
                    briefing_text=disk_hit["briefing_text"],
                    digest=disk_hit["digest"],
                    resolution_source="CACHE_HIT",
                    company_name=company_name,
                    target_role=target_role,
                    confidence_score=float(disk_hit.get("confidence_score", 1.0)),
                    evidence_count=int(disk_hit.get("evidence_count", 1)),
                    airlock_sanitized=bool(disk_hit.get("airlock_sanitized", True)),
                    strategic_priorities=tuple(disk_hit.get("strategic_priorities", ())),
                    is_verified=True,
                    metadata={"cache_key": cache_key, "cached_at": disk_hit["timestamp"], "reused_from_shared_disk": True},
                )

            if artifact_runs_root is not None:
                from apps_lic.integrations.apps_research_bridge import _find_valid_persisted_artifact_bundle

                persisted, _ = _find_valid_persisted_artifact_bundle(
                    artifact_runs_root=artifact_runs_root,
                    company_name=company_name,
                    job_title=target_role,
                    freshness_ttl_seconds=cls.DEFAULT_CACHE_TTL_SECONDS,
                )
                if persisted is not None and persisted.is_verified and not persisted.is_blocked:
                    clean_brief, receipt = _sanitize_briefing_content(
                        persisted.company_brief_text, trace_id=trace_id
                    )
                    priorities = tuple(persisted.strategic_priorities)
                    res = SealedBriefingResolution(
                        briefing_text=clean_brief,
                        digest=receipt.clean_digest,
                        resolution_source="PERSISTED_ARTIFACT",
                        company_name=company_name,
                        target_role=target_role,
                        confidence_score=persisted.confidence_score,
                        evidence_count=len(persisted.evidence_items),
                        airlock_sanitized=receipt.sanitized,
                        strategic_priorities=priorities,
                        research_artifact_dir=persisted.research_artifact_dir,
                        briefing_artifact_path=persisted.briefing_artifact_path,
                        is_verified=True,
                        metadata={
                            "signals_flagged": list(receipt.injection_signals_detected),
                            "reused_from_disk": True,
                            "cache_key": cache_key,
                        },
                    )
                    cls._save_to_cache(
                        cache_key,
                        {
                            "briefing_text": clean_brief,
                            "digest": receipt.clean_digest,
                            "confidence_score": persisted.confidence_score,
                            "evidence_count": len(persisted.evidence_items),
                            "airlock_sanitized": receipt.sanitized,
                            "strategic_priorities": priorities,
                            "research_artifact_dir": persisted.research_artifact_dir,
                            "briefing_artifact_path": persisted.briefing_artifact_path,
                            "is_verified": True,
                        },
                    )
                    return res

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
                force_fresh=force_fresh,
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
                ev_count = int(dispatch_res.research_evidence_count)
                ev_items = [str(item.get("label") or item.get("source_id") or "") for item in dispatch_res.evidence_lineage if isinstance(item, dict)]
                cls._save_to_cache(
                    cache_key,
                    {
                        "briefing_text": clean_brief,
                        "digest": receipt.clean_digest,
                        "confidence_score": dispatch_res.confidence_score,
                        "evidence_count": ev_count,
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
                    evidence_count=ev_count,
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
                        "evidence_items": ev_items or list(priorities),
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


__all__ = ["GovernedBriefingResolver"]
