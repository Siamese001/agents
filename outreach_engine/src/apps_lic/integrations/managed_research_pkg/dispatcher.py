"""Dispatcher execution for managed apps_research delegation."""

from __future__ import annotations

import inspect
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from apps_lic.integrations.apps_research_bridge import ResearchResult
from apps_lic.integrations.managed_research_pkg.contracts import (
    OutreachBriefingReady,
    RequestForOutreachBriefing,
    ResearchDispatchFailure,
    ResearchFailureReason,
    _utc_ms,
    _validate_persisted_research_artifacts,
)

_log = logging.getLogger(__name__)


def dispatch_outreach_research_briefing(
    request: RequestForOutreachBriefing,
    *,
    bridge: Any,
    consumer_artifact_dir: Path | None = None,
) -> OutreachBriefingReady | ResearchDispatchFailure:
    """Dispatch apps_research and admit only a validated, persisted bundle."""
    t_start = _utc_ms()
    if not request.research_authorized:
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_BLOCKED.value,
            detail="research_authorized=False",
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    try:
        fetch_kwargs: dict[str, Any] = {
            "company_name": request.company_name,
            "job_title": request.job_title,
            "capability_ref": request.research_capability_ref,
            "request_id": request.request_id,
            "run_id": request.run_id,
            "trace_id": request.trace_id,
            "job_description_ref": request.job_description_ref,
            "job_description_text": request.job_description_text,
        }
        sig = inspect.signature(bridge.fetch)
        for k in ("force_fresh", "timeout_seconds", "max_retries", "cost_limit_usd"):
            if k in sig.parameters:
                fetch_kwargs[k] = getattr(request, k)

        research_result = bridge.fetch(**fetch_kwargs)
    except TimeoutError as exc:
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_TIMEOUT.value,
            detail=f"TimeoutError: {exc}",
            dispatch_duration_ms=_utc_ms() - t_start,
        )
    except Exception as exc:  # noqa: BLE001
        reason_code = ResearchFailureReason.APPS_RESEARCH_FAILED.value
        exc_str = str(exc).lower()
        if "cost" in exc_str and "limit" in exc_str:
            reason_code = ResearchFailureReason.APPS_RESEARCH_COST_LIMIT_EXCEEDED.value
        elif "timeout" in exc_str:
            reason_code = ResearchFailureReason.APPS_RESEARCH_TIMEOUT.value
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=reason_code,
            detail=f"{type(exc).__name__}: {exc}",
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    if not isinstance(research_result, ResearchResult):
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_FAILED.value,
            detail="bridge returned unexpected type",
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    if research_result.is_blocked:
        reason_code = ResearchFailureReason.APPS_RESEARCH_BLOCKED.value
        b_reason = str(research_result.block_reason or "").upper()
        if "COST_LIMIT" in b_reason:
            reason_code = ResearchFailureReason.APPS_RESEARCH_COST_LIMIT_EXCEEDED.value
        elif "TIMEOUT" in b_reason:
            reason_code = ResearchFailureReason.APPS_RESEARCH_TIMEOUT.value
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=reason_code,
            detail=research_result.block_reason or "blocked",
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    if getattr(research_result, "is_stale", False):
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_STALE.value,
            detail="Research result is marked stale",
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    if not str(research_result.company_brief_text or "").strip():
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_EMPTY.value,
            detail="company_brief_text is empty",
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    if getattr(request, "require_evidence", False) and not research_result.evidence_items:
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_EMPTY.value,
            detail="zero evidence_items",
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    for ev in research_result.evidence_items:
        ev_uri = getattr(ev, "uri", "") or (ev.get("uri", "") if isinstance(ev, dict) else "")
        source_id = getattr(ev, "source_id", None) or (ev.get("source_id", "unknown") if isinstance(ev, dict) else "unknown")
        if not str(ev_uri).strip():
            return ResearchDispatchFailure(
                request_id=request.request_id,
                run_id=request.run_id,
                trace_id=request.trace_id,
                r5_reason_code=ResearchFailureReason.APPS_RESEARCH_FAILED.value,
                detail=f"Evidence item {source_id} lacks source URI",
                dispatch_duration_ms=_utc_ms() - t_start,
            )

    res_conf = float(research_result.confidence_score or 0.0) if research_result.confidence_score is not None else 0.0
    if res_conf < request.min_confidence_threshold:
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_WEAK_SUPPORT.value,
            detail=(
                f"confidence_score={res_conf:.3f} "
                f"below threshold={request.min_confidence_threshold:.3f}"
            ),
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    if request.artifact_runs_root and not research_result.research_artifact_dir:
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_ARTIFACT_MISSING.value,
            detail="missing research_artifact_dir",
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    if research_result.research_artifact_dir:
        ttl_seconds = max(1, request.freshness_ttl_days) * 86400.0
        meta_path = Path(research_result.research_artifact_dir) / "run_metadata.json"
        if meta_path.is_file():
            age_seconds = time.time() - meta_path.stat().st_mtime
            if age_seconds > ttl_seconds:
                return ResearchDispatchFailure(
                    request_id=request.request_id,
                    run_id=request.run_id,
                    trace_id=request.trace_id,
                    r5_reason_code=ResearchFailureReason.APPS_RESEARCH_STALE.value,
                    detail=f"Research artifact is stale (age={age_seconds / 86400.0:.1f}d > ttl={request.freshness_ttl_days}d)",
                    dispatch_duration_ms=_utc_ms() - t_start,
                )

        artifacts_valid, artifact_detail, _ = _validate_persisted_research_artifacts(
            research_result, request=request, bridge=bridge
        )
        if not artifacts_valid:
            reason_code = ResearchFailureReason.APPS_RESEARCH_ARTIFACT_MISSING.value
            if "stale" in artifact_detail.lower():
                reason_code = ResearchFailureReason.APPS_RESEARCH_STALE.value
            elif any(k in artifact_detail.lower() for k in ("blocked", "gate", "exit", "mismatch", "schema", "status", "contract")):
                reason_code = ResearchFailureReason.APPS_RESEARCH_BLOCKED.value
            return ResearchDispatchFailure(
                request_id=request.request_id,
                run_id=request.run_id,
                trace_id=request.trace_id,
                r5_reason_code=reason_code,
                detail=artifact_detail,
                dispatch_duration_ms=_utc_ms() - t_start,
            )

    if consumer_artifact_dir is not None:
        try:
            c_dir = Path(consumer_artifact_dir)
            c_dir.mkdir(parents=True, exist_ok=True)
            req_receipt = {
                "request_id": request.request_id,
                "run_id": request.run_id,
                "trace_id": request.trace_id,
                "company_name": request.company_name,
                "job_title": request.job_title,
                "research_capability_ref": request.research_capability_ref,
            }
            (c_dir / "research_bridge_request.json").write_text(
                json.dumps(req_receipt, indent=2) + "\n", encoding="utf-8"
            )
            resp_receipt = {
                "outcome": "OutreachBriefingReady",
                "research_run_id": research_result.run_id,
                "confidence_score": res_conf,
                "evidence_count": len(research_result.evidence_items),
                "research_artifact_dir": research_result.research_artifact_dir,
                "research_briefing_path": research_result.briefing_artifact_path,
            }
            (c_dir / "research_bridge_response.json").write_text(
                json.dumps(resp_receipt, indent=2) + "\n", encoding="utf-8"
            )
            if research_result.briefing_artifact_path:
                try:
                    b_path = Path(research_result.briefing_artifact_path).resolve()
                    if b_path.is_file():
                        shutil.copyfile(b_path, c_dir / "delegated_briefing.md")
                except (OSError, ValueError) as exc:
                    _log.warning("Could not copy briefing artifact from %s: %s", research_result.briefing_artifact_path, exc)
        except OSError as exc:
            _log.warning("Could not write consumer stage receipts to %s: %s", consumer_artifact_dir, exc)

    def _ev_dict(ev: Any) -> dict[str, Any]:
        g = lambda k, d="": getattr(ev, k, d) or (ev.get(k, d) if isinstance(ev, dict) else d)
        return {
            "source_id": g("source_id"), "label": g("label"), "uri": g("uri"),
            "source_type": g("source_type"), "field_ref": g("field_ref"),
            "confidence": getattr(ev, "confidence", 0.0) or (ev.get("confidence", 0.0) if isinstance(ev, dict) else 0.0),
        }

    lineage = tuple(_ev_dict(ev) for ev in research_result.evidence_items)
    resolution_source = getattr(research_result, "resolution_source", "WEB_RESEARCH")
    is_verified = bool(getattr(research_result, "is_verified", True))

    return OutreachBriefingReady(
        request_id=request.request_id, run_id=request.run_id, trace_id=request.trace_id,
        briefing_text=research_result.company_brief_text, research_run_id=research_result.run_id,
        research_evidence_count=len(research_result.evidence_items), confidence_score=res_conf,
        strategic_priorities=research_result.strategic_priorities,
        research_artifact_dir=research_result.research_artifact_dir,
        result_hash=research_result.result_metadata_digest or research_result.brief_sha256,
        evidence_lineage=lineage, apps_research_handoff_envelope=research_result.apps_research_handoff_envelope or {},
        dispatch_duration_ms=_utc_ms() - t_start, research_briefing_path=research_result.briefing_artifact_path,
        brief_sha256=research_result.brief_sha256, result_metadata_digest=research_result.result_metadata_digest,
        bundle_manifest_digest=research_result.bundle_manifest_digest, resolution_source=resolution_source,
        is_verified=is_verified,
    )


def execute_managed_research(
    request: RequestForOutreachBriefing,
    *,
    bridge: Any,
    consumer_artifact_dir: Path | None = None,
) -> OutreachBriefingReady | ResearchDispatchFailure:
    """Alias for dispatch_outreach_research_briefing."""
    return dispatch_outreach_research_briefing(
        request,
        bridge=bridge,
        consumer_artifact_dir=consumer_artifact_dir,
    )
