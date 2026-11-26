"""Wave 6 End-to-End Certification: Six Senior Executive Leadership Archetypes.

Exercises the complete unmocked production pipeline end-to-end:
  1. Multi-hop SQLite graph traversal & archive-verified capability activation
  2. Unified Mandate Routing Engine (zero split-brain, zero company overfitting)
  3. Mandate-adaptive two-page whole-resume solver (global uniqueness + 3-era weaving)
  4. Live graph-backed final resume assembly (zero static canned IBM prose, zero HOLD figures)
  5. X2 deterministic surface checks & blocking X1D career-arc/mandate differentiation veto
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from apps_rg.fact_inventory.graph_sqlite_path_index import validate_graphdb_capability_integrity
from apps_rg.runtime.c0.resume_graph_allocation import (
    ALL_CLAIM_BEARING_SECTIONS,
    build_whole_resume_graph_allocation,
    slice_section_plan_for_allocation,
    validate_resume_graph_allocation_plan,
)
from apps_rg.runtime.contracts.metric_lexical_primitives import HOLD_METRIC_TEXT_RE
from apps_rg.runtime.final_resume_outputs import _ensure_jd_tailored_final_resume_json
from apps_rg.runtime.judges.executive_summary_judge_packet import (
    build_executive_summary_judge_packet,
    render_judge_prompt_from_packet,
)
from apps_rg.runtime.judges.v3_section_judge import evaluate_v3_judge_response_to_dict
from apps_rg.runtime.sections.ibm_bullets.frozen_allocation import (
    _IBM_FROZEN_ALLOCATION_DISPLAY_COMPOSITIONS,
)

SIX_ARCHETYPES: tuple[dict[str, object], ...] = (
    {
        "id": "digital_insurer_cto",
        "company": "Digital Life Insurer",
        "role": "Lead Engineer CTO",
        "jd": (
            "Digital life insurer CTO leading underwriting modernization, actuarial reserving, "
            "policy administration systems, AWS cloud scale, P&L margin expansion, and governed "
            "agentic AI platform engineering."
        ),
        "expected_profile": "insurance_agentic_ai",
        "expected_credential": "cert_fsa_001",
        "min_ey_bullets": 2,
        "min_early_bullets": 2,
        "require_t1_headline": True,
        "require_commercial_pairing": True,
    },
    {
        "id": "global_bank_caio_mrm",
        "company": "Global Institutional Bank",
        "role": "Chief AI Officer",
        "jd": (
            "Global bank Chief AI Officer owning SR 11-7 model risk management, BCBS 239 risk data "
            "aggregation, enterprise AI governance, derivatives stress testing, and multi-agent control planes."
        ),
        "expected_profile": "banking_model_risk_ai",
        "expected_credential": "cert_fsa_001",
        "min_ey_bullets": 2,
        "min_early_bullets": 2,
        "require_t1_headline": True,
        "require_commercial_pairing": True,
    },
    {
        "id": "frontier_ai_partnerships",
        "company": "Frontier AI Lab",
        "role": "VP Applied AI & Partnerships",
        "jd": (
            "Frontier AI lab VP Applied AI & Partnerships scaling hyperscaler AWS and Google Cloud "
            "Vertex AI co-sell alliances, GSI reference architectures, executive workshops, and enterprise adoption."
        ),
        "expected_profile": "ai_partnerships_gtm",
        "expected_credential": "cert_aws_sap_001",
        "min_ey_bullets": 1,
        "min_early_bullets": 1,
        "require_t1_headline": False,
        "require_commercial_pairing": True,
    },
    {
        "id": "pe_operating_partner",
        "company": "Enterprise Private Equity Fund",
        "role": "Operating Partner, AI & Cloud Transformation",
        "jd": (
            "Private equity Operating Partner driving portfolio EBITDA growth, gross margin expansion, "
            "P&L value creation, AWS cloud modernization, and governed AI transformation across financial companies."
        ),
        "expected_profile": "executive_agentic_transformation",
        "expected_credential": "cert_aws_sap_001",
        "min_ey_bullets": 2,
        "min_early_bullets": 1,
        "require_t1_headline": False,
        "require_commercial_pairing": True,
    },
    {
        "id": "saas_svp_engineering",
        "company": "Enterprise SaaS Platform",
        "role": "SVP Engineering",
        "jd": (
            "SaaS SVP Engineering scaling multi-agent platform architecture, GraphRAG retrieval, "
            "distributed cloud reliability, P&L commercial growth, and enterprise AI adoption."
        ),
        "expected_profile": "svp_agentic_engineering",
        "expected_credential": "cert_aws_sap_001",
        "min_ey_bullets": 1,
        "min_early_bullets": 1,
        "require_t1_headline": False,
        "require_commercial_pairing": True,
    },
    {
        "id": "healthcare_payer_cdao",
        "company": "National Health Plan",
        "role": "Chief Data & AI Officer",
        "jd": (
            "Healthcare payer CDAO leading biostatistics, claims analytics, medical loss ratio "
            "forecasting, actuarial reserving, HIPAA governance, and clinical AI decision platforms."
        ),
        "expected_profile": "healthcare_payer_data_ai",
        "expected_credential": "edu_columbia_ms_biostat_001",
        "min_ey_bullets": 2,
        "min_early_bullets": 2,
        "require_t1_headline": True,
        "require_commercial_pairing": True,
    },
)


def _rg_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_multihop_sqlite_graph_integrity_is_verified_before_e2e_runs() -> None:
    db_path = _rg_root() / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
    assert db_path.is_file()
    conn = sqlite3.connect(str(db_path))
    try:
        integrity = validate_graphdb_capability_integrity(conn)
    finally:
        conn.close()
    assert integrity["status"] == "GRAPHDB_CAPABILITY_INTEGRITY_PASS", integrity
    assert _IBM_FROZEN_ALLOCATION_DISPLAY_COMPOSITIONS == {}


@pytest.mark.parametrize("spec", SIX_ARCHETYPES, ids=[s["id"] for s in SIX_ARCHETYPES])
def test_six_archetype_full_career_senior_resume_e2e(
    spec: dict[str, object],
    tmp_path: Path,
) -> None:
    rg_root = _rg_root()
    bundle = build_whole_resume_graph_allocation(
        repo_root=rg_root,
        target_role=str(spec["role"]),
        jd_text=str(spec["jd"]),
    )
    plan = bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(plan) == []
    assert plan["uniqueness_receipt"]["pass"] is True
    assert plan["mandate_route"]["selector_profile"] == spec["expected_profile"]
    assert spec["expected_credential"] in plan["credential_elevation_ids"]
    assert plan["mandate_route"]["requires_commercial_pairing"] is spec["require_commercial_pairing"]

    # Three-era top-section coverage guaranteed on every senior executive mandate.
    exec_lanes = {
        row["employer_lane"]
        for row in plan["assignments"]
        if row["section_id"] == "executive_summary"
    }
    assert {"slalom", "unify", "ibm"}.issubset(exec_lanes)
    assert exec_lanes & {"early_career", "ey", "insurtech"}

    if spec["require_t1_headline"]:
        headline_lanes = {
            row["employer_lane"]
            for row in plan["assignments"]
            if row["section_id"] == "headline"
        }
        assert headline_lanes & {"early_career", "ey", "insurtech"}

    # Dynamic two-page per-employer bullet budgets across all 6 career lanes.
    bullets_by_lane: dict[str, int] = {}
    for row in plan["assignments"]:
        if row["section_id"].endswith("_bullets"):
            bullets_by_lane[row["section_id"]] = bullets_by_lane.get(row["section_id"], 0) + 1
    assert bullets_by_lane["ey_bullets"] >= int(spec["min_ey_bullets"])
    assert bullets_by_lane["early_career_bullets"] >= int(spec["min_early_bullets"])
    total_bullets = sum(bullets_by_lane.values())
    assert 16 <= total_bullets <= 20

    # Every one of the 15 claim-bearing sections slices with sealed digest parity.
    for section_id in ALL_CLAIM_BEARING_SECTIONS:
        sliced = slice_section_plan_for_allocation(
            section_plan=bundle["section_plans"][section_id],
            allocation_plan=plan,
            final_evidence_contract=bundle["section_final_evidence_contracts"][section_id],
            section_id=section_id,
        )
        assert sliced["allocation_plan_digest"] == plan["allocation_plan_digest"]

    # Live graph-backed final resume assembly produces zero HOLD-banned figures & distinct prose.
    final_path = _ensure_jd_tailored_final_resume_json(
        tmp_path / str(spec["id"]),
        repo_root=rg_root,
        target_company=str(spec["company"]),
        target_role=str(spec["role"]),
        jd_text=str(spec["jd"]),
        briefing_text="",
    )
    final_doc = json.loads(final_path.read_text(encoding="utf-8"))
    assert final_doc["generated_content_source"] == "live_whole_resume_graph_allocation_zero_canned_prose"
    by_sec = {
        s["section_id"]: s.get("l2_output_snapshot") or {}
        for s in final_doc["sections"]
        if s.get("section_kind") == "generated_lane"
    }
    exec_text = str(by_sec["executive_summary"].get("resume_display_text") or "")
    headline_text = str(by_sec["headline"].get("headline_line") or "")
    assert exec_text and headline_text
    assert not HOLD_METRIC_TEXT_RE.search(exec_text)
    assert "$30M" not in exec_text and "$15M" not in exec_text and "$82M" not in exec_text

    # Blind judge packet includes candidate_mandate_differentiators and strips deterministic gate priming.
    packet = build_executive_summary_judge_packet(
        resume_display_text=exec_text,
        claim_ledger=[],
        allowed_fact_packet=[],
        targeting_context={"target_role": str(spec["role"]), "jd_text": str(spec["jd"])},
        deterministic_gate_summary={"all_passed": True},
    )
    assert packet["candidate_mandate_differentiators"]["mandate_profile"] == spec["expected_profile"]
    rendered_prompt = render_judge_prompt_from_packet(packet)
    assert "deterministic_gate_summary" not in rendered_prompt

    # Blocking X1D differentiation gate rejects an executive summary that drops mandate differentiation.
    failed_eval = evaluate_v3_judge_response_to_dict(
        {
            "cold_read_takeaway": f"Drops core differentiation for {spec['role']}.",
            "checks": {
                "verified_claim_entailment": {"verdict": "YES", "evidence_span": ""},
                "proof_boundary_integrity": {"verdict": "YES", "evidence_span": ""},
                "mandate_fit_without_clutter": {"verdict": "NO", "evidence_span": exec_text[:24]},
                "authentic_human_voice": {"verdict": "YES", "evidence_span": ""},
                "distinct_mechanism_to_outcome": {"verdict": "YES", "evidence_span": ""},
            },
            "failure_tags": ["OMITTED_CONSTRAINT"],
        },
        section_id="executive_summary",
        candidate_text=exec_text,
    )
    assert failed_eval["score"] == 0.8
    assert failed_eval["pass"] is False
    assert failed_eval["decisive_failure"] is True
