"""Wave 2 unit tests for Overview-vs-Bullet Disjoint Fact Partitioning and FactAnchor lane binding."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.c0.c0_fact_anchor import build_fact_anchor, resolve_raw_chunk_text
from apps_rg.runtime.c0.resume_graph_allocation import (
    NARRATIVE_DERIVATION_POLICY,
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
)
from apps_rg.runtime.contracts.metric_lexical_primitives import proof_fact_surface_tokens
from apps_rg.runtime.sections.ibm_bullets_lane import (
    _materialize_ibm_bullets_from_frozen_allocation,
)
from apps_rg.runtime.sections.role_episode_lane import run_slalom_bullets_x2_gates
from apps_rg.runtime.sections.unify_bullets_lane import (
    normalize_unify_parsed_without_ledger_synthesis,
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

    tokens = proof_fact_surface_tokens(fact_row)
    assert {"google", "vertex", "anthropic", "claude", "120m"}.issubset(tokens)
    rendered = resolve_raw_chunk_text(fact_row)
    assert len(rendered.split()) >= 18

    bound_text = (
        "Directed multi-partner AI ecosystem expansion across Google Cloud, Vertex AI, "
        "and Anthropic Claude delivering $120M+ total contract value."
    )
    bound_gates = run_slalom_bullets_x2_gates(
        l2={
            "display_text_authority": "model_selected_graph_bound_surface",
            "selected_fact_plan": {"facts": [fact_row]},
            "bullets": [
                {
                    "bullet_id": "bul_slalom_001",
                    "bullet_text": bound_text,
                    "source_fact_ids": ["bul_slalom_001"],
                }
            ],
            "claim_ledger": [
                {
                    "claim_text": bound_text,
                    "source_fact_ids": ["bul_slalom_001"],
                }
            ],
        },
        allowed=["bul_slalom_001"],
        runtime_generation_status="REAL_LLM",
    )
    bound_auth_gate = next(
        g for g in bound_gates if g["gate_id"] == "x2_slalom_bullets_display_text_proof_authorized"
    )
    assert bound_auth_gate["pass"] is True
    matched = bound_auth_gate["observed_value"]["rows"][0]["model_surface_binding"][0]["anchor_tokens"]
    assert len(matched) >= 3

    unbound_gates = run_slalom_bullets_x2_gates(
        l2={
            "display_text_authority": "model_selected_graph_bound_surface",
            "selected_fact_plan": {"facts": [fact_row]},
            "bullets": [
                {
                    "bullet_id": "bul_slalom_001",
                    "bullet_text": "Managed quarterly vendor invoices across retail branches.",
                    "source_fact_ids": ["bul_slalom_001"],
                }
            ],
            "claim_ledger": [
                {
                    "claim_text": "Managed quarterly vendor invoices across retail branches.",
                    "source_fact_ids": ["bul_slalom_001"],
                }
            ],
        },
        allowed=["bul_slalom_001"],
        runtime_generation_status="REAL_LLM",
    )
    unbound_auth_gate = next(
        g for g in unbound_gates if g["gate_id"] == "x2_slalom_bullets_display_text_proof_authorized"
    )
    assert unbound_auth_gate["pass"] is False

    unify_runtime_payload = {
        "allowed_fact_ids": ["bul_unify_004"],
        "selected_fact_plan": {
            "facts": [
                {
                    "fact_id": "bul_unify_004",
                    "claim_text": "",
                    "fact_anchor": anchor,
                }
            ]
        },
    }
    unify_norm = normalize_unify_parsed_without_ledger_synthesis(
        {
            "bullets": [
                {
                    "bullet_id": "bul_unify_004",
                    "bullet_text": rendered,
                    "source_fact_ids": ["bul_unify_004"],
                }
            ],
            "claim_ledger": [
                {
                    "claim_text": rendered,
                    "source_fact_ids": ["bul_unify_004"],
                }
            ],
        },
        unify_runtime_payload,
    )
    assert unify_norm is not None
    assert any(
        isinstance(entry, dict) and entry.get("operation") == "repair_unify_archive_verbatim_overlap"
        for entry in (unify_norm.get("change_log") or [])
    )

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
