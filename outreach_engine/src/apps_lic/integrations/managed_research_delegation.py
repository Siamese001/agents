"""Managed apps_research delegation for outreach_engine briefing.

Provides governed lifecycle delegation matching resume_graph_engine:
- Formal Request / Response contract
- Cryptographic artifact integrity and digest verification
- Audit stage receipt generation
- Fail-closed security boundaries
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from apps_lic.integrations.apps_research_bridge import ResearchResult


class ResearchFailureReason(str, Enum):
    APPS_RESEARCH_FAILED = "APPS_RESEARCH_FAILED"
    APPS_RESEARCH_EMPTY = "APPS_RESEARCH_EMPTY"
    APPS_RESEARCH_BLOCKED = "APPS_RESEARCH_BLOCKED"
    APPS_RESEARCH_STALE = "APPS_RESEARCH_STALE"
    APPS_RESEARCH_WEAK_SUPPORT = "APPS_RESEARCH_WEAK_SUPPORT"
    APPS_RESEARCH_ARTIFACT_MISSING = "APPS_RESEARCH_ARTIFACT_MISSING"


@dataclass(frozen=True)
class RequestForOutreachBriefing:
    request_id: str
    run_id: str
    trace_id: str
    company_name: str
    job_title: str
    research_authorized: bool = True
    tenant_id: str = "default"
    research_capability_ref: str = "apps_research.v1"
    freshness_ttl_days: int = 7
    min_confidence_threshold: float = 0.60
    job_description_ref: str = ""
    job_description_text: str = ""
    artifact_runs_root: Path | None = None


@dataclass(frozen=True)
class OutreachBriefingReady:
    request_id: str
    run_id: str
    trace_id: str
    briefing_text: str
    research_run_id: str
    research_evidence_count: int
    confidence_score: float
    strategic_priorities: tuple[str, ...]
    research_artifact_dir: str
    result_hash: str
    evidence_lineage: tuple[dict[str, Any], ...]
    apps_research_handoff_envelope: dict[str, Any]
    dispatch_duration_ms: float
    research_briefing_path: str = ""
    brief_sha256: str = ""
    result_metadata_digest: str = ""
    bundle_manifest_digest: str = ""
    resolution_source: str = "WEB_RESEARCH"


@dataclass(frozen=True)
class ResearchDispatchFailure:
    request_id: str
    run_id: str
    trace_id: str
    r5_reason_code: str
    detail: str
    dispatch_duration_ms: float


def _utc_ms() -> float:
    return time.time() * 1000.0


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _validate_persisted_research_artifacts(
    result: ResearchResult,
) -> tuple[bool, str, dict[str, str]]:
    """Verify that all 6 canonical producer artifacts exist and hashes bind exactly."""
    raw_dir = str(result.research_artifact_dir or "").strip()
    if not raw_dir:
        return False, "missing research_artifact_dir", {}
    run_dir = Path(raw_dir)
    if not run_dir.is_dir():
        return False, f"research_artifact_dir is not a directory: {raw_dir}", {}
    raw_brief = str(result.briefing_artifact_path or "").strip()
    if not raw_brief:
        return False, "missing briefing_artifact_path", {}
    briefing_path = Path(raw_brief)
    company_brief_path = run_dir / "company_brief.json"
    metadata_path = run_dir / "run_metadata.json"
    handoff_v2_path = run_dir / "apps_research_apps_rg_handoff_v2.json"
    commit_manifest_path = run_dir / "bundle_commit_manifest.json"
    u0_receipt_path = run_dir / "apps_research_u0_receipt.json"

    required = (
        briefing_path,
        company_brief_path,
        metadata_path,
        handoff_v2_path,
        commit_manifest_path,
        u0_receipt_path,
    )
    for path in required:
        if not _is_within(path, run_dir):
            return False, f"producer artifact escapes research_artifact_dir: {path}", {}
        if not path.is_file() or path.stat().st_size <= 0:
            return False, f"missing persisted apps_research artifact: {path}", {}

    try:
        persisted_text = briefing_path.read_text(encoding="utf-8").strip()
        persisted_handoff = json.loads(handoff_v2_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable persisted apps_research artifact: {type(exc).__name__}", {}

    if persisted_text != str(result.company_brief_text or "").strip():
        return False, "persisted briefing text does not match bridge result", {}
    if not isinstance(persisted_handoff, dict):
        return False, "persisted apps_research handoff v2 is not an object", {}
    if persisted_handoff.get("schema_version") != "apps_research.apps_rg_handoff.v2":
        return False, "persisted apps_research handoff is not v2", {}
    if persisted_handoff != (result.apps_research_handoff_envelope or {}):
        return False, "bridge handoff differs from persisted producer manifest", {}

    exact_brief_sha = "sha256:" + hashlib.sha256(briefing_path.read_bytes()).hexdigest()
    identity = persisted_handoff.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    if identity.get("brief_sha256") and identity.get("brief_sha256") != exact_brief_sha:
        return False, "persisted apps_research briefing digest mismatch", {}

    metadata_sha = "sha256:" + hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    manifest_sha = "sha256:" + hashlib.sha256(handoff_v2_path.read_bytes()).hexdigest()

    if result.brief_sha256 and result.brief_sha256 != exact_brief_sha:
        return False, "bridge brief_sha256 differs from committed bytes", {}
    if result.result_metadata_digest and result.result_metadata_digest != metadata_sha:
        return False, "bridge result_metadata_digest differs from committed bytes", {}
    if result.bundle_manifest_digest and result.bundle_manifest_digest != manifest_sha:
        return False, "bridge bundle_manifest_digest differs from committed bytes", {}

    return True, "ok", {
        "run_dir": str(run_dir.resolve()),
        "briefing_path": str(briefing_path.resolve()),
        "company_brief_path": str(company_brief_path.resolve()),
        "envelope_path": str(handoff_v2_path.resolve()),
        "metadata_path": str(metadata_path.resolve()),
        "handoff_v2_path": str(handoff_v2_path.resolve()),
        "commit_manifest_path": str(commit_manifest_path.resolve()),
        "u0_receipt_path": str(u0_receipt_path.resolve()),
    }


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
        research_result = bridge.fetch(
            company_name=request.company_name,
            job_title=request.job_title,
            capability_ref=request.research_capability_ref,
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            job_description_ref=request.job_description_ref,
            job_description_text=request.job_description_text,
        )
    except Exception as exc:  # noqa: BLE001
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_FAILED.value,
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
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_BLOCKED.value,
            detail=research_result.block_reason or "blocked",
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

    if research_result.confidence_score < request.min_confidence_threshold:
        return ResearchDispatchFailure(
            request_id=request.request_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            r5_reason_code=ResearchFailureReason.APPS_RESEARCH_WEAK_SUPPORT.value,
            detail=(
                f"confidence_score={research_result.confidence_score:.3f} "
                f"below threshold={request.min_confidence_threshold:.3f}"
            ),
            dispatch_duration_ms=_utc_ms() - t_start,
        )

    # Validate persisted producer artifacts if artifact persistence was expected
    if research_result.research_artifact_dir:
        artifacts_valid, artifact_detail, artifact_refs = _validate_persisted_research_artifacts(
            research_result
        )
        if not artifacts_valid:
            return ResearchDispatchFailure(
                request_id=request.request_id,
                run_id=request.run_id,
                trace_id=request.trace_id,
                r5_reason_code=ResearchFailureReason.APPS_RESEARCH_ARTIFACT_MISSING.value,
                detail=artifact_detail,
                dispatch_duration_ms=_utc_ms() - t_start,
            )

    # Emit consumer stage receipts if consumer_artifact_dir is supplied
    if consumer_artifact_dir is not None:
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
            "confidence_score": research_result.confidence_score,
            "evidence_count": len(research_result.evidence_items),
            "research_artifact_dir": research_result.research_artifact_dir,
            "research_briefing_path": research_result.briefing_artifact_path,
        }
        (c_dir / "research_bridge_response.json").write_text(
            json.dumps(resp_receipt, indent=2) + "\n", encoding="utf-8"
        )

        if research_result.briefing_artifact_path and Path(research_result.briefing_artifact_path).is_file():
            delegated_brief_path = c_dir / "delegated_briefing.md"
            shutil.copyfile(research_result.briefing_artifact_path, delegated_brief_path)

    lineage = tuple(
        {
            "source_id": ev.source_id,
            "label": ev.label,
            "uri": ev.uri,
            "source_type": ev.source_type,
            "field_ref": ev.field_ref,
            "confidence": ev.confidence,
        }
        for ev in research_result.evidence_items
    )

    resolution_source = getattr(research_result, "resolution_source", "WEB_RESEARCH")

    return OutreachBriefingReady(
        request_id=request.request_id,
        run_id=request.run_id,
        trace_id=request.trace_id,
        briefing_text=research_result.company_brief_text,
        research_run_id=research_result.run_id,
        research_evidence_count=len(research_result.evidence_items),
        confidence_score=research_result.confidence_score,
        strategic_priorities=research_result.strategic_priorities,
        research_artifact_dir=research_result.research_artifact_dir,
        result_hash=research_result.result_metadata_digest or research_result.brief_sha256,
        evidence_lineage=lineage,
        apps_research_handoff_envelope=research_result.apps_research_handoff_envelope or {},
        dispatch_duration_ms=_utc_ms() - t_start,
        research_briefing_path=research_result.briefing_artifact_path,
        brief_sha256=research_result.brief_sha256,
        result_metadata_digest=research_result.result_metadata_digest,
        bundle_manifest_digest=research_result.bundle_manifest_digest,
        resolution_source=resolution_source,
    )


__all__ = [
    "OutreachBriefingReady",
    "RequestForOutreachBriefing",
    "ResearchDispatchFailure",
    "ResearchFailureReason",
    "dispatch_outreach_research_briefing",
]
