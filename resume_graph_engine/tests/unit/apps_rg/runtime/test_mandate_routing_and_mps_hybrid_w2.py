"""Wave 2 verification: Unified Mandate Routing Engine, word-boundary scoring, and Apple Silicon MPS hybrid retrieval."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import canonical_sha256
from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    APPROVED_EDGE_TYPES,
    ROLE_FAMILY_TRACK_WEIGHTS,
    TAXONOMY_TO_PROJECTION_ROLE,
    build_track_weighted_expansion,
    infer_projection_role_family_key,
)
from apps_rg.runtime.c0.mandate_routing_engine import (
    CANONICAL_TAXONOMY_TO_PROJECTION,
    MandateRoutingEngine,
    has_word_signal,
    resolve_mandate_route,
)
from apps_rg.runtime.sections.graph_role_episode_selector import (
    _BUNDLE_FILES,
    build_selected_graph_evidence_plan_for_section,
)
from apps_rg.runtime.sections.lane_perf_sync_helpers import (
    score_domain_aware_target_alignment,
)
from apps_rg.runtime.semantic_unit_retrieval import (
    ACTIVATION_STATUS_ARCHIVE_VERIFIED,
    assert_semantic_unit_activation_status,
    retrieve_and_expand_semantic_units,
    retrieve_semantic_units_quad_hybrid,
)

REPO = Path(__file__).resolve().parents[4]


def test_all_20_taxonomy_families_map_without_fallback_collisions() -> None:
    tax_path = REPO / "src/apps_rg/config/domain_contract/master_role_family_taxonomy.yaml"
    tax = yaml.safe_load(tax_path.read_text(encoding="utf-8"))
    family_ids = [str(row["id"]) for row in tax["role_families"]]
    assert len(family_ids) == 20
    for fid in family_ids:
        assert fid in CANONICAL_TAXONOMY_TO_PROJECTION, fid
        assert fid in TAXONOMY_TO_PROJECTION_ROLE, fid
        proj = TAXONOMY_TO_PROJECTION_ROLE[fid]
        assert proj in ROLE_FAMILY_TRACK_WEIGHTS, (fid, proj)


def test_six_executive_archetypes_route_distinctly_without_split_brain() -> None:
    engine = MandateRoutingEngine(repo_root=REPO)

    # 1. Digital Insurer CTO / Lead Engineer (NO literal 'agentic' required in title!)
    insurer_cto = engine.route(
        target_role="Chief Technology Officer & Lead Engineer",
        jd_text="Digital life insurance carrier modernizing underwriting, actuarial pricing, policy administration, and AI decision platforms on AWS.",
    )
    assert insurer_cto.canonical_projection_role == "INSURANCE_CARRIER_TRANSFORMATION"
    assert insurer_cto.selector_profile == "insurance_agentic_ai"
    assert insurer_cto.track_weights["track_actuarial_risk_derivatives"] >= 0.30
    assert insurer_cto.employer_weights["early_career"] >= 0.80
    assert insurer_cto.employer_weights["ey"] >= 0.75
    assert "cert_fsa_001" in insurer_cto.credential_elevation_ids
    assert insurer_cto.fde_context is False
    assert insurer_cto.requires_commercial_pairing is True

    # 2. Global Bank Chief AI & Model Risk Officer (SR 11-7 must NOT trigger fde_context!)
    bank_mrm = engine.route(
        target_role="Chief AI & Model Risk Officer",
        jd_text="Global institutional bank owning SR 11-7 model risk governance, BCBS 239 data lineage, CCAR stress testing, and governed LLM deployment.",
    )
    assert bank_mrm.canonical_projection_role in {"BANKING_PLATFORM_AI", "REGULATED_AI_GOVERNANCE"}
    assert bank_mrm.selector_profile == "banking_model_risk_ai"
    assert bank_mrm.fde_context is False
    assert bank_mrm.employer_weights["ey"] >= 0.85
    assert bank_mrm.slot_budget_profile["ey_bullets"] >= 2

    # 3. Frontier AI Lab VP Applied AI & Partnerships
    frontier_partner = engine.route(
        target_role="VP Applied AI & Strategic Partnerships",
        jd_text="Lead hyperscaler alliances, GSI/ISV partner engineering, joint reference architectures, and enterprise co-sell GTM for frontier LLM deployment.",
    )
    assert frontier_partner.canonical_projection_role == "PARTNER_APPLIED_AI_ARCHITECTURE"
    assert frontier_partner.selector_profile == "ai_partnerships_gtm"
    assert frontier_partner.fde_context is False

    # 4. PE Operating Partner (Enterprise AI Transformation)
    pe_partner = engine.route(
        target_role="Operating Partner, Enterprise AI Transformation",
        jd_text="Private equity portfolio value creation across EBITDA margin expansion, M&A due diligence, board-level operating model redesign, and AI platforms.",
    )
    assert pe_partner.canonical_projection_role == "PE_OPERATING_PARTNER_TRANSFORMATION"
    assert pe_partner.selector_profile == "executive_agentic_transformation"
    assert pe_partner.employer_weights["ey"] >= 0.85
    assert pe_partner.slot_budget_profile["ey_bullets"] >= 2

    # 5. Pure SaaS SVP Engineering (compresses EY / early career cleanly while keeping 3-era floor)
    saas_svp = engine.route(
        target_role="SVP of Software Engineering",
        jd_text="Scale distributed systems, microservices, multi-agent LLM orchestration, developer platform reliability, and 100+ engineer org.",
    )
    assert saas_svp.canonical_projection_role == "SVP_ENGINEERING_AI_PLATFORM"
    assert saas_svp.selector_profile == "svp_agentic_engineering"
    assert saas_svp.slot_budget_profile["ey_bullets"] == 1
    assert saas_svp.slot_budget_profile["early_career_bullets"] == 1
    assert saas_svp.track_weights["track_actuarial_risk_derivatives"] >= 0.08

    # 6. Healthcare Payer CDAO (elevates Columbia MS Biostatistics + FSA early career)
    health_cdao = engine.route(
        target_role="Chief Data & AI Officer (CDAO)",
        jd_text="National healthcare payer optimizing medical loss ratio (MLR), HIPAA-compliant claims analytics, biostatistics risk modeling, and enterprise AI.",
    )
    assert health_cdao.canonical_projection_role == "HEALTHCARE_PAYER_DATA_AI"
    assert health_cdao.selector_profile == "healthcare_payer_data_ai"
    assert "edu_columbia_ms_biostat_001" in health_cdao.credential_elevation_ids
    assert "cert_fsa_001" in health_cdao.credential_elevation_ids
    assert health_cdao.slot_budget_profile["early_career_bullets"] >= 2

    # Consistency check: infer_projection_role_family_key matches MandateRoutingEngine SSOT.
    assert infer_projection_role_family_key(
        target_role="Chief Technology Officer & Lead Engineer",
        jd_text="Digital life insurance carrier modernizing underwriting, actuarial pricing, policy administration, and AI decision platforms on AWS.",
    ) == insurer_cto.canonical_projection_role


def test_word_boundary_alignment_blocks_substring_ai_false_positives() -> None:
    assert has_word_signal("claims maintain financial certainty", "ai") is False
    assert has_word_signal("enterprise ai platform governance", "ai") is True
    # 'claims' and 'maintain' both contain substring 'ai', must NOT get +1.0 for term 'ai'.
    score_false = score_domain_aware_target_alignment(
        "claims maintain financial",
        "certain terrain details",
        ("ai",),
    )
    score_true = score_domain_aware_target_alignment(
        "enterprise ai systems",
        "governed ai architecture",
        ("ai",),
    )
    assert score_false == 0.0
    assert score_true >= 1.0


def test_track_weighted_expansion_and_selector_include_bridges_and_early_career() -> None:
    assert "pillar_phase_bridge" in APPROVED_EDGE_TYPES
    assert "skill_reinforces_skill" in APPROVED_EDGE_TYPES
    assert any(lane == "early_career" for lane, _ in _BUNDLE_FILES)

    expansion = build_track_weighted_expansion(
        role_family_key="INSURANCE_CARRIER_TRANSFORMATION",
        jd_text="Insurance carrier CTO modernizing underwriting, actuarial pricing, cloud platform, and governed agentic AI.",
        bind_c03=False,
        repo_root=REPO,
    )
    assert len(expansion["tracks_with_facts"]) == 3
    assert expansion["selected_fact_count_by_track"]["track_actuarial_risk_derivatives"] > 0

    plan, _ordered, _allowed = build_selected_graph_evidence_plan_for_section(
        repo_root=REPO,
        section_id="early_career_bullets",
        target_role="Chief Technology Officer",
        jd_text="Digital life insurer CTO leading underwriting, actuarial reserving, derivatives hedging, and AI platforms.",
    )
    assert plan["role_family_key"] == "INSURANCE_CARRIER_TRANSFORMATION"
    assert plan["target_role_profile"] == "insurance_agentic_ai"
    assert any(str(nid).startswith("reb_early_career_") for nid in plan["selected_nodes"])


def test_apple_silicon_mps_runtime_contract_and_quad_hybrid_semantic_units(tmp_path: Path) -> None:
    contract_path = REPO / "tools/apps_rg_standalone/c03_embedding_runtime_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert contract["promoted_device"] == "mps"
    assert "cuda" not in json.dumps(contract).lower()
    unsigned = {k: v for k, v in contract.items() if k != "contract_sha256"}
    assert contract["contract_sha256"] == canonical_sha256(unsigned)

    act = assert_semantic_unit_activation_status(allow_unqualified=False, archive_verified=True)
    assert act["status"] == ACTIVATION_STATUS_ARCHIVE_VERIFIED

    db_path = tmp_path / "w2_hybrid.sqlite"
    materialize_augmented_skills_graph_sqlite(repo_root=REPO, db_path=db_path)
    conn = sqlite3.connect(db_path)
    try:
        epoch_units = conn.execute(
            "SELECT COUNT(*) FROM semantic_unit WHERE unit_type = 'career_epoch_summary'"
        ).fetchone()[0]
        assert epoch_units >= 3
        hybrid = retrieve_semantic_units_quad_hybrid(
            conn,
            "Digital life insurer CTO actuarial FSA underwriting cloud agentic AI platform",
            db_path=str(db_path),
            limit=12,
        )
        assert hybrid["unit_count"] > 0
        assert hybrid["dense_executed"] is True
        assert hybrid["sparse_executed"] is True
        assert hybrid["bm25_executed"] is True
        assert hybrid["colbert_executed"] is True

        expanded = retrieve_and_expand_semantic_units(
            conn,
            "Actuarial FSA risk governance and multi-agent AI runtime control plane",
            db_path=str(db_path),
            top_k_seeds=6,
            max_depth=2,
        )
        assert expanded["expanded_path_count"] > 0
    finally:
        conn.close()
