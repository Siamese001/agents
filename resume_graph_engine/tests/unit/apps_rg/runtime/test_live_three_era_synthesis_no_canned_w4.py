"""Wave 4 unit tests: live graph-backed three-era synthesis, retired canned prose, L1 v3 default, and multi-metric binding."""
from __future__ import annotations

import json
import re
from pathlib import Path

from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1_COGNITIVE_V3_CANDIDATE_ARM,
    build_l1_cognitive_treatment,
    treatment_from_task_spec,
)
from apps_rg.runtime.c0.resume_graph_claim_binding import _binding_for_claim
from apps_rg.runtime.contracts.metric_lexical_primitives import HOLD_METRIC_TEXT_RE
from apps_rg.runtime.final_resume_outputs import _ensure_jd_tailored_final_resume_json
from apps_rg.runtime.reasoning.CareerThesisAlignmentAgent import (
    CareerThesisAlignmentAgent,
    format_career_thesis_u0_block,
)
from apps_rg.runtime.sections.ibm_bullets.frozen_allocation import (
    _IBM_FROZEN_ALLOCATION_DISPLAY_COMPOSITIONS,
    _materialize_ibm_bullets_from_frozen_allocation,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def test_static_ibm_display_compositions_retired_and_live_graph_composition_active() -> None:
    assert _IBM_FROZEN_ALLOCATION_DISPLAY_COMPOSITIONS == {}
    parsed: dict = {"bullets": []}
    assignments = [
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": "ibm_bullets:bul_ibm_001",
            "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
            "skill_id": "skill_partner_cloud_vendor_joint_gtm",
            "skill_label": "Cloud Vendor Joint GTM",
            "root_claim_text": "Led IBM-AWS alliance co-sell motions across regulated financial-services accounts",
            "root_claim_outcome": "Accelerated joint modernization pipeline across banking and insurance carriers",
            "metric_text": "20% joint revenue growth",
        }
    ]
    assert _materialize_ibm_bullets_from_frozen_allocation(
        parsed, selected_fact_plan={"allocation_assignments": assignments}
    ) is True
    rendered = parsed["bullets"][0]["bullet_text"]
    assert "20%" in rendered
    assert "ibm-aws" in rendered.lower()


def test_final_resume_outputs_live_graph_synthesis_has_zero_hold_metrics_and_varies_by_mandate(
    tmp_path: Path,
) -> None:
    rg_root = _repo_root()
    ins_path = _ensure_jd_tailored_final_resume_json(
        tmp_path / "insurer_cto",
        repo_root=rg_root,
        target_company="Digital Life Carrier",
        target_role="Lead Engineer CTO",
        jd_text=(
            "Digital life insurer CTO leading underwriting modernization, actuarial reserving, "
            "policy administration, AWS cloud scale, and governed agentic AI platform engineering."
        ),
        briefing_text="Elevate FSA actuarial depth alongside governed agentic AI and commercial scale.",
    )
    payer_path = _ensure_jd_tailored_final_resume_json(
        tmp_path / "payer_cdao",
        repo_root=rg_root,
        target_company="National Health Plan",
        target_role="Chief Data & AI Officer",
        jd_text=(
            "Healthcare payer CDAO leading biostatistics, claims analytics, medical loss ratio "
            "forecasting, actuarial reserving, and governed clinical AI platforms."
        ),
        briefing_text="Elevate Columbia MS Biostatistics and FSA actuarial modeling alongside AI governance.",
    )
    ins_doc = json.loads(ins_path.read_text(encoding="utf-8"))
    payer_doc = json.loads(payer_path.read_text(encoding="utf-8"))

    assert ins_doc["generated_content_source"] == "live_whole_resume_graph_allocation_zero_canned_prose"
    assert ins_doc["target_role_profile"] != payer_doc["target_role_profile"]

    for doc in (ins_doc, payer_doc):
        by_sec = {s["section_id"]: s.get("l2_output_snapshot") or {} for s in doc["sections"] if s.get("section_kind") == "generated_lane"}
        exec_text = by_sec["executive_summary"]["resume_display_text"]
        assert exec_text
        assert not HOLD_METRIC_TEXT_RE.search(exec_text), f"HOLD metric leaked into executive_summary: {exec_text}"
        assert "$30M" not in exec_text and "$15M" not in exec_text and "$82M" not in exec_text
        assert len(by_sec["ey_bullets"]["bullets"]) >= 2
        assert len(by_sec["early_career_bullets"]["bullets"]) >= 2

    ins_exec = next(s["l2_output_snapshot"]["resume_display_text"] for s in ins_doc["sections"] if s["section_id"] == "executive_summary")
    payer_exec = next(s["l2_output_snapshot"]["resume_display_text"] for s in payer_doc["sections"] if s["section_id"] == "executive_summary")
    assert "FSA" in ins_exec
    assert "Columbia MS Biostatistics" in payer_exec or "FSA" in payer_exec
    assert ins_exec != payer_exec


def test_career_thesis_three_era_synthesis_and_u0_injection() -> None:
    agent = CareerThesisAlignmentAgent()
    plan = agent.synthesize(
        target_company="Digital Insurer",
        target_role="Lead Engineer CTO",
        job_description_text="Digital life insurer CTO leading underwriting, actuarial reserving, AWS cloud, and agentic AI.",
    )
    assert "FSA" in plan.career_thesis.primary_positioning
    assert "early_career_bullets" in plan.thematic_allocation.bullet_lanes_focus
    assert "ey_bullets" in plan.thematic_allocation.bullet_lanes_focus

    from dataclasses import asdict

    block = format_career_thesis_u0_block({"career_thesis_plan": asdict(plan)}, section_id="executive_summary")
    assert "CAREER_THESIS_GUIDANCE" in block
    assert "three_era_arc" in block


def test_l1_cognitive_v3_default_and_v2_opt_in() -> None:
    default_t = treatment_from_task_spec({})
    assert default_t["arm"] == L1_COGNITIVE_V3_CANDIDATE_ARM
    assert default_t["v3_cognitive_plan_enabled"] is True
    v2_t = build_l1_cognitive_treatment(L1_COGNITIVE_V2_CONTROL_ARM, assignment_origin="U0_VALIDATED_INGRESS")
    assert treatment_from_task_spec({"l1_cognitive_treatment": v2_t})["arm"] == L1_COGNITIVE_V2_CONTROL_ARM


def test_claim_binding_allows_verified_multi_metric_and_rejects_ungrounded_metric() -> None:
    assignments = [
        {
            "section_id": "executive_summary",
            "claim_unit_id": "executive_summary:claim:02",
            "root_id": "reb_unify_enterprise_adoption_revenue",
            "skill_id": "skill_platform_commercialization",
            "fact_id": "fact_unify_005",
            "metric_outcome_id": "metric_unify_22m_ip_revenue",
            "metric_text": "$22M IP-led revenue",
            "metric_value": "22",
            "metric_unit": "USD_M",
            "normalized_metric_signature": "22 usd_m ip led revenue",
            "proof_strength_raw": 1.0,
            "target_alignment_score": 2.0,
            "claim_entailment_score": 1.0,
            "metric_binding_score": 1.0,
            "path_confidence_raw": 1.0,
            "source_independence_score": 1.0,
            "selection_margin": 0.2,
            "graph_path_ids": ["root:reb_unify_enterprise_adoption_revenue"],
            "edge_ids": ["edge:pillar_phase_bridge:t2_t3"],
            "citation_refs": ["fact_unify_005"],
        },
        {
            "section_id": "executive_summary",
            "claim_unit_id": "executive_summary:claim:03",
            "root_id": "reb_unify_platform_commercialization_leadership",
            "skill_id": "skill_margin_expansion",
            "fact_id": "fact_unify_006",
            "metric_outcome_id": "metric_unify_20pct_gross_margin_expansion",
            "metric_text": "20% gross margin expansion",
            "metric_value": "20",
            "metric_unit": "PERCENT",
            "normalized_metric_signature": "20 pct gross margin expansion",
            "proof_strength_raw": 1.0,
            "target_alignment_score": 2.0,
            "claim_entailment_score": 1.0,
            "metric_binding_score": 1.0,
            "path_confidence_raw": 1.0,
            "source_independence_score": 1.0,
            "selection_margin": 0.2,
            "graph_path_ids": ["root:reb_unify_platform_commercialization_leadership"],
            "edge_ids": ["edge:pillar_phase_bridge:t2_t3"],
            "citation_refs": ["fact_unify_006"],
        },
    ]
    binding_ok, failures_ok = _binding_for_claim(
        {
            "claim_text": "Commercialized governed AI platform IP to deliver $22M revenue and 20% gross margin expansion.",
            "source_fact_ids": ["fact_unify_005", "fact_unify_006"],
        },
        ordinal=1,
        section_id="executive_summary",
        allocation_digest="a" * 64,
        assignments=assignments,
    )
    assert failures_ok == []
    assert binding_ok is not None

    binding_bad, failures_bad = _binding_for_claim(
        {
            "claim_text": "Commercialized governed AI platform IP to deliver $99M revenue and 20% gross margin expansion.",
            "source_fact_ids": ["fact_unify_005", "fact_unify_006"],
        },
        ordinal=2,
        section_id="executive_summary",
        allocation_digest="a" * 64,
        assignments=assignments,
    )
    assert binding_bad is None
    assert "rendered_metric_exact_value_unit_binding_failed" in failures_bad
