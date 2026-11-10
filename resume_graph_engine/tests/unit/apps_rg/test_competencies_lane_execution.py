"""Unit tests for Wave 3: Executive Summary diversity, Competencies clean splicing & Bullet metrics."""
from __future__ import annotations

from apps_rg.runtime.assembly.competencies_display import (
    competency_display_rows,
    render_competencies,
)
from apps_rg.runtime.c0.competencies_graph_authority import (
    normalize_competency_surface_term,
)
from apps_rg.runtime.c0.resume_graph_allocation import (
    _default_slot_specs,
    allocate_candidate_sets,
)
from apps_rg.runtime.sections.competencies_lane_execution import (
    _ensure_allocation_plan_coverage,
)
from apps_rg.runtime.sections.role_episode_lane import (
    _repair_role_episode_bullet_evidence_density,
    _role_episode_evidence_block,
)


def test_normalize_competency_surface_term_lowercases_non_acronyms_and_preserves_acronyms() -> None:
    assert (
        normalize_competency_surface_term("Enterprise solution architecture mapping for pursuits")
        == "enterprise solution architecture mapping for pursuits"
    )
    assert (
        normalize_competency_surface_term("Revenue target execution and quota-aligned solution leadership")
        == "revenue target execution and quota-aligned solution leadership"
    )
    assert (
        normalize_competency_surface_term("Quota-aligned enterprise deal support and execution")
        == "quota-aligned enterprise deal support and execution"
    )
    # Acronyms must remain capitalized
    assert (
        normalize_competency_surface_term("AWS alliance modernization co-sell and joint development")
        == "AWS alliance modernization co-sell and joint development"
    )
    assert (
        normalize_competency_surface_term("SOC2 zero-trust security controls for compliance")
        == "SOC2 zero-trust security controls for compliance"
    )
    assert (
        normalize_competency_surface_term("GraphRAG context pack grounding for governed execution")
        == "GraphRAG context pack grounding for governed execution"
    )


def test_ensure_allocation_plan_coverage_eliminates_midline_capitalized_splices_and_orders_insurance_it() -> None:
    parsed = {
        "competencies": [
            {
                "category_id": "cloud_partner_ecosystems",
                "category_label": "Cloud & Partner Ecosystems",
                "resume_display_label": "Partner Applied AI Architecture",
                "terms": [
                    {"text": "partner-ready applied AI reference architectures"},
                    {"text": "Enterprise solution architecture mapping for pursuits"},
                    {"text": "Enterprise cloud modernization portfolio architecture assets"},
                ],
            },
            {
                "category_id": "ai_platform_leadership",
                "category_label": "AI Platform Leadership",
                "resume_display_label": "Governed Agentic AI Platform Architecture",
                "terms": [
                    {"text": "governed multi-agent orchestration control planes"},
                    {"text": "Agentic platform route-policy dispatch architecture"},
                    {"text": "reusable accelerator assets for agentic platforms"},
                ],
            },
            {
                "category_id": "governance_risk_compliance",
                "category_label": "Governance, Risk & Compliance",
                "resume_display_label": "Model Risk Governance & AI Runtime Control Gates",
                "terms": [
                    {"text": "fail-closed policy authorization gates for runtime execution"},
                    {"text": "Enterprise BCBS239 risk data aggregation governance"},
                    {"text": "Enterprise credit adjudication default risk governance"},
                ],
            },
            {
                "category_id": "data_analytics_modernization",
                "category_label": "Data & Analytics Modernization",
                "resume_display_label": "Distributed Systems & Cloud Data Engineering",
                "terms": [
                    {"text": "regulated cloud-native data architecture reference patterns"},
                    {"text": "Databricks lakehouse architectures for AWS engineering"},
                    {"text": "AWS migration and modernization for regulated workloads"},
                ],
            },
            {
                "category_id": "tech_strategy_innovation",
                "category_label": "Technology Strategy & Innovation",
                "resume_display_label": "GraphRAG, Hybrid Retrieval & Context Engineering",
                "terms": [
                    {"text": "relationship-grounded context retrieval for enterprise workflows"},
                    {"text": "Dense-sparse retrieval execution for evidence grounding"},
                    {"text": "GraphRAG context pack grounding for governed execution"},
                ],
            },
            {
                "category_id": "engineering_delivery_leadership",
                "category_label": "Engineering & Delivery Leadership",
                "resume_display_label": "Engineering Leadership & Operating Model",
                "terms": [
                    {"text": "enterprise operating model for governed agentic delivery"},
                    {"text": "Revenue target execution and quota-aligned solution leadership"},
                    {"text": "Quota-aligned enterprise deal support and execution"},
                ],
            },
        ],
        "claim_ledger": [
            {"claim_text": "Enterprise solution architecture mapping for pursuits", "source_fact_ids": ["f1"]},
        ],
    }
    _ensure_allocation_plan_coverage(
        parsed,
        selected_plan={"target_role_profile": "insurance_it_strategy"},
    )
    rows = competency_display_rows(
        {
            **parsed,
            "selected_fact_plan": {"target_role_profile": "insurance_it_strategy"},
        }
    )
    assert rows[0][0] == "Governed Agentic AI Platform Architecture"
    assert rows[-1][0] == "Partner Applied AI Architecture"
    rendered = render_competencies(
        {
            **parsed,
            "selected_fact_plan": {"target_role_profile": "insurance_it_strategy"},
        }
    )
    assert ", Enterprise " not in rendered
    assert ", Revenue " not in rendered
    assert ", Quota-aligned " not in rendered


def test_executive_summary_prevents_duplicate_aws_migration_roots_and_unify_metric_required() -> None:
    slots = [
        {"slot_id": "executive_summary:claim:01", "section_id": "executive_summary", "metric_required": False},
        {"slot_id": "executive_summary:claim:02", "section_id": "executive_summary", "metric_required": False},
        {"slot_id": "executive_summary:claim:03", "section_id": "executive_summary", "metric_required": False},
    ]
    candidates_by_slot = {
        "executive_summary:claim:01": [
            {
                "claim_id": "c1",
                "skill_id": "skill_1",
                "root_id": "reb_insurtech_aws_migration_execution",
                "fact_id": "fact_1",
                "source_family": "insurtech:r1",
                "graph_path_ids": ["p1"],
                "edge_ids": ["e1"],
                "citation_refs": ["ref1"],
                "authority_pass": True,
                "selection_rank": 1,
            }
        ],
        "executive_summary:claim:02": [
            {
                "claim_id": "c2",
                "skill_id": "skill_2",
                "root_id": "reb_ibm_aws_modernization_architecture",
                "fact_id": "fact_2",
                "source_family": "ibm:r2",
                "graph_path_ids": ["p2"],
                "edge_ids": ["e2"],
                "citation_refs": ["ref2"],
                "authority_pass": True,
                "selection_rank": 1,
            },
            {
                "claim_id": "c3",
                "skill_id": "skill_3",
                "root_id": "reb_slalom_governed_runtime_scaling",
                "fact_id": "fact_3",
                "source_family": "slalom:r3",
                "graph_path_ids": ["p3"],
                "edge_ids": ["e3"],
                "citation_refs": ["ref3"],
                "authority_pass": True,
                "selection_rank": 2,
            },
        ],
        "executive_summary:claim:03": [
            {
                "claim_id": "c4",
                "skill_id": "skill_4",
                "root_id": "reb_ey_capital_optimization_solvency",
                "fact_id": "fact_4",
                "source_family": "ey:r4",
                "graph_path_ids": ["p4"],
                "edge_ids": ["e4"],
                "citation_refs": ["ref4"],
                "authority_pass": True,
                "selection_rank": 1,
            }
        ],
    }
    plan = allocate_candidate_sets(
        slot_specs=slots,
        candidate_sets=candidates_by_slot,
        graph_digest="g1",
        policy_digest="p1",
    )
    exec_roots = {row["root_id"] for row in plan["assignments"]}
    assert not (
        {"reb_insurtech_aws_migration_execution", "reb_ibm_aws_modernization_architecture"} <= exec_roots
    )

    section_plans = {
        "unify_bullets": {
            "unify_bullet_slot_bundle_map_resolved": {
                f"bul_unify_00{i}": f"reb_unify_root_{i}" for i in range(1, 7)
            },
            "graph_candidate_decision_ledger": [
                {
                    "candidate_type": "metric_outcome",
                    "root_id": "reb_unify_root_1",
                    "candidate_id": "m_unify_1",
                    "metric": "$3M+ partner-sourced revenue",
                    "authority_pass": True,
                },
                {
                    "candidate_type": "metric_outcome",
                    "root_id": "reb_unify_root_2",
                    "candidate_id": "m_unify_2",
                    "metric": "qualitative governance outcome without numbers",
                    "authority_pass": True,
                },
            ],
        }
    }
    spec_rows = _default_slot_specs(section_plans)
    unify_by_slot = {r["slot_id"]: r for r in spec_rows if r["section_id"] == "unify_bullets"}
    assert unify_by_slot["unify_bullets:bul_unify_001"]["metric_required"] is True
    assert unify_by_slot["unify_bullets:bul_unify_002"]["metric_required"] is False


def test_role_episode_evidence_block_and_slalom_100pct_metric_injection() -> None:
    runtime_payload = {
        "proof_pool_metadata": {
            "role_episode_bundles": [
                {
                    "role_episode_bundle_id": "reb_slalom_governed_runtime_scaling",
                    "bullet_intent": "Governed runtime scaling and safety validation mesh",
                    "bound_skills": [
                        {
                            "skill_id": "skill_runtime_gate_mesh_design",
                            "activation_status": "ACTIVE_CONFIRMED",
                            "allowed_phrases": ["deterministic gate mesh"],
                        }
                    ],
                }
            ]
        },
        "selected_fact_plan": {
            "allocation_assignments": [
                {
                    "section_id": "slalom_bullets",
                    "claim_unit_id": "bul_slalom_003",
                    "root_id": "reb_slalom_governed_runtime_scaling",
                    "metric_outcome_id": "metric_slalom_validation_gate_mesh_conformance_pct",
                    "metric_text": "100% deterministic gate mesh conformance for safety-critical agent decisions",
                }
            ]
        },
    }
    block = _role_episode_evidence_block(runtime_payload)
    assert "metric_slalom_validation_gate_mesh_conformance_pct" in block
    assert "100% deterministic gate mesh conformance for safety-critical agent decisions" in block

    bullets, repairs = _repair_role_episode_bullet_evidence_density(
        [
            {
                "bullet_id": "bul_slalom_003",
                "bullet_text": "Designed a governed runtime scaling framework incorporating deterministic proof lineage and a safety validation mesh, establishing auditable controls.",
                "source_fact_ids": ["bul_slalom_003"],
            }
        ],
        facts=[
            {
                "fact_id": "bul_slalom_003",
                "role_episode_bundle_id": "reb_slalom_governed_runtime_scaling",
            }
        ],
    )
    assert "100%" in bullets[0]["bullet_text"]
    assert repairs
