"""Cross-section graph and pillar coherence gates for cross-section X2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.runtime.aggregation.cross_section.models import (
    GRAPH_COHERENCE_MIN_ACTIVE_SECTIONS,
    GRAPH_COHERENCE_MIN_UNIQUE_SKILLS,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    VERDICT_WARN,
    CrossSectionGateResult,
    _PILLAR_COHERENCE_JACCARD_WARN_THRESHOLD,
    _PRIMARY_COHERENCE_SECTIONS,
    _collect_string_values,
    _collect_values_for_keys,
    _jaccard,
    _load_runtime_payload_for_section,
)

def build_cross_section_graph_coherence_receipt(
    *,
    repo: Path,
    final_resume_blob: dict[str, Any],
    sealed_index: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate C0.3 / role-episode graph use across generated sections."""
    from apps_rg.runtime.graph_skills_utilization_scorer import (
        build_graph_binding_materiality_summary,
    )

    sections = [s for s in (final_resume_blob.get("sections") or []) if isinstance(s, dict)]
    section_rows: list[dict[str, Any]] = []
    active_section_ids: set[str] = set()
    native_section_ids: set[str] = set()
    role_section_ids: set[str] = set()
    unique_skill_ids: set[str] = set()
    unique_fact_ids: set[str] = set()
    unique_bundle_ids: set[str] = set()
    materiality_warnings: list[dict[str, Any]] = []

    for sec in sections:
        if sec.get("section_kind") != "generated_lane":
            continue
        sid = str(sec.get("section_id") or "")
        if not sid:
            continue
        snap = sec.get("l2_output_snapshot") if isinstance(sec.get("l2_output_snapshot"), dict) else {}
        runtime_payload = _load_runtime_payload_for_section(
            repo=repo,
            sealed_index=sealed_index,
            section_id=sid,
        )
        meta = runtime_payload.get("proof_pool_metadata")
        if not isinstance(meta, dict):
            meta = snap.get("proof_pool_metadata") if isinstance(snap.get("proof_pool_metadata"), dict) else {}
        claim_ledger = snap.get("claim_ledger") if isinstance(snap.get("claim_ledger"), list) else []
        embedded_summary = (
            snap.get("graph_binding_materiality_summary")
            if isinstance(snap.get("graph_binding_materiality_summary"), Mapping)
            else None
        )
        summary = (
            dict(embedded_summary)
            if embedded_summary is not None
            else build_graph_binding_materiality_summary(
                section_id=sid,
                proof_pool_metadata=meta,
                candidate_output=snap,
                claim_ledger=claim_ledger,
                parsed_output=snap,
            )
        )
        if summary.get("status") == "NO_GRAPH_BINDING_METADATA":
            continue

        active_section_ids.add(sid)
        if summary.get("native_c03_active"):
            native_section_ids.add(sid)
        if summary.get("role_episode_active"):
            role_section_ids.add(sid)

        payloads = [snap, claim_ledger, summary]
        unique_skill_ids.update(
            _collect_values_for_keys(
                payloads,
                {
                    "claim_support_graph_refs",
                    "graph_node_refs",
                    "graph_skill_node_ids",
                    "skill_ids_used",
                    "source_skill_ids",
                },
            )
        )
        unique_fact_ids.update(
            _collect_values_for_keys(payloads, {"source_fact_ids", "fact_ids", "cited_fact_ids"})
        )
        unique_bundle_ids.update(
            _collect_values_for_keys(payloads, {"role_episode_bundle_id", "role_episode_bundle_ids"})
        )

        if str(summary.get("status") or "") == "FAIL":
            materiality_warnings.append(
                {
                    "section_id": sid,
                    "status": summary.get("status"),
                    "violations": summary.get("violations") or [],
                }
            )
        section_rows.append(
            {
                "section_id": sid,
                "status": summary.get("status"),
                "native_c03_active": bool(summary.get("native_c03_active")),
                "role_episode_active": bool(summary.get("role_episode_active")),
                "native_c03_cited_fact_count": int(summary.get("native_c03_cited_fact_count") or 0),
                "role_episode_bundle_intersection_count": int(
                    summary.get("role_episode_bundle_intersection_count") or 0
                ),
                "role_episode_skill_intersection_count": int(
                    summary.get("role_episode_skill_intersection_count") or 0
                ),
                "role_episode_fact_intersection_count": int(
                    summary.get("role_episode_fact_intersection_count") or 0
                ),
            }
        )

    warnings: list[dict[str, Any]] = list(materiality_warnings)
    if active_section_ids and len(active_section_ids) < GRAPH_COHERENCE_MIN_ACTIVE_SECTIONS:
        warnings.append(
            {
                "reason_code": "graph_metadata_breadth_below_floor",
                "observed": len(active_section_ids),
                "threshold": GRAPH_COHERENCE_MIN_ACTIVE_SECTIONS,
            }
        )
    if active_section_ids and len(unique_skill_ids) < GRAPH_COHERENCE_MIN_UNIQUE_SKILLS:
        warnings.append(
            {
                "reason_code": "unique_graph_skill_breadth_below_floor",
                "observed": len(unique_skill_ids),
                "threshold": GRAPH_COHERENCE_MIN_UNIQUE_SKILLS,
            }
        )

    if not active_section_ids:
        status = VERDICT_UNKNOWN
    elif warnings:
        status = VERDICT_WARN
    else:
        status = VERDICT_PASS

    return {
        "schema": "apps_rg.cross_section_graph_coherence_receipt.v1",
        "status": status,
        "active_section_count": len(active_section_ids),
        "native_c03_section_count": len(native_section_ids),
        "role_episode_section_count": len(role_section_ids),
        "unique_graph_skill_node_count": len(unique_skill_ids),
        "unique_source_fact_id_count": len(unique_fact_ids),
        "unique_role_episode_bundle_count": len(unique_bundle_ids),
        "active_section_ids": sorted(active_section_ids),
        "native_c03_section_ids": sorted(native_section_ids),
        "role_episode_section_ids": sorted(role_section_ids),
        "unique_graph_skill_node_ids": sorted(unique_skill_ids)[:64],
        "unique_role_episode_bundle_ids": sorted(unique_bundle_ids)[:64],
        "sections": section_rows,
        "warnings": warnings,
        "thresholds": {
            "min_active_sections": GRAPH_COHERENCE_MIN_ACTIVE_SECTIONS,
            "min_unique_graph_skill_node_ids": GRAPH_COHERENCE_MIN_UNIQUE_SKILLS,
        },
    }


def check_cross_section_graph_coherence(
    *,
    repo: Path,
    final_resume_blob: dict[str, Any],
    sealed_index: dict[str, Any],
) -> CrossSectionGateResult:
    receipt = build_cross_section_graph_coherence_receipt(
        repo=repo,
        final_resume_blob=final_resume_blob,
        sealed_index=sealed_index,
    )
    status = str(receipt.get("status") or VERDICT_UNKNOWN)
    if status == VERDICT_PASS:
        reason = "cross-section graph metadata is materially used with sufficient breadth"
        verdict = VERDICT_PASS
    elif status == VERDICT_WARN:
        reason = f"graph coherence warnings: {len(receipt.get('warnings') or [])}"
        verdict = VERDICT_WARN
    else:
        reason = "no generated section graph metadata available for cross-section coherence"
        verdict = VERDICT_WARN
    return CrossSectionGateResult(
        gate_id="x2_cross_section_graph_coherence",
        verdict=verdict,
        decisive_reason=reason,
        threshold=receipt.get("thresholds"),
        observed=receipt,
        evidence_refs=["cross_section_x2_gate_outputs.json::graph_coherence_receipt"],
    )


def _extract_pillar_ids_from_section(section: dict[str, Any]) -> set[str]:
    """Pull pillar IDs from targeting_graph_refs or graph_targeting block."""
    snap = section.get("l2_output_snapshot") or {}
    # Try graph_targeting.pillar_hint_ids first (from C0.3 merge)
    gt = snap.get("graph_targeting") or section.get("graph_targeting") or {}
    pillar_hint_ids: list[Any] = gt.get("pillar_hint_ids") or []
    briefing_supplement: list[Any] = gt.get("briefing_targeting_supplement") or []
    # Also look at targeting_graph_refs flat list
    targeting_refs: list[Any] = (
        snap.get("targeting_graph_refs")
        or section.get("targeting_graph_refs")
        or []
    )
    ids: set[str] = set()
    for item in pillar_hint_ids:
        ids.add(str(item))
    for item in briefing_supplement:
        ids.add(str(item))
    for item in targeting_refs:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, dict):
            ref_id = item.get("pillar_id") or item.get("skill_id") or item.get("ref_id") or ""
            if ref_id:
                ids.add(str(ref_id))
    return ids


def check_cross_section_pillar_coherence(sections: list[dict[str, Any]]) -> CrossSectionGateResult:
    """Verify that primary resume sections target overlapping JD pillar IDs (advisory only)."""
    primary_pillar_map: dict[str, set[str]] = {}
    for sec in sections:
        sid = str(sec.get("section_id") or "")
        if sid not in _PRIMARY_COHERENCE_SECTIONS:
            continue
        ids = _extract_pillar_ids_from_section(sec)
        if ids:
            primary_pillar_map[sid] = ids

    if len(primary_pillar_map) < 2:
        return CrossSectionGateResult(
            gate_id="x2_cross_section_pillar_coherence", verdict=VERDICT_UNKNOWN,
            decisive_reason="fewer than 2 primary sections with pillar targeting data — cannot assess coherence",
            threshold=_PILLAR_COHERENCE_JACCARD_WARN_THRESHOLD, observed=None, evidence_refs=[],
        )

    section_ids = sorted(primary_pillar_map.keys())
    min_jaccard: float = 1.0
    worst_pair: tuple[str, str] = (section_ids[0], section_ids[1])
    for i in range(len(section_ids)):
        for j in range(i + 1, len(section_ids)):
            a_id, b_id = section_ids[i], section_ids[j]
            j_score = _jaccard(primary_pillar_map[a_id], primary_pillar_map[b_id])
            if j_score < min_jaccard:
                min_jaccard = j_score
                worst_pair = (a_id, b_id)

    if min_jaccard >= _PILLAR_COHERENCE_JACCARD_WARN_THRESHOLD:
        return CrossSectionGateResult(
            gate_id="x2_cross_section_pillar_coherence",
            verdict=VERDICT_PASS,
            decisive_reason=(
                f"min pairwise Jaccard {min_jaccard:.3f} ≥ {_PILLAR_COHERENCE_JACCARD_WARN_THRESHOLD}"
            ),
            threshold=_PILLAR_COHERENCE_JACCARD_WARN_THRESHOLD,
            observed=round(min_jaccard, 4),
            evidence_refs=section_ids,
        )

    return CrossSectionGateResult(
        gate_id="x2_cross_section_pillar_coherence",
        verdict=VERDICT_WARN,
        decisive_reason=(
            f"sections '{worst_pair[0]}' and '{worst_pair[1]}' have Jaccard {min_jaccard:.3f} "
            f"< {_PILLAR_COHERENCE_JACCARD_WARN_THRESHOLD} — possible cross-section targeting mismatch"
        ),
        threshold=_PILLAR_COHERENCE_JACCARD_WARN_THRESHOLD,
        observed=round(min_jaccard, 4),
        evidence_refs=section_ids,
    )
