"""Indexing stage: metric outcomes, clusters, selection features, and evidence budgets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.candidate_fact_ledger import load_master_role_family_taxonomy
from apps_rg.fact_inventory.graph_metric_heterogeneity_policy import (
    POLICY_VERSION as C03_METRIC_POLICY_VERSION,
    metric_bucket_for_row,
)
from apps_rg.fact_inventory.graph_sqlite_path_index import (
    GRAPH_INDEX_SCHEMA_VERSION,
    build_graph_index_rows,
)
from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    ROLE_FAMILY_TRACK_WEIGHTS,
    SENIOR_ROLE_TAXONOMY_IDS,
)
from .constants import (
    C03_SQLITE_MATERIALIZER_CODE_VERSION,
    FORBIDDEN_SKILL_NODE_IDS,
    canonical_career_epoch_and_ordinal,
)
from .classification import _is_skill_id
from .graph_builder import _resolve_projection_pillar_hints

def run_materializer_indexing(ctx: dict[str, Any]) -> None:
    """Compute metric outcomes, clusters, section features, and graph summary."""
    root = ctx["root"]
    repo_root = root
    out_path = ctx["out_path"]
    payload = ctx["payload"]
    skill_rows_by_id = ctx["skill_rows_by_id"]
    node_rows = ctx["node_rows"]
    edge_rows = ctx["edge_rows"]
    section_rows = ctx["section_rows"]
    skill_fact_rows = ctx["skill_fact_rows"]
    projected_signature_report = ctx["projected_signature_report"]
    ts = ctx["ts"]
    gver = ctx["gver"]
    ledger_hash = ctx["ledger_hash"]
    src_path = ctx["src_path"]

    from apps_rg.fact_inventory.graph_metric_heterogeneity_policy import (
        POLICY_VERSION as C03_METRIC_POLICY_VERSION,
    )
    from apps_rg.fact_inventory.graph_metric_heterogeneity_policy import (
        metric_bucket_for_row,
    )

    allowed_sections_by_skill: dict[str, list[str]] = {}
    for row in section_rows:
        if int(row.get("allowed") or 0) != 1:
            continue
        sid = str(row.get("node_id") or "").strip()
        sec = str(row.get("section_id") or "").strip()
        if sid and sec:
            allowed_sections_by_skill.setdefault(sid, []).append(sec)

    selection_feature_rows: list[dict[str, Any]] = []
    role_family_skill_weight_rows: list[dict[str, Any]] = []
    for sid, row in skill_rows_by_id.items():
        if sid in FORBIDDEN_SKILL_NODE_IDS or sid not in node_rows:
            continue
        fact_ids = [
            str(fid).strip()
            for fid in row.get("fact_id_links") or []
            if str(fid).strip() and not _is_skill_id(str(fid))
        ]
        pillar = str(row.get("pillar") or "").strip()
        domain_id = str(row.get("domain_id") or row.get("domain") or "").strip()
        subpillar = str(row.get("subpillar") or "").strip()
        family = pillar or domain_id or subpillar or "unclassified"
        epoch, ordinal = canonical_career_epoch_and_ordinal(sid, row.get("career_epoch"))
        selection_feature_rows.append(
            {
                "skill_id": sid,
                "pillar": pillar,
                "subpillar": subpillar,
                "domain_id": domain_id,
                "career_track_id": str(row.get("career_track_id") or "").strip(),
                "career_epoch": epoch,
                "phase_ordinal": ordinal,
                "skill_family": family,
                "metric_bucket": metric_bucket_for_row(row),
                "role_family_weights": json.dumps(row.get("role_family_weights") or {}, sort_keys=True),
                "allowed_sections": json.dumps(
                    sorted(set(allowed_sections_by_skill.get(sid) or row.get("allowed_sections") or []))
                ),
                "source_fact_count": len(fact_ids),
                "confidence": str(node_rows[sid].get("confidence") or ""),
                "activation_status": str(node_rows[sid].get("activation_status") or ""),
                "support_level": str(node_rows[sid].get("support_level") or ""),
                "external_eligible": int(node_rows[sid].get("external_eligible") or 0),
                "source_authority": "augmented_skills_graph",
                "source_trace": json.dumps(list(row.get("source_resume_files") or [])[:5]),
                "updated_at": ts,
            }
        )
        weights = row.get("role_family_weights") or {}
        if isinstance(weights, dict):
            for role_family_key, weight in weights.items():
                rf_key = str(role_family_key or "").strip()
                if not rf_key:
                    continue
                try:
                    weight_f = float(weight)
                except (TypeError, ValueError):
                    continue
                role_family_skill_weight_rows.append(
                    {
                        "skill_id": sid,
                        "role_family_key": rf_key,
                        "weight": weight_f,
                        "source": "skill_row.role_family_weights",
                    }
                )

    projection_rows: list[dict[str, Any]] = []
    profiles = payload.get("role_family_projection_profiles") or {}
    from apps_rg.fact_inventory.candidate_fact_ledger import load_master_role_family_taxonomy

    tax = load_master_role_family_taxonomy(repo_root=repo_root)
    for rf_key in ROLE_FAMILY_TRACK_WEIGHTS:
        if rf_key in profiles:
            continue
        if rf_key not in SENIOR_ROLE_TAXONOMY_IDS:
            continue
        pillar_ids = list(_resolve_projection_pillar_hints(rf_key, taxonomy=tax))
        weights = ROLE_FAMILY_TRACK_WEIGHTS.get(rf_key, {})
        profiles[rf_key] = {
            "label": rf_key.replace("_", " ").title(),
            "taxonomy_ids": [rf_key],
            "top_weighted_pillars": [
                {"pillar_id": pid, "weight": round(1.0 - (i * 0.08), 2)}
                for i, pid in enumerate(pillar_ids[:6])
            ],
            "synthesized_for_sqlite": True,
        }
    for rf_key, prof in profiles.items():
        if not isinstance(prof, dict):
            continue
        weights = ROLE_FAMILY_TRACK_WEIGHTS.get(rf_key, {})
        note = "graph_routing_not_claim_proof"
        if rf_key == "ANTHROPIC_PARTNERSHIPS_APPLIED_AI":
            note = (
                "graph_routing_not_claim_proof;"
                " marketplace_listing_claims_blocked;"
                " pillars_include_hyperscaler_marketplace_and_applied_ai_partner_architecture"
            )
        projection_rows.append(
            {
                "role_family_id": rf_key,
                "projection_role_family_key": rf_key,
                "track_weight_profile": json.dumps(weights, sort_keys=True),
                "taxonomy_source": json.dumps(list(prof.get("taxonomy_ids") or [])),
                "targeting_keywords": json.dumps(list(prof.get("top_weighted_pillars") or [])[:8]),
                "proof_policy_note": note,
            }
        )

    from apps_rg.fact_inventory.graph_sqlite_path_index import (
        GRAPH_INDEX_SCHEMA_VERSION,
        build_graph_index_rows,
        compute_sqlite_graph_digest,
        compute_sqlite_schema_digest,
        require_graphdb_capability_schema,
        validate_graphdb_capability_integrity,
    )

    graph_index_rows = build_graph_index_rows(
        node_rows=list(node_rows.values()),
        edge_rows=edge_rows,
        section_rows=section_rows,
        role_family_projection_rows=projection_rows,
        created_at=ts,
    )

    gm = payload.get("graph_metadata") if isinstance(payload.get("graph_metadata"), dict) else {}
    summary = {
        "c03_sqlite_materializer_code_version": C03_SQLITE_MATERIALIZER_CODE_VERSION,
        "node_count_json": gm.get("node_count"),
        "edge_count_json": gm.get("edge_count"),
        "node_count_sqlite": len(node_rows),
        "edge_count_sqlite": len(edge_rows),
        "skill_fact_link_count": len(skill_fact_rows),
        "section_eligibility_count": len(section_rows),
        "role_family_projection_count": len(projection_rows),
        "c03_skill_selection_feature_count": len(selection_feature_rows),
        "c03_role_family_skill_weight_count": len(role_family_skill_weight_rows),
        "c03_metric_policy_version": C03_METRIC_POLICY_VERSION,
        "graph_index_schema_version": GRAPH_INDEX_SCHEMA_VERSION,
        "graph_path_count": len(graph_index_rows["graph_paths"]),
        "graph_neighborhood_count": len(graph_index_rows["graph_neighborhoods"]),
        "graph_sibling_link_count": len(graph_index_rows["graph_sibling_links"]),
        "section_evidence_budget_count": len(graph_index_rows["section_evidence_budget"]),
        "projected_registered_edge_count": projected_signature_report["registered_edge_count"],
        "projected_registered_edge_signature_valid_count": projected_signature_report["valid_edge_count"],
    }


    ctx["selection_feature_rows"] = selection_feature_rows
    ctx["role_family_skill_weight_rows"] = role_family_skill_weight_rows
    ctx["projection_rows"] = projection_rows
    ctx["graph_index_rows"] = graph_index_rows
    ctx["summary"] = summary

__all__ = ["run_materializer_indexing"]
