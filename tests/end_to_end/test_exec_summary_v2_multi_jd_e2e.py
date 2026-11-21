"""Unmocked 6-JD Multi-Industry End-to-End Benchmark for executive_summary_v2.

Executes real production C0 whole-resume allocation, candidate truth firewall,
executive_summary_v2 deterministic X2 invariants (positive human voice + pinned v4
inanimate-subject negative control), and blind X1D judge prompt rendering across
all 6 canonical JDs without any mocks or synthetic stubs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RG_ROOT = REPO_ROOT / "resume_graph_engine"
RG_SRC = RG_ROOT / "src"
if str(RG_SRC) not in sys.path:
    sys.path.insert(0, str(RG_SRC))

from apps_rg.runtime.c0.resume_graph_allocation import (  # noqa: E402
    build_whole_resume_graph_allocation,
    validate_resume_graph_allocation_plan,
)
from apps_rg.runtime.judges.executive_summary_judge_packet import (  # noqa: E402
    build_executive_summary_judge_packet,
    render_judge_prompt_from_packet,
)
from apps_rg.runtime.sections.executive_summary_v2.evidence_firewall import (  # noqa: E402
    verify_and_compact_fact_slice,
)
from apps_rg.runtime.sections.executive_summary_v2.x2_invariants import (  # noqa: E402
    evaluate_executive_summary_v2_x2,
)
from tools.audit_resume_fact_provenance import audit_fact_provenance  # noqa: E402

TARGETING_DIR = RG_SRC / "apps_rg" / "config" / "targeting"

SIX_CANONICAL_JDS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "truist_fde",
        "company": "Truist Financial Corporation",
        "role": "Head of Forward Deployed Engineering",
        "jd_file": "truist_head_forward_deployed_engineering_jd.txt",
        "brief_file": "truist_head_forward_deployed_engineering_briefing.md",
        "is_insurance": False,
    },
    {
        "case_id": "citi_ai_strategy",
        "company": "Citigroup",
        "role": "Head of AI Strategy",
        "jd_file": "citi_head_of_ai_strategy_jd.txt",
        "brief_file": "citi_head_of_ai_strategy_briefing.md",
        "is_insurance": False,
    },
    {
        "case_id": "anthropic_partnerships",
        "company": "Anthropic",
        "role": "Manager, Applied AI Architecture & Partnerships",
        "jd_file": "anthropic_manager_applied_ai_architecture_partnerships_jd.txt",
        "brief_file": "anthropic_manager_applied_ai_architecture_partnerships_briefing.md",
        "is_insurance": False,
    },
    {
        "case_id": "brown_brown_insurance",
        "company": "Brown & Brown",
        "role": "SVP IT Strategy & Innovation",
        "jd_file": "brown_brown_svp_it_strategy_innovation_jd.txt",
        "brief_file": "brown_brown_svp_it_strategy_innovation_briefing.md",
        "is_insurance": True,
    },
    {
        "case_id": "neo4j_vp_product",
        "company": "Neo4j",
        "role": "VP Product Management, Agentic AI",
        "jd_file": "neo4j_vp_product_management_agentic_ai_jd.txt",
        "brief_file": "neo4j_vp_product_management_agentic_ai_briefing.md",
        "is_insurance": False,
    },
    {
        "case_id": "invesco_advanced_eng",
        "company": "Invesco",
        "role": "Global Head of Advanced Engineering",
        "jd_file": "invesco_global_head_advanced_engineering_jd.txt",
        "brief_file": "invesco_global_head_advanced_engineering_briefing.md",
        "is_insurance": False,
    },
)

PINNED_V4_ROBOTIC_DRAFT = (
    "Agentic AI and enterprise platform engineering leader who builds governed multi-agent architectures "
    "and converts prototype workflows into audited, production-grade software. "
    "Platform ownership covered a multi-layer agentic control plane with deterministic route policy and "
    "sandboxed tool execution, generating $22M in IP-led platform revenue across 14 enterprise accounts. "
    "Fail-closed validation meshes enforced 100% deterministic gate conformance across multi-agent RAG "
    "workflows, and reusable cloud, Confluent Kafka, and AI accelerators cut solution design cycle time "
    "35% and lifted renewals 24%. "
    "Field delivery scaled a 45-engineer architecture organization across regulated financial portfolios, "
    "cutting release rollback rates 38% and lifting architectural reuse 48%."
)


def test_fact_graph_truth_firewall_zero_agent_synthesis_e2e() -> None:
    report = audit_fact_provenance(REPO_ROOT)
    assert report["status"] == "PASS"
    assert report["graph_presence_count"] == 0
    assert report["counts"]["quarantined_unverified_synthetic_metrics"] >= 20
    assert report["violations"] == []


@pytest.mark.parametrize("case", SIX_CANONICAL_JDS, ids=[c["case_id"] for c in SIX_CANONICAL_JDS])
def test_six_jd_multi_industry_allocation_truth_firewall_and_v2_gates_e2e(case: dict[str, Any]) -> None:
    jd_text = (TARGETING_DIR / case["jd_file"]).read_text(encoding="utf-8")
    brief_text = (TARGETING_DIR / case["brief_file"]).read_text(encoding="utf-8")

    bundle = build_whole_resume_graph_allocation(
        repo_root=RG_ROOT,
        target_role=case["role"],
        jd_text=jd_text,
        briefing_text=brief_text,
    )
    plan = bundle["allocation_plan"]
    assert validate_resume_graph_allocation_plan(plan) == []
    assert plan["uniqueness_receipt"]["pass"] is True

    exec_rows = [r for r in plan["assignments"] if r["section_id"] == "executive_summary"]
    assert len(exec_rows) >= 3

    lanes = {str(r.get("employer_lane") or "") for r in exec_rows}
    assert "ey" not in lanes, f"EY leaked into executive_summary on {case['case_id']}"
    if case["is_insurance"]:
        assert "insurtech" in lanes, "Brown & Brown insurance JD should include verified InsurTech root"
    else:
        assert "insurtech" not in lanes, f"InsurTech leaked into non-insurance JD {case['case_id']}"

    from apps_rg.runtime.sections.graph_role_episode_selector import (
        build_selected_graph_evidence_plan_for_section,
    )

    comp_plan, _comp_trace, _comp_audit = build_selected_graph_evidence_plan_for_section(
        repo_root=RG_SRC,
        section_id="competencies",
        target_role=case["role"],
        jd_text=jd_text,
        briefing_text=brief_text,
    )
    comp_items = list(comp_plan.get("facts") or [])
    assert len(comp_items) == 8, f"competencies graph evidence plan expected 8 facts on {case['case_id']}, got {len(comp_items)}"
    assert comp_plan.get("graph_evidence_depth_status") == "judge_grade", f"competencies depth insufficient on {case['case_id']}: {comp_plan.get('graph_evidence_depth_report')}"
    assert all(bool(it.get("selected_metric_ids")) for it in comp_items), (
        f"0-metric thin root leaked into competencies on {case['case_id']}: "
        f"{[it.get('role_episode_bundle_id') for it in comp_items if not it.get('selected_metric_ids')]}"
    )

    raw_facts = [
        {
            "fact_id": str(r.get("root_id") or r.get("fact_id") or ""),
            "employer_lane": str(r.get("employer_lane") or ""),
            "claim_text": str(r.get("root_claim_text") or r.get("root_bundle_theme") or ""),
            "metric_raw": f"{r.get('metric_value')} {r.get('metric_unit')}".strip(),
            "approved": True,
            "support_level": "verified_base_resume",
            "section_eligibility": ["executive_summary"],
        }
        for r in exec_rows
    ]
    allowed_ids = {f["fact_id"] for f in raw_facts if f["fact_id"]}
    compact, verified_nums, verified_corpus = verify_and_compact_fact_slice(
        {"facts": raw_facts},
        allowed_ids,
        {"facts": {"summary": "20+ years scaling enterprise cloud and AI platforms."}},
    )
    assert len(compact) >= 3
    blob = json.dumps(compact).lower()
    for banned in ("confluent", "kafka", "24% renewal", "48%", "38%"):
        assert banned not in blob, f"Quarantined token {banned!r} leaked on {case['case_id']}"

    fids = sorted(allowed_ids)[:3]
    s1 = "Enterprise AI and platform engineering executive with 20+ years scaling governed cloud and multi-agent architectures into enterprise production."
    s2 = "Productized reusable agentic orchestration and deterministic validation blueprints across regulated enterprise accounts, accelerating solution delivery and executive adoption."
    s3 = "Partnered with C-suite technology leaders to modernize data platforms with strict auditability."
    s4 = "Scaled cross-functional engineering teams to ship production cloud and AI software across enterprise portfolios."
    positive_human_draft = f"{s1} {s2} {s3} {s4}"
    pos_ledger = [
        {"claim_text": s1, "source_fact_ids": [fids[0]]},
        {"claim_text": s2, "source_fact_ids": [fids[1 % len(fids)]]},
        {"claim_text": s3, "source_fact_ids": [fids[2 % len(fids)]]},
        {"claim_text": s4, "source_fact_ids": [fids[0]]},
    ]
    pos_gates = evaluate_executive_summary_v2_x2(
        resume_display_text=positive_human_draft,
        claim_ledger=pos_ledger,
        parsed_output={"resume_display_text": positive_human_draft, "claim_ledger": pos_ledger, "jd_alignment": {"targeting_only": True, "jd_used_as_proof": False, "briefing_used_as_proof": False}},
        allowed_fact_ids=allowed_ids,
        verified_numbers=verified_nums | frozenset({"20"}),
        verified_corpus_lower=verified_corpus + " 20+ years",
        target_company=case["company"],
        jd_text=jd_text,
    )
    failed_pos = [g["gate_id"] for g in pos_gates if not g["pass"]]
    assert failed_pos == [], f"Positive human draft failed X2 on {case['case_id']}: {failed_pos}"

    neg_gates = evaluate_executive_summary_v2_x2(
        resume_display_text=PINNED_V4_ROBOTIC_DRAFT,
        claim_ledger=pos_ledger + [{"claim_text": "s4", "source_fact_ids": [fids[0]]}],
        parsed_output={"resume_display_text": PINNED_V4_ROBOTIC_DRAFT},
        allowed_fact_ids=allowed_ids,
        verified_numbers=verified_nums,
        verified_corpus_lower=verified_corpus,
        target_company=case["company"],
        jd_text=jd_text,
    )
    neg_by_id = {g["gate_id"]: g for g in neg_gates}
    assert neg_by_id["x2_v2_no_inanimate_subject_openers"]["pass"] is False
    assert neg_by_id["x2_v2_zero_unverified_numbers"]["pass"] is False
    assert neg_by_id["x2_v2_zero_unverified_vendors_or_employers"]["pass"] is False

    packet = build_executive_summary_judge_packet(
        resume_display_text=positive_human_draft,
        claim_ledger=pos_ledger,
        allowed_fact_packet=raw_facts,
        allowed_fact_ids=allowed_ids,
        target_title=case["role"],
        target_company=case["company"],
        jd_text=jd_text,
        briefing_text=brief_text,
        parsed_output={"resume_display_text": positive_human_draft},
        repo_root=RG_SRC,
    )
    rendered = render_judge_prompt_from_packet(packet)
    assert "DETERMINISTIC_GATE_SUMMARY" not in rendered
    assert "INANIMATE_SUBJECT_DATASHEET_BAN" in rendered
