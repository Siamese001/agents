"""Retrieval caching, top-k capping, and frozen-allocation helpers for C0 runtime."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import Any

_COLLECTION_SCAN_CACHE: dict[tuple[str, int], dict[str, Any]] = {}

_SECTION_EMBEDDING_TOP_K_CAPS: dict[str, int] = {
    "executive_summary": 96,
    "headline": 96,
    "competencies": 160,
}


def resolve_effective_section_id_filter(
    section_id_filter: str | None,
    section_profile: Any,
) -> str | None:
    if not section_id_filter:
        return None
    resolved_sid = section_profile.resolve_section_id(section_id_filter)
    known_sids = {str(s.get("section_id") or "") for s in section_profile.get_sections()}
    if section_id_filter in known_sids or resolved_sid in known_sids:
        return section_id_filter
    return None


def get_or_scan_fact_vectors_collection(
    *,
    chroma_path: str,
    collection: Any,
    count: int,
    limit: int,
    metadata_counter_fn: Any,
) -> dict[str, Any]:
    cache_key = (str(Path(chroma_path).resolve()), count)
    cached_scan = _COLLECTION_SCAN_CACHE.get(cache_key)
    if cached_scan is not None:
        return cached_scan
    metadata = getattr(collection, "metadata", None)
    collection_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    rows = collection.get(limit=limit, include=["metadatas"]) if limit else {"metadatas": []}
    metas = [m for m in (rows.get("metadatas") or []) if isinstance(m, dict)]
    source_id_counts: Counter[str] = Counter()
    for meta in metas:
        sid = str(meta.get("source_document_id") or meta.get("candidate_fact_id") or "").strip()
        if sid:
            source_id_counts[sid] += 1
    cached_scan = {
        "collection_metadata": collection_metadata,
        "metas": metas,
        "source_id_counts": dict(sorted(source_id_counts.items())),
        "model_counts": metadata_counter_fn(metas, "embedding_model_id", fallback_key="embedding_model"),
        "dim_counts": metadata_counter_fn(metas, "embedding_dim", fallback_key="embedding_dimension"),
        "source_class_counts": metadata_counter_fn(metas, "source_class"),
        "tier_counts": metadata_counter_fn(metas, "tier"),
    }
    _COLLECTION_SCAN_CACHE[cache_key] = cached_scan
    return cached_scan


def resolve_section_embedding_top_k(authority_section_id: str, assertion_count: int) -> int:
    count = int(assertion_count)
    return min(count, _SECTION_EMBEDDING_TOP_K_CAPS.get(authority_section_id, count))


def compute_distinct_root_sections(
    slots: list[Any],
    eligible_by_slot: dict[str, list[dict[str, Any]]],
) -> set[str]:
    slot_counts_by_section = Counter(slot.section_id for slot in slots)
    distinct_root_sections: set[str] = set()
    for sec_id, sec_slot_count in slot_counts_by_section.items():
        if sec_id.endswith("_bullets"):
            distinct_root_sections.add(sec_id)
        elif sec_id in {"executive_summary", "headline"}:
            sec_roots = {
                str(r.get("root_id") or "")
                for s in slots
                if s.section_id == sec_id
                for r in eligible_by_slot.get(s.slot_id, ())
                if str(r.get("root_id") or "")
            }
            if len(sec_roots) >= sec_slot_count:
                distinct_root_sections.add(sec_id)
    return distinct_root_sections


def slot_priority_tier(slot: Any) -> int:
    if slot.section_id == "executive_summary":
        return 0
    if slot.section_id == "headline":
        return 1
    if slot.required_root_id:
        return 2
    if slot.section_id.endswith("_bullets"):
        return 3
    return 4


def compute_career_band_filter(
    *,
    section_id: str,
    sec_plan: dict[str, Any],
    grouped_section_buckets: dict[str, dict[str, list[dict[str, Any]]]],
) -> tuple[dict[str, float], dict[str, float], bool, set[str]]:
    employer_root_weights = {
        str(k): float(v) for k, v in dict(sec_plan.get("employer_root_weights") or {}).items()
    }
    employer_weights = {
        str(k): float(v)
        for k, v in dict(((sec_plan.get("graph_weight_profile") or {}).get("employer_weights")) or {}).items()
    }
    is_shared_top_section = section_id in {"executive_summary", "headline", "competencies"}
    primary_secondary_roots = {
        r_id
        for r_id, bkt in grouped_section_buckets.items()
        for r_row in bkt["root"]
        if r_row.get("authority_pass") is True
        and float(
            employer_root_weights.get(
                r_id,
                employer_weights.get(str(r_row.get("employer_lane") or ""), 1.0),
            )
        )
        >= 0.55
    }
    enforce_career_band = is_shared_top_section and len(primary_secondary_roots) >= 3
    return employer_root_weights, employer_weights, enforce_career_band, primary_secondary_roots


def compute_candidate_alignment_and_independence(
    *,
    root: dict[str, Any],
    skill: dict[str, Any],
    metric: dict[str, Any] | None,
    root_weight: float,
    citation_refs: list[str],
    skill_sources: list[str],
) -> tuple[float, float, float]:
    raw_proof = float(skill.get("proof_strength_raw") or 0.0)
    raw_align = (
        float(root.get("target_alignment_score") or 0.0)
        + float(skill.get("target_alignment_score") or 0.0)
        + float((metric or {}).get("target_alignment_score") or 0.0)
    ) / (3 if metric is not None else 2)
    proof_score = 1.0 if raw_proof >= 1.0 else raw_proof
    align_score = round(raw_align * root_weight, 6)
    indep_score = (
        1.0
        if citation_refs and skill_sources
        else round(min(len(set(citation_refs + skill_sources)), 4) / 4, 6)
    )
    return proof_score, align_score, indep_score


def build_targeting_provenance(
    *,
    target_role: str | None,
    jd_text: str | None,
    briefing_text: str | None,
) -> dict[str, str]:
    return {
        "target_role": str(target_role or "").strip(),
        "jd_sha256": hashlib.sha256(str(jd_text or "").encode("utf-8")).hexdigest() if jd_text else "",
        "briefing_sha256": hashlib.sha256(str(briefing_text or "").encode("utf-8")).hexdigest() if briefing_text else "",
    }


def build_frozen_competencies_proof_payload(
    selected_graph_plan: dict[str, Any],
    *,
    graph_ref: str,
) -> dict[str, Any]:
    return {
        "graph_source": graph_ref,
        "selection_method": str(
            selected_graph_plan.get("selection_method") or "frozen_whole_resume_fact_allocation"
        ),
        "selected_skill_rows": list(selected_graph_plan.get("selected_skills") or []),
        "selected_tracks": list(selected_graph_plan.get("selected_tracks") or []),
        "selected_skill_count_by_track": dict(
            selected_graph_plan.get("selected_skill_count_by_track") or {}
        ),
        "selected_fact_count_by_track": dict(
            selected_graph_plan.get("selected_fact_count_by_track") or {}
        ),
        "legacy_broad_skills_ledger_path": None,
        "track_expansion": {
            "c03_graph_bound_status": "BOUND",
            "c03_graph_hop_paths_count": len(
                selected_graph_plan.get("allocation_assignments")
                or selected_graph_plan.get("facts")
                or []
            ),
            "tracks_with_facts": list(selected_graph_plan.get("selected_tracks") or []),
        },
        "track_weighted_expansion_ref": str(selected_graph_plan.get("allocation_plan_ref") or ""),
        "graph_hop_paths_sample": list(
            (selected_graph_plan.get("allocation_assignments") or [])[:5]
        ),
    }
