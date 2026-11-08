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
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from apps_lic.integrations.apps_research_bridge import ResearchResult

_log = logging.getLogger(__name__)


class ResearchFailureReason(str, Enum):
    APPS_RESEARCH_FAILED = "APPS_RESEARCH_FAILED"
    APPS_RESEARCH_EMPTY = "APPS_RESEARCH_EMPTY"
    APPS_RESEARCH_BLOCKED = "APPS_RESEARCH_BLOCKED"
    APPS_RESEARCH_STALE = "APPS_RESEARCH_STALE"
    APPS_RESEARCH_WEAK_SUPPORT = "APPS_RESEARCH_WEAK_SUPPORT"
    APPS_RESEARCH_ARTIFACT_MISSING = "APPS_RESEARCH_ARTIFACT_MISSING"
    APPS_RESEARCH_TIMEOUT = "APPS_RESEARCH_TIMEOUT"
    APPS_RESEARCH_COST_LIMIT_EXCEEDED = "APPS_RESEARCH_COST_LIMIT_EXCEEDED"


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
    require_evidence: bool = False
    force_fresh: bool = False
    timeout_seconds: float = 30.0
    max_retries: int = 2
    cost_limit_usd: float | None = None


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
    request: RequestForOutreachBriefing | None = None,
) -> tuple[bool, str, dict[str, str]]:
    """Verify that all authentic canonical producer artifacts exist, bind to execution, and pass verification."""
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
        persisted_company_brief = json.loads(company_brief_path.read_text(encoding="utf-8"))
        persisted_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
        persisted_handoff = json.loads(handoff_v2_path.read_text(encoding="utf-8"))
        commit_manifest = json.loads(commit_manifest_path.read_text(encoding="utf-8"))
        u0_receipt = json.loads(u0_receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable persisted apps_research artifact: {type(exc).__name__}", {}

    if not persisted_text:
        return False, "persisted briefing text is empty", {}
    if persisted_text != str(result.company_brief_text or "").strip():
        return False, "persisted briefing text does not match bridge result", {}
    if not isinstance(persisted_handoff, dict):
        return False, "persisted apps_research handoff v2 is not an object", {}
    if not isinstance(commit_manifest, dict):
        return False, "bundle_commit_manifest is not an object", {}
    if not isinstance(u0_receipt, dict):
        return False, "apps_research_u0_receipt is not an object", {}
    if not isinstance(persisted_meta, dict):
        return False, "run_metadata is not an object", {}
    if not isinstance(persisted_company_brief, dict):
        return False, "company_brief is not an object", {}

    # 1. Authentic U0 Receipt Validation
    if u0_receipt.get("schema_version") != "apps_research.u0_receipt.v1":
        return False, f"apps_research_u0_receipt schema_version is not apps_research.u0_receipt.v1 (got {u0_receipt.get('schema_version')})", {}
    if u0_receipt.get("status") != "PASS":
        return False, f"apps_research_u0_receipt status is not PASS (got {u0_receipt.get('status')})", {}
    if u0_receipt.get("authority_contract_id") != "apps_research_rg_e2e_authority":
        return False, f"apps_research_u0_receipt authority_contract_id invalid: {u0_receipt.get('authority_contract_id')}", {}
    auth_receipt = u0_receipt.get("authority_validation_receipt")
    if not isinstance(auth_receipt, dict) or auth_receipt.get("passed") is not True or auth_receipt.get("allowed") is not True:
        return False, "apps_research_u0_receipt missing verified authority_validation_receipt", {}
    reflection = u0_receipt.get("reflection_receipt")
    if not isinstance(reflection, dict) or reflection.get("legacy_authority_scan_passed") is not True:
        return False, "apps_research_u0_receipt missing verified reflection_receipt", {}
    if not u0_receipt.get("raw_input_sha256") or not u0_receipt.get("normalized_input_sha256"):
        return False, "apps_research_u0_receipt missing input digests", {}

    exact_u0_sha = "sha256:" + hashlib.sha256(u0_receipt_path.read_bytes()).hexdigest()

    # 2. Authentic Bundle Commit Manifest Validation
    if commit_manifest.get("schema_version") != "apps_research.apps_rg_bundle_commit_manifest.v1":
        return False, f"bundle_commit_manifest schema_version is not apps_research.apps_rg_bundle_commit_manifest.v1 (got {commit_manifest.get('schema_version')})", {}
    if commit_manifest.get("status") != "COMMITTED":
        return False, f"bundle_commit_manifest status is not COMMITTED (got {commit_manifest.get('status')})", {}
    if commit_manifest.get("authority_contract_id") != "apps_research_rg_e2e_authority":
        return False, f"bundle_commit_manifest authority_contract_id invalid: {commit_manifest.get('authority_contract_id')}", {}
    if commit_manifest.get("u0_receipt_sha256") and commit_manifest.get("u0_receipt_sha256") != exact_u0_sha:
        return False, "bundle_commit_manifest u0_receipt_sha256 mismatch with persisted u0 receipt", {}

    # 3. Authentic Handoff v2 Envelope Validation
    if persisted_handoff.get("schema_version") != "apps_research.apps_rg_handoff.v2":
        return False, f"persisted apps_research handoff is not v2 (got {persisted_handoff.get('schema_version')})", {}
    if persisted_handoff.get("authority_contract_id") != "apps_research_rg_e2e_authority":
        return False, f"persisted apps_research handoff authority_contract_id invalid: {persisted_handoff.get('authority_contract_id')}", {}
    if persisted_handoff != (result.apps_research_handoff_envelope or {}):
        return False, "bridge handoff differs from persisted producer manifest", {}

    gate_receipts = persisted_handoff.get("mandatory_gate_receipts")
    if not isinstance(gate_receipts, dict):
        return False, "persisted apps_research handoff missing mandatory_gate_receipts", {}
    expected_gates = {"G5", "G6", "G7", "G21", "G24", "G26"}
    if set(gate_receipts.keys()) != expected_gates:
        return False, f"mandatory_gate_receipts does not match expected gates: {set(gate_receipts.keys())} != {expected_gates}", {}
    for gid in expected_gates:
        gr = gate_receipts.get(gid)
        if not isinstance(gr, dict) or gr.get("status") != "PASS":
            return False, f"mandatory gate {gid} status is not PASS: {gr}", {}

    exit_auth = persisted_handoff.get("exit_authorization")
    if not isinstance(exit_auth, dict):
        return False, "persisted apps_research handoff missing exit_authorization", {}
    if exit_auth.get("x3_code") != "X3D_ALLOW_FINISH":
        return False, f"exit authorization x3_code is not X3D_ALLOW_FINISH (got {exit_auth.get('x3_code')})", {}

    producer = persisted_handoff.get("producer")
    if not isinstance(producer, dict) or producer.get("producer_app_id") != "apps_research" or not producer.get("attestation_sha256"):
        return False, "persisted apps_research handoff missing valid producer attestation", {}

    # 4. Cryptographic Digests Binding
    exact_brief_sha = "sha256:" + hashlib.sha256(briefing_path.read_bytes()).hexdigest()
    metadata_sha = "sha256:" + hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    manifest_sha = "sha256:" + hashlib.sha256(handoff_v2_path.read_bytes()).hexdigest()

    if result.brief_sha256 and result.brief_sha256 != exact_brief_sha:
        return False, "bridge brief_sha256 differs from committed bytes", {}
    if result.result_metadata_digest and result.result_metadata_digest != metadata_sha:
        return False, "bridge result_metadata_digest differs from committed bytes", {}
    if result.bundle_manifest_digest and result.bundle_manifest_digest != manifest_sha:
        return False, "bridge bundle_manifest_digest differs from committed bytes", {}

    identity = persisted_handoff.get("identity")
    if not isinstance(identity, dict):
        return False, "persisted apps_research handoff missing identity object", {}
    if identity.get("brief_sha256") and identity.get("brief_sha256") != exact_brief_sha:
        return False, "persisted apps_research briefing digest mismatch", {}

    # 5. Exact Execution Identity Binding
    if request is not None:
        target_co = str(identity.get("target_company") or identity.get("company_name") or "").strip().lower()
        req_co = str(request.company_name or "").strip().lower()
        if req_co and target_co and req_co != target_co:
            return False, f"research identity company mismatch: request={req_co!r} vs persisted={target_co!r}", {}

        def _norm_role(val: str) -> str:
            cleaned = re.sub(r"[^a-z0-9]+", " ", val.lower())
            tokens = [t for t in cleaned.split() if t not in ("of", "the", "and", "for", "in", "at", "to")]
            return " ".join(tokens)

        target_role = str(identity.get("target_role") or "").strip()
        req_role = str(request.job_title or "").strip()
        if req_role and target_role and _norm_role(req_role) != _norm_role(target_role):
            return False, f"research identity role mismatch: request={req_role!r} vs persisted={target_role!r}", {}

        def _norm_trace(val: str) -> str:
            parts = str(val or "").strip().split(":")
            return parts[-1] if len(parts) >= 3 and parts[0] == "bridge" else str(val or "").strip()

        persisted_run_id = str(identity.get("child_run_id") or identity.get("run_id") or identity.get("parent_run_id") or "").strip()
        persisted_trace = _norm_trace(identity.get("trace_root") or identity.get("trace_id") or "")
        u0_run_id = str(u0_receipt.get("child_run_id") or u0_receipt.get("parent_run_id") or u0_receipt.get("run_id") or "").strip()
        u0_trace = _norm_trace(u0_receipt.get("trace_root") or "")
        res_trace = _norm_trace(result.trace_id)

        # result run_id and trace_id must always match persisted identity
        if result.run_id and persisted_run_id and result.run_id != persisted_run_id:
            return False, f"research identity run_id mismatch: result={result.run_id!r} vs persisted={persisted_run_id!r}", {}
        if res_trace and persisted_trace and res_trace != persisted_trace:
            return False, f"research identity trace mismatch: result={result.trace_id!r} vs persisted={persisted_trace!r}", {}
        if result.run_id and u0_run_id and result.run_id != u0_run_id:
            return False, f"u0 receipt run_id mismatch: result={result.run_id!r} vs u0={u0_run_id!r}", {}
        if res_trace and u0_trace and res_trace != u0_trace:
            return False, f"u0 receipt trace mismatch: result={result.trace_id!r} vs u0={u0_trace!r}", {}

        # If not reused (fresh live dispatch), request execution identity must bind to persisted producer artifacts
        is_reused = getattr(result, "resolution_source", "") == "PERSISTED_ARTIFACT"
        if not is_reused:
            req_run_id = str(request.run_id or "").strip()
            if req_run_id and persisted_run_id and req_run_id != persisted_run_id:
                return False, f"research identity run_id mismatch: request={req_run_id!r} vs persisted={persisted_run_id!r}", {}

            req_trace = _norm_trace(request.trace_id or "")
            if req_trace and persisted_trace and req_trace != persisted_trace:
                return False, f"research identity trace mismatch: request={req_trace!r} vs persisted={persisted_trace!r}", {}

            if req_run_id and u0_run_id and req_run_id != u0_run_id:
                return False, f"u0 receipt run_id mismatch: request={req_run_id!r} vs u0={u0_run_id!r}", {}

            if req_trace and u0_trace and req_trace != u0_trace:
                return False, f"u0 receipt trace mismatch: request={req_trace!r} vs u0={u0_trace!r}", {}

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
        import inspect
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

    # Validate evidence items source integrity
    for ev in research_result.evidence_items:
        ev_uri = getattr(ev, "uri", "") or ""
        if not str(ev_uri).strip():
            return ResearchDispatchFailure(
                request_id=request.request_id,
                run_id=request.run_id,
                trace_id=request.trace_id,
                r5_reason_code=ResearchFailureReason.APPS_RESEARCH_FAILED.value,
                detail=f"Evidence item {getattr(ev, 'source_id', 'unknown')} lacks source URI",
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

    # Validate persisted producer artifacts if artifact persistence was expected or present
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

        artifacts_valid, artifact_detail, artifact_refs = _validate_persisted_research_artifacts(
            research_result, request=request
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

        if research_result.briefing_artifact_path:
            try:
                b_path = Path(research_result.briefing_artifact_path).resolve()
                if b_path.is_file():
                    delegated_brief_path = c_dir / "delegated_briefing.md"
                    shutil.copyfile(b_path, delegated_brief_path)
            except (OSError, ValueError) as exc:
                _log.warning(
                    "Could not copy briefing artifact from %s: %s",
                    research_result.briefing_artifact_path,
                    exc,
                )

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


execute_managed_research = dispatch_outreach_research_briefing

__all__ = [
    "OutreachBriefingReady",
    "RequestForOutreachBriefing",
    "ResearchDispatchFailure",
    "ResearchFailureReason",
    "dispatch_outreach_research_briefing",
    "execute_managed_research",
]

