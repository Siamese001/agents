"""Translation, persistence, and hermetic fallback helpers for AppsResearchBridge."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from apps_lic.integrations.research_boundary_policy import _extract_priorities_from_text
from apps_lic.integrations.research_bridge_pkg.models import EvidenceItem, ResearchResult

_log = logging.getLogger(__name__)


def translate_and_persist_research_result(
    *,
    artifact_runs_root: Path | None,
    raw: Any,
    run_id: str,
    trace_id: str,
    request_id: str,
    t_start: float,
    company_name: str,
    job_title: str,
    job_description_text: str = "",
    resolution_source: str = "WEB_RESEARCH",
) -> ResearchResult:
    """Translate raw apps_research response into ResearchResult with v2 artifact persistence."""
    brief_text = str(getattr(raw, "company_brief_text", "") or "").strip()
    priorities = getattr(raw, "strategic_priorities", None) or _extract_priorities_from_text(brief_text)
    brief_bytes = (brief_text + "\n").encode("utf-8")
    brief_sha = "sha256:" + hashlib.sha256(brief_bytes).hexdigest()

    evidence_items = tuple(
        EvidenceItem(
            source_id=str(getattr(ev, "source_id", f"ev-{i}")),
            label=str(getattr(ev, "label", f"evidence_{i}")),
            uri=str(getattr(ev, "uri", getattr(ev, "source_uri", "apps_research://briefing"))),
            source_type=str(getattr(ev, "source_type", "company_brief")),
            field_ref=str(getattr(ev, "field_ref", "company_brief")),
            confidence=float(getattr(ev, "confidence", 0.0)),
        )
        for i, ev in enumerate(getattr(raw, "evidence_items", None) or ())
    )

    confidence = float(getattr(raw, "confidence_score", 0.0) or 0.0)
    is_stale = bool(getattr(raw, "is_stale", False))
    is_verified = (
        resolution_source in ("WEB_RESEARCH", "CANONICAL_FIXTURE")
        and bool(brief_text)
        and not is_stale
        and confidence > 0.0
    )

    research_artifact_dir = str(getattr(raw, "research_artifact_dir", "") or "").strip()
    briefing_path_str = str(getattr(raw, "briefing_artifact_path", "") or "").strip()
    metadata_digest = str(getattr(raw, "result_metadata_digest", "") or "").strip()
    manifest_digest = str(getattr(raw, "bundle_manifest_digest", "") or "").strip()
    envelope = getattr(raw, "apps_research_handoff_envelope", None) or {}
    if getattr(raw, "brief_sha256", None):
        brief_sha = str(raw.brief_sha256)

    if not research_artifact_dir and artifact_runs_root is not None:
        try:
            jd_text = str(job_description_text or "")
            eff_role = str(job_title or "Technology Leadership").strip()
            try:
                from apps_research.integrations.apps_rg_handoff import persist_apps_rg_targeting_brief_artifacts
                artifact_bundle = persist_apps_rg_targeting_brief_artifacts(
                    record=raw, target_company=company_name, target_role=eff_role, jd_text=jd_text,
                    runs_root=artifact_runs_root, mode="brief", depth_profile="COMPANY_BRIEF_STANDARD",
                )
            except ModuleNotFoundError:
                from apps_lic.integrations.research_bridge_support import persist_standalone_outreach_research_bundle
                artifact_bundle = persist_standalone_outreach_research_bundle(
                    record=raw, target_company=company_name, target_role=eff_role, jd_text=jd_text,
                    runs_root=artifact_runs_root,
                )

            research_artifact_dir = str(artifact_bundle.run_dir.resolve())
            briefing_path_str = str(artifact_bundle.briefing_path.resolve())
            compat_brief = artifact_bundle.run_dir / "company_brief.md"
            if not compat_brief.is_file() and artifact_bundle.briefing_path.is_file():
                compat_brief.write_bytes(artifact_bundle.briefing_path.read_bytes())
            cm_p, u0_p = artifact_bundle.run_dir / "bundle_commit_manifest.json", artifact_bundle.run_dir / "apps_research_u0_receipt.json"
            if cm_p.is_file() and u0_p.is_file():
                cm_d = json.loads(cm_p.read_text(encoding="utf-8"))
                if not cm_d.get("u0_receipt_sha256"):
                    cm_d["u0_receipt_sha256"] = "sha256:" + hashlib.sha256(u0_p.read_bytes()).hexdigest()
                    cm_p.write_text(json.dumps(cm_d, indent=2) + "\n", encoding="utf-8")
            metadata_digest = artifact_bundle.result_metadata_digest
            manifest_digest = artifact_bundle.bundle_manifest_digest
            brief_sha = artifact_bundle.brief_sha256
            envelope = artifact_bundle.envelope
            is_verified = True
        except Exception as exc:
            _log.warning("Authentic apps_research artifact persistence failed: %s", exc)
            return ResearchResult(
                run_id=run_id,
                trace_id=trace_id,
                request_id=request_id,
                is_blocked=True,
                block_reason=f"apps_research_artifact_persistence_failed:{exc}",
                is_stale=is_stale,
                evidence_items=evidence_items,
                confidence_score=confidence,
                brief_sha256="",
                company_brief_text="",
                strategic_priorities=(),
                fetch_duration_ms=time.time() * 1000.0 - t_start,
                audit_ref=trace_id,
                apps_research_handoff_envelope=None,
                research_artifact_dir="",
                briefing_artifact_path="",
                result_metadata_digest="",
                bundle_manifest_digest="",
                resolution_source=resolution_source,
                is_verified=False,
            )

    return ResearchResult(
        run_id=run_id,
        trace_id=trace_id,
        request_id=request_id,
        is_blocked=bool(getattr(raw, "is_blocked", False)),
        block_reason=str(getattr(raw, "block_reason", "") or ""),
        is_stale=is_stale,
        evidence_items=evidence_items,
        confidence_score=confidence,
        brief_sha256=brief_sha,
        company_brief_text=brief_text,
        strategic_priorities=tuple(priorities),
        fetch_duration_ms=time.time() * 1000.0 - t_start,
        audit_ref=trace_id,
        apps_research_handoff_envelope=envelope,
        research_artifact_dir=research_artifact_dir,
        briefing_artifact_path=briefing_path_str,
        result_metadata_digest=metadata_digest,
        bundle_manifest_digest=manifest_digest,
        resolution_source=resolution_source,
        is_verified=is_verified,
    )


def build_hermetic_fallback_result(
    *,
    artifact_runs_root: Path | None,
    company_name: str,
    job_title: str,
    job_description_text: str,
    req_id: str,
    r_id: str,
    bridge_trace_id: str,
    t_start: float,
) -> ResearchResult:
    """Build an explicitly unverified hermetic fallback ResearchResult."""
    priorities = _extract_priorities_from_text(job_description_text) if job_description_text else []
    brief_text = (
        f"# Research Briefing: {company_name}\n\n"
        f"## Strategic Mandate\n- Entity: {company_name}\n- Target Role: {job_title or 'Technology Leadership'}\n\n"
        f"## Status\nUnverified offline fallback brief for {company_name} - {job_title}\n\n"
        f"## Governance\n- Provenance: apps_research hermetic fallback (unverified)\n"
    )
    brief_bytes = (brief_text + "\n").encode("utf-8")
    brief_sha = "sha256:" + hashlib.sha256(brief_bytes).hexdigest()
    research_artifact_dir, briefing_path_str, metadata_digest, manifest_digest = "", "", "", ""
    envelope: dict[str, Any] = {}

    if artifact_runs_root is not None:
        clean_r_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", str(r_id or "run")).strip("./")
        if not clean_r_id:
            clean_r_id = f"run_{int(time.time())}"
        run_dir = (artifact_runs_root / clean_r_id).resolve()
        if not run_dir.is_relative_to(artifact_runs_root.resolve()):
            run_dir = artifact_runs_root / f"run_sanitized_{int(time.time())}"
        run_dir.mkdir(parents=True, exist_ok=True)
        briefing_file = run_dir / "company_brief.md"
        briefing_file.write_bytes(brief_bytes)
        (run_dir / "company_brief.json").write_text(
            json.dumps({"brief": brief_text, "status": "UNVERIFIED_FALLBACK"}, indent=2) + "\n",
            encoding="utf-8",
        )
        envelope = {
            "schema_version": "apps_research.apps_rg_handoff.v2",
            "identity": {"company_name": company_name, "brief_sha256": brief_sha},
            "status": "UNVERIFIED_FALLBACK",
            "confidence_score": 0.0,
            "never_treated_as_candidate_proof": True,
        }
        envelope_file = run_dir / "apps_research_apps_rg_handoff_v2.json"
        envelope_file.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        meta_file = run_dir / "run_metadata.json"
        meta_file.write_text(
            json.dumps({"status": "HERMETIC_FALLBACK", "is_verified": False, "confidence_score": 0.0}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        (run_dir / "bundle_commit_manifest.json").write_text(
            json.dumps({"status": "COMMITTED_UNVERIFIED"}, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        (run_dir / "apps_research_u0_receipt.json").write_text(
            json.dumps({"u0_status": "UNVERIFIED"}, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        metadata_digest = "sha256:" + hashlib.sha256(meta_file.read_bytes()).hexdigest()
        manifest_digest = "sha256:" + hashlib.sha256(envelope_file.read_bytes()).hexdigest()
        research_artifact_dir, briefing_path_str = str(run_dir.resolve()), str(briefing_file.resolve())

    return ResearchResult(
        run_id=r_id,
        trace_id=bridge_trace_id,
        request_id=req_id,
        is_blocked=False,
        block_reason="",
        is_stale=False,
        evidence_items=(),
        confidence_score=0.0,
        brief_sha256=brief_sha,
        company_brief_text=brief_text,
        strategic_priorities=tuple(priorities),
        fetch_duration_ms=time.time() * 1000.0 - t_start,
        audit_ref=bridge_trace_id,
        apps_research_handoff_envelope=envelope,
        research_artifact_dir=research_artifact_dir,
        briefing_artifact_path=briefing_path_str,
        result_metadata_digest=metadata_digest,
        bundle_manifest_digest=manifest_digest,
        resolution_source="HERMETIC_FALLBACK",
        is_verified=False,
    )
