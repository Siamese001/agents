"""Unit tests for section authority display repairs and X2 gate enumeration."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps_rg.runtime.sections.section_authority_repairs import (
    apply_exec_summary_display_authority_repairs,
    prune_competencies_rigor_failing_terms,
    repair_exec_summary_cross_fact_conflation_rows,
    repair_exec_summary_causal_multi_metric_rows,
    repair_exec_summary_causal_multi_root_allocation_rows,
    repair_exec_summary_unallocated_metric_rows,
    repair_exec_summary_mechanism_inventory_sentences,
    repair_exec_summary_thin_sentence_weave,
    repair_exec_summary_orphan_rows_with_unused_required_facts,
    repair_required_brushstroke_citations_from_materialized_sentences,
    sanitize_ibm_narrative_display_text,
    strip_exec_summary_credential_dump_sentences,
    strip_target_company_tailoring_sentences,
)
from apps_rg.runtime.validators.executive_summary_x2 import (
    check_exec_summary_no_credential_dump,
    check_exec_summary_no_mechanism_inventory,
    check_exec_summary_meta_filler_patterns,
    check_exec_summary_paragraph_max_words,
    run_x2_gates,
)
from apps_rg.runtime.validators.ibm_narrative_x2 import run_ibm_narrative_x2_gates
from tests.unit.apps_rg.section_rigor.lane_registry import spec_for_lane


def test_strip_target_company_tailoring_removes_alignment_sentences() -> None:
    text = (
        "Engineering executive who builds governed agentic AI platforms for regulated workflows. "
        "He aligns with Acme Corp on enterprise architecture and innovation priorities. "
        "Platform lifecycle work ties architecture to commercial adoption and operating discipline."
    )
    repaired, removed = strip_target_company_tailoring_sentences(text, "Acme Corp")
    assert removed
    assert "acme corp" not in repaired.lower()
    assert "governed agentic ai" in repaired.lower()


def test_retry10_graph_allocation_shape_repairs_before_x2() -> None:
    """Replay the two executive-summary failures from W8 Retry 10."""
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        validate_claim_rows_against_resume_graph_allocation,
    )
    from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
        FACT_C0_DISPLAY_OVERRIDES,
    )
    from apps_rg.runtime.sections.executive_summary_voice_repair import (
        finalize_executive_summary_coherence,
    )
    from apps_rg.runtime.validators.executive_summary_x2 import (
        check_exec_summary_display_override_compliance,
    )

    roots = [
        {
            "fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
            "role_episode_bundle_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
            "claim_text": "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities",
            "domain": "AWS partnership, alliance co-sell, and joint GTM execution",
            "linked_source_fact_ids": ["fact_partnerships_gtm_002"],
            "linked_identity_fact_ids": ["fact_partnerships_gtm_002"],
            "allowed_graph_evidence_ids": [
                "reb_ibm_aws_alliance_partner_cosell_gtm",
                "fact_partnerships_gtm_002",
                "metric_ibm_alliance_cosell_operating_cadence",
                "metric_ibm_ai_driven_sales_frameworks",
            ],
        },
        {
            "fact_id": "reb_ibm_devsecops_release_resilience",
            "role_episode_bundle_id": "reb_ibm_devsecops_release_resilience",
            "claim_text": "Embedded release automation and security scanning into regulated modernization delivery paths",
            "domain": "DevSecOps release resilience and governed delivery automation",
            "linked_source_fact_ids": ["fact_engineering_platform_002"],
            "linked_identity_fact_ids": ["fact_engineering_platform_002"],
            "allowed_graph_evidence_ids": [
                "reb_ibm_devsecops_release_resilience",
                "fact_engineering_platform_002",
                "metric_ibm_deployment_blueprint_repeatability",
                "metric_ibm_release_gate_security_scanning_coverage",
            ],
        },
        {
            "fact_id": "reb_unify_platform_commercialization_leadership",
            "role_episode_bundle_id": "reb_unify_platform_commercialization_leadership",
            "claim_text": "Platform productization, IP-led revenue, margin expansion, team scale",
            "domain": "Platform productization and commercialization",
            "linked_source_fact_ids": ["fact_engineering_platform_006"],
            "linked_identity_fact_ids": ["fact_engineering_platform_006"],
            "allowed_graph_evidence_ids": [
                "reb_unify_platform_commercialization_leadership",
                "fact_engineering_platform_006",
                "metric_unify_22m_ip_led_revenue",
            ],
        },
    ]
    assignments = [
        {
            "section_id": "executive_summary",
            "claim_unit_id": "executive_summary:claim:01",
            "root_id": "reb_unify_platform_commercialization_leadership",
            "skill_id": "skill_agentic_platform_productization",
            "fact_id": "fact_engineering_platform_006",
            "metric_outcome_id": "metric_unify_22m_ip_led_revenue",
            "metric_value": "22",
            "metric_unit": "USD_M",
            "root_bundle_theme": "Platform productization, IP-led revenue, margin expansion, team scale",
            "root_claim_text": "Platform productization, IP-led revenue, margin expansion, team scale",
            "root_claim_outcome": "Frame as platform commercialization leadership and $22M IP-led revenue.",
            "counts_toward_global_uniqueness": True,
        },
        {
            "section_id": "executive_summary",
            "claim_unit_id": "executive_summary:claim:02",
            "root_id": "reb_ibm_devsecops_release_resilience",
            "skill_id": "skill_ibm_devsecops_pipeline_security",
            "fact_id": "fact_engineering_platform_002",
            "metric_outcome_id": "",
            "metric_value": "",
            "metric_unit": "",
            "root_bundle_theme": "DevSecOps release resilience and governed delivery automation",
            "root_claim_text": "Embedded release automation and security scanning into regulated modernization delivery paths",
            "counts_toward_global_uniqueness": True,
        },
        {
            "section_id": "executive_summary",
            "claim_unit_id": "executive_summary:claim:03",
            "root_id": "reb_ibm_aws_alliance_partner_cosell_gtm",
            "skill_id": "skill_partner_cloud_vendor_joint_gtm",
            "fact_id": "fact_partnerships_gtm_002",
            "metric_outcome_id": "",
            "metric_value": "",
            "metric_unit": "",
            "root_bundle_theme": "AWS partnership, alliance co-sell, and joint GTM execution",
            "root_claim_text": "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities",
            "counts_toward_global_uniqueness": True,
        },
    ]
    sentences = [
        "Alliance-led technology executive who sets operating direction for partner co-sell and platform productization, connecting cloud-market execution with IP-led growth.",
        "From that commercial base, regulated modernization delivery anchors release automation and security scanning in resilient operating paths.",
        "Against that delivery foundation, alliance operating cadence and AI-driven sales frameworks supported 20% joint revenue growth.",
        "In parallel, repeatable deployment blueprints and release-gate security scanning coverage strengthen control across modernization delivery.",
        "That operating model also enabled platform productization tied to $22M in IP-led revenue, with margin expansion and team scale reinforcing the commercial case.",
        "Future partner-led growth can build on this platform discipline, extending secure delivery while increasing monetization of platform IP.",
    ]
    ledger_sources = [
        ["reb_ibm_aws_alliance_partner_cosell_gtm", "reb_unify_platform_commercialization_leadership"],
        ["reb_ibm_devsecops_release_resilience"],
        ["metric_ibm_alliance_cosell_operating_cadence", "metric_ibm_ai_driven_sales_frameworks"],
        ["metric_ibm_deployment_blueprint_repeatability", "metric_ibm_release_gate_security_scanning_coverage", "fact_engineering_platform_002"],
        ["reb_unify_platform_commercialization_leadership", "metric_unify_22m_ip_led_revenue", "fact_engineering_platform_006"],
        ["reb_ibm_aws_alliance_partner_cosell_gtm", "reb_ibm_devsecops_release_resilience", "reb_unify_platform_commercialization_leadership"],
    ]
    plan = {
        "allocation_plan_digest": "retry10-plan",
        "facts": roots,
        "allocation_assignments": assignments,
    }
    parsed = {
        "resume_display_text": " ".join(sentences),
        "claim_ledger": [
            {"claim_text": sentence, "source_fact_ids": source_ids}
            for sentence, source_ids in zip(sentences, ledger_sources, strict=True)
        ],
        "selected_fact_plan": plan,
        "change_log": [],
    }
    allowed = {
        value
        for root in roots
        for value in root["allowed_graph_evidence_ids"]
    }

    causal_repairs = repair_exec_summary_causal_multi_root_allocation_rows(parsed)
    assert causal_repairs
    parsed, _ = finalize_executive_summary_coherence(
        parsed,
        selected_facts=roots,
        allowed_fact_ids=allowed,
        target_role="Manager of Applied AI Architecture, Partnerships",
    )

    override = FACT_C0_DISPLAY_OVERRIDES["fact_engineering_platform_002"]
    assert override in parsed["resume_display_text"]
    override_ok, override_reason = check_exec_summary_display_override_compliance(
        parsed["resume_display_text"],
        parsed["claim_ledger"],
    )
    assert override_ok, override_reason
    failures = validate_claim_rows_against_resume_graph_allocation(
        section_id="executive_summary",
        claim_rows=parsed["claim_ledger"],
        selected_fact_plan=plan,
    )
    assert failures == []


def test_final_coherence_reclamps_causal_graph_roots_after_ledger_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final ledger rebuild must not undo a graph-root attribution repair."""
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        validate_claim_rows_against_resume_graph_allocation,
    )
    platform_root = "reb_unify_agentic_platform_architecture"
    commercialization_root = "reb_unify_platform_commercialization_leadership"
    platform_fact = "fact_engineering_platform_001"
    commercialization_fact = "fact_engineering_platform_006"
    revenue_metric = "metric_unify_22m_ip_led_revenue"
    roots = [
        {
            "fact_id": platform_root,
            "role_episode_bundle_id": platform_root,
            "claim_text": "Governed agentic AI platform control-plane architecture",
            "linked_source_fact_ids": [platform_fact],
            "allowed_graph_evidence_ids": [platform_root, platform_fact],
        },
        {
            "fact_id": commercialization_root,
            "role_episode_bundle_id": commercialization_root,
            "claim_text": "Platform productization generated $22M in IP-led revenue",
            "linked_source_fact_ids": [commercialization_fact],
            "metric_outcome_ids": [revenue_metric],
            "allowed_graph_evidence_ids": [
                commercialization_root,
                commercialization_fact,
                revenue_metric,
            ],
        },
    ]
    allocation = {
        "allocation_plan_digest": "a" * 64,
        "facts": roots,
        "allocation_assignments": [
            {
                "section_id": "executive_summary",
                "claim_unit_id": "executive_summary:claim:01",
                "root_id": platform_root,
                "fact_id": platform_fact,
                "root_claim_text": "Governed agentic AI platform control-plane architecture",
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "executive_summary:claim:02",
                "root_id": commercialization_root,
                "fact_id": commercialization_fact,
                "metric_outcome_id": revenue_metric,
                "metric_value": "22",
                "metric_unit": "USD_M",
                "root_claim_text": "Platform productization generated $22M in IP-led revenue",
            },
        ],
    }
    sentences = [
        "Technology executive leads governed platform delivery for regulated enterprises.",
        "Control-plane discipline keeps decisions traceable across delivery workflows.",
        "Engineering teams apply that discipline to complex modernization programs.",
        "Human oversight remains embedded as automated capability expands.",
        "Release controls keep regulated delivery paths dependable and auditable.",
        "That same platform discipline underpins productization work that generated $22M in IP-led platform revenue, an outcome that positions this operating model for new enterprise delivery contexts.",
    ]
    parsed = {
        "resume_display_text": " ".join(sentences),
        "claim_ledger": [
            {"claim_text": sentence, "source_fact_ids": [platform_root]}
            for sentence in sentences[:5]
        ]
        + [
            {
                "claim_text": sentences[5],
                "source_fact_ids": [platform_root, commercialization_root],
            }
        ],
        "selected_fact_plan": allocation,
        "change_log": [],
    }
    from apps_rg.runtime.sections import executive_summary_voice_repair as voice_repair

    def rebuild_with_cross_root(value: dict[str, object]) -> dict[str, object]:
        """Replay the final display-to-ledger rebind that previously restored both roots."""
        rebuilt = dict(value)
        rows = [dict(row) for row in value["claim_ledger"]]  # type: ignore[index]
        rows[-1]["source_fact_ids"] = [platform_root, commercialization_root]
        rebuilt["claim_ledger"] = rows
        return rebuilt

    monkeypatch.setattr(
        voice_repair,
        "_rebuild_claim_ledger_from_display",
        rebuild_with_cross_root,
    )
    allowed = {
        value
        for root in roots
        for value in root["allowed_graph_evidence_ids"]
    }

    final, receipt = voice_repair.finalize_executive_summary_coherence(
        parsed,
        selected_facts=roots,
        allowed_fact_ids=allowed,
    )

    assert receipt["graph_claim_binding_repairs"]
    assert final["claim_ledger"][-1]["source_fact_ids"] == [commercialization_root]
    assert not any(
        "causal_claim_merges_unrelated_graph_roots" in failure
        for failure in validate_claim_rows_against_resume_graph_allocation(
        section_id="executive_summary",
        claim_rows=final["claim_ledger"],
        selected_fact_plan=allocation,
        )
    )


def test_r4_causal_multi_metric_repair_keeps_only_reserved_metric_path() -> None:
    """Replay r4's final executive-summary failure without another model call."""
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        validate_claim_rows_against_resume_graph_allocation,
    )

    unify_root = "reb_unify_platform_commercialization_leadership"
    ibm_delivery_root = "reb_ibm_devsecops_release_resilience"
    ibm_alliance_root = "reb_ibm_aws_alliance_partner_cosell_gtm"
    unify_fact = "fact_engineering_platform_006"
    ibm_delivery_fact = "fact_engineering_platform_002"
    ibm_alliance_fact = "fact_partnerships_gtm_002"
    unify_metric = "metric_unify_22m_ip_led_revenue"
    ibm_metric = "metric_ibm_20pct_joint_revenue_growth"
    plan = {
        "allocation_plan_digest": "r4-captured-plan",
        "facts": [
            {
                "fact_id": unify_root,
                "role_episode_bundle_id": unify_root,
                "linked_source_fact_ids": [unify_fact],
                "allowed_graph_evidence_ids": [unify_root, unify_fact, unify_metric],
            },
            {
                "fact_id": ibm_delivery_root,
                "role_episode_bundle_id": ibm_delivery_root,
                "linked_source_fact_ids": [ibm_delivery_fact],
                "allowed_graph_evidence_ids": [ibm_delivery_root, ibm_delivery_fact],
            },
            {
                "fact_id": ibm_alliance_root,
                "role_episode_bundle_id": ibm_alliance_root,
                "linked_source_fact_ids": [ibm_alliance_fact],
                "allowed_graph_evidence_ids": [
                    ibm_alliance_root,
                    ibm_alliance_fact,
                    ibm_metric,
                ],
            },
        ],
        "allocation_assignments": [
            {
                "section_id": "executive_summary",
                "claim_unit_id": "executive_summary:claim:01",
                "root_id": unify_root,
                "fact_id": unify_fact,
                "metric_outcome_id": unify_metric,
                "metric_value": "22",
                "metric_unit": "USD_M",
                "root_claim_text": "Platform productization, IP-led revenue, margin expansion, team scale",
                "counts_toward_global_uniqueness": True,
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "executive_summary:claim:02",
                "root_id": ibm_delivery_root,
                "fact_id": ibm_delivery_fact,
                "metric_outcome_id": "",
                "metric_value": "",
                "metric_unit": "",
                "root_claim_text": "Embedded release automation and security scanning into regulated modernization delivery paths",
                "counts_toward_global_uniqueness": True,
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "executive_summary:claim:03",
                "root_id": ibm_alliance_root,
                "fact_id": ibm_alliance_fact,
                "metric_outcome_id": "",
                "metric_value": "",
                "metric_unit": "",
                "root_claim_text": "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities",
                "counts_toward_global_uniqueness": True,
            },
        ],
    }
    broken_sentence = (
        "That operating foundation also drove 20% joint revenue growth across the IBM-AWS "
        "alliance, while platform productization work elsewhere generated $22M in IP-led revenue."
    )
    parsed = {
        "resume_display_text": " ".join(
            [
                "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities.",
                "Embedded release automation and security scanning into regulated modernization delivery paths.",
                broken_sentence,
            ]
        ),
        "claim_ledger": [
            {
                "claim_text": "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities.",
                "source_fact_ids": [ibm_alliance_root, ibm_alliance_fact],
            },
            {
                "claim_text": "Embedded release automation and security scanning into regulated modernization delivery paths.",
                "source_fact_ids": [ibm_delivery_root, ibm_delivery_fact],
            },
            {
                "claim_text": (
                    "20% joint revenue growth across the IBM-AWS alliance and $22M in "
                    "IP-led revenue from platform productization"
                ),
                "source_fact_ids": [ibm_metric, unify_metric],
            },
        ],
        "selected_fact_plan": plan,
        "change_log": [],
    }

    repairs = repair_exec_summary_causal_multi_metric_rows(parsed)

    assert len(repairs) == 1
    assert parsed["claim_ledger"][2]["claim_text"] == (
        "Platform productization work elsewhere generated $22M in IP-led revenue."
    )
    assert "20%" not in parsed["resume_display_text"]
    assert parsed["claim_ledger"][2]["source_fact_ids"] == [
        unify_root,
        unify_fact,
        unify_metric,
    ]
    assert validate_claim_rows_against_resume_graph_allocation(
        section_id="executive_summary",
        claim_rows=parsed["claim_ledger"],
        selected_fact_plan=plan,
    ) == []


def test_unallocated_alliance_metric_rehydrates_frozen_root_claim() -> None:
    from apps_rg.runtime.c0.resume_graph_claim_binding import (
        validate_claim_rows_against_resume_graph_allocation,
    )

    root_id = "reb_ibm_aws_alliance_partner_cosell_gtm"
    fact_id = "fact_partnerships_gtm_002"
    metric_id = "metric_ibm_20pct_joint_revenue_growth"
    root_claim = (
        "Led IBM-AWS alliance co-sell motions for financial-services modernization opportunities"
    )
    assignment = {
        "section_id": "executive_summary",
        "claim_unit_id": "executive_summary:claim:03",
        "root_id": root_id,
        "skill_id": "skill_partner_cloud_vendor_joint_gtm",
        "fact_id": fact_id,
        "metric_outcome_id": "",
        "metric_value": "",
        "metric_unit": "",
        "root_bundle_theme": "AWS partnership, alliance co-sell, and joint GTM execution",
        "root_claim_text": root_claim,
        "counts_toward_global_uniqueness": True,
    }
    plan = {
        "allocation_plan_digest": "retry11-plan",
        "facts": [
            {
                "fact_id": root_id,
                "role_episode_bundle_id": root_id,
                "linked_source_fact_ids": [fact_id],
                "allowed_graph_evidence_ids": [root_id, fact_id, metric_id],
            }
        ],
        "allocation_assignments": [assignment],
    }
    parsed = {
        "resume_display_text": (
            "In parallel, alliance operating cadence supported 20% joint revenue growth, "
            "linking partner execution to measurable commercial accountability."
        ),
        "claim_ledger": [
            {
                "claim_text": (
                    "In parallel, alliance operating cadence supported 20% joint revenue growth, "
                    "linking partner execution to measurable commercial accountability."
                ),
                "source_fact_ids": [metric_id],
            }
        ],
        "selected_fact_plan": plan,
        "change_log": [],
    }

    repairs = repair_exec_summary_unallocated_metric_rows(parsed)

    assert repairs
    assert parsed["resume_display_text"] == root_claim + "."
    assert "20%" not in parsed["resume_display_text"]
    assert parsed["claim_ledger"][0]["source_fact_ids"] == [root_id, fact_id]
    assert validate_claim_rows_against_resume_graph_allocation(
        section_id="executive_summary",
        claim_rows=parsed["claim_ledger"],
        selected_fact_plan=plan,
    ) == []


def test_repair_orphan_rows_materializes_unused_required_fact() -> None:
    """Orphan ledger rows must cite unused required facts without fabricating prose."""
    orphan_bridge = (
        "That foundation informs data governance and AI strategy at scale."
    )
    text = (
        "Enterprise technology leader who unifies governed AI platforms for regulated enterprises. "
        "Designed and operationalized a governed agentic AI platform with deterministic routing. "
        f"{orphan_bridge} "
        "That regulatory foundation is grounded in FSA-chartered actuarial work in capital modeling. "
        "Directed large-scale regulatory IT transformations for major financial institutions. "
        "Software dependency graph intelligence enables accelerated legacy-system analysis."
    )
    facts = [
        {"fact_id": "fact_engineering_platform_001", "claim_text": "Governed agentic AI platform."},
        {
            "fact_id": "fact_engineering_platform_006",
            "claim_text": (
                "Platform commercialization generated $22M in IP-led revenue and expanded gross "
                "margins by 20%, while scaling the ML engineering organization from 8 to 28 specialists."
            ),
        },
        {"fact_id": "fact_quant_hpc_003", "claim_text": "FSA-chartered actuarial work in capital modeling."},
        {"fact_id": "fact_consulting_001", "claim_text": "Directed large-scale regulatory IT transformations."},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Software dependency graph intelligence."},
        {"fact_id": "fact_exec_002", "claim_text": "Scaled ML engineering organization from 8 to 28."},
    ]
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim_text": "a", "source_fact_ids": ["fact_engineering_platform_001"]},
            {"claim_text": "b", "source_fact_ids": ["fact_engineering_platform_001"]},
            {"claim_text": "c", "source_fact_ids": []},
            {"claim_text": "d", "source_fact_ids": ["fact_quant_hpc_003"]},
            {"claim_text": "e", "source_fact_ids": ["fact_consulting_001"]},
            {"claim_text": "f", "source_fact_ids": ["fact_engineering_platform_002", "fact_exec_002"]},
        ],
        "change_log": [],
    }
    allowed = {f["fact_id"] for f in facts}
    repairs = repair_exec_summary_orphan_rows_with_unused_required_facts(
        parsed,
        allowed_fact_ids=allowed,
        plan_facts=facts,
    )
    assert repairs
    assert parsed["claim_ledger"][2]["source_fact_ids"] == ["fact_engineering_platform_006"]
    assert "$22m" in str(parsed["resume_display_text"]).lower()
    assert orphan_bridge not in str(parsed["resume_display_text"])


def test_apply_authority_repairs_runs_orphan_repair_before_shape_check() -> None:
    text = (
        "Enterprise technology leader who unifies governed AI platforms for regulated enterprises. "
        "Designed and operationalized a governed agentic AI platform with deterministic routing. "
        "That foundation informs data governance and AI strategy at scale. "
        "That regulatory foundation is grounded in FSA-chartered actuarial work in capital modeling. "
        "Directed large-scale regulatory IT transformations for major financial institutions. "
        "Software dependency graph intelligence enables accelerated legacy-system analysis."
    )
    facts = [
        {"fact_id": "fact_engineering_platform_001", "claim_text": "Governed agentic AI platform."},
        {
            "fact_id": "fact_engineering_platform_006",
            "claim_text": (
                "Platform commercialization generated $22M in IP-led revenue and expanded gross "
                "margins by 20%, while scaling the ML engineering organization from 8 to 28 specialists."
            ),
        },
        {"fact_id": "fact_quant_hpc_003", "claim_text": "FSA-chartered actuarial work in capital modeling."},
        {"fact_id": "fact_consulting_001", "claim_text": "Directed large-scale regulatory IT transformations."},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Software dependency graph intelligence."},
        {"fact_id": "fact_exec_002", "claim_text": "Scaled ML engineering organization from 8 to 28."},
    ]
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim_text": "a", "source_fact_ids": ["fact_engineering_platform_001"]},
            {"claim_text": "b", "source_fact_ids": ["fact_engineering_platform_001"]},
            {"claim_text": "c", "source_fact_ids": []},
            {"claim_text": "d", "source_fact_ids": ["fact_quant_hpc_003"]},
            {"claim_text": "e", "source_fact_ids": ["fact_consulting_001"]},
            {"claim_text": "f", "source_fact_ids": ["fact_engineering_platform_002", "fact_exec_002"]},
        ],
        "change_log": [],
        "selected_fact_plan": {"facts": facts},
    }
    out = apply_exec_summary_display_authority_repairs(
        parsed,
        allowed_fact_ids={f["fact_id"] for f in facts},
        plan_facts=facts,
    )
    assert out["claim_ledger"][2]["source_fact_ids"] == ["fact_engineering_platform_006"]
    assert any(
        c.get("operation") == "repair_orphan_row_with_unused_required_fact"
        for c in out.get("change_log") or []
    )


def test_repair_required_brushstroke_citation_from_materialized_sentence() -> None:
    text = (
        "Executive leader who unifies governed AI platform architecture for enterprise adoption. "
        "Led AWS modernization for regulated financial-services workloads through cloud-native delivery. "
        "Reusable accelerators and decision-support models turned modernization into client pursuits. "
        "In parallel, regulated cloud adoption standards grounded delivery patterns. "
        "That operating foundation supported IP-led revenue of $22M. "
        "Positioned partner ecosystems to scale safe enterprise AI."
    )
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim_text": "s1", "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {"claim_text": "s2", "source_fact_ids": ["reb_ibm_aws_modernization_architecture"]},
            {"claim_text": "s3", "source_fact_ids": ["reb_ibm_offering_accelerator_management"]},
            {"claim_text": "s4", "source_fact_ids": ["reb_insurtech_insurance_regulatory_cloud_adoption_standards"]},
            {"claim_text": "s5", "source_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
            {"claim_text": "s6", "source_fact_ids": ["reb_unify_partner_channel_cosell"]},
        ],
        "executive_summary_composition_plan": {
            "brushstrokes": [
                {
                    "brushstroke_id": "B1_executive_identity",
                    "required_fact_ids": ["reb_insurtech_aws_migration_execution"],
                }
            ]
        },
        "change_log": [],
    }
    facts = [
        {
            "fact_id": "reb_insurtech_aws_migration_execution",
            "claim_text": "Led AWS modernization execution for monolithic policy administration and insurance platform workloads.",
        }
    ]

    repairs = repair_required_brushstroke_citations_from_materialized_sentences(
        parsed,
        allowed_fact_ids={"reb_insurtech_aws_migration_execution"},
        plan_facts=facts,
    )

    assert repairs
    assert parsed["claim_ledger"][1]["source_fact_ids"] == [
        "reb_ibm_aws_modernization_architecture",
        "reb_insurtech_aws_migration_execution",
    ]
    assert parsed["resume_display_text"] == text


def test_repair_exec_summary_thin_sentence_weave_updates_display_and_ledger() -> None:
    text = (
        "Enterprise AI partnerships leader for regulated enterprises. "
        "Led AWS modernization architecture across financial-services workloads. "
        "Built reusable accelerators that linked modernization to executive decisions. "
        "In parallel, insurer regulatory adoption reinforced controls and standards readiness. "
        "Platform productization generated $22M in IP-led revenue and margin expansion. "
        "That operating foundation positions partner ecosystems to scale safe AI."
    )
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim": "s1", "claim_text": "Enterprise AI partnerships leader for regulated enterprises.", "source_fact_ids": ["reb_a"]},
            {"claim": "s2", "claim_text": "Led AWS modernization architecture across financial-services workloads.", "source_fact_ids": ["reb_b"]},
            {"claim": "s3", "claim_text": "Built reusable accelerators that linked modernization to executive decisions.", "source_fact_ids": ["reb_c"]},
            {"claim": "s4", "claim_text": "In parallel, insurer regulatory adoption reinforced controls and standards readiness.", "source_fact_ids": ["reb_d"]},
            {"claim": "s5", "claim_text": "Platform productization generated $22M in IP-led revenue and margin expansion.", "source_fact_ids": ["reb_e"]},
            {"claim": "s6", "claim_text": "That operating foundation positions partner ecosystems to scale safe AI.", "source_fact_ids": ["reb_f"]},
        ],
        "change_log": [],
    }

    repairs = repair_exec_summary_thin_sentence_weave(parsed)

    assert repairs
    first = parsed["resume_display_text"].split(". ", 1)[0]
    assert "regulated enterprise operating models" in first.lower()
    assert parsed["claim_ledger"][0]["claim_text"] == first + "."


def test_repair_exec_summary_mechanism_inventory_updates_display_and_ledger() -> None:
    text = (
        "An engineering and partnership executive directs cloud migration and modernization for regulated insurance and financial-services workloads, aligning insurer and regulatory adoption standards with delivery execution. "
        "This leader architects a governed agentic AI control plane spanning distributed cloud and data infrastructure, deterministic routing, and policy-gated execution surfaces. "
        "Alliance co-sell motions with AWS and IBM's modernization architecture convert on-prem constraints into cloud-native reference patterns reused across regulated client pursuits. "
        "In parallel, decision-support data models and BI views connect those modernization programs directly to executive operating decisions, while regulator and NAIC data-security engagement keeps cloud adoption standards lineage-ready. "
        "That same partner discipline extends into IBM-AWS joint go-to-market cadence, producing 20% joint revenue growth alongside AI-driven sales frameworks adopted across alliance teams. "
        "This foundation positions the leader to scale partner-led AI solution architecture and enablement across cloud and GSI ecosystems for enterprise-wide adoption."
    )
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim": "s1", "claim_text": "s1", "source_fact_ids": ["reb_insurtech_aws_migration_execution"]},
            {
                "claim": "s2",
                "claim_text": "This leader architects a governed agentic AI control plane spanning distributed cloud and data infrastructure, deterministic routing, and policy-gated execution surfaces.",
                "source_fact_ids": [
                    "reb_unify_agentic_platform_architecture",
                    "reb_unify_distributed_ecosystem_engineering",
                ],
            },
            {"claim": "s3", "claim_text": "s3", "source_fact_ids": ["reb_ibm_aws_alliance_partner_cosell_gtm"]},
            {"claim": "s4", "claim_text": "s4", "source_fact_ids": ["reb_ibm_data_modeling_bi_decision_support"]},
            {"claim": "s5", "claim_text": "s5", "source_fact_ids": ["metric_ibm_20pct_joint_revenue_growth"]},
            {"claim": "s6", "claim_text": "s6", "source_fact_ids": ["reb_unify_partner_channel_cosell"]},
        ],
        "change_log": [],
    }

    ok_before, reason_before = check_exec_summary_no_mechanism_inventory(text, parsed)
    assert ok_before is False
    assert reason_before is not None and "mechanism_inventory" in reason_before

    repairs = repair_exec_summary_mechanism_inventory_sentences(parsed)

    assert repairs
    repaired_text = str(parsed["resume_display_text"])
    ok_after, reason_after = check_exec_summary_no_mechanism_inventory(repaired_text, parsed)
    assert ok_after is True, reason_after
    assert "policy-gated" not in repaired_text
    assert "deterministic" not in repaired_text
    assert "route selection and governed execution surfaces" in repaired_text
    assert parsed["claim_ledger"][1]["claim_text"].endswith(
        "route selection and governed execution surfaces."
    )


def test_repair_exec_summary_mechanism_inventory_handles_live_route_selection_sentence() -> None:
    live_sentence = (
        "Deterministic route selection, graph-aware relationship grounding, and sandboxed execution "
        "give agentic systems policy-gated, replayable runtime traceability across distributed cloud "
        "and data infrastructure."
    )
    text = (
        "Engineering leader who builds governed agentic AI platform architecture for regulated delivery. "
        f"{live_sentence} "
        "Alliance modernization work connected partner reference patterns to measured delivery outcomes."
    )
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim": "s1", "claim_text": "s1", "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {
                "claim": "s2",
                "claim_text": live_sentence,
                "source_fact_ids": [
                    "reb_unify_agentic_platform_architecture",
                    "reb_unify_distributed_ecosystem_engineering",
                ],
            },
            {"claim": "s3", "claim_text": "s3", "source_fact_ids": ["reb_ibm_aws_alliance_partner_cosell_gtm"]},
        ],
        "change_log": [],
    }

    ok_before, reason_before = check_exec_summary_no_mechanism_inventory(text, parsed)
    assert ok_before is False
    assert reason_before is not None and "mechanism_inventory:4_terms" in reason_before

    repairs = repair_exec_summary_mechanism_inventory_sentences(parsed)

    assert repairs
    repaired_text = str(parsed["resume_display_text"])
    ok_after, reason_after = check_exec_summary_no_mechanism_inventory(repaired_text, parsed)
    assert ok_after is True, reason_after
    assert "Deterministic" not in repaired_text
    assert "sandboxed" not in repaired_text
    assert "policy-gated" not in repaired_text
    assert "replayable" not in repaired_text
    assert "relationship-aware grounding" in repaired_text
    assert "auditable runtime traceability" in repaired_text
    assert parsed["claim_ledger"][1]["claim_text"] in repaired_text


def test_retry32_exec_summary_control_inventory_is_compacted_and_ledger_synced() -> None:
    live_sentence = (
        "In parallel, security gates, human override paths, and runtime proof-bundle lineage "
        "bring policy, escalation, and evidence into the platform lifecycle."
    )
    first = "Technology executive links regulated modernization with governed platform architecture."
    third = "Commercial operating discipline connects platform productization with enterprise growth."
    text = f"{first} {live_sentence} {third}"
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim": "s1", "claim_text": first, "source_fact_ids": ["reb_ibm_devsecops_release_resilience"]},
            {
                "claim": "s2",
                "claim_text": live_sentence,
                "source_fact_ids": [
                    "skill_ibm_devsecops_pipeline_security",
                    "skill_unify_agentic_human_override_escalation_paths",
                    "skill_unify_agentic_runtime_proof_bundle_lineage",
                ],
            },
            {"claim": "s3", "claim_text": third, "source_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
        ],
        "change_log": [],
    }

    ok_before, _ = check_exec_summary_no_mechanism_inventory(text, parsed)
    assert ok_before is False
    repairs = repair_exec_summary_mechanism_inventory_sentences(parsed)

    assert repairs
    repaired_text = str(parsed["resume_display_text"])
    assert "governed release controls and runtime proof lineage" in repaired_text
    assert "security gates, human override paths" not in repaired_text
    ok_after, reason_after = check_exec_summary_no_mechanism_inventory(repaired_text, parsed)
    assert ok_after is True, reason_after
    assert parsed["claim_ledger"][1]["claim_text"] in repaired_text


def test_w8_patch_exec_summary_route_control_inventory_is_compacted_and_ledger_synced() -> None:
    live_sentence = (
        "Leads design of an agentic platform control plane spanning route policy dispatch, "
        "replay key controls manifest lineage, and human override escalation paths so autonomous "
        "execution stays bounded and explainable."
    )
    first = "Engineering executive unites governed agentic AI architecture with regulated delivery discipline."
    third = "Commercial leadership converts platform productization into measurable enterprise growth."
    text = f"{first} {live_sentence} {third}"
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim": "s1", "claim_text": first, "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {
                "claim": "s2",
                "claim_text": live_sentence,
                "source_fact_ids": [
                    "skill_unify_agentic_l0_route_policy_dispatch",
                    "skill_unify_agentic_replay_key_audit_manifest_design",
                    "skill_unify_agentic_human_override_escalation_paths",
                ],
            },
            {"claim": "s3", "claim_text": third, "source_fact_ids": ["metric_unify_22m_ip_led_revenue"]},
        ],
        "change_log": [],
    }

    ok_before, reason_before = check_exec_summary_no_mechanism_inventory(text, parsed)
    assert ok_before is False
    assert reason_before is not None and "mechanism_comma_list" in reason_before

    repairs = repair_exec_summary_mechanism_inventory_sentences(parsed)

    assert repairs
    repaired_text = str(parsed["resume_display_text"])
    assert "governed routing, auditable runtime lineage, and human escalation paths" in repaired_text
    assert "route policy dispatch" not in repaired_text
    ok_after, reason_after = check_exec_summary_no_mechanism_inventory(repaired_text, parsed)
    assert ok_after is True, reason_after
    assert parsed["claim_ledger"][1]["claim_text"] in repaired_text


def test_repair_exec_summary_cross_fact_conflation_compacts_live_alliance_row() -> None:
    text = (
        "Enterprise technology executive aligning AWS modernization, governed agentic architecture, and hyperscaler co-sell into an applied-AI partnership model for regulated enterprises. "
        "Insurance workloads were classified by cloud fit and moved into AWS-native modernization waves reused as reference architectures. "
        "The governed agentic platform control plane pairs route selection with controlled execution and auditable runtime traceability. "
        "Insurer and regulatory cloud-adoption standards were engaged directly through NAIC readiness across multiple regulatory bodies. "
        "IBM-AWS alliance co-sell motions built on reusable offering accelerators and joint solution development, producing a 20% joint-revenue growth cadence. "
        "Partner channel co-sell and joint solution development position this leader to scale partner solutions architecture across hyperscaler ecosystems."
    )
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim_text": "s1", "source_fact_ids": ["reb_insurtech_aws_migration_execution"]},
            {
                "claim_text": "s2",
                "source_fact_ids": [
                    "reb_insurtech_aws_migration_execution",
                    "metric_insurtech_workloads_classified_by_cloud_fit_count",
                    "metric_ibm_onprem_to_aws_modernization_waves",
                    "metric_ibm_regulated_reference_architecture_reuse",
                ],
            },
            {"claim_text": "s3", "source_fact_ids": ["reb_unify_agentic_platform_architecture"]},
            {"claim_text": "s4", "source_fact_ids": ["reb_insurtech_insurance_regulatory_cloud_adoption_standards"]},
            {
                "claim_text": "s5",
                "source_fact_ids": [
                    "reb_ibm_aws_alliance_partner_cosell_gtm",
                    "metric_ibm_20pct_joint_revenue_growth",
                    "reb_ibm_offering_accelerator_management",
                    "skill_partner_joint_solution_development",
                    "metric_ibm_ai_driven_sales_frameworks",
                ],
            },
            {"claim_text": "s6", "source_fact_ids": ["reb_unify_partner_channel_cosell"]},
        ],
        "change_log": [],
    }

    repairs = repair_exec_summary_cross_fact_conflation_rows(parsed)

    assert repairs
    assert all(
        len(row.get("source_fact_ids") or []) <= 3
        for row in parsed["claim_ledger"]
    )
    assert any(
        c.get("operation") == "repair_exec_summary_cross_fact_conflation_row"
        for c in parsed.get("change_log") or []
    )


def test_apply_authority_repairs_compacts_mechanism_inventory_before_x2() -> None:
    text = (
        "An engineering and partnership executive directs cloud migration and modernization for regulated insurance and financial-services workloads, aligning insurer and regulatory adoption standards with delivery execution. "
        "This leader architects a governed agentic AI control plane spanning distributed cloud and data infrastructure, deterministic routing, and policy-gated execution surfaces. "
        "Alliance co-sell motions with AWS and IBM's modernization architecture convert on-prem constraints into cloud-native reference patterns reused across regulated client pursuits. "
        "In parallel, decision-support data models and BI views connect those modernization programs directly to executive operating decisions, while regulator and NAIC data-security engagement keeps cloud adoption standards lineage-ready. "
        "That same partner discipline extends into IBM-AWS joint go-to-market cadence, producing 20% joint revenue growth alongside AI-driven sales frameworks adopted across alliance teams. "
        "This foundation positions the leader to scale partner-led AI solution architecture and enablement across cloud and GSI ecosystems for enterprise-wide adoption."
    )
    facts = [
        {"fact_id": "reb_insurtech_aws_migration_execution", "claim_text": "Led AWS modernization execution for insurance platform workloads."},
        {"fact_id": "reb_unify_agentic_platform_architecture", "claim_text": "Architected governed agentic AI control-plane architecture."},
        {"fact_id": "reb_unify_distributed_ecosystem_engineering", "claim_text": "Distributed cloud and data execution infrastructure."},
        {"fact_id": "reb_ibm_aws_alliance_partner_cosell_gtm", "claim_text": "IBM-AWS alliance co-sell motions."},
        {"fact_id": "reb_ibm_data_modeling_bi_decision_support", "claim_text": "Decision-support data models and BI views."},
        {"fact_id": "metric_ibm_20pct_joint_revenue_growth", "claim_text": "20% joint revenue growth."},
        {"fact_id": "reb_unify_partner_channel_cosell", "claim_text": "Partner channel co-sell foundation."},
    ]
    parsed = {
        "resume_display_text": text,
        "claim_ledger": [
            {"claim": "s1", "claim_text": "s1", "source_fact_ids": ["reb_insurtech_aws_migration_execution"]},
            {"claim": "s2", "claim_text": "s2", "source_fact_ids": ["reb_unify_agentic_platform_architecture", "reb_unify_distributed_ecosystem_engineering"]},
            {"claim": "s3", "claim_text": "s3", "source_fact_ids": ["reb_ibm_aws_alliance_partner_cosell_gtm"]},
            {"claim": "s4", "claim_text": "s4", "source_fact_ids": ["reb_ibm_data_modeling_bi_decision_support"]},
            {"claim": "s5", "claim_text": "s5", "source_fact_ids": ["metric_ibm_20pct_joint_revenue_growth"]},
            {"claim": "s6", "claim_text": "s6", "source_fact_ids": ["reb_unify_partner_channel_cosell"]},
        ],
        "selected_fact_plan": {"facts": facts},
        "change_log": [],
    }

    out = apply_exec_summary_display_authority_repairs(
        parsed,
        allowed_fact_ids={f["fact_id"] for f in facts},
        plan_facts=facts,
    )

    ok, reason = check_exec_summary_no_mechanism_inventory(str(out["resume_display_text"]), out)
    assert ok is True, reason
    assert any(
        c.get("operation") == "repair_exec_summary_mechanism_inventory_sentence"
        for c in out.get("change_log") or []
    )


def test_strip_credential_dump_removes_cert_sentence():
    text = (
        "Engineering executive who builds governed agentic AI platforms for regulated workflows. "
        "He designs platform operating systems that bind routing and orchestration into enterprise capability. "
        "He leads platform lifecycle work across architecture and engineering scale-out. "
        "AWS Certified Machine Learning Engineer, AWS Certified Solutions Architect, Databricks Lakehouse "
        "Fundamentals, and Fellow of the Society of Actuaries credentials reinforce senior IT strategy leadership."
    )
    repaired, removed = strip_exec_summary_credential_dump_sentences(text)
    assert removed
    ok, _ = check_exec_summary_no_credential_dump(repaired)
    assert ok is True


def test_exec_summary_authority_repairs_blocks_graph_only_fallback_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPS_RG_EXEC_SUMMARY_GRAPH_ONLY_REPAIR_MODE", raising=False)
    bad = (
        "This executive has extensive experience in designing governed agentic AI platforms. "
        "This expertise led to productization generating $22M in IP-led revenue. "
        "Additionally, Basel III/CCAR validation reduced reporting errors by 40%. "
        "The executive holds quantitative finance credentials including derivatives pricing."
    )
    facts = [
        {
            "fact_id": "fact_engineering_platform_001",
            "claim_text": "Designed governed agentic AI platforms for regulated workflows.",
        },
        {
            "fact_id": "fact_engineering_platform_006",
            "claim_text": "Platform commercialization generated $22M in IP-led revenue.",
        },
        {"fact_id": "fact_governance_003", "claim_text": "Implemented Basel III/CCAR validation frameworks."},
        {"fact_id": "fact_exec_002", "claim_text": "Scaled ML engineering organization from 8 to 28."},
        {"fact_id": "fact_quant_hpc_001", "claim_text": "Delivered HPC quant pipelines for risk analytics."},
        {"fact_id": "fact_quant_hpc_003", "claim_text": "Applied stochastic calculus for derivatives pricing."},
        {"fact_id": "fact_partner_001", "claim_text": "Led joint GTM motions with cloud alliance partners."},
    ]
    parsed = {
        "resume_display_text": bad,
        "claim_ledger": [{"claim_text": "x", "source_fact_ids": ["fact_engineering_platform_001"]}],
        "change_log": [],
        "selected_fact_plan": {"facts": facts},
    }
    out = apply_exec_summary_display_authority_repairs(
        parsed,
        allowed_fact_ids={f["fact_id"] for f in facts},
        plan_facts=facts,
    )
    assert out["resume_display_text"] == bad
    assert not any(
        c.get("operation") == "graph_only_display_authority_fallback" for c in out.get("change_log") or []
    )


def test_exec_summary_authority_repairs_graph_only_fallback_on_bad_llm_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPS_RG_EXEC_SUMMARY_GRAPH_ONLY_REPAIR_MODE", "1")
    bad = (
        "This executive has extensive experience in designing governed agentic AI platforms. "
        "This expertise led to productization generating $22M in IP-led revenue. "
        "Additionally, Basel III/CCAR validation reduced reporting errors by 40%. "
        "The executive holds quantitative finance credentials including derivatives pricing."
    )
    facts = [
        {
            "fact_id": "fact_engineering_platform_001",
            "claim_text": "Designed governed agentic AI platforms for regulated workflows.",
        },
        {
            "fact_id": "fact_engineering_platform_006",
            "claim_text": "Platform commercialization generated $22M in IP-led revenue.",
        },
        {"fact_id": "fact_governance_003", "claim_text": "Implemented Basel III/CCAR validation frameworks."},
        {"fact_id": "fact_exec_002", "claim_text": "Scaled ML engineering organization from 8 to 28."},
        {"fact_id": "fact_quant_hpc_001", "claim_text": "Delivered HPC quant pipelines for risk analytics."},
        {"fact_id": "fact_quant_hpc_003", "claim_text": "Applied stochastic calculus for derivatives pricing."},
        {"fact_id": "fact_partner_001", "claim_text": "Led joint GTM motions with cloud alliance partners."},
    ]
    parsed = {
        "resume_display_text": bad,
        "claim_ledger": [{"claim_text": "x", "source_fact_ids": ["fact_engineering_platform_001"]}],
        "change_log": [],
        "selected_fact_plan": {"facts": facts},
    }
    out = apply_exec_summary_display_authority_repairs(
        parsed,
        allowed_fact_ids={f["fact_id"] for f in facts},
        plan_facts=facts,
    )
    text = str(out["resume_display_text"])
    assert "this executive" not in text.lower()
    assert check_exec_summary_meta_filler_patterns(text)[0] is True
    assert check_exec_summary_paragraph_max_words(text, out)[0] is True
    assert any(
        c.get("operation") == "graph_only_display_authority_fallback" for c in out.get("change_log") or []
    )


def test_sanitize_ibm_meta_disclaimer():
    raw = (
        "At IBM, led enterprise-scale cloud foundations for regulated financial services, "
        "establishing reliability discipline without claiming IBM delivered modern agentic platform products."
    )
    cleaned, changed = sanitize_ibm_narrative_display_text(raw)
    assert changed is True
    assert "without claiming" not in cleaned.lower()


def test_sanitize_ibm_narrative_does_not_rewrite_claim_substance() -> None:
    raw = (
        "Led enterprise-scale cloud modernization, decision-support analytics, and AWS alliance co-sell programs "
        "for regulated financial clients at IBM, establishing governed delivery discipline and reusable platform "
        "architecture that accelerated partner-led adoption and joint revenue expansion."
    )
    cleaned, changed = sanitize_ibm_narrative_display_text(raw)
    assert changed is False
    assert cleaned == raw
    assert cleaned.lower().startswith("led")
    assert "runtime" not in cleaned.lower()
    gates = run_ibm_narrative_x2_gates(
        narrative_sentence=cleaned,
        parsed_output={"narrative_sentence": cleaned, "jd_alignment": {"targeting_only": True}},
        claim_ledger=[{"claim_text": cleaned, "source_fact_ids": ["bul_ibm_001"]}],
        jd_text="enterprise modernization",
        runtime_generation_status="REAL_LLM",
        companion_bullet_texts="",
        allowed_fact_ids=["bul_ibm_001"],
        artifacts_dir=None,
    )
    by_id = {g.gate_id: g for g in gates}
    assert by_id["x2_ibm_narrative_no_meta_disclaimer_in_display"].pass_ is True
    assert by_id["x2_narrative_technical_specificity_floor"].pass_ is True


def test_prune_low_rigor_competency_terms():
    parsed = {
        "competencies": [
            {
                "category_label": "ENGINEERING & PLATFORM COMPETENCIES",
                "terms": [
                    {"text": "data sales", "source_fact_id": "bul_unify_001", "source_fact_ids": ["bul_unify_001"]},
                    {
                        "text": "agentic platform orchestration",
                        "source_fact_id": "bul_unify_002",
                        "source_fact_ids": ["bul_unify_002"],
                    },
                ],
            }
        ],
        "change_log": [],
    }
    removed = prune_competencies_rigor_failing_terms(parsed)
    terms = [t["text"] for t in parsed["competencies"][0]["terms"]]
    assert "data sales" not in terms
    assert removed


def test_run_x2_gates_includes_rigor_critical_executive_summary_gates(tmp_path: Path):
    text = (
        "Engineering executive who builds governed agentic AI platforms for regulated enterprise workflows. "
        "The leader scales deterministic routing and orchestration across platform programs. "
        "Platform lifecycle work ties architecture to commercial adoption and operating discipline. "
        "Prior delivery outcomes stay grounded in selected executive facts only."
    )
    parsed = {
        "resume_display_text": text,
        "jd_alignment": {
            "targeting_only": True,
            "jd_used_as_proof": False,
            "briefing_used_as_proof": False,
        },
        "self_check": {"no_first_person": True},
        "input_payload_hash": "a" * 16,
        "output_payload_hash": "b" * 16,
    }
    (tmp_path / "prompt_selection_trace.json").write_text(
        '{"apps_rg_prompt_template_ref":"apps_rg/prompt_assembly/templates/executive_summary.generate_scratch_v1.yaml",'
        '"compiler_template_id":"executive_summary.generate_scratch_v1"}',
        encoding="utf-8",
    )
    gates = run_x2_gates(
        resume_display_text=text,
        parsed_output=parsed,
        claim_ledger=[{"claim_text": "platform", "source_fact_ids": ["bul_unify_001"]}],
        text_claim_coverage={"sentences": [], "overall_pass": True},
        allowed_fact_ids={"bul_unify_001"},
        target_company="Acme",
        jd_text="jd",
        temperature=0.4,
        runtime_generation_status="REAL_LLM",
        monolithic_prompt_invoked=False,
        strategic_tailor_v1_invoked=True,
        artifacts_dir=tmp_path,
        provider_requested="retired_provider_profile",
        provider_attempted="retired_provider_profile",
        model_name="retired_provider-test",
        prompt_hash="c" * 16,
        compiled_prompt="x" * 32,
        raw_output='{"resume_display_text":"x"}',
        x1d_judges=[],
    )
    present = {g.gate_id for g in gates}
    crit = spec_for_lane("executive_summary").critical_gates
    c0 = {"x2_c0_metrics_artifact_present", "x2_c0_support_status_gate"}
    missing = sorted(g for g in crit if g not in present and g not in c0)
    assert not missing, f"missing rigor gates in run_x2_gates: {missing}"


def test_run_headline_x2_always_emits_text_claim_coverage_gate():
    from apps_rg.runtime.validators.headline_x2 import run_headline_x2_gates

    gates = run_headline_x2_gates(
        headline_line="SVP Engineering | Agentic Platforms | Cloud Scale | Governance",
        parsed_output={
            "headline_line": "SVP Engineering | Agentic Platforms | Cloud Scale | Governance",
            "claim_ledger": [
                {"claim_text": "Agentic Platforms", "source_fact_ids": ["bul_unify_001"]},
            ],
            "jd_alignment": {
                "targeting_only": True,
                "jd_used_as_proof": False,
                "briefing_used_as_proof": False,
                "companion_used_as_proof": False,
            },
        },
        claim_ledger=[{"claim_text": "Agentic Platforms", "source_fact_ids": ["bul_unify_001"]}],
        allowed_fact_ids={"bul_unify_001"},
        jd_text="",
        target_company="Acme",
        resume_support_blob="",
        employer_names_lower=[],
        runtime_generation_status="REAL_LLM",
        text_claim_coverage=None,
    )
    present = {g.gate_id for g in gates}
    assert "x2_headline_text_claim_coverage_integrity" in present
    cov_gate = next(g for g in gates if g.gate_id == "x2_headline_text_claim_coverage_integrity")
    assert cov_gate.pass_ is False


def test_run_ibm_narrative_x2_includes_meta_disclaimer_gate():
    narrative = "Led cloud and data foundations for regulated financial services at IBM."
    gates = run_ibm_narrative_x2_gates(
        narrative_sentence=narrative,
        parsed_output={"narrative_sentence": narrative, "jd_alignment": {"targeting_only": True}},
        claim_ledger=[{"claim_text": "cloud", "source_fact_ids": ["bul_ibm_001"]}],
        jd_text="",
        runtime_generation_status="REAL_LLM",
        companion_bullet_texts=None,
        allowed_fact_ids=["bul_ibm_001"],
        artifacts_dir=None,
    )
    present = {g.gate_id for g in gates}
    assert "x2_ibm_narrative_no_meta_disclaimer_in_display" in present
    assert "x2_ibm_narrative_claim_ledger_clause_decomposition" in present
