"""Wave 2 unit tests for Overview-vs-Bullet Disjoint Fact Partitioning and FactAnchor lane binding."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.c0.c0_fact_anchor import build_fact_anchor
from apps_rg.runtime.c0.resume_graph_allocation import (
    NARRATIVE_DERIVATION_POLICY,
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
)
from apps_rg.runtime.sections.ibm_bullets_lane import (
    _materialize_ibm_bullets_from_frozen_allocation,
)
from apps_rg.runtime.sections.role_episode_lane import (
    _model_bullet_surface_binding,
    _proof_fact_surface_tokens,
    _proof_fact_text,
)
from apps_rg.runtime.sections.unify_bullets_lane import (
    _claim_text_by_unify_slot,
)


def _apps_rg_root() -> Path:
    return Path(__file__).resolve().parents[3] / "resume_graph_engine"


def test_overview_and_bullet_disjoint_fact_partitioning_for_agentic_and_balanced_profiles() -> None:
    repo_root = _apps_rg_root()
    bundle = build_whole_resume_graph_allocation(
        repo_root=repo_root,
        target_role="SVP Agentic Engineering and Platform",
        jd_text=(
            "Lead agentic AI platform architecture, multi-agent runtime governance, GraphRAG, "
            "and hyperscaler co-sell across Google Cloud, Vertex AI, Anthropic Claude, and AWS."
        ),
    )
    plan = bundle["allocation_plan"]
    assignments = plan["assignments"]

    exec_roots = {
        str(row["root_id"])
        for row in assignments
        if row["section_id"] == "executive_summary"
    }
    assert len(exec_roots) == 3

    for narrative_section, bullet_section in NARRATIVE_DERIVATION_POLICY.items():
        if bullet_section in ("ey_bullets", "insurtech_bullets"):
            continue
        bullet_roots = {
            str(row["root_id"])
            for row in assignments
            if row["section_id"] == bullet_section
        }
        narrative_roots = {
            str(row["root_id"])
            for row in assignments
            if row["section_id"] == narrative_section
        }
        # Bullet roots must be disjoint from executive_summary roots when unpinned
        assert bullet_roots.isdisjoint(exec_roots), (
            f"Expected {bullet_section} roots {bullet_roots} to be disjoint from executive_summary {exec_roots}"
        )
        # Narrative derived roots must pull from unused role roots disjoint from bullet_roots and exec_roots
        assert narrative_roots.isdisjoint(bullet_roots), (
            f"Expected {narrative_section} roots {narrative_roots} to be disjoint from {bullet_section} {bullet_roots}"
        )
        assert narrative_roots.isdisjoint(exec_roots), (
            f"Expected {narrative_section} roots {narrative_roots} to be disjoint from executive_summary {exec_roots}"
        )


def test_role_episode_ibm_and_unify_lanes_consume_fact_anchor() -> None:
    fact_row = {
        "fact_id": "bul_slalom_001",
        "role_episode_bundle_id": "reb_slalom_ecosystem_accelerators",
        "employer_lane": "slalom",
        "claim_text": "",
        "graph_skill_node_ids": ["skill_hyperscaler_alliance_cosell"],
    }
    anchor = build_fact_anchor(
        {
            **fact_row,
            "metric_text": "$120M+ total contract value across 50+ accounts",
            "metric_value": "120",
            "root_claim_text": "Directed multi-partner AI ecosystem expansion across Google Cloud, Vertex AI, Model Armor, Anthropic Claude, OpenAI Codex, and AWS",
        },
        repo_root=_apps_rg_root(),
    )
    fact_row["fact_anchor"] = anchor
    fact_row["raw_chunk"] = anchor["resolved_raw_chunk"]

    tokens = _proof_fact_surface_tokens(fact_row)
    assert {"google", "vertex", "anthropic", "claude", "120m"}.issubset(tokens)
    rendered = _proof_fact_text(fact_row)
    assert len(rendered.split()) >= 18

    bound, matched = _model_bullet_surface_binding(
        "Directed multi-partner AI ecosystem expansion across Google Cloud, Vertex AI, and Anthropic Claude delivering $120M+ total contract value.",
        fact_row,
    )
    assert bound is True
    assert len(matched) >= 3

    unify_plan = {
        "facts": [
            {
                "fact_id": "bul_unify_001",
                "claim_text": "",
                "fact_anchor": anchor,
            }
        ]
    }
    unify_claims = _claim_text_by_unify_slot(unify_plan)
    assert len(unify_claims["bul_unify_001"].split()) >= 18

    ibm_parsed: dict[str, object] = {"bullets": []}
    ibm_plan = {
        "allocation_assignments": [
            {
                "section_id": "ibm_bullets",
                "claim_unit_id": f"ibm_bullets:bul_ibm_00{i}",
                "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                "skill_id": "skill_partner_cloud_vendor_joint_gtm",
                "root_claim_text": "",
                "metric_text": "20% joint revenue growth",
                "fact_anchor": anchor,
            }
            for i in range(1, 6)
        ]
    }
    assert _materialize_ibm_bullets_from_frozen_allocation(ibm_parsed, selected_fact_plan=ibm_plan) is True
    assert len(ibm_parsed["bullets"]) == 5
