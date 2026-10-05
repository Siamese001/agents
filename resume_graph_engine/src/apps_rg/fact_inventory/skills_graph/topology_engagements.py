"""First-class engagement node and edge projection from role-episode bundles (Wave 3)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_rg.repository_layout import repository_root
from .topology_normalization import (
    CANONICAL_EMPLOYMENT_EPOCHS,
    FACT_TO_EMPLOYMENT_MAP,
    normalize_employment_id,
)


def build_engagement_nodes_and_edges(
    repo_root: Path | None = None,
    *,
    ts: str = "",
    build_run_id: str = "",
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load role-episode bundles and build first-class engagement nodes and edges."""
    root = repository_root(repo_root)
    bundles_dir = (
        root / "src/apps_rg/fact_inventory"
        if (root / "src/apps_rg/fact_inventory").is_dir()
        else root / "resume_graph_engine/src/apps_rg/fact_inventory"
    )
    bundle_files = sorted(bundles_dir.glob("*_role_episode_bundles.json"))

    engagement_nodes: dict[str, dict[str, Any]] = {}
    engagement_edges: list[dict[str, Any]] = []

    for bpath in bundle_files:
        try:
            data = json.loads(bpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        bundles = data.get("bundles") or []
        for b in bundles:
            reb_id = str(b.get("role_episode_bundle_id") or "").strip()
            if not reb_id:
                continue

            raw_emp = str(b.get("employer_node_id") or "").strip()
            emp_id = normalize_employment_id(raw_emp)
            title = str(b.get("title") or "").strip()
            employer = str(b.get("employer") or "").strip()
            context = str(b.get("operating_context") or b.get("claim_scope") or "").strip()
            theme = str(b.get("bundle_theme") or title or reb_id).strip()
            claim = str(b.get("claim_text") or context or theme).strip()
            epoch = CANONICAL_EMPLOYMENT_EPOCHS.get(emp_id, "")

            engagement_nodes[reb_id] = {
                "node_id": reb_id,
                "node_type": "engagement",
                "label": theme,
                "description": claim,
                "title": title,
                "operating_context": context,
                "employer": employer,
                "career_epoch": epoch,
                "activation_status": "ACTIVE",
                "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
                "confidence": "HIGH",
                "confidence_score": 0.95,
                "confidence_tier": "HIGH",
                "external_eligible": 1,
                "source_authority": "augmented_skills_graph",
                "origin_kind": "bundle_row",
                "origin_ref": reb_id,
                "source_refs_json": "[]",
                "authority_refs_json": "[]",
                "build_run_id": build_run_id,
                "created_at": ts,
                "updated_at": ts,
            }

            # 1. engagement_at_employment edge
            if emp_id:
                eid = f"edge_engagement_at_employment__{reb_id}__{emp_id}"
                engagement_edges.append(
                    {
                        "edge_id": eid,
                        "source_node_id": reb_id,
                        "target_node_id": emp_id,
                        "edge_family": "engagement_employment",
                        "edge_type": "engagement_at_employment",
                        "weight": 1.0,
                        "confidence": "HIGH",
                        "directional": 1,
                        "evidence_status": "approved_graph_ssot",
                        "section_fit": "ALL",
                        "source_authority": "augmented_skills_graph",
                        "rationale": f"Engagement {reb_id} performed at {emp_id}.",
                        "projection_behavior": "graph_structure",
                        "external_claim_policy": "approved_by_graph_presence",
                        "validation_status": "validated",
                        "edge_note": "",
                        "operator_note": "",
                        "business_story": "",
                        "technical_story": "",
                        "assertion_type": "STRUCTURAL_CONTAINMENT",
                        "assertion_basis": "taxonomy_rule",
                        "assertion_basis_refs_json": json.dumps([f"bundle:{reb_id}", f"employment:{emp_id}"]),
                        "canonical_assertion_text": f"Engagement {reb_id} took place at {emp_id}.",
                        "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                        "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                        "origin_kind": "bundle_row",
                        "origin_ref": f"{reb_id}::{emp_id}",
                        "origin_artifact_sha256": "",
                        "derivation_rule_id": "rule_engagement_at_employment",
                        "build_run_id": build_run_id,
                        "confidence_score": 0.98,
                        "confidence_tier": "HIGH",
                        "confidence_method": "deterministic_taxonomy_rule",
                        "traversable": 1,
                    }
                )

            # 2. engagement_exercises_skill edges
            skills = [str(s).strip() for s in b.get("graph_skill_node_ids") or [] if str(s).strip()]
            for sid in skills:
                eid = f"edge_engagement_exercises_skill__{reb_id}__{sid}"
                engagement_edges.append(
                    {
                        "edge_id": eid,
                        "source_node_id": reb_id,
                        "target_node_id": sid,
                        "edge_family": "engagement_skill",
                        "edge_type": "engagement_exercises_skill",
                        "weight": 1.0,
                        "confidence": "HIGH",
                        "directional": 1,
                        "evidence_status": "approved_graph_ssot",
                        "section_fit": "ALL",
                        "source_authority": "augmented_skills_graph",
                        "rationale": f"Engagement {reb_id} exercises skill {sid}.",
                        "projection_behavior": "graph_structure",
                        "external_claim_policy": "approved_by_graph_presence",
                        "validation_status": "validated",
                        "edge_note": "",
                        "operator_note": "",
                        "business_story": "",
                        "technical_story": "",
                        "assertion_type": "EVIDENTIAL_SUPPORT",
                        "assertion_basis": "source_field_derivation",
                        "assertion_basis_refs_json": json.dumps([f"bundle:{reb_id}", f"skill:{sid}"]),
                        "canonical_assertion_text": f"Engagement {reb_id} demonstrates skill {sid}.",
                        "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                        "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                        "origin_kind": "bundle_row",
                        "origin_ref": f"{reb_id}::{sid}",
                        "origin_artifact_sha256": "",
                        "derivation_rule_id": "rule_engagement_exercises_skill",
                        "build_run_id": build_run_id,
                        "confidence_score": 0.95,
                        "confidence_tier": "HIGH",
                        "confidence_method": "source_bundle_skill_binding",
                        "traversable": 1,
                    }
                )

            # 3. engagement_evidenced_by_fact edges
            raw_facts = [str(f).strip() for f in b.get("linked_source_fact_ids") or [] if str(f).strip()]
            candidate_facts = [f for f in raw_facts if f.startswith("fact_")]
            if not candidate_facts and emp_id:
                candidate_facts = [fid for fid, emp in FACT_TO_EMPLOYMENT_MAP.items() if emp == emp_id][:2]

            for fid in candidate_facts:
                eid = f"edge_engagement_evidenced_by_fact__{reb_id}__{fid}"
                engagement_edges.append(
                    {
                        "edge_id": eid,
                        "source_node_id": reb_id,
                        "target_node_id": fid,
                        "edge_family": "engagement_fact",
                        "edge_type": "engagement_evidenced_by_fact",
                        "weight": 1.0,
                        "confidence": "HIGH",
                        "directional": 1,
                        "evidence_status": "approved_graph_ssot",
                        "section_fit": "ALL",
                        "source_authority": "augmented_skills_graph",
                        "rationale": f"Engagement {reb_id} evidenced by fact {fid}.",
                        "projection_behavior": "graph_structure",
                        "external_claim_policy": "approved_by_graph_presence",
                        "validation_status": "validated",
                        "edge_note": "",
                        "operator_note": "",
                        "business_story": "",
                        "technical_story": "",
                        "assertion_type": "EVIDENTIAL_SUPPORT",
                        "assertion_basis": "evidence_reference",
                        "assertion_basis_refs_json": json.dumps([f"bundle:{reb_id}", f"fact:{fid}"]),
                        "canonical_assertion_text": f"Engagement {reb_id} is supported by verified fact {fid}.",
                        "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                        "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                        "origin_kind": "bundle_row",
                        "origin_ref": f"{reb_id}::{fid}",
                        "origin_artifact_sha256": "",
                        "derivation_rule_id": "rule_engagement_evidenced_by_fact",
                        "build_run_id": build_run_id,
                        "confidence_score": 0.95,
                        "confidence_tier": "HIGH",
                        "confidence_method": "fact_bundle_evidence_link",
                        "traversable": 1,
                    }
                )

    return engagement_nodes, engagement_edges


__all__ = ["build_engagement_nodes_and_edges"]
