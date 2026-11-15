"""Core ResearchResult data contract for apps_research_bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from infrastructure.types.research_handoff_contracts import EvidenceItem


@dataclass(frozen=True)
class ResearchResult:
    run_id: str
    trace_id: str
    request_id: str
    is_blocked: bool
    block_reason: str
    is_stale: bool
    evidence_items: tuple[EvidenceItem, ...]
    confidence_score: float
    brief_sha256: str
    company_brief_text: str
    strategic_priorities: tuple[str, ...]
    fetch_duration_ms: float
    audit_ref: str
    apps_research_handoff_envelope: dict[str, Any] | None = None
    research_artifact_dir: str = ""
    briefing_artifact_path: str = ""
    result_metadata_digest: str = ""
    bundle_manifest_digest: str = ""
    resolution_source: str = "WEB_RESEARCH"
    is_verified: bool = True
    never_treated_as_candidate_proof: bool = True
