"""Career-phase (epoch) wiring migration for the master skills arsenal ledger.

Completes the epoch/phase layer across skills, employment nodes, and edges:
  1. Remap the 8 legacy-epoch skills to canonical epochs.
  2. Move the 6 P6 productization/commercialization skills to Phase 6 (epoch_ai_platform_commercialization).
  3. Assign phase_ordinal 1..6 to all skill_rows and graph_nodes skill stubs.
  4. Assign phase_ordinal to the 6 career_epoch nodes, set activation_status='ACTIVE', confidence='HIGH'.
  5. Assign min_phase/max_phase to the 5 employment nodes.
  6. Reconcile and wire canonical epoch_contains_skill edges (source=epoch, target=skill) with
     confidence='HIGH', edge_semantic_status='HARDENED', and lifecycle_disposition='ACTIVE_POLICY_GATED'.
  7. Update graph_metadata node_count and edge_count, ensuring collect_canonical_graph_issues passes.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    collect_canonical_graph_issues,
)

LEDGER = Path(__file__).resolve().parent / "master_skills_arsenal_ledger.json"

EPOCH_ORDINAL: dict[str, int] = {
    "epoch_actuarial_financial_engineering": 1,
    "epoch_enterprise_risk_governance": 2,
    "epoch_cloud_data_platform_engineering": 3,
    "epoch_partner_gtm_revenue_leadership": 4,
    "epoch_agentic_ai_runtime_architecture": 5,
    "epoch_ai_platform_commercialization": 6,
}

EPOCH_LABELS: dict[str, str] = {
    "epoch_actuarial_financial_engineering": "Actuarial & Financial Engineering",
    "epoch_enterprise_risk_governance": "Enterprise Risk & Governance",
    "epoch_cloud_data_platform_engineering": "Cloud & Data Platform Engineering",
    "epoch_partner_gtm_revenue_leadership": "Partner GTM & Revenue Leadership",
    "epoch_agentic_ai_runtime_architecture": "Agentic AI Runtime Architecture",
    "epoch_ai_platform_commercialization": "AI Platform Commercialization",
}

P6_SKILLS: set[str] = {
    "skill_agentic_platform_productization",
    "skill_reusable_ai_ip_design",
    "skill_app_specific_runtime_overlay_design",
    "skill_enterprise_workflow_adoption",
    "skill_operating_model_for_agentic_ai",
    "skill_ai_platform_commercialization",
}

LEGACY_SKILL_EPOCHS: dict[str, str] = {
    "skill_meddpicc_sales_qualification": "epoch_partner_gtm_revenue_leadership",
    "skill_cpq_deal_velocity_automation": "epoch_ai_platform_commercialization",
    "skill_soc2_zero_trust_security": "epoch_enterprise_risk_governance",
    "skill_saas_arr_ltv_cac_metrics": "epoch_ai_platform_commercialization",
    "skill_confluent_streaming_platforms": "epoch_cloud_data_platform_engineering",
    "skill_watson_studio_fraud_aml": "epoch_cloud_data_platform_engineering",
    "skill_nps_customer_health_scoring": "epoch_ai_platform_commercialization",
    "skill_credit_adjudication_default_risk": "epoch_enterprise_risk_governance",
}

EMPLOYMENT_PHASES: dict[str, tuple[int, int]] = {
    "employment_exp_early_career_001": (1, 1),
    "employment_exp_ey_001": (2, 2),
    "employment_exp_insurtech_001": (3, 3),
    "employment_exp_ibm_001": (3, 4),
    "employment_exp_unify_001": (5, 6),
}


def main() -> None:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    changes: Counter[str] = Counter()

    # 1. Remap legacy skills, move P6 skills, stamp phase_ordinal on skill_rows.
    for s in data["skill_rows"]:
        sid = s.get("skill_id")
        if sid in LEGACY_SKILL_EPOCHS:
            s["career_epoch"] = LEGACY_SKILL_EPOCHS[sid]
            changes["legacy_epochs_remapped"] += 1
        elif sid in P6_SKILLS and s.get("career_epoch") != "epoch_ai_platform_commercialization":
            s["career_epoch"] = "epoch_ai_platform_commercialization"
            changes["p6_moved"] += 1
        s["phase_ordinal"] = EPOCH_ORDINAL.get(s.get("career_epoch"))
        changes["skill_rows_tagged"] += 1

    skill_epoch = {
        s["skill_id"]: (s.get("career_epoch"), s.get("phase_ordinal"))
        for s in data["skill_rows"]
        if s.get("skill_id")
    }

    # 2. Update graph_nodes: epochs, employments, skill stubs.
    for n in data["graph_nodes"]:
        nt = n.get("node_type")
        nid = n.get("node_id")
        if nt == "career_epoch":
            n["phase_ordinal"] = EPOCH_ORDINAL.get(nid)
            n["activation_status"] = "ACTIVE"
            n["confidence"] = "HIGH"
            changes["epochs_activated"] += 1
        elif nt == "employment":
            phases = EMPLOYMENT_PHASES.get(nid)
            if phases:
                n["min_phase"], n["max_phase"] = phases
                changes["employments_phased"] += 1
        elif nt in ("skill", "skill_row"):
            epoch, ordinal = skill_epoch.get(nid, (None, None))
            if epoch is not None:
                n["career_epoch"] = epoch
                n["phase_ordinal"] = ordinal
                changes["graph_stubs_tagged"] += 1

    # 3. Canonical epoch_contains_skill edges.
    # Keep non-epoch edges and deduplicate epoch_contains_skill by skill_id.
    non_epoch_edges: list[dict] = []
    for e in data["graph_edges"]:
        if e.get("edge_type") == "epoch_contains_skill":
            continue
        non_epoch_edges.append(e)

    # Re-wire canonical epoch_contains_skill edges for all eligible skills.
    new_epoch_edges: list[dict] = []
    for sid, (epoch, ordinal) in sorted(skill_epoch.items()):
        if not epoch or epoch not in EPOCH_ORDINAL:
            continue
        epoch_label = EPOCH_LABELS.get(epoch, epoch)
        edge_id = f"edge_epoch_contains_skill_{epoch}_{sid}"[:200]
        new_epoch_edges.append(
            {
                "edge_id": edge_id,
                "edge_type": "epoch_contains_skill",
                "source_node_id": epoch,
                "target_node_id": sid,
                "weight": 1.0,
                "confidence": "HIGH",
                "rationale": f"The {epoch_label} career epoch contains skill {sid}.",
                "projection_behavior": "epoch_filter",
                "external_claim_policy": "skill_projection_not_proof",
                "validation_status": "validated",
                "edge_semantic_contract_version": "apps_rg.c03_graph_edge_semantic_contract.v1",
                "canonical_assertion_text": (
                    f"The {epoch_label} epoch classifies {sid} within career phase {ordinal} "
                    f"according to canonical skill-row career_epoch; membership scopes chronology "
                    f"and does not independently prove a claim."
                ),
                "assertion_basis": "source_field_derivation",
                "assertion_basis_refs": [
                    f"ledger:graph_nodes/{epoch}",
                    f"ledger:skill_rows/{sid}/career_epoch",
                ],
                "edge_semantic_status": "HARDENED",
                "lifecycle_disposition": "ACTIVE_POLICY_GATED",
                "hardening_wave": "C03_CLUSTER_EMBEDDING_W2",
            }
        )
        changes["canonical_epoch_edges"] += 1

    data["graph_edges"] = non_epoch_edges + new_epoch_edges

    # 4. Update graph_metadata.
    data["graph_metadata"]["node_count"] = len(data["graph_nodes"])
    data["graph_metadata"]["edge_count"] = len(data["graph_edges"])

    # 5. Validate integrity.
    issues = collect_canonical_graph_issues(data)
    if issues:
        raise ValueError(f"Reconciled ledger failed canonical validation: {issues[:10]}")

    LEDGER.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    phase_counts = Counter(s.get("phase_ordinal") for s in data["skill_rows"])
    print("CAREER-PHASE WIRING — COMPLETE & RECONCILED")
    for key, val in sorted(changes.items()):
        print(f"  {key}: {val}")
    print("  phase distribution (skill_rows):")
    for phase in (1, 2, 3, 4, 5, 6, None):
        label = f"P{phase}" if phase else "cross_career"
        print(f"    {label}: {phase_counts.get(phase, 0)}")
    print(f"  nodes: {len(data['graph_nodes'])}, edges: {len(data['graph_edges'])}")


if __name__ == "__main__":
    main()

