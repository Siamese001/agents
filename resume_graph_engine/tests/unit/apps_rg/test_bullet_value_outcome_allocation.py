"""Regression tests for C0 bullet value-outcome allocation, IBM metric wiring, and X2 outcome floor."""
from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.c0.allocation.orchestration import build_whole_resume_graph_allocation
from apps_rg.runtime.contracts.metric_lexical_primitives import is_quantified_metric_outcome_text
from apps_rg.runtime.sections.ibm_bullets.metric_repairs import _scrub_foreign_ibm_metric_tokens
from apps_rg.runtime.sections.ibm_role_episode_evidence import format_ibm_role_episode_evidence_pack
from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
    check_experience_bullet_evidence_density,
)

RG_ROOT = Path(__file__).resolve().parents[3]


def test_is_quantified_metric_outcome_text_separates_outcomes_from_surfaces() -> None:
    quantified_samples = [
        "$22M IP-led revenue",
        "35% reduction in regulatory findings across banking AI rollouts",
        "AI systems lifecycle compressed from six months to three weeks",
        "250K+ daily unstructured regulatory and trade-surveillance signals triaged into review queues",
        "100% immutable CloudTrail, AWS Config, and VPC Flow Log audit coverage",
        "9 core insurance workloads and 11 legacy Oracle/SQL Server databases (14TB) replatformed",
        "14 repeatable Terraform and OpenShift DevSecOps deployment blueprints",
        "engineering team scaled from 8 to 28",
    ]
    for sample in quantified_samples:
        assert is_quantified_metric_outcome_text(sample), f"Expected quantified: {sample!r}"

    non_quantified_samples = [
        "",
        "runtime gate verdict contract surface for continue, repair, rollback, and stop decisions",
        "cloud data/runtime integration patterns across Databricks, vector services, and API gateways",
        "audit-grade runtime observability coverage for regulated AI workflows",
        "L0 route-policy dispatch surface for deterministic agent workflow selection",
        "SOC 2 Type II compliance alignment",
    ]
    for sample in non_quantified_samples:
        assert not is_quantified_metric_outcome_text(sample), f"Expected non-quantified: {sample!r}"


def test_truist_fde_c0_allocation_binds_quantified_metrics_across_all_four_bullet_lanes() -> None:
    jd_path = RG_ROOT / "src/apps_rg/config/targeting/truist_head_forward_deployed_engineering_jd.txt"
    br_path = RG_ROOT / "src/apps_rg/config/targeting/truist_head_forward_deployed_engineering_briefing.md"
    bundle = build_whole_resume_graph_allocation(
        repo_root=RG_ROOT,
        target_role="Head of Forward Deployed Engineering",
        jd_text=jd_path.read_text(encoding="utf-8"),
        briefing_text=br_path.read_text(encoding="utf-8"),
    )
    assignments = list(bundle["allocation_plan"]["assignments"])
    by_section: dict[str, list[dict]] = {}
    for row in assignments:
        by_section.setdefault(str(row["section_id"]), []).append(row)

    exec_roots = {str(r["root_id"]) for r in by_section["executive_summary"]}

    # IBM: all 5 slots must receive distinct quantified graph metrics
    ibm_rows = by_section["ibm_bullets"]
    assert len(ibm_rows) == 5
    assert all(r.get("metric_outcome_id") for r in ibm_rows)
    assert all(is_quantified_metric_outcome_text(str(r.get("metric_text") or "")) for r in ibm_rows)
    assert {str(r["root_id"]) for r in ibm_rows}.isdisjoint(exec_roots)

    # InsurTech: both slots must receive distinct quantified graph metrics
    insurtech_rows = by_section["insurtech_bullets"]
    assert len(insurtech_rows) == 2
    assert all(r.get("metric_outcome_id") for r in insurtech_rows)
    assert all(is_quantified_metric_outcome_text(str(r.get("metric_text") or "")) for r in insurtech_rows)
    assert {str(r["root_id"]) for r in insurtech_rows}.isdisjoint(exec_roots)

    # Slalom: all 4 slots bound, >= 3 quantified
    slalom_rows = by_section["slalom_bullets"]
    assert len(slalom_rows) == 4
    assert all(r.get("metric_outcome_id") for r in slalom_rows)
    assert sum(is_quantified_metric_outcome_text(str(r.get("metric_text") or "")) for r in slalom_rows) >= 3
    assert {str(r["root_id"]) for r in slalom_rows}.isdisjoint(exec_roots)

    # Unify: >= 4 quantified including banking regulatory governance, disjoint from executive_summary
    unify_rows = by_section["unify_bullets"]
    assert len(unify_rows) == 6
    assert all(r.get("metric_outcome_id") for r in unify_rows)
    assert sum(is_quantified_metric_outcome_text(str(r.get("metric_text") or "")) for r in unify_rows) >= 4
    unify_roots = {str(r["root_id"]) for r in unify_rows}
    assert "reb_unify_regulated_enterprise_ai_governance" in unify_roots
    assert unify_roots.isdisjoint(exec_roots)


def test_ibm_evidence_pack_surfaces_plural_allocated_metric_outcome_ids() -> None:
    payload = {
        "allowed_fact_ids": ["bul_ibm_001"],
        "selected_fact_plan": {
            "facts": [
                {
                    "fact_id": "bul_ibm_001",
                    "role_episode_bundle_id": "reb_ibm_devsecops_release_resilience",
                    "claim_text": "Engineered DevSecOps release resilience frameworks for regulated banking workloads",
                    "metric_outcome_ids": ["metric_ibm_deployment_blueprint_repeatability"],
                    "metric_raw": "14 repeatable Terraform and OpenShift DevSecOps deployment blueprints",
                    "has_metric": True,
                }
            ]
        },
    }
    pack = format_ibm_role_episode_evidence_pack(payload, section_id="ibm_bullets")
    assert "(none - all active slots are qualitative" not in pack
    assert "metric_ibm_deployment_blueprint_repeatability" in pack
    assert "MANDATORY: include this exact quantified metric proof" in pack


def test_scrub_foreign_ibm_metric_tokens_preserves_own_allocated_metric() -> None:
    text = (
        "Architected 9 BCBS 239-compliant cloud reference architectures across 14 banking pursuits "
        "sustaining 99.9% uptime and cutting costs by 30%."
    )
    cleaned = _scrub_foreign_ibm_metric_tokens(
        text,
        "bul_ibm_005",
        own_metric="9 BCBS 239 and OCC-compliant cloud reference architectures reused across 14 banking pursuits at 99.9% uptime",
    )
    assert "99.9%" in cleaned
    assert "30%" not in cleaned


def test_evidence_density_rejects_feature_only_unify_bullets_and_accepts_outcomes() -> None:
    feature_only_bullets = [
        (
            "bul_unify_001",
            "Delivered deterministic enterprise AI orchestration by authoring control-plane "
            "architecture with runtime gate verdict contracts for continue, repair, rollback, and stop decisions.",
        ),
        (
            "bul_unify_004",
            "Standardized cloud data/runtime integration patterns across AWS, Databricks Lakehouse, "
            "vector services, and API gateways to power distributed enterprise AI execution.",
        ),
    ]
    for bid, text in feature_only_bullets:
        res = check_experience_bullet_evidence_density(bid, text)
        assert not res.passed, f"Expected feature-only bullet to fail outcome floor: {bid}"
        assert "business_or_delivery_outcome" in (res.failure_reason or "")

    outcome_bullets = [
        (
            "bul_unify_003",
            "Eliminated silent runtime regressions and established audit-grade runtime observability "
            "coverage for regulated AI workflows to protect production reliability through governed "
            "context engineering and automated rollback controls.",
        ),
        (
            "bul_unify_004",
            "Enabled resilient, high-availability enterprise AI execution for regulated data estates "
            "via cloud data/runtime integration patterns across Databricks, vector services, and API gateways.",
        ),
        (
            "bul_unify_004",
            "Delivered resilient, high-availability enterprise AI execution across regulated data "
            "estates using cloud data/runtime integration patterns across Databricks and API gateways.",
        ),
    ]
    for bid, text in outcome_bullets:
        res_ok = check_experience_bullet_evidence_density(bid, text)
        assert res_ok.passed, f"{bid}: {res_ok.failure_reason}"
