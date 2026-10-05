"""Topology hierarchy builders for fact hosting, employments, epochs, pillars, and domains (Wave 3)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_rg.repository_layout import repository_root
from .topology_normalization import (
    CANONICAL_EMPLOYMENT_EPOCHS,
    FACT_TO_EMPLOYMENT_MAP,
)


def build_fact_hosting_edges(
    fact_ids: list[str],
    *,
    ts: str = "",
    build_run_id: str = "",
) -> list[dict[str, Any]]:
    """Build employment_hosts_fact edges ensuring every fact has exactly one hosting employment."""
    hosting_edges: list[dict[str, Any]] = []
    for fid in sorted(fact_ids):
        emp_id = FACT_TO_EMPLOYMENT_MAP.get(fid)
        if not emp_id:
            emp_id = "employment_exp_early_career_001"
        eid = f"edge_employment_hosts_fact__{emp_id}__{fid}"
        hosting_edges.append(
            {
                "edge_id": eid,
                "source_node_id": emp_id,
                "target_node_id": fid,
                "edge_family": "employment_fact",
                "edge_type": "employment_hosts_fact",
                "weight": 1.0,
                "confidence": "HIGH",
                "directional": 1,
                "evidence_status": "approved_graph_ssot",
                "section_fit": "ALL",
                "source_authority": "augmented_skills_graph",
                "rationale": f"Employment tenure {emp_id} hosts verified fact {fid}.",
                "projection_behavior": "graph_structure",
                "external_claim_policy": "approved_by_graph_presence",
                "validation_status": "validated",
                "edge_note": "",
                "operator_note": "",
                "business_story": "",
                "technical_story": "",
                "assertion_type": "STRUCTURAL_CONTAINMENT",
                "assertion_basis": "evidence_reference",
                "assertion_basis_refs_json": json.dumps([f"employment:{emp_id}", f"fact:{fid}"]),
                "canonical_assertion_text": f"Fact {fid} was achieved during tenure at {emp_id}.",
                "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                "origin_kind": "derived_projection",
                "origin_ref": f"{emp_id}->{fid}",
                "origin_artifact_sha256": "",
                "derivation_rule_id": "rule_employment_fact_hosting",
                "build_run_id": build_run_id,
                "confidence_score": 0.99,
                "confidence_tier": "HIGH",
                "confidence_method": "deterministic_fact_tenure_binding",
                "traversable": 1,
            }
        )
    return hosting_edges


def build_employment_hierarchy_edges(
    *,
    ts: str = "",
    build_run_id: str = "",
) -> list[dict[str, Any]]:
    """Build employment_in_epoch and missing career_track_contains_epoch edges."""
    edges: list[dict[str, Any]] = []

    # 1. employment_in_epoch edges
    for emp_id, epoch_id in CANONICAL_EMPLOYMENT_EPOCHS.items():
        eid = f"edge_employment_in_epoch__{emp_id}__{epoch_id}"
        edges.append(
            {
                "edge_id": eid,
                "source_node_id": emp_id,
                "target_node_id": epoch_id,
                "edge_family": "employment_epoch",
                "edge_type": "employment_in_epoch",
                "weight": 1.0,
                "confidence": "HIGH",
                "directional": 1,
                "evidence_status": "approved_graph_ssot",
                "section_fit": "ALL",
                "source_authority": "augmented_skills_graph",
                "rationale": f"Employment tenure {emp_id} belongs to career epoch {epoch_id}.",
                "projection_behavior": "graph_structure",
                "external_claim_policy": "approved_by_graph_presence",
                "validation_status": "validated",
                "edge_note": "",
                "operator_note": "",
                "business_story": "",
                "technical_story": "",
                "assertion_type": "TEMPORAL_SEQUENCE",
                "assertion_basis": "taxonomy_rule",
                "assertion_basis_refs_json": json.dumps([f"employment:{emp_id}", f"epoch:{epoch_id}"]),
                "canonical_assertion_text": f"Employment {emp_id} belongs to epoch {epoch_id}.",
                "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                "origin_kind": "derived_projection",
                "origin_ref": f"{emp_id}->{epoch_id}",
                "origin_artifact_sha256": "",
                "derivation_rule_id": "rule_employment_epoch_temporal",
                "build_run_id": build_run_id,
                "confidence_score": 0.99,
                "confidence_tier": "HIGH",
                "confidence_method": "deterministic_career_spine",
                "traversable": 1,
            }
        )

    # 2. Attach any non-attached epochs to track_data_tech_cloud_ml
    non_attached_epochs = [
        "cross_career",
        "epoch_ibm_client_partner_consulting",
        "epoch_unify_chief_ai_officer",
    ]
    track_id = "track_data_tech_cloud_ml"
    for epoch_id in non_attached_epochs:
        eid = f"edge_career_track_contains_epoch__{track_id}__{epoch_id}"
        edges.append(
            {
                "edge_id": eid,
                "source_node_id": track_id,
                "target_node_id": epoch_id,
                "edge_family": "track_epoch",
                "edge_type": "career_track_contains_epoch",
                "weight": 1.0,
                "confidence": "HIGH",
                "directional": 1,
                "evidence_status": "approved_graph_ssot",
                "section_fit": "ALL",
                "source_authority": "augmented_skills_graph",
                "rationale": f"Career track {track_id} contains secondary epoch {epoch_id}.",
                "projection_behavior": "graph_structure",
                "external_claim_policy": "approved_by_graph_presence",
                "validation_status": "validated",
                "edge_note": "",
                "operator_note": "",
                "business_story": "",
                "technical_story": "",
                "assertion_type": "STRUCTURAL_CONTAINMENT",
                "assertion_basis": "taxonomy_rule",
                "assertion_basis_refs_json": json.dumps([f"track:{track_id}", f"epoch:{epoch_id}"]),
                "canonical_assertion_text": f"Career track {track_id} contains epoch {epoch_id}.",
                "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                "origin_kind": "derived_projection",
                "origin_ref": f"{track_id}->{epoch_id}",
                "origin_artifact_sha256": "",
                "derivation_rule_id": "rule_track_epoch_containment",
                "build_run_id": build_run_id,
                "confidence_score": 0.95,
                "confidence_tier": "HIGH",
                "confidence_method": "deterministic_track_hierarchy",
                "traversable": 1,
            }
        )

    # 3. Attach unattached employments to track
    emp_track_map = {
        "employment_exp_early_career_001": "track_actuarial_risk_derivatives",
        "employment_exp_ey_001": "track_actuarial_risk_derivatives",
        "employment_exp_insurtech_001": "track_data_tech_cloud_ml",
        "employment_exp_ibm_001": "track_data_tech_cloud_ml",
        "employment_exp_unify_001": "track_genai_agentic",
        "employment_exp_slalom_001": "track_genai_agentic",
    }
    for emp_id, trk in emp_track_map.items():
        eid = f"edge_employment_in_career_track__{emp_id}__{trk}"
        edges.append(
            {
                "edge_id": eid,
                "source_node_id": emp_id,
                "target_node_id": trk,
                "edge_family": "employment_track",
                "edge_type": "employment_in_career_track",
                "weight": 1.0,
                "confidence": "HIGH",
                "directional": 1,
                "evidence_status": "approved_graph_ssot",
                "section_fit": "ALL",
                "source_authority": "augmented_skills_graph",
                "rationale": f"Employment {emp_id} belongs to track {trk}.",
                "projection_behavior": "graph_structure",
                "external_claim_policy": "approved_by_graph_presence",
                "validation_status": "validated",
                "edge_note": "",
                "operator_note": "",
                "business_story": "",
                "technical_story": "",
                "assertion_type": "TAXONOMIC_ATTRIBUTION",
                "assertion_basis": "operator_confirmation",
                "assertion_basis_refs_json": json.dumps([f"employment:{emp_id}", f"track:{trk}"]),
                "canonical_assertion_text": f"Employment {emp_id} is aligned to {trk}.",
                "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                "origin_kind": "derived_projection",
                "origin_ref": f"{emp_id}->{trk}",
                "origin_artifact_sha256": "",
                "derivation_rule_id": "rule_employment_track_attribution",
                "build_run_id": build_run_id,
                "confidence_score": 0.95,
                "confidence_tier": "HIGH",
                "confidence_method": "deterministic_track_attribution",
                "traversable": 1,
            }
        )

    return edges


def build_pillar_containment_edges(
    pillar_skills_map: dict[str, list[str]],
    *,
    ts: str = "",
    build_run_id: str = "",
) -> list[dict[str, Any]]:
    """Build pillar_contains_skill edges so every pillar reaches >= 1 skill."""
    merged_map = dict(pillar_skills_map)
    if "pillar_enterprise_risk_controls" not in merged_map:
        merged_map["pillar_enterprise_risk_controls"] = ["skill_risk_enterprise_risk_controls"]
    if "pillar_trading_hpc" not in merged_map:
        merged_map["pillar_trading_hpc"] = ["skill_algo_trading_sub_ms_inference"]
    edges: list[dict[str, Any]] = []
    for pillar_id, skills in sorted(merged_map.items()):
        for sid in skills[:4]:
            eid = f"edge_pillar_contains_skill__{pillar_id}__{sid}"
            edges.append(
                {
                    "edge_id": eid,
                    "source_node_id": pillar_id,
                    "target_node_id": sid,
                    "edge_family": "pillar_skill",
                    "edge_type": "pillar_contains_skill",
                    "weight": 1.0,
                    "confidence": "HIGH",
                    "directional": 1,
                    "evidence_status": "approved_graph_ssot",
                    "section_fit": "ALL",
                    "source_authority": "augmented_skills_graph",
                    "rationale": f"Pillar {pillar_id} contains core skill {sid}.",
                    "projection_behavior": "graph_structure",
                    "external_claim_policy": "approved_by_graph_presence",
                    "validation_status": "validated",
                    "edge_note": "",
                    "operator_note": "",
                    "business_story": "",
                    "technical_story": "",
                    "assertion_type": "STRUCTURAL_CONTAINMENT",
                    "assertion_basis": "taxonomy_rule",
                    "assertion_basis_refs_json": json.dumps([f"pillar:{pillar_id}", f"skill:{sid}"]),
                    "canonical_assertion_text": f"Pillar {pillar_id} contains competency {sid}.",
                    "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                    "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                    "origin_kind": "derived_projection",
                    "origin_ref": f"{pillar_id}->{sid}",
                    "origin_artifact_sha256": "",
                    "derivation_rule_id": "rule_pillar_contains_skill",
                    "build_run_id": build_run_id,
                    "confidence_score": 0.95,
                    "confidence_tier": "HIGH",
                    "confidence_method": "deterministic_pillar_skill_containment",
                    "traversable": 1,
                }
            )
    return edges


def populate_stub_descriptions(
    node_rows: dict[str, dict[str, Any]],
    candidate_ledger_path: Path | None = None,
) -> None:
    """Populate descriptions for facts, concepts, and repo evidence from candidate ledger."""
    root = repository_root()
    p1 = root / "artifacts/apps_rg/fact_inventory/master_candidate_skills_fact_ledger_20260518T1100Z.json"
    p2 = root / "resume_graph_engine/artifacts/apps_rg/fact_inventory/master_candidate_skills_fact_ledger_20260518T1100Z.json"
    cand_path = candidate_ledger_path or (p1 if p1.is_file() else p2)
    if not cand_path.is_file():
        return

    try:
        cand_data = json.loads(cand_path.read_text(encoding="utf-8"))
        facts = cand_data.get("candidate_facts") or []
        fact_map = {f.get("candidate_fact_id"): f for f in facts if f.get("candidate_fact_id")}
    except Exception:
        return

    for nid, node in node_rows.items():
        ntype = node.get("node_type")
        if ntype == "fact" and nid in fact_map:
            cf = fact_map[nid]
            claim = str(cf.get("claim_text") or "").strip()
            company = str(cf.get("company") or "").strip()
            node["description"] = f"[{company}] {claim}" if company else claim
            node["label"] = str(cf.get("claim_text") or nid)[:80]
        elif ntype == "concept" and not node.get("description"):
            clean_term = nid.replace("concept_", "").replace("_", " ").title()
            node["description"] = f"Domain architecture concept: {clean_term}"
            node["label"] = clean_term
        elif ntype == "repo_evidence" and not node.get("description"):
            clean_repo = nid.replace("repo_", "").replace("_", " ").title()
            node["description"] = f"Production implementation evidence: {clean_repo}"
            node["label"] = clean_repo


def build_domain_hierarchy_edges(
    domain_ids: list[str],
    *,
    ts: str = "",
    build_run_id: str = "",
) -> list[dict[str, Any]]:
    """Build career_track_contains_capability_domain edges for unparented domains,
    and capability_domain_contains_skill for domain_reasoning_planning_decomposition."""
    edges: list[dict[str, Any]] = []

    domain_track_map = {
        # Track: Actuarial, Risk & Derivatives
        "domain_actuarial_foundation": "track_actuarial_risk_derivatives",
        "domain_enterprise_risk": "track_actuarial_risk_derivatives",
        "domain_legacy_matrix": "track_actuarial_risk_derivatives",
        "domain_banking_platform_responsible_ai": "track_actuarial_risk_derivatives",
        "domain_regulatory_governance": "track_actuarial_risk_derivatives",
        "domain_risk_management": "track_actuarial_risk_derivatives",
        # Track: Data, Tech, Cloud & ML
        "domain_partner_gtm": "track_data_tech_cloud_ml",
        "domain_revenue_operations": "track_data_tech_cloud_ml",
        "domain_commercial_expansion": "track_data_tech_cloud_ml",
        "domain_phase2_gtm_presales": "track_data_tech_cloud_ml",
        "domain_phase2_technical_presales": "track_data_tech_cloud_ml",
        "domain_senior_role_w8_w11": "track_data_tech_cloud_ml",
        "domain_senior_role_w12_partner": "track_data_tech_cloud_ml",
        "domain_customer_stakeholder": "track_data_tech_cloud_ml",
        "domain_gtm_presales_motion": "track_data_tech_cloud_ml",
        "domain_insurance_core_modernization": "track_data_tech_cloud_ml",
        "domain_interoperability_integration_ecosystem": "track_data_tech_cloud_ml",
        "domain_strategic_finance_saas": "track_data_tech_cloud_ml",
        # Track: GenAI & Agentic AI
        "domain_agentic_runtime_routing_dispatch": "track_genai_agentic",
        "domain_agentic_multi_agent_orchestration": "track_genai_agentic",
        "domain_agentic_context_graph_grounding": "track_genai_agentic",
        "domain_agentic_tool_sandbox_controls": "track_genai_agentic",
        "domain_agentic_runtime_gate_verdicts": "track_genai_agentic",
        "domain_agentic_human_override_escalation": "track_genai_agentic",
        "domain_agentic_replay_audit_manifests": "track_genai_agentic",
        "domain_agentic_runtime_proof_lineage": "track_genai_agentic",
        # C03 Hardening Domains
        "capability_metric_heterogeneity_selection": "track_data_tech_cloud_ml",
        "capability_reverse_graph_traversal": "track_data_tech_cloud_ml",
        "capability_sibling_rejection_receipts": "track_data_tech_cloud_ml",
    }

    for did in sorted(domain_ids):
        trk = domain_track_map.get(did)
        if trk:
            eid = f"edge_career_track_contains_capability_domain__{trk}__{did}"
            edges.append(
                {
                    "edge_id": eid,
                    "source_node_id": trk,
                    "target_node_id": did,
                    "edge_family": "track_domain",
                    "edge_type": "career_track_contains_capability_domain",
                    "weight": 1.0,
                    "confidence": "HIGH",
                    "directional": 1,
                    "evidence_status": "approved_graph_ssot",
                    "section_fit": "ALL",
                    "source_authority": "augmented_skills_graph",
                    "rationale": f"Career track {trk} contains capability domain {did}.",
                    "projection_behavior": "graph_structure",
                    "external_claim_policy": "approved_by_graph_presence",
                    "validation_status": "validated",
                    "edge_note": "",
                    "operator_note": "",
                    "business_story": "",
                    "technical_story": "",
                    "assertion_type": "STRUCTURAL_CONTAINMENT",
                    "assertion_basis": "taxonomy_rule",
                    "assertion_basis_refs_json": json.dumps([f"track:{trk}", f"domain:{did}"]),
                    "canonical_assertion_text": f"Career track {trk} contains capability domain {did}.",
                    "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                    "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                    "origin_kind": "derived_projection",
                    "origin_ref": f"{trk}->{did}",
                    "origin_artifact_sha256": "",
                    "derivation_rule_id": "rule_track_domain_containment",
                    "build_run_id": build_run_id,
                    "confidence_score": 0.95,
                    "confidence_tier": "HIGH",
                    "confidence_method": "deterministic_track_domain_hierarchy",
                    "traversable": 1,
                }
            )

    # Reasoning / planning domain skill edge
    edges.append(
        {
            "edge_id": "edge_capability_domain_contains_skill__domain_reasoning_planning_decomposition__skill_agentic_control_plane_design",
            "source_node_id": "domain_reasoning_planning_decomposition",
            "target_node_id": "skill_agentic_control_plane_design",
            "edge_family": "domain_skill",
            "edge_type": "capability_domain_contains_skill",
            "weight": 1.0,
            "confidence": "HIGH",
            "directional": 1,
            "evidence_status": "approved_graph_ssot",
            "section_fit": "ALL",
            "source_authority": "augmented_skills_graph",
            "rationale": "Reasoning domain contains control plane design skill.",
            "projection_behavior": "graph_structure",
            "external_claim_policy": "approved_by_graph_presence",
            "validation_status": "validated",
            "edge_note": "",
            "operator_note": "",
            "business_story": "",
            "technical_story": "",
            "assertion_type": "STRUCTURAL_CONTAINMENT",
            "assertion_basis": "taxonomy_rule",
            "assertion_basis_refs_json": json.dumps(
                ["domain:domain_reasoning_planning_decomposition", "skill:skill_agentic_control_plane_design"]
            ),
            "canonical_assertion_text": "Reasoning and planning domain contains agentic control plane design skill.",
            "lifecycle_disposition": "ACTIVE_POLICY_GATED",
            "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
            "origin_kind": "derived_projection",
            "origin_ref": "domain_reasoning_planning_decomposition->skill_agentic_control_plane_design",
            "origin_artifact_sha256": "",
            "derivation_rule_id": "rule_domain_skill_containment",
            "build_run_id": build_run_id,
            "confidence_score": 0.95,
            "confidence_tier": "HIGH",
            "confidence_method": "deterministic_domain_skill_containment",
            "traversable": 1,
        }
    )

    # C03 Hardening capability domain skill edges
    c03_skill_bindings = [
        ("capability_metric_heterogeneity_selection", "skill_c03_metric_heterogeneity_selection"),
        ("capability_reverse_graph_traversal", "skill_c03_reverse_traversal_receipts"),
        ("capability_sibling_rejection_receipts", "skill_c03_sibling_skill_rejection_reasoning"),
    ]
    for c_dom, c_sk in c03_skill_bindings:
        edges.append(
            {
                "edge_id": f"edge_capability_domain_contains_skill__{c_dom}__{c_sk}",
                "source_node_id": c_dom,
                "target_node_id": c_sk,
                "edge_family": "domain_skill",
                "edge_type": "capability_domain_contains_skill",
                "weight": 1.0,
                "confidence": "HIGH",
                "directional": 1,
                "evidence_status": "approved_graph_ssot",
                "section_fit": "ALL",
                "source_authority": "augmented_skills_graph",
                "rationale": f"Hardening domain {c_dom} contains skill {c_sk}.",
                "projection_behavior": "graph_structure",
                "external_claim_policy": "approved_by_graph_presence",
                "validation_status": "validated",
                "edge_note": "",
                "operator_note": "",
                "business_story": "",
                "technical_story": "",
                "assertion_type": "STRUCTURAL_CONTAINMENT",
                "assertion_basis": "taxonomy_rule",
                "assertion_basis_refs_json": json.dumps([f"domain:{c_dom}", f"skill:{c_sk}"]),
                "canonical_assertion_text": f"Capability domain {c_dom} contains competency {c_sk}.",
                "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                "semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v2",
                "origin_kind": "derived_projection",
                "origin_ref": f"{c_dom}->{c_sk}",
                "origin_artifact_sha256": "",
                "derivation_rule_id": "rule_domain_skill_containment",
                "build_run_id": build_run_id,
                "confidence_score": 0.95,
                "confidence_tier": "HIGH",
                "confidence_method": "deterministic_domain_skill_containment",
                "traversable": 1,
            }
        )

    return edges


__all__ = [
    "build_fact_hosting_edges",
    "build_employment_hierarchy_edges",
    "build_pillar_containment_edges",
    "populate_stub_descriptions",
    "build_domain_hierarchy_edges",
]
