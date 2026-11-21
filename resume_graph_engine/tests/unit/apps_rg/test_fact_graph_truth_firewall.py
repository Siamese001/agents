"""Bilateral recall-and-precision tests for Wave 1 Candidate Truth Firewall (INV-FACT-GRAPH-NO-AGENT-SYNTHESIS)."""

from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.c0.allocation.orchestration import build_whole_resume_graph_allocation
from apps_rg.runtime.c0.allocation.slot_candidates import _candidate_sets_from_section_plans
from apps_rg.runtime.c0.c03_resume_graph_contracts import evaluate_pretarget_authority
from apps_rg.runtime.sections.graph_role_episode_selector import _metric_authority

REPO_ROOT = Path(__file__).resolve().parents[4]
RG_ROOT = REPO_ROOT / "resume_graph_engine"
INV_DIR = RG_ROOT / "src" / "apps_rg" / "fact_inventory"


def test_zero_approved_by_graph_presence_and_full_provenance_audit() -> None:
    from tools.audit_resume_fact_provenance import audit_fact_provenance

    report = audit_fact_provenance(REPO_ROOT)
    assert report["status"] == "PASS", report["violations"]
    assert report["graph_presence_count"] == 0
    assert report["counts"]["quarantined_unverified_synthetic_metrics"] >= 24
    assert report["counts"]["verified_base_resume_metrics"] + report["counts"]["verified_operator_confirmed_metrics"] >= 100


def test_kafka_confluent_and_24pct_renewal_lift_are_quarantined_and_blocked() -> None:
    ibm_doc = json.loads((INV_DIR / "ibm_role_episode_bundles.json").read_text(encoding="utf-8"))
    kafka_node = ibm_doc["metric_outcome_nodes"]["metric_ibm_offering_accelerator_package_reuse"]
    assert kafka_node["approved"] is False
    assert kafka_node["support_level"] == "quarantined_unverified_synthetic"
    assert "metric_ibm_offering_accelerator_package_reuse" not in ibm_doc.get("approved_metric_outcome_ids", {})

    bundle = next(
        b for b in ibm_doc["bundles"]
        if b["role_episode_bundle_id"] == "reb_ibm_offering_accelerator_management"
    )
    auth = _metric_authority(
        metric_id="metric_ibm_offering_accelerator_package_reuse",
        node=kafka_node,
        bundle=bundle,
        section_id="executive_summary",
    )
    assert auth["authority_pass"] is False
    assert "approved_false" in auth["reason_codes"]
    assert "section_not_allowed" in auth["reason_codes"]

    for jd_file, role in (
        ("truist_head_forward_deployed_engineering_jd.txt", "Head of Forward Deployed Engineering"),
        ("anthropic_manager_applied_ai_architecture_partnerships_jd.txt", "Manager, Applied AI Architecture & Partnerships"),
        ("brown_brown_svp_it_strategy_innovation_jd.txt", "SVP, IT Strategy & Innovation"),
    ):
        jd_text = (RG_ROOT / "src" / "apps_rg" / "config" / "targeting" / jd_file).read_text(encoding="utf-8")
        alloc = build_whole_resume_graph_allocation(
            repo_root=RG_ROOT,
            target_role=role,
            jd_text=jd_text,
            briefing_text="",
        )
        blob = json.dumps(alloc["allocation_plan"]["assignments"]).lower()
        assert "confluent" not in blob, f"Confluent leaked into {jd_file}"
        assert "kafka" not in blob, f"Kafka leaked into {jd_file}"
        assert "24% renewal" not in blob, f"24% renewal lift leaked into {jd_file}"


def test_section_eligibility_strictly_enforced_per_metric() -> None:
    metric_node = {
        "metric_outcome_id": "metric_test_bullets_only",
        "metric": "20% joint revenue growth",
        "approved": True,
        "approval_status": "APPROVED_VERIFIED_PROVENANCE",
        "support_level": "verified_operator_confirmed",
        "provenance_source_refs": ["exp_ibm_001", "fact_partnerships_gtm_002"],
        "bundle_bindings": ["reb_ibm_aws_alliance_partner_cosell_gtm"],
        "section_eligibility": ["ibm_bullets", "ibm_narrative", "competencies"],
    }
    bundle = {
        "role_episode_bundle_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
        "section_eligibility": ["ibm_bullets", "ibm_narrative", "competencies", "executive_summary"],
        "linked_source_fact_ids": ["exp_ibm_001"],
    }
    exec_auth = _metric_authority(
        metric_id="metric_test_bullets_only",
        node=metric_node,
        bundle=bundle,
        section_id="executive_summary",
    )
    assert exec_auth["authority_pass"] is False
    assert "section_not_allowed" in exec_auth["reason_codes"]

    bullet_auth = _metric_authority(
        metric_id="metric_test_bullets_only",
        node=metric_node,
        bundle=bundle,
        section_id="ibm_bullets",
    )
    assert bullet_auth["authority_pass"] is True

    fake_plan = {
        "executive_summary": {
            "target_role_profile": "svp_agentic_engineering",
            "graph_candidate_decision_ledger": [
                {
                    "candidate_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "candidate_type": "role_episode_root",
                    "candidate_path_id": "root:reb_ibm_aws_alliance_partner_cosell_gtm",
                    "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "employer_lane": "ibm",
                    "authority_pass": True,
                },
                {
                    "candidate_id": "skill_partner_hyperscaler_cosell",
                    "candidate_type": "leaf_skill",
                    "candidate_path_id": "root:reb_ibm_aws_alliance_partner_cosell_gtm/skill:s1",
                    "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "authority_pass": True,
                    "skill_label": "Hyperscaler Co-Sell",
                },
                {
                    "candidate_id": "exp_ibm_001",
                    "candidate_type": "source_fact",
                    "candidate_path_id": "root:reb_ibm_aws_alliance_partner_cosell_gtm/fact:f1",
                    "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "authority_pass": True,
                },
                {
                    "candidate_id": "metric_test_bullets_only",
                    "candidate_type": "metric_outcome",
                    "candidate_path_id": "root:reb_ibm_aws_alliance_partner_cosell_gtm/metric:m1",
                    "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "authority_pass": True,
                    "approved": True,
                    "metric": "20% joint revenue growth",
                    "section_eligibility": ["ibm_bullets"],
                },
            ],
        }
    }
    cands = _candidate_sets_from_section_plans(
        fake_plan,
        [{"slot_id": "executive_summary:claim:03", "section_id": "executive_summary", "metric_required": False, "employer_lane": "ibm"}],
    )
    assert all(r["metric_outcome_id"] == "" for r in cands["executive_summary:claim:03"])


def test_pretarget_authority_blocks_self_certifying_and_quarantined_support_levels() -> None:
    for blocked_level in ("approved_by_graph_presence", "quarantined_unverified_synthetic"):
        res = evaluate_pretarget_authority(
            candidate_id="m_bad",
            candidate_type="metric_outcome",
            section_id="executive_summary",
            section_allowed=True,
            support_level=blocked_level,
            approved=True,
            source_refs=["exp_ibm_001"],
            path_present=True,
        )
        assert res["authority_pass"] is False


def test_zero_jd_company_overfitting_repo_wide() -> None:
    from tools.lint_no_jd_overfitting import collect_production_files, scan_files

    res = scan_files(collect_production_files(REPO_ROOT), REPO_ROOT, use_baseline=False)
    assert res["status"] == "PASS", res["violations"]
    assert res["total_hits"] == 0
