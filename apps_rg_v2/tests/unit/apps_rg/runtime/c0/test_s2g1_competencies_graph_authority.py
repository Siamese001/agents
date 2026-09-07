"""apps-test-model: LAW. S2G1 competencies graph-authority closure."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from apps_rg.runtime.c0.competencies_graph_authority import (
    _ALLOCATION_VISIBLE_SURFACE_COMPOSITIONS,
    _INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT,
    _allocation_surface_category,
    _allocation_surface_phrase,
    build_competencies_graph_authority_discrepancy_ledger,
    insurance_it_strategy_frozen_layout_is_present,
    materialize_unmatched_competencies_allocation_terms,
    project_insurance_it_strategy_competencies_from_frozen_allocation,
    reconcile_competencies_allocation_claim_units,
    synchronize_competencies_allocation_bindings_to_categories,
)
from apps_rg.runtime.c0.resume_graph_allocation import (
    allocate_candidate_sets,
    canonical_allocation_digest,
    slice_section_plan_for_allocation,
)
from apps_rg.runtime.c0.resume_graph_claim_binding import (
    bind_final_claims_to_resume_graph_allocation,
)
from apps_rg.runtime.claim_ledger.canonical_exec_summary_v2 import (
    build_canonical_claim_ledger_v2_payload,
    normalize_exec_summary_claim_ledger,
)
from apps_rg.runtime.spine.c0_fec_compose import (
    SectionFecBridge,
    _bind_allocation_authority_fields,
)
from apps_rg.runtime.validators.competencies_quality_x2 import (
    _build_traversal_sufficiency_receipt,
    _role_axis_coverage,
)
from apps_rg.runtime.validators.competencies_x2 import (
    find_bullet_restatement_term,
    run_competencies_x2_gates,
)
from apps_rg.runtime.sections.competencies_rigor import (
    check_competencies_keyword_repetition_limit,
    check_competencies_visible_terms_svp_agentic_richness,
)


def test_anthropic_alliance_allocation_has_bound_compact_surface() -> None:
    assignment = {
        "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_id": "skill_partner_alliance_gtm_execution",
        "root_bundle_theme": "AWS partnership, alliance co-sell, and joint GTM execution",
        "root_claim_outcome": (
            "Frame as alliance GTM leadership: joint planning, solution architecture, "
            "and co-sell execution."
        ),
        "skill_label": "Partner alliance GTM execution",
        "source_refs": [],
    }
    selected_plan = {
        "facts": [
            {
                "fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "role_episode_bundle_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "domain": "AWS partnership, alliance co-sell, and joint GTM execution",
            }
        ],
        "graph_candidate_decision_ledger": [],
    }

    phrase, source = _allocation_surface_phrase(
        assignment,
        selected_plan=selected_plan,
    )

    assert phrase == "AWS alliance joint architecture leadership"
    assert source == "graph_authority_surface_composition"


def test_runtime_proof_allocation_avoids_deterministic_x2_self_block() -> None:
    assignment = {
        "root_id": "reb_unify_agentic_platform_architecture",
        "skill_id": "skill_unify_agentic_runtime_proof_bundle_lineage",
        "root_bundle_theme": "SVP Engineering agentic AI platform control-plane architecture",
        "root_claim_scope": "Runtime proof-bundle lineage for governed execution.",
        "skill_label": "Runtime proof-bundle lineage",
        "source_refs": [],
    }
    selected_plan = {
        "facts": [
            {
                "fact_id": "fact_engineering_platform_001",
                "role_episode_bundle_id": "reb_unify_agentic_platform_architecture",
                "domain": assignment["root_bundle_theme"],
                "claim_text": assignment["root_bundle_theme"],
            }
        ],
        "graph_candidate_decision_ledger": [],
    }

    phrase, source = _allocation_surface_phrase(assignment, selected_plan=selected_plan)
    categories = [
        {
            "terms": [
                {"text": phrase},
                {"text": "agentic workflow routing across enterprise systems"},
                {"text": "Agentic platform route-policy dispatch architecture"},
                {"text": "production reliability lifecycle for agentic workflows"},
            ]
        }
    ]

    assert phrase == "Runtime proof-bundle lineage for platforms"
    assert source == "graph_authority_surface_composition"
    assert check_competencies_keyword_repetition_limit(categories) == (True, None)
    assert find_bullet_restatement_term(
        categories,
        ["svp engineering agentic ai platform control-plane architecture"],
    ) is None
    gates = run_competencies_x2_gates(
        competencies=categories,
        parsed_output={
            "competencies": categories,
            "selected_fact_plan": {"selected_fact_ids": ["fact_engineering_platform_001"]},
        },
        claim_ledger=[],
        jd_text="",
        bullet_texts_lower=["svp engineering agentic ai platform control-plane architecture"],
        resume_support_blob="agentic workflow runtime platform architecture proof bundle lineage",
        allowed_fact_ids={"fact_engineering_platform_001"},
        runtime_generation_status="REAL_LLM",
    )
    assert all(
        gate.pass_
        for gate in gates
        if gate.gate_id
        in {
            "x2_competencies_keyword_repetition_limit",
            "x2_no_bullet_outcome_restatement",
            "x2_no_keyword_stuffing",
        }
    )


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _allocation_bundle() -> tuple[dict[str, object], dict[str, object]]:
    slots: list[dict[str, object]] = []
    candidates: dict[str, list[dict[str, object]]] = {}
    for index in range(1, 9):
        slot_id = f"competencies:skill:{index:02d}"
        root_id = "root_partner_cosell_04" if index == 4 else f"root_{index:02d}"
        skill_id = f"skill_domain_{index:02d}"
        fact_id = f"fact_{index:02d}"
        slots.append(
            {"slot_id": slot_id, "section_id": "competencies", "metric_required": False}
        )
        candidates[slot_id] = [
            {
                "candidate_id": f"candidate_{index:02d}",
                "section_id": "competencies",
                "claim_unit_id": slot_id,
                "skill_id": skill_id,
                "fact_id": fact_id,
                "metric_outcome_id": "",
                "root_id": root_id,
                "authority_pass": True,
                "proof_strength_raw": 1.0,
                "target_alignment_score": 1.0,
                "claim_entailment_score": 1.0,
                "path_confidence_raw": 1.0,
                "source_independence_score": 1.0,
                "employer_lane": "unify",
                "source_family": "unify",
                "graph_path_ids": [
                    f"root:{root_id}",
                    f"root:{root_id}/skill:{skill_id}",
                    f"root:{root_id}/fact:{fact_id}",
                ],
                "edge_ids": [f"edge:{root_id}:{skill_id}"],
                "citation_refs": [f"source:{fact_id}"],
            }
        ]
    allocation = allocate_candidate_sets(
        candidate_sets=candidates,
        slot_specs=slots,
        graph_digest="g" * 64,
        policy_digest="p" * 64,
        max_fact_reuse=1,
        max_source_family_share=1.0,
    )
    section_plan: dict[str, object] = {
        "section_id": "competencies",
        "facts": [],
        "selected_skills": [],
        "selected_skill_ids": [],
        "selected_metrics_detail": [],
        "selected_metrics": [],
        "selected_edges": [],
        "graph_candidate_decision_ledger": [],
        "target_role_profile": "ai_partnerships_gtm",
    }
    for index in range(1, 9):
        root_id = "root_partner_cosell_04" if index == 4 else f"root_{index:02d}"
        skills = [f"skill_domain_{index:02d}", f"skill_sibling_{index:02d}"]
        if index == 4:
            skills[1] = "skill_sr_w12_hyperscaler_alliance_co_sell"
        metric_id = f"metric_{index:02d}"
        section_plan["facts"].append(
            {
                "fact_id": root_id,
                "role_episode_bundle_id": root_id,
                "graph_skill_node_ids": skills,
                "metric_outcome_ids": [metric_id],
                "linked_source_fact_ids": [f"fact_{index:02d}"],
            }
        )
        for skill_id in skills:
            section_plan["selected_skills"].append(
                {"skill_id": skill_id, "role_episode_bundle_id": root_id}
            )
            section_plan["selected_skill_ids"].append(skill_id)
        section_plan["selected_metrics_detail"].append(
            {
                "metric_outcome_id": metric_id,
                "role_episode_bundle_id": root_id,
                "metric": f"authorized outcome {index:02d}",
            }
        )
        section_plan["selected_metrics"].append(metric_id)
        section_plan["graph_candidate_decision_ledger"].append(
            {
                "candidate_id": skills[0],
                "candidate_type": "leaf_skill",
                "root_id": root_id,
                "candidate_path_id": f"root:{root_id}/skill:{skills[0]}",
                "path_signature": f"{root_id}->contains->{skills[0]}",
                "decision": "selected",
                "authority_pass": True,
                "reason_codes": ["selected_by_authority"],
                "linked_source_fact_ids": [f"fact_{index:02d}"],
            }
        )
    return allocation, section_plan


def _slice(monkeypatch: object) -> dict[str, object]:
    from apps_rg.runtime.c0 import c03_resume_graph_contracts

    monkeypatch.setattr(c03_resume_graph_contracts, "finalize_canonical_section_plan", dict)
    allocation, section_plan = _allocation_bundle()
    contract = {
        "section_id": "competencies",
        "allocation_plan_digest": allocation["allocation_plan_digest"],
    }
    return slice_section_plan_for_allocation(
        section_plan=section_plan,
        allocation_plan=allocation,
        final_evidence_contract=contract,
        section_id="competencies",
    )


def _parsed_for_plan(plan: dict[str, object]) -> dict[str, object]:
    categories = []
    for assignment in plan["allocation_assignments"]:
        categories.append(
            {
                "category_id": assignment["claim_unit_id"],
                "source_fact_ids": [assignment["fact_id"]],
                "graph_skill_node_ids": [assignment["skill_id"]],
                "terms": [
                    {
                        "text": str(assignment["skill_id"]).replace("skill_", "").replace("_", " "),
                        "source_fact_id": assignment["fact_id"],
                        "source_fact_ids": [assignment["fact_id"]],
                        "source_skill_ids": [assignment["skill_id"]],
                    }
                ],
            }
        )
    return {"competencies": categories, "claim_ledger": []}


def _insurance_it_strategy_projection_fixture() -> tuple[dict[str, object], dict[str, object], set[str]]:
    """A full frozen allocation with source-bound display anchors."""

    assignments: list[dict[str, object]] = []
    facts_by_root: dict[str, dict[str, object]] = {}
    stale_fact_id = "fact_stale_preprojection_category"
    allowed: set[str] = {stale_fact_id}
    claim_number = 0
    for spec in _INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT:
        for root_id, skill_id in spec["assignment_keys"]:
            claim_number += 1
            fact_id = f"fact_projection_{root_id}"
            phrase = _ALLOCATION_VISIBLE_SURFACE_COMPOSITIONS[(root_id, skill_id)]
            allowed.add(fact_id)
            facts_by_root.setdefault(
                root_id,
                {
                    "role_episode_bundle_id": root_id,
                    "fact_id": fact_id,
                    "graph_skill_node_ids": [],
                    "claim_text": phrase,
                },
            )
            facts_by_root[root_id]["graph_skill_node_ids"].append(skill_id)
            assignments.append(
                {
                    "section_id": "competencies",
                    "claim_unit_id": f"competencies:section_only:{claim_number:02d}",
                    "root_id": root_id,
                    "skill_id": skill_id,
                    "fact_id": fact_id,
                    "root_bundle_theme": phrase,
                    "source_refs": [phrase],
                }
            )

    categories: list[dict[str, object]] = []
    for index, spec in enumerate(_INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT, start=1):
        root_id, _ = spec["assignment_keys"][0]
        fact_id = str(facts_by_root[root_id]["fact_id"])
        anchor_text = str(
            spec.get("generic_anchor_phrase") or f"fixture graph capability anchor {index}"
        )
        categories.append(
            {
                "category_id": spec["category_id"],
                "category_label": spec["category_label"],
                "competency_bundle_id": spec["competency_bundle_id"],
                "capability_family": f"fixture_family_{index}",
                # Existing generated categories can have broad, category-level
                # provenance. The final frozen-allocation projection must not
                # carry an unrelated (though otherwise allowed) source into a
                # newly regrouped competency.
                "source_fact_ids": [fact_id, stale_fact_id],
                "graph_skill_node_ids": [f"fixture_skill_{index}"],
                "confidence": 0.80 + (index / 100),
                "selection_score": 0.80 + (index / 100),
                "selector_confidence": 0.80 + (index / 100),
                "terms": [
                    {
                        "text": anchor_text,
                        "term": anchor_text,
                        "source_fact_id": fact_id,
                        "source_fact_ids": [fact_id],
                        "source_skill_ids": [f"fixture_skill_{index}"],
                        "graph_skill_node_ids": [f"fixture_skill_{index}"],
                    }
                ],
            }
        )
    plan: dict[str, object] = {
        "target_role_profile": "insurance_it_strategy",
        "allocation_plan_digest": "fixture-allocation-digest",
        "allocation_assignments": assignments,
        "facts": list(facts_by_root.values()),
    }
    parsed: dict[str, object] = {
        "categories": copy.deepcopy(categories),
        "competencies": copy.deepcopy(categories),
        "claim_ledger": [],
    }
    return plan, parsed, allowed


def test_stale_nested_seals_do_not_change_canonical_allocation_digest() -> None:
    allocation, _ = _allocation_bundle()
    baseline = canonical_allocation_digest(allocation)
    mutated = copy.deepcopy(allocation)
    mutated["selection_policy"] = {
        "policy": "same",
        "prior_seal": {"allocation_plan_digest": "stale"},
        "downstream_receipt": {"status": "stale"},
    }
    without_receipts = copy.deepcopy(mutated)
    without_receipts["selection_policy"] = {"policy": "same"}
    assert canonical_allocation_digest(mutated) == canonical_allocation_digest(without_receipts)
    assert baseline != canonical_allocation_digest(without_receipts)


def test_allocation_slice_separates_visible_paths_from_source_traversal(monkeypatch: object) -> None:
    plan = _slice(monkeypatch)
    source = plan["allocation_source_traversal_evidence"]
    assert len(plan["selected_skill_ids"]) == 8
    assert len(plan["selected_metrics"]) == 0
    assert source["scope"] == "C03_SOURCE_CANDIDATE_UNIVERSE"
    assert len(source["selected_skill_ids"]) == 16
    assert len(source["selected_metrics"]) == 8
    assert "skill_sr_w12_hyperscaler_alliance_co_sell" in source["selected_skill_ids"]


def test_x2_traversal_uses_source_candidate_universe_for_an_allocation_slice(
    monkeypatch: object,
) -> None:
    plan = _slice(monkeypatch)
    receipt = _build_traversal_sufficiency_receipt(
        proof_pool_metadata={"selected_graph_evidence_plan": plan},
        parsed_output={"competencies": []},
        category_count=0,
    )
    assert receipt["traversal_evidence_scope"] == "C03_SOURCE_CANDIDATE_UNIVERSE"
    assert receipt["selected_unique_leaf_skill_count"] == 16
    assert receipt["selected_unique_metric_count"] == 8


def test_ineligible_candidate_is_not_added_to_numeric_floors(monkeypatch: object) -> None:
    allocation, section_plan = _allocation_bundle()
    section_plan["graph_candidate_decision_ledger"].append(
        {
            "candidate_id": "skill_ineligible",
            "candidate_type": "leaf_skill",
            "root_id": "root_01",
            "decision": "rejected",
            "authority_pass": False,
        }
    )
    from apps_rg.runtime.c0 import c03_resume_graph_contracts

    monkeypatch.setattr(c03_resume_graph_contracts, "finalize_canonical_section_plan", dict)
    plan = slice_section_plan_for_allocation(
        section_plan=section_plan,
        allocation_plan=allocation,
        final_evidence_contract={
            "section_id": "competencies",
            "allocation_plan_digest": allocation["allocation_plan_digest"],
        },
        section_id="competencies",
    )
    assert "skill_ineligible" not in plan["selected_skill_ids"]


def test_role_axis_normalizes_cosell_root_identity() -> None:
    coverage = _role_axis_coverage(
        {
            "target_role_profile": "ai_partnerships_gtm",
            "selected_nodes": ["reb_ibm_aws_alliance_partner_cosell_gtm"],
            "selected_skill_ids": [
                "skill_partner_hyperscaler_cosell",
                "skill_partner_cloud_vendor_joint_gtm",
                "skill_partner_gtm_enablement",
                "skill_partner_solution_architecture",
            ],
        }
    )
    assert "co_sell" in coverage["covered_axes"]


def test_reconciliation_consumes_every_allocation_once(monkeypatch: object) -> None:
    plan = _slice(monkeypatch)
    parsed = _parsed_for_plan(plan)
    allowed = set(plan["allowed_graph_evidence_ids"])
    receipt = reconcile_competencies_allocation_claim_units(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=allowed,
    )
    explicit = [row["claim_unit_id"] for row in parsed["claim_ledger"]]
    assert receipt["pass"] is True
    assert len(explicit) == len(set(explicit)) == 8


def test_reconciliation_fails_closed_with_complete_unmatched_ledger(monkeypatch: object) -> None:
    plan = _slice(monkeypatch)
    parsed = {"competencies": [{"terms": [{"text": "unrelated"}]}]}
    receipt = reconcile_competencies_allocation_claim_units(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=set(plan["allowed_graph_evidence_ids"]),
    )
    assert receipt["pass"] is False
    assert len(receipt["unmatched_claim_unit_ids"]) == 8


def test_materialization_fails_closed_when_two_units_share_one_surface() -> None:
    """A duplicate phrase cannot falsely consume two allocation units."""

    assignments = [
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:01",
            "root_id": "reb_shared_delivery",
            "skill_id": "skill_delivery_one",
            "fact_id": "fact_shared_delivery",
            "root_bundle_theme": "Governed enterprise delivery workflow execution",
            "root_claim_text": "Governed enterprise delivery workflow execution",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:02",
            "root_id": "reb_shared_delivery",
            "skill_id": "skill_delivery_two",
            "fact_id": "fact_shared_delivery",
            "root_bundle_theme": "Governed enterprise delivery workflow execution",
            "root_claim_text": "Governed enterprise delivery workflow execution",
        },
    ]
    plan = {
        "allocation_plan_digest": "shared-surface-test",
        "allocation_assignments": assignments,
        "facts": [
            {
                "role_episode_bundle_id": "reb_shared_delivery",
                "bundle_theme": "Governed enterprise delivery workflow execution",
                "claim_text": "Governed enterprise delivery workflow execution",
            }
        ],
    }
    parsed = {
        "categories": [{"category_label": "Engineering & Delivery Leadership", "terms": []}],
        "competencies": [{"category_label": "Engineering & Delivery Leadership", "terms": []}],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={"fact_shared_delivery"},
        claim_unit_ids=["competencies:skill:01", "competencies:skill:02"],
    )

    assert receipt["pass"] is False
    assert receipt["added_claim_unit_ids"] == ["competencies:skill:01"]
    assert receipt["unresolved_claim_unit_ids"] == ["competencies:skill:02"]


def test_reconciliation_preserves_explicit_allocation_identity_on_second_pass() -> None:
    assignments = [
        {
            "section_id": "competencies",
            "claim_unit_id": f"competencies:skill:{index:02d}",
            "root_id": "reb_shared_runtime",
            "skill_id": f"skill_runtime_{index:02d}",
            "fact_id": "fact_runtime",
        }
        for index in (1, 2)
    ]
    parsed = {
        "competencies": [
            {
                "source_fact_ids": ["fact_runtime"],
                "graph_skill_node_ids": [row["skill_id"] for row in assignments],
                "terms": [
                    {
                        "text": f"governed runtime execution path {index}",
                        "source_fact_ids": ["fact_runtime"],
                        "source_skill_ids": [assignment["skill_id"]],
                        "allocation_claim_unit_id": assignment["claim_unit_id"],
                    }
                    for index, assignment in enumerate(assignments, start=1)
                ],
            }
        ],
        "claim_ledger": [],
    }

    receipt = reconcile_competencies_allocation_claim_units(
        parsed,
        selected_plan={
            "allocation_plan_digest": "explicit-identity-test",
            "allocation_assignments": assignments,
            "facts": [],
        },
        allowed_fact_ids={"fact_runtime"},
    )

    assert receipt["pass"] is True
    assert [
        term["allocation_claim_unit_id"]
        for term in parsed["competencies"][0]["terms"]
    ] == ["competencies:skill:01", "competencies:skill:02"]
    assert all(
        "EXPLICIT_ALLOCATION_CLAIM_UNIT_ID" in row["match_reasons"]
        for row in receipt["matches"]
    )


def test_materialization_replaces_optional_term_at_category_ceiling() -> None:
    assignment = {
        "section_id": "competencies",
        "claim_unit_id": "competencies:skill:01",
        "root_id": "reb_unify_agentic_platform_architecture",
        "skill_id": "skill_unify_agentic_l0_route_policy_dispatch",
        "fact_id": "fact_runtime",
        "root_bundle_theme": "SVP Engineering agentic AI platform control-plane architecture",
    }
    optional_terms = [
        {"text": f"optional governed platform execution anchor {index}"}
        for index in range(6)
    ]
    parsed = {
        "categories": [
            {"category_label": "AI Platform Leadership", "terms": copy.deepcopy(optional_terms)}
        ],
        "competencies": [
            {"category_label": "AI Platform Leadership", "terms": copy.deepcopy(optional_terms)}
        ],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan={
            "allocation_plan_digest": "category-cap-test",
            "allocation_assignments": [assignment],
            "facts": [
                {
                    "role_episode_bundle_id": assignment["root_id"],
                    "claim_text": assignment["root_bundle_theme"],
                }
            ],
        },
        allowed_fact_ids={"fact_runtime"},
        claim_unit_ids=[assignment["claim_unit_id"]],
    )

    assert receipt["pass"] is True
    assert len(receipt["optional_term_replacements"]) == 2
    assert all(len(parsed[key][0]["terms"]) == 6 for key in ("categories", "competencies"))
    assert all(
        any(
            term.get("allocation_claim_unit_id") == assignment["claim_unit_id"]
            for term in parsed[key][0]["terms"]
        )
        for key in ("categories", "competencies")
    )


def test_partner_gtm_projection_preserves_productization_family_and_drops_stale_fact() -> None:
    assignment = {
        "section_id": "competencies",
        "claim_unit_id": "competencies:skill:01",
        "root_id": "reb_unify_partner_channel_cosell",
        "skill_id": "skill_partner_partner_revenue_3m",
        "fact_id": "exp_unify_001",
        "root_bundle_theme": "AI Partnerships, Co-Sell Channel & Alliance GTM",
        "source_refs": ["3 million dollars in partner-derived revenue"],
    }
    parsed = {
        key: [
            {
                "category_label": "Commercial & Operating Impact",
                "competency_bundle_id": "ccb_platform_productization",
                "capability_family": "platform_productization",
                "source_fact_ids": ["fact_stale_replaced_term"],
                "terms": [],
            }
        ]
        for key in ("categories", "competencies")
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan={
            "allocation_plan_digest": "partner-category-authority-test",
            "allocation_assignments": [assignment],
            "facts": [
                {
                    "role_episode_bundle_id": assignment["root_id"],
                    "claim_text": assignment["root_bundle_theme"],
                }
            ],
        },
        allowed_fact_ids={"exp_unify_001"},
        claim_unit_ids=[assignment["claim_unit_id"]],
    )

    assert receipt["pass"] is True
    assert receipt["category_authority_rebindings"] == []
    for key in ("categories", "competencies"):
        category = parsed[key][0]
        assert category["competency_bundle_id"] == "ccb_platform_productization"
        assert category["capability_family"] == "platform_productization"
        assert category["source_fact_ids"] == ["exp_unify_001"]


def test_partner_allocation_routes_units_without_density_or_family_orphans() -> None:
    category_specs = (
        ("Cloud & Partner Ecosystems", "ccb_partner_applied_ai_architecture", "partner_applied_ai_architecture"),
        ("AI Platform Leadership", "ccb_agentic_platforms", "agentic_platforms"),
        ("Governance, Risk & Compliance", "ccb_runtime_governance", "runtime_governance"),
        ("Technology Strategy & Innovation", "ccb_retrieval_context_engineering", "retrieval_context_engineering"),
        ("Commercial & Operating Impact", "ccb_platform_productization", "platform_productization"),
        ("LLMOps & Reliability", "ccb_llmops_reliability", "llmops_reliability"),
        ("Data & Analytics Modernization", "ccb_distributed_systems_engineering", "distributed_systems_engineering"),
        ("Engineering & Delivery Leadership", "ccb_engineering_leadership", "engineering_leadership"),
    )
    categories = [
        {
            "category_label": label,
            "competency_bundle_id": bundle,
            "capability_family": family,
            "terms": [{"text": f"optional {label} anchor {index}"} for index in range(3)],
        }
        for label, bundle, family in category_specs
    ]
    assignments = [
        {
            "section_id": "competencies",
            "claim_unit_id": f"competencies:skill:{index:02d}",
            "root_id": root_id,
            "skill_id": skill_id,
            "fact_id": fact_id,
            "root_bundle_theme": theme,
        }
        for index, root_id, skill_id, fact_id, theme in (
            (1, "reb_ibm_presales_solution_engineering", "skill_partner_pre_sales", "fact_revenue_ops_004", "Technical pre-sales solution engineering and buyer-specific architecture mapping"),
            (2, "reb_ibm_revenue_sales_target_execution", "skill_partner_enterprise_negotiations", "fact_revenue_ops_001", "Revenue target execution and quota-aligned solution leadership"),
            (4, "reb_ibm_devsecops_release_resilience", "skill_ibm_automated_release_pipelines", "fact_engineering_platform_002", "DevSecOps release resilience and governed delivery automation"),
            (5, "reb_ibm_aws_alliance_partner_cosell_gtm", "skill_partner_alliance_gtm_execution", "fact_partnerships_gtm_002", "AWS partnership, alliance co-sell, and joint GTM execution"),
            (6, "reb_ibm_customer_success_value_realization", "skill_p2_gtm_presales_delivery_handoff", "fact_revenue_ops_004", "Customer success and value-realization operating cadence"),
            (7, "reb_unify_partner_channel_cosell", "skill_partner_partner_led_ai_solutions", "exp_unify_001", "AI Partnerships, Co-Sell Channel & Alliance GTM"),
            (8, "reb_ibm_customer_success_value_realization", "skill_partner_customer_deal_support", "fact_revenue_ops_004", "Partner customer deal support and value realization"),
        )
    ]
    assignments[0]["root_claim_action"] = (
        "Led technical discovery and solution mapping for enterprise financial-services pursuits"
    )
    assignments[3]["root_claim_outcome"] = (
        "Frame as alliance GTM leadership: joint planning, solution architecture, "
        "and co-sell execution."
    )
    parsed = {
        "categories": copy.deepcopy(categories),
        "competencies": copy.deepcopy(categories),
    }
    plan = {
        "allocation_plan_digest": "retry16-partner-routing",
        "allocation_assignments": assignments,
        "facts": [
            {
                "role_episode_bundle_id": row["root_id"],
                "claim_text": row["root_bundle_theme"],
            }
            for row in assignments
        ],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={row["fact_id"] for row in assignments},
        claim_unit_ids=[row["claim_unit_id"] for row in assignments],
    )

    assert receipt["pass"] is True, receipt["unresolved_claim_unit_ids"]
    assert receipt["unresolved_claim_unit_ids"] == []
    assert receipt["category_authority_rebindings"] == []
    expected_units = {row["claim_unit_id"] for row in assignments}
    for surface in ("categories", "competencies"):
        assert sum(len(category["terms"]) for category in parsed[surface]) == 24
        assert {category["competency_bundle_id"] for category in parsed[surface]} >= {
            "ccb_platform_productization",
            "ccb_partner_applied_ai_architecture",
            "ccb_engineering_leadership",
        }
        visible_units = [
            term.get("allocation_claim_unit_id")
            for category in parsed[surface]
            for term in category["terms"]
            if term.get("allocation_claim_unit_id")
        ]
        assert set(visible_units) == expected_units
        assert len(visible_units) == len(expected_units)

        engineering = next(
            category
            for category in parsed[surface]
            if category["competency_bundle_id"] == "ccb_engineering_leadership"
        )
        engineering_allocations = {
            term.get("allocation_claim_unit_id")
            for term in engineering["terms"]
            if term.get("allocation_claim_unit_id")
        }
        assert engineering_allocations == {"competencies:skill:06"}
        assert sum(
            1 for term in engineering["terms"] if not term.get("allocation_claim_unit_id")
        ) == 2
        assert "Presales-to-delivery customer success operating handoff cadence" in {
            term.get("text") or term.get("term") for term in engineering["terms"]
        }
        commercial = next(
            category
            for category in parsed[surface]
            if category["competency_bundle_id"] == "ccb_platform_productization"
        )
        assert commercial["resume_display_label"] == (
            "Partner Commercialization & Value Realization"
        )


def test_partner_gtm_projection_replaces_generic_anchors_at_three_item_ceiling() -> None:
    assignments = [
        {
            "section_id": "competencies",
            "claim_unit_id": f"competencies:skill:{index:02d}",
            "root_id": root_id,
            "skill_id": skill_id,
            "fact_id": fact_id,
            "root_bundle_theme": phrase,
        }
        for index, root_id, skill_id, fact_id, phrase in (
            (
                1,
                "reb_unify_partner_channel_cosell",
                "skill_partner_partner_revenue_3m",
                "exp_unify_001",
                "Partner channel commercialization and alliance co-sell execution",
            ),
            (
                2,
                "reb_ibm_aws_alliance_partner_cosell_gtm",
                "skill_partner_cloud_vendor_joint_gtm",
                "fact_partnerships_gtm_002",
                "AWS alliance joint architecture leadership",
            ),
            (
                3,
                "reb_ibm_customer_success_value_realization",
                "skill_partner_customer_success_value_realization",
                "fact_revenue_ops_004",
                "Customer success and value realization operating cadence",
            ),
        )
    ]
    optional = [
        {"text": "demoable AI accelerators for executive buyers"},
        {"text": "reusable AI platform commercialization for adoption"},
        {"text": "generic commercial solution execution cadence"},
    ]
    parsed = {
        key: [
            {
                "category_label": "Commercial & Operating Impact",
                "competency_bundle_id": "ccb_platform_productization",
                "capability_family": "platform_productization",
                "terms": copy.deepcopy(optional),
            }
        ]
        for key in ("categories", "competencies")
    }
    plan = {
        "allocation_plan_digest": "compact-partner-gtm",
        "allocation_assignments": assignments,
        "facts": [
            {
                "role_episode_bundle_id": row["root_id"],
                "claim_text": row["root_bundle_theme"],
            }
            for row in assignments
        ],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={row["fact_id"] for row in assignments},
        claim_unit_ids=[row["claim_unit_id"] for row in assignments],
    )

    assert receipt["pass"] is True
    assert len(receipt["optional_term_replacements"]) == 6
    for key in ("categories", "competencies"):
        terms = parsed[key][0]["terms"]
        assert len(terms) == 3
        assert {
            term.get("allocation_claim_unit_id")
            for term in terms
        } == {row["claim_unit_id"] for row in assignments}


def test_materialization_uses_distinct_bound_surfaces_for_revenue_assignments() -> None:
    assignments = [
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:06",
            "root_id": "reb_ibm_revenue_sales_target_execution",
            "skill_id": "skill_partner_sales_revenue_targets",
            "fact_id": "fact_revenue_ops_003",
            "root_bundle_theme": "Revenue target execution and quota-aligned solution leadership",
            "root_claim_text": "Owned quota-aligned solution leadership across enterprise pursuits and client portfolio expansion motions",
            "root_claim_scope": "IBM partner role with quota and revenue-target accountability for enterprise financial-services solution motions.",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:08",
            "root_id": "reb_ibm_revenue_sales_target_execution",
            "skill_id": "skill_partner_enterprise_negotiations",
            "fact_id": "fact_revenue_ops_002",
            "root_bundle_theme": "Revenue target execution and quota-aligned solution leadership",
            "root_claim_text": "Owned quota-aligned solution leadership across enterprise pursuits and client portfolio expansion motions",
            "root_claim_scope": "IBM partner role with quota and revenue-target accountability for enterprise financial-services solution motions.",
        },
    ]
    plan = {
        "allocation_plan_digest": "revenue-assignment-test",
        "allocation_assignments": assignments,
        "facts": [
            {
                "role_episode_bundle_id": "reb_ibm_revenue_sales_target_execution",
                "bundle_theme": "Revenue target execution and quota-aligned solution leadership",
                "claim_text": "Owned quota-aligned solution leadership across enterprise pursuits and client portfolio expansion motions",
                "claim_scope": "IBM partner role with quota and revenue-target accountability for enterprise financial-services solution motions.",
            }
        ],
    }
    parsed = {
        "categories": [{"category_label": "Commercial & Operating Impact", "terms": []}],
        "competencies": [{"category_label": "Commercial & Operating Impact", "terms": []}],
        "claim_ledger": [],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={"fact_revenue_ops_002", "fact_revenue_ops_003"},
        claim_unit_ids=["competencies:skill:06", "competencies:skill:08"],
    )
    reconciliation = reconcile_competencies_allocation_claim_units(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={"fact_revenue_ops_002", "fact_revenue_ops_003"},
    )

    visible = {
        term["text"]
        for category in parsed["competencies"]
        for term in category["terms"]
    }
    assert receipt["pass"] is True
    assert "Revenue target execution and quota-aligned solution leadership" in visible
    assert "Enterprise pursuit execution across portfolio expansion motions" in visible
    assert reconciliation["pass"] is True


def test_devsecops_recovery_surface_is_bound_and_meets_visible_rigor() -> None:
    assignment = {
        "section_id": "competencies",
        "claim_unit_id": "competencies:skill:01",
        "root_id": "reb_ibm_devsecops_release_resilience",
        "skill_id": "skill_ibm_automated_release_pipelines",
        "fact_id": "fact_engineering_platform_002",
        "root_bundle_theme": "DevSecOps release resilience and governed delivery automation",
        "root_claim_text": "Embedded release automation and security scanning into regulated modernization delivery paths",
        "root_claim_scope": "IBM delivery programs requiring release governance, security scanning, and deployment repeatability.",
    }
    plan = {
        "allocation_plan_digest": "devsecops-surface-test",
        "allocation_assignments": [assignment],
        "facts": [
            {
                "role_episode_bundle_id": "reb_ibm_devsecops_release_resilience",
                "bundle_theme": assignment["root_bundle_theme"],
                "claim_text": assignment["root_claim_text"],
                "claim_scope": assignment["root_claim_scope"],
            }
        ],
    }
    parsed = {
        "categories": [
            {
                "category_label": "AI Platform Leadership",
                "visible_graph_surface": True,
                "terms": [],
            }
        ],
        "competencies": [
            {
                "category_label": "AI Platform Leadership",
                "visible_graph_surface": True,
                "terms": [],
            }
        ],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={"fact_engineering_platform_002"},
        claim_unit_ids=["competencies:skill:01"],
    )

    assert receipt["pass"] is True
    assert parsed["competencies"][0]["terms"][0]["text"] == (
        "Regulated DevSecOps release governance pipelines"
    )
    assert check_competencies_visible_terms_svp_agentic_richness(
        parsed["competencies"]
    ) == (True, None)


def test_presales_recovery_surface_is_bound_and_meets_visible_rigor() -> None:
    assignment = {
        "section_id": "competencies",
        "claim_unit_id": "competencies:skill:05",
        "root_id": "reb_ibm_presales_solution_engineering",
        "skill_id": "skill_partner_pre_sales",
        "fact_id": "fact_revenue_ops_001",
        "root_bundle_theme": "Technical pre-sales solution engineering and buyer-specific architecture mapping",
        "root_claim_text": "Led technical discovery and solution mapping for enterprise financial-services pursuits",
        "root_claim_scope": "IBM technical pre-sales role surface; partner-level solution engineering across regulated client pursuits.",
        "root_claim_outcome": "Frame as commercial-technical leadership: buyer discovery, architecture mapping, and delivery-ready solution handoff with no unsupported dollar claims.",
    }
    plan = {
        "allocation_plan_digest": "presales-surface-test",
        "allocation_assignments": [assignment],
        "facts": [
            {
                "role_episode_bundle_id": "reb_ibm_presales_solution_engineering",
                "bundle_theme": assignment["root_bundle_theme"],
                "claim_text": assignment["root_claim_text"],
                "claim_scope": assignment["root_claim_scope"],
                "claim_outcome": assignment["root_claim_outcome"],
            }
        ],
    }
    parsed = {
        "categories": [
            {
                "category_label": "Engineering & Delivery Leadership",
                "visible_graph_surface": True,
                "terms": [],
            }
        ],
        "competencies": [
            {
                "category_label": "Engineering & Delivery Leadership",
                "visible_graph_surface": True,
                "terms": [],
            }
        ],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={"fact_revenue_ops_001"},
        claim_unit_ids=["competencies:skill:05"],
    )

    assert receipt["pass"] is True
    assert parsed["competencies"][0]["terms"][0]["text"] == (
        "Buyer-specific solution mapping for enterprise pursuits"
    )
    assert check_competencies_visible_terms_svp_agentic_richness(
        parsed["competencies"]
    ) == (True, None)


def test_insurance_it_strategy_projection_uses_exact_frozen_allocation_once() -> None:
    """The final visible résumé groups preserve both bundle and allocation authority."""

    plan, parsed, allowed = _insurance_it_strategy_projection_fixture()
    receipt = project_insurance_it_strategy_competencies_from_frozen_allocation(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=allowed,
    )

    assert receipt["applicable"] is True
    assert receipt["pass"] is True
    assert receipt["category_count"] == 8
    assert receipt["allocation_claim_unit_count"] == 24
    assert all(len(category["terms"]) == 4 for category in parsed["competencies"])
    projected_claim_unit_ids = {
        term["allocation_claim_unit_id"]
        for category in parsed["competencies"]
        for term in category["terms"]
        if term.get("allocation_claim_unit_id")
    }
    assert len(projected_claim_unit_ids) == 24
    assert all(
        "fact_stale_preprojection_category" not in category["source_fact_ids"]
        for category in parsed["competencies"]
    )
    reconciliation = reconcile_competencies_allocation_claim_units(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=allowed,
    )
    assert reconciliation["pass"] is True


def test_insurance_it_strategy_projection_precondition_requires_exact_24_unit_layout(
    monkeypatch: object,
) -> None:
    full_plan, _, _ = _insurance_it_strategy_projection_fixture()
    assert insurance_it_strategy_frozen_layout_is_present(full_plan) is True

    generic_plan = _slice(monkeypatch)
    generic_plan["target_role_profile"] = "insurance_it_strategy"
    assert len(generic_plan["allocation_assignments"]) == 8
    assert insurance_it_strategy_frozen_layout_is_present(generic_plan) is False


def test_insurance_it_strategy_projection_fails_closed_if_allocation_changes() -> None:
    plan, parsed, allowed = _insurance_it_strategy_projection_fixture()
    plan["allocation_assignments"].pop()
    before = copy.deepcopy(parsed)

    receipt = project_insurance_it_strategy_competencies_from_frozen_allocation(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=allowed,
    )

    assert receipt["applicable"] is True
    assert receipt["pass"] is False
    assert receipt["status"] == "BLOCKED_FROZEN_ALLOCATION_LAYOUT_MISMATCH"
    assert parsed == before


def test_insurance_it_strategy_visible_projection_terms_pass_executive_rigor() -> None:
    categories = [
        {
            "visible_graph_surface": True,
            "resume_display_label": spec["resume_display_label"],
            "terms": [
                {
                    "text": _ALLOCATION_VISIBLE_SURFACE_COMPOSITIONS[(root_id, skill_id)]
                }
                for root_id, skill_id in spec["assignment_keys"]
            ],
        }
        for spec in _INSURANCE_IT_STRATEGY_FROZEN_ALLOCATION_LAYOUT
    ]

    assert check_competencies_visible_terms_svp_agentic_richness(categories) == (True, None)
    assert check_competencies_keyword_repetition_limit(categories) == (True, None)


def test_reconciliation_does_not_bind_an_unrelated_term_through_shared_fact_only() -> None:
    """Fact/root provenance supports a term; it does not replace skill identity."""
    plan = {
        "allocation_plan_digest": "test-plan",
        "allocation_assignments": [
            {
                "section_id": "competencies",
                "claim_unit_id": "competencies:section_only:01",
                "root_id": "reb_security",
                "skill_id": "skill_pii_encryption_for_insurance_data",
                "fact_id": "fact_security",
            }
        ],
        "facts": [
            {
                "role_episode_bundle_id": "reb_security",
                "graph_skill_node_ids": ["skill_pii_encryption_for_insurance_data"],
                "linked_source_fact_ids": ["fact_security"],
            }
        ],
    }
    parsed = {
        "competencies": [
            {
                "source_fact_ids": ["fact_security"],
                "graph_skill_node_ids": ["skill_pii_encryption_for_insurance_data"],
                "terms": [
                    {
                        "text": "governed multi-agent orchestration control planes",
                        "source_fact_ids": ["fact_security"],
                        "source_skill_ids": [
                            "skill_pii_encryption_for_insurance_data",
                            "skill_other_category_support",
                        ],
                    }
                ],
            }
        ]
    }

    receipt = reconcile_competencies_allocation_claim_units(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={"fact_security"},
    )

    assert receipt["pass"] is False
    assert receipt["matched_claim_unit_count"] == 0
    assert receipt["unmatched_claim_unit_ids"] == ["competencies:section_only:01"]


def test_unmatched_allocations_materialize_only_graph_authored_terms(monkeypatch: object) -> None:
    plan = _slice(monkeypatch)
    assignments = plan["allocation_assignments"]
    assert isinstance(assignments, list)
    target_units = [assignments[0]["claim_unit_id"], assignments[1]["claim_unit_id"]]
    for index, assignment in enumerate(assignments[:2]):
        assignment["root_bundle_theme"] = (
            f"Authorized operating cadence for enterprise delivery {index + 1}"
        )
    parsed = {
        "competencies": [
            {
                "category_label": "Commercial & Operating Impact",
                "terms": [{"text": "existing graph-backed term"}],
            }
        ],
        "categories": [
            {
                "category_label": "Commercial & Operating Impact",
                "terms": [{"text": "existing graph-backed term"}],
            }
        ],
        "claim_ledger": [],
    }
    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=set(plan["allowed_graph_evidence_ids"]),
        claim_unit_ids=target_units,
    )
    assert receipt["pass"] is True
    assert receipt["unresolved_claim_unit_ids"] == []
    additions = [
        term
        for category in parsed["competencies"]
        for term in category["terms"]
        if term.get("allocation_claim_unit_id") in target_units
    ]
    assert {term["allocation_claim_unit_id"] for term in additions} == set(target_units)
    assert all(term["source_fact_id"] in set(plan["allowed_graph_evidence_ids"]) for term in additions)
    assert all(term["source_skill_ids"] for term in additions)
    assert all(
        term["allocation_surface_source_field"] == "root_bundle_theme"
        for term in additions
    )
    final = reconcile_competencies_allocation_claim_units(
        parsed,
        selected_plan=plan,
        allowed_fact_ids=set(plan["allowed_graph_evidence_ids"]),
    )
    assert set(final["unmatched_claim_unit_ids"]) == {
        row["claim_unit_id"] for row in assignments[2:]
    }


def test_joint_solution_surface_is_placed_in_partner_architecture_category() -> None:
    categories = [
        {"category_label": "Partner Applied AI Architecture", "terms": []},
        {
            "category_label": "Commercial & Operating Impact",
            "resume_display_label": "Platform Productization & Commercialization",
            "terms": [],
        },
    ]
    assignment = {
        "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
        "skill_id": "skill_partner_joint_solution_development",
    }

    category = _allocation_surface_category(
        categories,
        phrase="AI analytics framework co-development for partners",
        assignment=assignment,
    )

    assert category is categories[0]
    rich, reason = check_competencies_visible_terms_svp_agentic_richness(
        [
            {
                "visible_graph_surface": True,
                "resume_display_label": "Partner Applied AI Architecture",
                "terms": [
                    {
                        "text": "AI analytics framework co-development for partners"
                    }
                ],
            }
        ]
    )
    assert rich is True, reason


def test_unmatched_allocations_use_bound_resume_surfaces_for_compact_graph_skills() -> None:
    """Short graph labels are rendered as source-bound, reviewer-readable terms."""
    roots = {
        "reb_insurtech_regulated_aws_control_implementation": {
            "fact_id": "exp_insurtech_001",
            "domain": "Regulated AWS Control Implementation",
            "claim_text": "Implemented SOC 2-aligned AWS controls for regulated insurers adopting analytics and ML.",
        },
        "reb_insurtech_aws_migration_execution": {
            "fact_id": "exp_insurtech_001",
            "domain": "AWS Migration Execution for Legacy Insurance Platforms",
            "claim_text": "Led AWS modernization execution for monolithic policy administration and insurance platform workloads.",
        },
        "reb_ey_erm_risk_governance": {
            "fact_id": "exp_ey_001",
            "domain": "Enterprise Risk Management Operating Model and Risk-Data Aggregation",
            "claim_text": "Architected ERM operating models and BCBS 239-aligned risk-data aggregation by defining three-lines-of-defense accountability.",
        },
        "reb_ey_insurance_core_modernization": {
            "fact_id": "exp_ey_001",
            "domain": "Insurance Core Modernization: Policy, Claims, Billing, and Data Workflows",
            "claim_text": "Led insurance core modernization spanning claims automation, integration/data conversion, and BI handoffs; Guidewire was an example platform.",
        },
    }
    sources = {
        "skill_soc2_zero_trust_security": [
            "Embedded zero-trust security and compliance (SOC2, GDPR, CCPA)."
        ],
        "skill_sr_insurtech_regulated_insurer_controls": [
            "Designed SOC2-aligned cloud control frameworks enabling regulated insurers to adopt modern analytics and ML."
        ],
        "skill_credit_adjudication_default_risk": [
            "AI-driven credit adjudication project with dynamic risk profiling."
        ],
        "skill_risk_model_risk": ["model explainability and data security frameworks"],
        "skill_insurance_claims_automation": [
            "Insurance core modernization spanning policy administration, claims automation, integration/data conversion, and BI handoffs."
        ],
        "skill_insurance_core_to_bi_reporting_handoff": [
            "Insurance core modernization spanning policy administration, claims automation, integration/data conversion, and BI handoffs."
        ],
        "skill_insurance_guidewire": [
            "Guidewire is an example platform, not the claim boundary."
        ],
    }
    chosen = [
        ("reb_insurtech_regulated_aws_control_implementation", "skill_pii_encryption_for_insurance_data"),
        ("reb_insurtech_regulated_aws_control_implementation", "skill_aws_iam_kms_cloudtrail_controls"),
        ("reb_insurtech_regulated_aws_control_implementation", "skill_soc2_zero_trust_security"),
        ("reb_insurtech_regulated_aws_control_implementation", "skill_sr_insurtech_regulated_insurer_controls"),
        ("reb_insurtech_aws_migration_execution", "skill_application_dependency_mapping"),
        ("reb_insurtech_aws_migration_execution", "skill_migration_wave_cutover_planning"),
        ("reb_ey_erm_risk_governance", "skill_credit_adjudication_default_risk"),
        ("reb_ey_erm_risk_governance", "skill_risk_three_lines_of_defense"),
        ("reb_ey_erm_risk_governance", "skill_risk_model_risk"),
        ("reb_ey_insurance_core_modernization", "skill_insurance_claims_automation"),
        ("reb_ey_insurance_core_modernization", "skill_insurance_core_to_bi_reporting_handoff"),
        ("reb_ey_insurance_core_modernization", "skill_insurance_guidewire"),
    ]
    assignments = []
    for index, (root_id, skill_id) in enumerate(chosen, start=1):
        root = roots[root_id]
        assignments.append(
            {
                "section_id": "competencies",
                "claim_unit_id": f"competencies:section_only:{index:02d}",
                "root_id": root_id,
                "skill_id": skill_id,
                "fact_id": root["fact_id"],
                "root_bundle_theme": root["domain"],
                "root_claim_text": root["claim_text"],
                "source_refs": sources.get(skill_id, []),
            }
        )
    plan = {
        "allocation_plan_digest": "test-plan",
        "allocation_assignments": assignments,
        "facts": [
            {"role_episode_bundle_id": root_id, **root}
            for root_id, root in roots.items()
        ],
    }
    parsed = {
        "categories": [
            {"category_label": "Governance, Risk & Compliance", "visible_graph_surface": True, "terms": []},
            {"category_label": "Data & Analytics Modernization", "visible_graph_surface": True, "terms": []},
        ],
        "competencies": [
            {"category_label": "Governance, Risk & Compliance", "visible_graph_surface": True, "terms": []},
            {"category_label": "Data & Analytics Modernization", "visible_graph_surface": True, "terms": []},
        ],
        "claim_ledger": [],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan=plan,
        allowed_fact_ids={"exp_insurtech_001", "exp_ey_001"},
        claim_unit_ids=[row["claim_unit_id"] for row in assignments],
    )

    expected = {
        "PII encryption controls for regulated data",
        "IAM KMS CloudTrail controls for insurers",
        "SOC2 zero-trust security controls for compliance",
        "SOC2 control frameworks for regulated insurers",
        "Application dependency mapping for migration execution",
        "Migration wave cutover execution planning",
        "AI credit adjudication for enterprise risk",
        "Enterprise three-lines-of-defense risk operating model",
        "Model explainability for enterprise risk operating model",
        "Insurance claims workflow automation integration",
        "Insurance core reporting integration and BI workflows",
        "Guidewire platform workflow modernization integration",
    }
    visible = {
        term["text"]
        for category in parsed["categories"]
        for term in category["terms"]
    }
    assert receipt["pass"] is True
    assert visible == expected
    assert all(
        term["allocation_surface_source_field"] == "graph_authority_surface_composition"
        for category in parsed["categories"]
        for term in category["terms"]
    )
    richness_ok, richness_reason = check_competencies_visible_terms_svp_agentic_richness(
        parsed["categories"]
    )
    assert richness_ok, richness_reason


def test_anthropic_allocation_recovery_emits_distinct_graph_bound_surfaces() -> None:
    assignments = [
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:04",
            "root_id": "reb_unify_agentic_platform_architecture",
            "skill_id": "skill_unify_agentic_l0_route_policy_dispatch",
            "fact_id": "fact_engineering_platform_001",
            "root_bundle_theme": "SVP Engineering agentic AI platform control-plane architecture",
            "root_claim_scope": "Runtime control plane and governed execution for regulated institutions.",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:05",
            "root_id": "reb_unify_agentic_platform_architecture",
            "skill_id": "skill_unify_agentic_graphrag_context_pack_grounding",
            "fact_id": "fact_engineering_platform_001",
            "root_bundle_theme": "SVP Engineering agentic AI platform control-plane architecture",
            "root_claim_scope": (
                "Production-grade agentic AI Solution Accelerator within a consulting firm; "
                "SVP Engineering ownership of runtime control plane, GraphRAG grounding, "
                "multi-agent orchestration, and governed execution for regulated financial "
                "institutions."
            ),
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:06",
            "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
            "skill_id": "skill_partner_cloud_vendor_joint_gtm",
            "fact_id": "fact_partnerships_gtm_002",
            "root_bundle_theme": "AWS partnership alliance co-sell and joint GTM execution",
            "root_claim_scope": "Cloud and AI modernization opportunities.",
            "root_claim_outcome": "Joint planning, solution architecture, and co-sell execution.",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:07",
            "root_id": "reb_ibm_customer_success_value_realization",
            "skill_id": "skill_partner_customer_deal_support",
            "fact_id": "fact_revenue_ops_004",
            "root_bundle_theme": "Customer success and value-realization operating cadence",
            "root_claim_outcome": "Client success cadence and value-realization leadership.",
        },
        {
            "section_id": "competencies",
            "claim_unit_id": "competencies:skill:08",
            "root_id": "reb_unify_partner_channel_cosell",
            "skill_id": "skill_partner_partner_led_ai_solutions",
            "fact_id": "exp_unify_001",
            "root_bundle_theme": "AI Partnerships, Co-Sell Channel & Alliance GTM",
            "root_claim_scope": (
                "Global AI channel program from inception: co-developed analytics "
                "frameworks with strategic partners, co-sell bundling with cloud vendors."
            ),
            "root_claim_outcome": "Frame as AI partnerships and co-sell channel leadership.",
        },
    ]
    facts = [
        {
            "role_episode_bundle_id": row["root_id"],
            "fact_id": row["fact_id"],
            "domain": row.get("root_claim_scope", ""),
            "claim_text": row.get("root_bundle_theme", ""),
            "claim_outcome": row.get("root_claim_outcome", ""),
        }
        for row in assignments
    ]
    parsed = {
        "categories": [
            {
                "category_label": "Agentic Platforms & Partner Architecture",
                "visible_graph_surface": True,
                "terms": [],
            }
        ],
        "claim_ledger": [],
    }

    receipt = materialize_unmatched_competencies_allocation_terms(
        parsed,
        selected_plan={
            "allocation_plan_digest": "anthropic-plan",
            "allocation_assignments": assignments,
            "facts": facts,
        },
        allowed_fact_ids={row["fact_id"] for row in assignments},
        claim_unit_ids=[row["claim_unit_id"] for row in assignments],
    )

    visible = {term["text"] for term in parsed["categories"][0]["terms"]}
    assert receipt["pass"] is True, receipt["unresolved_claim_unit_ids"]
    assert visible == {
        "Agentic platform route-policy dispatch architecture",
        "GraphRAG context pack grounding for governed execution",
        "Partner AI solution architecture and co-sell execution",
        "Partner value-realization operating cadence and deal support",
        "AI co-sell bundling with strategic partners",
    }
    assert "AI Partnerships, Co-Sell Channel & Alliance GTM" not in visible
    assert check_competencies_visible_terms_svp_agentic_richness(
        parsed["categories"]
    ) == (True, None)
    assert check_competencies_keyword_repetition_limit(
        parsed["categories"]
    ) == (True, None)
    assert all(len(text) < 36 or "SVP Engineering" not in text for text in visible)


def test_allocation_sync_copies_provenance_to_canonical_v3_categories() -> None:
    parsed = {
        "categories": [
            {
                "category_id": "governance_risk_compliance",
                "category_label": "Governance, Risk & Compliance",
                "terms": [{"term": "governed runtime control architecture"}],
                "source_fact_ids": [],
                "graph_skill_node_ids": [],
            }
        ],
        "competencies": [
            {
                "category_id": "governance_risk_compliance",
                "category_label": "Governance, Risk & Compliance",
                "terms": [
                    {
                        "text": "governed runtime control architecture",
                        "source_fact_id": "fact_runtime",
                        "source_fact_ids": ["fact_runtime"],
                        "source_skill_ids": ["skill_runtime_control"],
                        "allocation_claim_unit_id": "competencies:section_only:01",
                    }
                ],
            }
        ],
    }

    receipt = synchronize_competencies_allocation_bindings_to_categories(parsed)

    category = parsed["categories"][0]
    term = category["terms"][0]
    assert receipt["pass"] is True
    assert term["allocation_claim_unit_id"] == "competencies:section_only:01"
    assert term["source_fact_ids"] == ["fact_runtime"]
    assert category["source_fact_ids"] == ["fact_runtime"]
    assert category["graph_skill_node_ids"] == ["skill_runtime_control"]


def test_assertion_skill_fact_and_claim_unit_ids_remain_distinct(monkeypatch: object) -> None:
    plan = _slice(monkeypatch)
    parsed = _parsed_for_plan(plan)
    allowed = set(plan["allowed_graph_evidence_ids"])
    receipt = reconcile_competencies_allocation_claim_units(
        parsed, selected_plan=plan, allowed_fact_ids=allowed
    )
    ledger = build_competencies_graph_authority_discrepancy_ledger(
        selected_plan=plan,
        proof_pool_metadata={
            "graph_skill_embedding_assertion_bindings": [
                {
                    "assertion_id": "assertion_01",
                    "skill_id": "skill_domain_01",
                    "rank": 1,
                }
            ]
        },
        parsed=parsed,
        reconciliation_receipt=receipt,
    )
    row = next(row for row in ledger["rows"] if row["assertion_id"] == "assertion_01")
    assert row["assertion_id"] not in row["skill_ids"]
    assert row["assertion_id"] not in row["fact_ids"]
    assert all(unit not in row["skill_ids"] for unit in row["allocation_claim_unit_ids"])


def test_final_evidence_contract_receives_canonical_digest_at_top_level() -> None:
    digest = "a" * 64
    bridge = SectionFecBridge(section_id="competencies", bridge_doc={})
    pool = SimpleNamespace(
        proof_pool_metadata={
            "resume_graph_allocation_scope": "WHOLE_RESUME",
            "resume_graph_allocation_plan_id": "resume_graph_allocation:test",
            "resume_graph_allocation_plan_digest": digest,
            "resume_graph_global_uniqueness_claimed": True,
        }
    )
    bound = _bind_allocation_authority_fields(bridge, pool=pool)
    assert bound.bridge_doc["resume_graph_allocation_plan_digest"] == digest


def test_canonical_claim_ledger_preserves_allocation_claim_unit_identity() -> None:
    rows = normalize_exec_summary_claim_ledger(
        [
            {
                "claim_text": "governed systems architecture",
                "source_fact_ids": ["fact_01"],
                "claim_unit_id": "competencies:skill:01",
            }
        ]
    )
    payload = build_canonical_claim_ledger_v2_payload(rows, parse_status="OK")
    assert payload["claims"][0]["claim_unit_id"] == "competencies:skill:01"


def test_graph_claim_binding_requires_exactly_once_consumption(
    monkeypatch: object, tmp_path: Path
) -> None:
    plan = _slice(monkeypatch)
    parsed = _parsed_for_plan(plan)
    allowed = set(plan["allowed_graph_evidence_ids"])
    receipt = reconcile_competencies_allocation_claim_units(
        parsed, selected_plan=plan, allowed_fact_ids=allowed
    )
    assert receipt["pass"] is True
    claims = normalize_exec_summary_claim_ledger(parsed["claim_ledger"])
    canonical = build_canonical_claim_ledger_v2_payload(
        claims, parse_status="OK", claim_id_prefix="competencies_claim"
    )
    display = "\n".join(row["claim_text"] for row in claims)
    digest = str(plan["allocation_plan_digest"])
    _write_json(tmp_path / "l2_output.json", {"claim_ledger": claims})
    _write_json(tmp_path / "claim_ledger.json", claims)
    _write_json(tmp_path / "canonical_claim_ledger_v2.json", canonical)
    _write_json(tmp_path / "selected_fact_plan.json", plan)
    _write_json(
        tmp_path / "final_evidence_contract.json",
        {"resume_graph_allocation_plan_digest": digest},
    )
    _write_json(
        tmp_path / "compiled_prompt_artifact.json",
        {"resume_graph_allocation_plan_digest": digest},
    )
    (tmp_path / "command_output.txt").write_text(display, encoding="utf-8")
    binding = bind_final_claims_to_resume_graph_allocation(
        tmp_path, section_id="competencies"
    )
    assert binding["pass"] is True
    assert binding["orphan_allocation_claim_unit_ids"] == []
    assert binding["allocation_claim_unit_consumption_exactly_once_pass"] is True
    assert set(binding["allocation_claim_unit_consumption_counts"].values()) == {1}
