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
    assert all("required_root_id" not in row for row in plan["assignments"])

    # Headline and Executive Summary dynamically allocate insurance, core modernization & regulated cloud/AI roots
    head_roots = {by_slot[f"headline:skill:{i:02d}"]["root_id"] for i in range(1, 4)}
    exec_roots = {by_slot[f"executive_summary:claim:{i:02d}"]["root_id"] for i in range(1, 5)}
    assert len(head_roots) == 3
    assert len(exec_roots) == 4
    assert any(r.startswith(("reb_insurtech_", "reb_ey_insurance_")) for r in head_roots)
    assert any(r.startswith(("reb_insurtech_", "reb_unify_regulated_")) for r in exec_roots)
    assert by_slot["executive_summary:claim:01"]["metric_value"] != ""
    assert by_slot["executive_summary:claim:01"]["metric_unit"] == "PERCENT"

    # Unify bullets preserve exact numeric metrics on bul_unify_005 and bul_unify_006 and remain disjoint from exec_summary
    unify_roots = {by_slot[f"unify_bullets:bul_unify_{i:03d}"]["root_id"] for i in range(1, 7)}
    assert len(unify_roots) == 6
    assert unify_roots.isdisjoint(exec_roots)
    assert by_slot["unify_bullets:bul_unify_005"]["metric_value"] != ""
    assert by_slot["unify_bullets:bul_unify_006"]["metric_value"] != ""

    # IBM bullets dynamically allocate 5 distinct role episode roots disjoint from exec_summary with numeric metric on bul_ibm_005
    ibm_roots = {by_slot[f"ibm_bullets:bul_ibm_{i:03d}"]["root_id"] for i in range(1, 6)}
    assert len(ibm_roots) == 5
    assert ibm_roots.isdisjoint(exec_roots)
    assert "reb_ibm_aws_modernization_architecture" in (ibm_roots | exec_roots)
    assert by_slot["ibm_bullets:bul_ibm_005"]["metric_outcome_id"] != ""
    assert by_slot["ibm_bullets:bul_ibm_005"]["metric_value"] != ""

    # InsurTech bullets dynamically allocate 2 distinct non-metric insurance roots disjoint from exec_summary
    insurtech_bullet_roots = {
        by_slot["insurtech_bullets:bul_insurtech_001"]["root_id"],
        by_slot["insurtech_bullets:bul_insurtech_002"]["root_id"],
    }
    assert len(insurtech_bullet_roots) == 2
    assert insurtech_bullet_roots.isdisjoint(exec_roots)
    assert by_slot["insurtech_bullets:bul_insurtech_001"]["metric_value"] == ""
    assert by_slot["insurtech_bullets:bul_insurtech_002"]["metric_value"] == ""

    # InsurTech narrative derives disjoint roots from the remaining InsurTech pool
    insurtech_narrative_roots = {
        by_slot["insurtech_narrative:derived:01"]["root_id"],
        by_slot["insurtech_narrative:derived:02"]["root_id"],
    }
    assert insurtech_narrative_roots.isdisjoint(insurtech_bullet_roots)
    assert insurtech_narrative_roots.isdisjoint(exec_roots)

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

    # Unrelated archetypes must dynamically select distinct role-episode roots (< 65% Jaccard overlap)
    jacc_ins_ai = len(ins_roots & ai_roots) / len(ins_roots | ai_roots)
    jacc_ai_cloud = len(ai_roots & cloud_roots) / len(ai_roots | cloud_roots)
    assert jacc_ins_ai < 0.65, f"Expected < 0.65 Jaccard overlap between Insurance and AI/ML JDs, got {jacc_ins_ai:.3f}"
    assert jacc_ai_cloud < 0.65, f"Expected < 0.65 Jaccard overlap between AI/ML and Cloud JDs, got {jacc_ai_cloud:.3f}"
    assert "reb_slalom_bi_temporal_knowledge_graph_hybrid_retrieval" in ai_roots or "reb_slalom_autonomous_agentic_sdlc_mcp" in ai_roots


def test_truist_forward_deployed_engineering_allocation_excludes_cosell_bundles() -> None:
    from apps_rg.fact_inventory.candidate_fact_ledger import load_master_role_family_taxonomy
    from apps_rg.fact_inventory.track_weighted_graph_expansion import infer_projection_role_family_key

    repo = _repo_root()
    jd_text = (
        "Head of Forward Deployed Engineering - Truist Financial Corporation. "
        "Build and lead the Forward Deployed Engineering organization, embed with business "
        "and technology teams as design partners, translate complex workflows into rapid "
        "AI prototypes and production-grade enterprise solutions on AWS, and enforce SR 11-7 "
        "model risk management, auditability, and cybersecurity guardrails."
    )
    briefing_text = (
        "Target Role: Head of Forward Deployed Engineering at Truist Financial Corporation. "
        "Emphasize 105-person engineering organization leadership, rapid prototyping to production "
        "activation, governed agentic AI runtime controls, and regulated banking MRM/SR 11-7 compliance."
    )
    rf_key = infer_projection_role_family_key(
        target_role="Head of Forward Deployed Engineering",
        jd_text=jd_text,
        briefing_text=briefing_text,
        taxonomy=load_master_role_family_taxonomy(repo_root=repo),
    )
    assert rf_key == "SVP_ENGINEERING_AI_PLATFORM"

    bundle = build_whole_resume_graph_allocation(
        repo_root=repo,
        target_role="Head of Forward Deployed Engineering",
        jd_text=jd_text,
        briefing_text=briefing_text,
    )
    plan = bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(plan) == []
    assert plan["uniqueness_receipt"]["pass"] is True
    assert bundle["section_plans"]["executive_summary"]["target_role_profile"] == "svp_agentic_engineering"

    cosell_roots = {
        "reb_unify_partner_channel_cosell",
        "reb_unify_hyperscaler_joint_solution_architecture",
        "reb_slalom_ecosystem_accelerators",
        "reb_ibm_aws_alliance_partner_cosell_gtm",
    }
    allocated_roots = {str(row["root_id"]) for row in plan["assignments"]}
    assert not (allocated_roots & cosell_roots)
    exec_roots = {
        str(row["root_id"])
        for row in plan["assignments"]
        if str(row["section_id"]) == "executive_summary"
    }
    slalom_bullet_roots = {
        str(row["root_id"])
        for row in plan["assignments"]
        if str(row["section_id"]) == "slalom_bullets"
    }
    assert slalom_bullet_roots.isdisjoint(exec_roots)
    assert "reb_slalom_autonomous_agentic_sdlc_mcp" not in exec_roots
    assert {
        "reb_slalom_engineering_practice_leadership",
        "reb_slalom_agentic_client_delivery",
        "reb_slalom_governed_runtime_scaling",
    }.issubset(slalom_bullet_roots | exec_roots)
    assert {
        "reb_slalom_engineering_practice_leadership",
        "reb_slalom_agentic_client_delivery",
        "reb_unify_regulated_enterprise_ai_governance",
        "reb_unify_agentic_platform_architecture",
        "reb_ibm_aws_modernization_architecture",
    }.issubset(allocated_roots)

    banned_plumbing = (
        "119-package",
        "32 readiness gates",
        "6 custom mcp servers",
        "sqlite wal",
        "1024-d bge-m3",
        "dirichlet-laplace",
        "universal write gateway",
        "dual-track live executive copilot",
    )
    for sec_id, sec_plan in bundle["section_plans"].items():
        for fact in sec_plan.get("selected_facts") or []:
            prose_blob = " ".join(
                str(fact.get(k) or "")
                for k in ("claim", "proof", "raw_chunk", "metric_values")
            ).lower()
            for token in banned_plumbing:
                assert (
                    token not in prose_blob
                ), f"Internal repo plumbing token {token!r} leaked in {sec_id}"





