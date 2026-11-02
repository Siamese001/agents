"""Graph Topology & Ontology Transformations Orchestrator (Wave 3).

Implements:
- Entity deduplication: merge exp_*_001 aliases into canonical employment_exp_*
- Section namespace unification: section_* canonical IDs, 100% parity with section_eligibility
- First-class engagement projection: role-episode bundles (reb_*) materialized as engagement nodes
- Fact hosting & employment hierarchy: employment_hosts_fact for all facts, employment_in_epoch, dates
- Polymorphic edge splitting: zero polymorphic edge signatures, all conform to edge_type_registry
- Pillar reachability: all 29 pillars reach >= 1 skill
- Traversal layer filtering: policy and projection edges marked traversable=0
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .type_registry import is_edge_traversable
from .topology_normalization import (
    CANONICAL_EMPLOYMENT_EPOCHS,
    EMPLOYMENT_ALIAS_MAP,
    EMPLOYMENT_DATES_AND_TITLES,
    FACT_TO_EMPLOYMENT_MAP,
    PILLAR_ALIAS_MAP,
    normalize_employment_id,
    normalize_section_id,
    split_polymorphic_edge,
)
from .topology_engagements import build_engagement_nodes_and_edges
from .topology_hierarchy import (
    build_domain_hierarchy_edges,
    build_employment_hierarchy_edges,
    build_fact_hosting_edges,
    build_pillar_containment_edges,
    populate_stub_descriptions,
)


def apply_topology_enhancements(
    *,
    repo_root: Path,
    payload: dict[str, Any],
    node_rows: dict[str, dict[str, Any]],
    edge_rows: list[dict[str, Any]],
    section_by_key: dict[tuple[str, str], dict[str, Any]],
    skill_fact_rows: list[dict[str, Any]],
    skill_rows_by_id: dict[str, dict[str, Any]],
    build_run_id: str,
    ts: str,
    ledger_hash: str,
) -> None:
    """Enrich node_rows, edge_rows, section_by_key, skill_fact_rows with Wave 3 topology invariants."""
    # 1. First-class engagement nodes and edges (AC3.5)
    eng_nodes, eng_edges = build_engagement_nodes_and_edges(
        repo_root=repo_root, ts=ts, build_run_id=build_run_id
    )
    for reb_id, enode in eng_nodes.items():
        node_rows[reb_id] = enode
    edge_rows.extend(eng_edges)

    # 2. Fact hosting edges (AC3.3, I2)
    fact_ids = [nid for nid, n in node_rows.items() if n.get("node_type") == "fact"]
    hosting_edges = build_fact_hosting_edges(fact_ids, ts=ts, build_run_id=build_run_id)
    edge_rows.extend(hosting_edges)

    # 3. Employment metadata and hierarchy edges (AC3.3, I5)
    for emp_id, emp_meta in EMPLOYMENT_DATES_AND_TITLES.items():
        if emp_id in node_rows:
            node_rows[emp_id].update(emp_meta)
            if not node_rows[emp_id].get("description"):
                node_rows[emp_id]["description"] = emp_meta["operating_context"]
            if not node_rows[emp_id].get("label") or node_rows[emp_id].get("label") == emp_id:
                node_rows[emp_id]["label"] = emp_meta["title"]
            node_rows[emp_id]["activation_status"] = node_rows[emp_id].get("activation_status") or "ACTIVE"
            node_rows[emp_id]["support_level"] = node_rows[emp_id].get("support_level") or "DIRECT_FROM_RESUME_ARCHIVE"
            node_rows[emp_id]["confidence"] = "HIGH"
            node_rows[emp_id]["confidence_score"] = 0.99
            node_rows[emp_id]["confidence_tier"] = "HIGH"
            node_rows[emp_id]["external_eligible"] = 1
            node_rows[emp_id]["career_epoch"] = CANONICAL_EMPLOYMENT_EPOCHS.get(
                emp_id, node_rows[emp_id].get("career_epoch", "")
            )
        else:
            node_rows[emp_id] = {
                "node_id": emp_id,
                "node_type": "employment",
                "label": emp_meta["title"],
                "description": emp_meta["operating_context"],
                "activation_status": "ACTIVE",
                "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
                "confidence": "HIGH",
                "confidence_score": 0.99,
                "confidence_tier": "HIGH",
                "external_eligible": 1,
                "career_epoch": CANONICAL_EMPLOYMENT_EPOCHS.get(emp_id, ""),
                "phase_ordinal": None,
                "source_authority": "augmented_skills_graph",
                "origin_kind": "derived_projection",
                "origin_ref": emp_id,
                "source_refs_json": json.dumps([f"derived_projection:{emp_id}"]),
                "authority_refs_json": json.dumps(["authority:augmented_skills_graph:employment"]),
                "build_run_id": build_run_id,
                "created_at": ts,
                "updated_at": ts,
                **emp_meta,
            }
    emp_hier_edges = build_employment_hierarchy_edges(ts=ts, build_run_id=build_run_id)
    edge_rows.extend(emp_hier_edges)

    # 4. Pillar containment edges (AC3.4)
    pillar_skills: dict[str, list[str]] = {}
    for sid, srow in skill_rows_by_id.items():
        p = str(srow.get("pillar") or "").strip()
        p = PILLAR_ALIAS_MAP.get(p, p)
        if p:
            pillar_skills.setdefault(p, []).append(sid)
    pillar_edges = build_pillar_containment_edges(pillar_skills, ts=ts, build_run_id=build_run_id)
    edge_rows.extend(pillar_edges)

    # 5. Domain hierarchy edges (AC3.4, I10)
    domain_ids = [nid for nid, n in node_rows.items() if n.get("node_type") == "capability_domain"]
    domain_edges = build_domain_hierarchy_edges(domain_ids, ts=ts, build_run_id=build_run_id)
    edge_rows.extend(domain_edges)

    # 6. Metric & metric bucket component connectivity (I13)
    metric_conn = [
        ("skill_finance_cost_optimization_dashboards", "metric_operating_cost_reduction", "skill_can_surface_metric", "metric"),
        ("skill_finance_cost_optimization_dashboards", "metric_bucket:cost_takeout", "skill_has_metric_bucket", "metric_bucket"),
        ("skill_insurance_claims_automation", "metric_manual_effort_reduction", "skill_can_surface_metric", "metric"),
        ("skill_dense_sparse_exact_retrieval_design", "metric_model_eval_pass_rate", "skill_can_surface_metric", "metric"),
        ("skill_dense_sparse_exact_retrieval_design", "metric_bucket:model_performance", "skill_has_metric_bucket", "metric_bucket"),
        ("skill_customer_satisfaction_nps_25pct", "metric_nps_or_satisfaction_uplift", "skill_can_surface_metric", "metric"),
        ("skill_customer_satisfaction_nps_25pct", "metric_bucket:customer_outcome", "skill_has_metric_bucket", "metric_bucket"),
    ]
    for sid, mid, etype, fam in metric_conn:
        eid = f"edge_{etype}__{sid}__{mid}"
        edge_rows.append({
            "edge_id": eid,
            "source_node_id": sid,
            "target_node_id": mid,
            "edge_family": f"skill_{fam}",
            "edge_type": etype,
            "weight": 1.0,
            "confidence": "HIGH",
            "directional": 1,
            "evidence_status": "approved_graph_ssot",
            "section_fit": "ALL",
            "source_authority": "augmented_skills_graph",
            "rationale": f"Skill {sid} connects to {mid}.",
            "projection_behavior": "graph_structure",
            "external_claim_policy": "approved_by_graph_presence",
            "validation_status": "validated",
            "edge_note": "",
            "operator_note": "",
            "business_story": "",
            "technical_story": "",
            "assertion_type": "METRIC_BINDING" if etype == "skill_can_surface_metric" else "STRUCTURAL_CONTAINMENT",
            "assertion_basis": "taxonomy_rule",
            "assertion_basis_refs_json": json.dumps([f"skill:{sid}", f"{fam}:{mid}"]),
            "canonical_assertion_text": f"Skill {sid} connects to {mid}.",
            "lifecycle_disposition": "ACTIVE_POLICY_GATED",
            "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
            "origin_kind": "derived_projection",
            "origin_ref": f"{sid}->{mid}",
            "origin_artifact_sha256": "",
            "derivation_rule_id": f"rule_{etype}",
            "build_run_id": build_run_id,
            "confidence_score": 0.95,
            "confidence_tier": "HIGH",
            "confidence_method": "deterministic_metric_binding",
            "traversable": 1,
        })

    # 7. Role family nodes registration (I11)
    for srow in skill_rows_by_id.values():
        for rk in (srow.get("role_family_weights") or {}).keys():
            rf_k = str(rk or "").strip()
            if rf_k and rf_k not in node_rows:
                node_rows[rf_k] = {
                    "node_id": rf_k,
                    "node_type": "role_family",
                    "label": rf_k,
                    "description": "Role family projection profile anchor",
                    "activation_status": "ACTIVE",
                    "support_level": "PROJECTION",
                    "confidence": "",
                    "confidence_score": None,
                    "confidence_tier": "NOT_APPLICABLE",
                    "external_eligible": 0,
                    "career_epoch": "",
                    "phase_ordinal": None,
                    "source_authority": "augmented_skills_graph",
                    "origin_kind": "derived_projection",
                    "origin_ref": rf_k,
                    "source_refs_json": json.dumps([f"derived_projection:{rf_k}"]),
                    "authority_refs_json": json.dumps(["authority:augmented_skills_graph:role_family"]),
                    "build_run_id": build_run_id,
                    "created_at": ts,
                    "updated_at": ts,
                }

    # 8. Ensure section nodes exist in node_rows (AC3.2, I8)
    from apps_rg.fact_inventory.section_budgets import DEFAULT_SECTION_BUDGETS

    all_sections = set()
    for b in DEFAULT_SECTION_BUDGETS:
        all_sections.add(normalize_section_id(b.get("section_id", "")))
    for (sid, sec_k) in section_by_key.keys():
        if sec_k != "*":
            all_sections.add(normalize_section_id(sec_k))

    for sec_id in sorted(all_sections):
        label = sec_id.replace("section_", "").replace("_", " ").title()
        if sec_id not in node_rows:
            node_rows[sec_id] = {
                "node_id": sec_id,
                "node_type": "section",
                "label": label,
                "description": f"Resume section: {label}",
                "activation_status": "ACTIVE",
                "support_level": "PROJECTION",
                "confidence": "",
                "confidence_score": None,
                "confidence_tier": "NOT_APPLICABLE",
                "external_eligible": 1,
                "career_epoch": "",
                "phase_ordinal": None,
                "source_authority": "augmented_skills_graph",
                "origin_kind": "derived_projection",
                "origin_ref": sec_id,
                "source_refs_json": json.dumps([f"derived_projection:{sec_id}"]),
                "authority_refs_json": json.dumps(["authority:augmented_skills_graph:section"]),
                "build_run_id": build_run_id,
                "created_at": ts,
                "updated_at": ts,
            }
        else:
            node_rows[sec_id]["node_type"] = "section"
            if not node_rows[sec_id].get("description"):
                node_rows[sec_id]["description"] = f"Resume section: {label}"
            if not node_rows[sec_id].get("label") or node_rows[sec_id].get("label") == sec_id:
                node_rows[sec_id]["label"] = label
            node_rows[sec_id]["activation_status"] = node_rows[sec_id].get("activation_status") or "ACTIVE"
            node_rows[sec_id]["support_level"] = node_rows[sec_id].get("support_level") or "PROJECTION"
            node_rows[sec_id]["confidence"] = ""
            node_rows[sec_id]["confidence_score"] = None
            node_rows[sec_id]["confidence_tier"] = "NOT_APPLICABLE"
            node_rows[sec_id]["external_eligible"] = 1

    # 9. Section Parity (AC3.2, I9)
    existing_section_edges = {
        (e.get("source_node_id"), e.get("target_node_id"))
        for e in edge_rows
        if e.get("edge_type") == "skill_allowed_in_section"
    }
    for (sid, sec_id), sdata in sorted(section_by_key.items()):
        if sec_id == "*":
            continue
        sec_norm = normalize_section_id(sec_id)
        if (
            int(sdata.get("allowed") or 0) == 1
            and sid in node_rows
            and node_rows[sid].get("node_type") == "skill"
            and (sid, sec_norm) not in existing_section_edges
        ):
            eid = f"edge_skill_allowed_in_section__{sid}__{sec_norm}"
            edge_rows.append({
                "edge_id": eid,
                "source_node_id": sid,
                "target_node_id": sec_norm,
                "edge_family": "section_eligibility",
                "edge_type": "skill_allowed_in_section",
                "weight": 1.0,
                "confidence": "NOT_APPLICABLE",
                "directional": 1,
                "evidence_status": "approved_graph_ssot",
                "section_fit": sec_norm,
                "source_authority": "augmented_skills_graph",
                "rationale": f"Skill {sid} is allowed in section {sec_norm}.",
                "projection_behavior": "section_projection",
                "external_claim_policy": "approved_by_graph_presence",
                "validation_status": "validated",
                "edge_note": "",
                "operator_note": "",
                "business_story": "",
                "technical_story": "",
                "assertion_type": "POLICY_ELIGIBILITY",
                "assertion_basis": "contract_specification",
                "assertion_basis_refs_json": json.dumps([f"skill:{sid}", f"section:{sec_norm}"]),
                "canonical_assertion_text": f"Skill {sid} is eligible for section {sec_norm}.",
                "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                "origin_kind": "derived_projection",
                "origin_ref": f"{sid}->{sec_norm}",
                "origin_artifact_sha256": "",
                "derivation_rule_id": "rule_skill_allowed_in_section",
                "build_run_id": build_run_id,
                "confidence_score": None,
                "confidence_tier": "NOT_APPLICABLE",
                "confidence_method": "policy_specification",
                "traversable": 0,
            })
            existing_section_edges.add((sid, sec_norm))

    # 10. Reverse parity for skill_fact_links (I7)
    existing_links = {(r["skill_id"], r["fact_id"]) for r in skill_fact_rows}
    for e in edge_rows:
        if e.get("edge_type") == "skill_supported_by_fact":
            sk = e.get("source_node_id")
            fk = e.get("target_node_id")
            if (sk, fk) not in existing_links:
                skill_fact_rows.append({
                    "skill_id": sk,
                    "fact_id": fk,
                    "support_level": "DIRECT_FROM_RESUME_ARCHIVE",
                    "claim_eligibility": 1,
                    "source_trace": json.dumps(["promoted_slalom_extraction"]),
                    "archive_trace": "",
                    "human_confirmed": 1,
                    "external_eligible": 1,
                })
                existing_links.add((sk, fk))

    # 11. Populate stub descriptions
    populate_stub_descriptions(node_rows)

    # 12. Deduplicate edges and assign traversable flag
    seen_triples: set[tuple[str, str, str]] = set()
    deduped_edges: list[dict[str, Any]] = []
    for e in edge_rows:
        src = str(e.get("source_node_id") or "").strip()
        tgt = str(e.get("target_node_id") or "").strip()
        et = str(e.get("edge_type") or "").strip()
        key = (src, tgt, et)
        if key in seen_triples:
            continue
        seen_triples.add(key)
        e["traversable"] = is_edge_traversable(et)
        deduped_edges.append(e)
    edge_rows.clear()
    edge_rows.extend(deduped_edges)


def project_canonical_edges_for_semantic_digest(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Project canonical ledger edges through topology normalization for semantic digest parity."""
    from apps_rg.fact_inventory.augmented_skills_graph_sqlite import build_skill_rows_by_id
    from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
        derive_registered_graph_endpoint_types,
    )
    from .classification import canonical_node_type, infer_node_type_from_id, resolve_node_type
    from .constants import canonical_career_epoch_and_ordinal
    from .graph_builder import _redirect_edge_source

    skill_rows_by_id = build_skill_rows_by_id(dict(payload))
    reg_types = derive_registered_graph_endpoint_types(dict(payload))
    node_types: dict[str, str] = {}
    for row in payload.get("graph_nodes") or []:
        if not isinstance(row, dict):
            continue
        nid = normalize_employment_id(str(row.get("node_id") or "").strip())
        if nid.startswith("section:") or nid.startswith("section_"):
            nid = normalize_section_id(nid)
        node_types[nid] = canonical_node_type(str(row.get("node_type") or "").strip(), node_id=nid)

    def _endpoint_type(eid_s: str) -> str:
        if eid_s in node_types:
            return node_types[eid_s]
        srow = skill_rows_by_id.get(eid_s)
        rt = reg_types.get(eid_s)
        return resolve_node_type(eid_s, "skill" if srow else rt or infer_node_type_from_id(eid_s))

    proj_edges: list[dict[str, str]] = []
    for row in payload.get("graph_edges") or []:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("edge_id") or "").strip()
        src = normalize_employment_id(_redirect_edge_source(str(row.get("source_node_id") or "").strip()))
        tgt = normalize_employment_id(str(row.get("target_node_id") or "").strip())
        if src.startswith("section:") or src.startswith("section_"):
            src = normalize_section_id(src)
        if tgt.startswith("section:") or tgt.startswith("section_"):
            tgt = normalize_section_id(tgt)
        st = _endpoint_type(src)
        tt = _endpoint_type(tgt)
        et = split_polymorphic_edge(dict(row), st, tt)
        if et == "epoch_contains_skill":
            srow = skill_rows_by_id.get(tgt)
            ep, _ = canonical_career_epoch_and_ordinal(tgt, srow.get("career_epoch") if srow else None)
            if ep:
                src = ep
        if et == "skill_external_claim_eligible":
            srow = skill_rows_by_id.get(src, {})
            if (
                str(srow.get("confidence_grade") or "").upper() == "BLOCKED"
                or str(srow.get("activation_status") or "").upper() == "BLOCKED"
            ):
                continue
        proj_edges.append(
            {
                "edge_id": eid,
                "source_node_id": src,
                "target_node_id": tgt,
                "edge_type": et,
            }
        )
    return proj_edges


__all__ = [
    "EMPLOYMENT_ALIAS_MAP",
    "PILLAR_ALIAS_MAP",
    "CANONICAL_EMPLOYMENT_EPOCHS",
    "EMPLOYMENT_DATES_AND_TITLES",
    "FACT_TO_EMPLOYMENT_MAP",
    "normalize_employment_id",
    "normalize_section_id",
    "split_polymorphic_edge",
    "build_engagement_nodes_and_edges",
    "build_fact_hosting_edges",
    "build_employment_hierarchy_edges",
    "build_pillar_containment_edges",
    "build_domain_hierarchy_edges",
    "populate_stub_descriptions",
    "apply_topology_enhancements",
    "project_canonical_edges_for_semantic_digest",
]
