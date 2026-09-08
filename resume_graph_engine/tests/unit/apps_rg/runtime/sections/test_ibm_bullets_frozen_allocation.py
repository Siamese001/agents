from __future__ import annotations

from apps_rg.runtime.sections.ibm_bullets_lane import (
    IBM_BULLET_IDS,
    _materialize_ibm_bullets_from_frozen_allocation,
)
from apps_rg.runtime.validators.bullet_quality_floor_x2 import (
    check_experience_bullet_evidence_density,
    check_bullet_technical_specificity_floor,
)
from apps_rg.runtime.validators.ibm_bullets_x2 import (
    ibm_cross_bullet_semantic_overlap_violations,
)


def test_pnl_frozen_allocation_materialization_keeps_technical_mechanism() -> None:
    parsed = {
        "bullets": [
            {
                "bullet_id": bullet_id,
                "bullet_text": "Provider draft.",
                "source_fact_ids": [bullet_id],
            }
            for bullet_id in IBM_BULLET_IDS
        ]
    }
    assignments = []
    for bullet_id in IBM_BULLET_IDS:
        root_id = f"reb_test_{bullet_id}"
        skill_id = f"skill_test_{bullet_id}"
        root_claim_text = f"Architected platform delivery for {bullet_id}."
        if bullet_id == "bul_ibm_004":
            root_id = "reb_ibm_revenue_sales_target_execution"
            skill_id = "skill_partner_pnl_oversight"
            root_claim_text = "Owned quota-aligned enterprise pursuits."
        assignments.append(
            {
                "section_id": "ibm_bullets",
                "claim_unit_id": f"ibm_bullets:{bullet_id}",
                "root_id": root_id,
                "skill_id": skill_id,
                "root_claim_text": root_claim_text,
                "metric_text": "",
            }
        )

    applied = _materialize_ibm_bullets_from_frozen_allocation(
        parsed,
        selected_fact_plan={"allocation_assignments": assignments},
    )

    assert applied is True
    bullet = next(row for row in parsed["bullets"] if row["bullet_id"] == "bul_ibm_004")
    assert "pipeline" in bullet["bullet_text"].lower()
    result = check_bullet_technical_specificity_floor(
        bullet["bullet_id"],
        bullet["bullet_text"],
    )
    assert result.passed is True


def test_frozen_allocation_materialization_restores_a_provider_omitted_slot() -> None:
    """A sealed graph allocation, not the provider, controls required slot presence."""
    omitted = "bul_ibm_004"
    parsed = {
        "bullets": [
            {
                "bullet_id": bullet_id,
                "bullet_text": "Provider draft.",
                "source_fact_ids": [bullet_id],
            }
            for bullet_id in IBM_BULLET_IDS
            if bullet_id != omitted
        ]
    }
    assignments = [
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": f"ibm_bullets:{bullet_id}",
            "root_id": "reb_ibm_data_modeling_bi_decision_support",
            "skill_id": "skill_sr_cloud_data_platform_engineering",
            "root_claim_text": "Built decision-support data models and BI views.",
            "metric_text": "",
        }
        for bullet_id in IBM_BULLET_IDS
    ]

    assert _materialize_ibm_bullets_from_frozen_allocation(
        parsed,
        selected_fact_plan={"allocation_assignments": assignments},
    )
    restored = next(row for row in parsed["bullets"] if row["bullet_id"] == omitted)
    assert restored["source_fact_ids"] == [omitted]
    assert restored["bullet_text"] != "Provider draft."
    assert len(parsed["claim_ledger"]) == len(IBM_BULLET_IDS)


def test_frozen_allocation_materialization_keeps_revenue_slots_semantically_distinct() -> None:
    parsed = {
        "bullets": [
            {
                "bullet_id": bullet_id,
                "bullet_text": "Provider draft.",
                "source_fact_ids": [bullet_id],
            }
            for bullet_id in IBM_BULLET_IDS
        ]
    }
    assignments = [
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": f"ibm_bullets:{bullet_id}",
            "root_id": root_id,
            "skill_id": skill_id,
            "root_claim_text": root_claim_text,
            "metric_text": metric_text,
        }
        for bullet_id, root_id, skill_id, root_claim_text, metric_text in (
            (
                "bul_ibm_001",
                "reb_ibm_aws_alliance_partner_cosell_gtm",
                "skill_partner_joint_solution_development",
                "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities",
                "20% joint revenue growth",
            ),
            (
                "bul_ibm_003",
                "reb_ibm_data_modeling_bi_decision_support",
                "skill_sr_cloud_data_platform_engineering",
                "Built decision-support data models",
                "",
            ),
            (
                "bul_ibm_004",
                "reb_ibm_revenue_sales_target_execution",
                "skill_p2_gtm_enterprise_deal_support",
                "Owned quota-aligned enterprise pursuits",
                "",
            ),
        )
    ]

    assert _materialize_ibm_bullets_from_frozen_allocation(
        parsed,
        selected_fact_plan={"allocation_assignments": assignments},
    ) is True

    by_id = {row["bullet_id"]: row["bullet_text"] for row in parsed["bullets"]}
    assert "pipeline discipline" in by_id["bul_ibm_004"]
    assert "deal-support cadence" in by_id["bul_ibm_004"]
    assert check_bullet_technical_specificity_floor(
        "bul_ibm_004", by_id["bul_ibm_004"]
    ).passed is True
    assert by_id["bul_ibm_003"].endswith(".")
    assert ibm_cross_bullet_semantic_overlap_violations(parsed["bullets"]) == []


def test_semantic_overlap_gate_detects_retry15_quota_pipeline_duplicate() -> None:
    bullets = [
        {
            "bullet_id": "bul_ibm_002",
            "bullet_text": (
                "Owned P&L oversight and quota-aligned solution leadership across enterprise "
                "pursuits, applying pipeline discipline to client portfolio expansion motions."
            ),
        },
        {
            "bullet_id": "bul_ibm_004",
            "bullet_text": (
                "Owned quota-aligned solution leadership and pipeline governance across enterprise "
                "pursuits and client portfolio expansion motions."
            ),
        },
    ]

    violations = ibm_cross_bullet_semantic_overlap_violations(bullets)

    assert violations[0]["bullet_ids"] == ["bul_ibm_002", "bul_ibm_004"]
    assert violations[0]["token_jaccard"] >= 0.60


def test_frozen_allocation_materialization_preserves_evidence_density_for_every_bullet() -> None:
    """A post-selection graph projection must not erase the selected outcome."""
    parsed = {
        "bullets": [
            {"bullet_id": bullet_id, "bullet_text": "Provider draft."}
            for bullet_id in IBM_BULLET_IDS
        ]
    }
    assignments = [
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": "ibm_bullets:bul_ibm_001",
            "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
            "skill_id": "skill_partner_alliance_gtm_execution",
            "root_claim_text": "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities",
            "metric_text": "20% joint revenue growth",
        },
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": "ibm_bullets:bul_ibm_002",
            "root_id": "reb_ibm_data_modeling_bi_decision_support",
            "skill_id": "skill_sr_cloud_data_platform_engineering",
            "root_claim_text": "Built decision-support data models and BI views",
        },
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": "ibm_bullets:bul_ibm_003",
            "root_id": "reb_ibm_presales_solution_engineering",
            "skill_id": "skill_p2_gtm_solution_mapping",
            "root_claim_text": "Led technical discovery and solution mapping for enterprise pursuits",
        },
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": "ibm_bullets:bul_ibm_004",
            "root_id": "reb_ibm_revenue_sales_target_execution",
            "skill_id": "skill_p2_gtm_enterprise_deal_support",
            "root_claim_text": "Owned quota-aligned solution leadership across enterprise pursuits",
        },
        {
            "section_id": "ibm_bullets",
            "claim_unit_id": "ibm_bullets:bul_ibm_005",
            "root_id": "reb_ibm_data_modeling_bi_decision_support",
            "skill_id": "skill_p2_tech_reference_architecture",
            "root_claim_text": "Built decision-support data models and BI views",
        },
    ]

    assert _materialize_ibm_bullets_from_frozen_allocation(
        parsed,
        selected_fact_plan={"allocation_assignments": assignments},
    )
    failures = [
        check_experience_bullet_evidence_density(row["bullet_id"], row["bullet_text"])
        for row in parsed["bullets"]
    ]
    assert all(row.passed for row in failures), [row.failure_reason for row in failures]
