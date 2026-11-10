"""Unit tests for headline title anchor derivation and positioning evidence (Wave 2)."""

from __future__ import annotations

from apps_rg.runtime.sections.headline_lane import _rewrite_machine_headline_segments
from apps_rg.runtime.sections.headline_pa import _format_allocation_authority_block
from apps_rg.runtime.sections.headline_positioning_evidence import (
    derive_headline_title_anchor,
    infer_headline_prefix,
)
from apps_rg.runtime.sections.headline_repair_policy import candidate_3word_subsequences


def test_derive_headline_title_anchor_abbreviates_svp_with_specialization() -> None:
    anchor = derive_headline_title_anchor("Senior Vice President, IT Strategy & Innovation")
    assert anchor == "SVP Enterprise Architecture"
    assert anchor != "Senior Vice President"
    assert len(anchor.split()) == 3
    assert infer_headline_prefix("Senior Vice President, IT Strategy & Innovation") == anchor


def test_derive_headline_title_anchor_variants() -> None:
    assert derive_headline_title_anchor("Senior Vice President, AI Strategy") == "SVP AI Strategy"
    assert derive_headline_title_anchor("Senior Vice President, IT Strategy") == "SVP IT Strategy"
    assert derive_headline_title_anchor("SVP Enterprise Architecture") == "SVP Enterprise Architecture"
    assert derive_headline_title_anchor("Senior Vice President") == "SVP Enterprise Architecture"


def test_allocation_authority_block_and_repairs_forbid_backoffice_labels() -> None:
    plan = {
        "allocation_assignments": [
            {
                "section_id": "headline",
                "claim_unit_id": "headline:skill:01",
                "root_id": "reb_unify_agentic_platform_architecture",
            },
            {
                "section_id": "headline",
                "claim_unit_id": "headline:skill:02",
                "root_id": "reb_ibm_aws_modernization_architecture",
            },
            {
                "section_id": "headline",
                "claim_unit_id": "headline:skill:03",
                "root_id": "reb_ey_erm_risk_governance",
            },
        ]
    }
    block = _format_allocation_authority_block(plan, prefix="SVP Enterprise Architecture")
    assert "Agentic AI Platforms" in block
    assert "Cloud Data Modernization" in block
    assert "Regulated Insurance Governance" in block
    assert "Never emit 'Three Lines Governance' or 'Client Adoption Systems'" in block

    rewritten, changes = _rewrite_machine_headline_segments(
        "SVP Enterprise Architecture | Three Lines Governance | Hyperscaler Alliance Ecosystem | Client Adoption Systems"
    )
    assert rewritten == (
        "SVP Enterprise Architecture | Regulated Insurance Governance "
        "| Hyperscaler Partner Ecosystem | Cloud Data Modernization"
    )
    assert len(changes) == 3
    assert candidate_3word_subsequences("Three Lines Risk Governance") == [
        "Regulated Insurance Governance"
    ]
