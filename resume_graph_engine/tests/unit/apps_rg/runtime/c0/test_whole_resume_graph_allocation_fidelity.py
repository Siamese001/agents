from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.c0.resume_graph_allocation import (
    ALL_CLAIM_BEARING_SECTIONS,
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
    validate_resume_graph_allocation_plan,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_insurance_it_strategy_whole_resume_allocation_fidelity() -> None:
    repo = _repo_root()
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="Senior Vice President, IT Strategy & Innovation",
        jd_text=(
            "Brown & Brown Insurance - Senior Vice President, IT Strategy & Innovation. "
            "Lead enterprise technology strategy, core P&C insurance platform modernization, "
            "underwriting and claims automation, enterprise architecture, and AI governance."
        ),
        briefing_text=(
            "Target role: SVP IT Strategy & Innovation at Brown & Brown Insurance. "
            "Emphasize P&C insurance platform modernization, regulated cloud/AI governance, "
            "and enterprise architecture."
        ),
    )
    plan = bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(plan) == []
    assert plan["uniqueness_receipt"]["pass"] is True
    assert plan["budget_receipt"]["pass"] is True

    by_slot = {row["claim_unit_id"]: row for row in plan["assignments"]}

    # Headline slots allocate insurance & platform roots
    assert by_slot["headline:skill:01"]["root_id"] == "reb_insurtech_aws_guidewire_core_modernization"
    assert by_slot["headline:skill:02"]["root_id"] == "reb_insurtech_regulated_aws_control_implementation"
    assert by_slot["headline:skill:03"]["root_id"] == "reb_unify_distributed_ecosystem_engineering"

    # Executive summary slots allocate regulated AI governance (35%), InsurTech AWS migration, and agentic architecture
    assert by_slot["executive_summary:claim:01"]["root_id"] == "reb_unify_regulated_enterprise_ai_governance"
    assert by_slot["executive_summary:claim:01"]["metric_value"] == "35"
    assert by_slot["executive_summary:claim:01"]["metric_unit"] == "PERCENT"
    assert by_slot["executive_summary:claim:02"]["root_id"] == "reb_insurtech_aws_migration_execution"
    assert by_slot["executive_summary:claim:03"]["root_id"] == "reb_unify_agentic_platform_architecture"

    # Unify bullets preserve 40% on bul_unify_005 and $22M on bul_unify_006
    assert by_slot["unify_bullets:bul_unify_005"]["metric_value"] == "40"
    assert by_slot["unify_bullets:bul_unify_005"]["metric_unit"] == "PERCENT"
    assert by_slot["unify_bullets:bul_unify_006"]["metric_value"] == "22"
    assert by_slot["unify_bullets:bul_unify_006"]["metric_unit"] == "USD_M"

    # IBM bullets allocate all 5 distinct role episode roots and 20% joint revenue growth on bul_ibm_005
    assert by_slot["ibm_bullets:bul_ibm_001"]["root_id"] == "reb_ibm_customer_success_value_realization"
    assert by_slot["ibm_bullets:bul_ibm_002"]["root_id"] == "reb_ibm_presales_solution_engineering"
    assert by_slot["ibm_bullets:bul_ibm_003"]["root_id"] == "reb_ibm_revenue_sales_target_execution"
    assert by_slot["ibm_bullets:bul_ibm_004"]["root_id"] == "reb_ibm_data_modeling_bi_decision_support"
    assert by_slot["ibm_bullets:bul_ibm_005"]["root_id"] == "reb_ibm_aws_alliance_partner_cosell_gtm"
    assert by_slot["ibm_bullets:bul_ibm_005"]["metric_outcome_id"] == "metric_ibm_20pct_joint_revenue_growth"
    assert by_slot["ibm_bullets:bul_ibm_005"]["metric_value"] == "20"
    assert by_slot["ibm_bullets:bul_ibm_005"]["metric_unit"] == "PERCENT"

    # InsurTech bullets allocate non-metric AWS migration and regulated control roots
    assert by_slot["insurtech_bullets:bul_insurtech_001"]["root_id"] == "reb_insurtech_aws_migration_execution"
    assert by_slot["insurtech_bullets:bul_insurtech_001"]["metric_value"] == ""
    assert by_slot["insurtech_bullets:bul_insurtech_002"]["root_id"] == "reb_insurtech_regulated_aws_control_implementation"
    assert by_slot["insurtech_bullets:bul_insurtech_002"]["metric_value"] == ""

    # InsurTech narrative derives from the two InsurTech bullet roots
    assert by_slot["insurtech_narrative:derived:01"]["root_id"] == "reb_insurtech_aws_migration_execution"
    assert by_slot["insurtech_narrative:derived:02"]["root_id"] == "reb_insurtech_regulated_aws_control_implementation"

    # All 11 active claim-bearing sections slice cleanly with matching allocation_plan_digest
    active_sections = [s for s in ALL_CLAIM_BEARING_SECTIONS if not s.startswith("ey_")]
    for section_id in active_sections:
        sliced = slice_section_plan_for_allocation(
            section_plan=bundle["section_plans"][section_id],
            allocation_plan=plan,
            final_evidence_contract=bundle["section_final_evidence_contracts"][section_id],
            section_id=section_id,
        )
        assert sliced["allocation_plan_digest"] == plan["allocation_plan_digest"]
        assert sliced["global_uniqueness_claimed"] is True
        assert len(sliced["allocation_assignments"]) >= 1


def test_patch_wave_dispatch_caps_lane_wait_by_run_timeout() -> None:
    import inspect
    from apps_rg.runtime.orchestration import patch_run_wave_dispatch

    src = inspect.getsource(patch_run_wave_dispatch.dispatch_patch_lanes_wave_parallel)
    assert "run_timeout - (now_mono - clock_start)" in src


def test_mandatory_output_posix_paths_and_passing_section_classification() -> None:
    from apps_rg.runtime.outputs.bcg_inline_output import _build_inline_required_output
    from apps_rg.runtime.outputs.section_lane_tables import _classify_failure

    assert (
        _classify_failure("competencies", [], {}, x3_code="X3_ALLOW")
        == "No section-level failure recorded."
    )
    assert "Evidence mapping failure" in _classify_failure(
        "competencies",
        [{"gate_id": "x2_competencies_source_fact"}],
        {},
        x3_code="X3_BLOCK",
    )
    doc = {
        "run_root_abs": "/tmp/run_root",
        "result_summary": {"outcome_authorized": True, "x3_disposition": "X3_ALLOW", "completion_status": "PASS"},
        "section_counts": {"total": 12, "ran_real_llm": 11, "allowed": 12, "blocked": 0, "pre_run_blocked": 0, "not_run": 0},
        "section_lane_table": [],
        "final_resume_output": {"status": "PASS"},
        "rca_findings": [],
        "sections": [],
    }
    inline = _build_inline_required_output(doc)
    for item in inline["bcg"]["evidence_map"]:
        assert "\\" not in item["path"]


def test_multi_archetype_dynamic_jd_allocation_diversity() -> None:
    repo = _repo_root()
    ins_bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="Senior Vice President, IT Strategy & Innovation",
        jd_text=(
            "Brown & Brown Insurance - Senior Vice President, IT Strategy & Innovation. "
            "Lead enterprise technology strategy, core P&C insurance platform modernization, "
            "underwriting and claims automation, Guidewire policy administration, and enterprise architecture."
        ),
        briefing_text="Target role: SVP IT Strategy & Innovation at Brown & Brown Insurance.",
    )
    ai_bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="SVP Engineering, Agentic AI & Knowledge Graph Platforms",
        jd_text=(
            "Lead agentic AI platform engineering, multi-agent orchestration, bitemporal GraphRAG "
            "hybrid retrieval, LLM runtime control planes, and MCP tool governance."
        ),
        briefing_text="Target role: SVP Engineering, Agentic AI & Knowledge Graph Platforms.",
    )
    cloud_bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="SVP Cloud Architecture & Distributed Data Platforms",
        jd_text=(
            "Citi Institutional Banking - Firmwide AI Strategy & Cloud Architecture. "
            "Lead AWS cloud modernization, microservices event-driven Kafka architectures, "
            "Databricks lakehouse data pipelines, and DevSecOps release resilience."
        ),
        briefing_text="Target role: SVP Cloud Architecture & Distributed Data Platforms.",
    )

    def _visible_roots(bundle: dict) -> set[str]:
        return {
            str(r["root_id"])
            for r in bundle["allocation_plan"]["assignments"]
            if r.get("counts_toward_global_uniqueness") is not False
        }

    ins_roots = _visible_roots(ins_bundle)
    ai_roots = _visible_roots(ai_bundle)
    cloud_roots = _visible_roots(cloud_bundle)

    # Unrelated archetypes must dynamically select distinct role-episode roots (< 55% Jaccard overlap)
    jacc_ins_ai = len(ins_roots & ai_roots) / len(ins_roots | ai_roots)
    jacc_ai_cloud = len(ai_roots & cloud_roots) / len(ai_roots | cloud_roots)
    assert jacc_ins_ai < 0.55, f"Expected < 0.55 Jaccard overlap between Insurance and AI/ML JDs, got {jacc_ins_ai:.3f}"
    assert jacc_ai_cloud < 0.55, f"Expected < 0.55 Jaccard overlap between AI/ML and Cloud JDs, got {jacc_ai_cloud:.3f}"
    assert "reb_slalom_bi_temporal_knowledge_graph_hybrid_retrieval" in ai_roots or "reb_slalom_autonomous_agentic_sdlc_mcp" in ai_roots



