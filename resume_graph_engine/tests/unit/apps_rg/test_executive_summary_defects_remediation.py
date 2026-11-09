"""Regression test suite for Executive Summary Defect Remediation (M1: R1 and R2).

Verifies:
1. Elimination of the forced canned 21-word dependency graph sentence across synthesis contracts,
   validators, and voice repairs, allowing natural model synthesis.
2. Correct role episode bundle lineage with zero cross-employer misattribution between IBM and Unify.
3. Support for multi-milestone claims combining career milestones in executive summary,
   preserving both milestone roots and the $22M revenue metric without orphan errors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.sections.executive_summary_synthesis_contract import (
    DEPENDENCY_GRAPH_FACT_ID,
    FACT_C0_DISPLAY_OVERRIDES,
    FSA_CREDENTIAL_FACT_ID,
)
from apps_rg.runtime.validators.executive_summary_x2 import (
    _DISPLAY_OVERRIDE_REQUIRED_SUBSTRINGS,
    check_exec_summary_display_override_compliance,
)
from apps_rg.runtime.sections.executive_summary_voice_repair import (
    _CANONICAL_DISPLAY_SENTENCES,
    _CANONICAL_FACT_SLOT,
    _source_fact_ids_for_display_sentence,
    finalize_executive_summary_coherence,
    polish_executive_summary_judge_alignment,
)
from apps_rg.runtime.c0.resume_graph_claim_binding import (
    validate_claim_rows_against_resume_graph_allocation,
)
from apps_rg.runtime.sections.section_authority_repairs import (
    repair_exec_summary_causal_multi_root_allocation_rows,
    repair_exec_summary_unallocated_metric_rows,
)
from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import (
    resolve_unallocated_metric_sentence_replacement,
)


_CANNED_21_WORD_SENTENCE = (
    "Software dependency graph intelligence enables accelerated legacy-system analysis, "
    "exposes architecture dependency chains, and improves transformation visibility across enterprise complexity."
)


def test_dependency_graph_natural_synthesis_no_canned_override() -> None:
    """R1.1: Verify no forced canned 21-word dependency graph override in contracts or repairs."""
    # 1. Synthesis contract overrides
    assert DEPENDENCY_GRAPH_FACT_ID not in FACT_C0_DISPLAY_OVERRIDES
    assert FSA_CREDENTIAL_FACT_ID in FACT_C0_DISPLAY_OVERRIDES

    # 2. X2 validator requirements
    assert "fact_engineering_platform_002" not in _DISPLAY_OVERRIDE_REQUIRED_SUBSTRINGS
    assert FSA_CREDENTIAL_FACT_ID in _DISPLAY_OVERRIDE_REQUIRED_SUBSTRINGS

    # 3. Voice repair canonical sentences and slots
    assert DEPENDENCY_GRAPH_FACT_ID not in _CANONICAL_DISPLAY_SENTENCES
    assert DEPENDENCY_GRAPH_FACT_ID not in _CANONICAL_FACT_SLOT

    # 4. Display override compliance allows natural synthesis without the canned override
    natural_text = (
        "Enterprise technology leader who unifies governed AI platforms. "
        "Through that operating model, Basel III and CCAR data lineage cut regulatory reporting errors by 40%. "
        "Software dependency graph analysis accelerates legacy modernization across complex distributed environments. "
        "That regulatory foundation is grounded in FSA-chartered actuarial work in capital modeling. "
        "Directed large-scale regulatory IT transformations for major financial institutions. "
        "Designs and operates platform runtimes with deterministic controls and traceable execution."
    )
    claim_ledger = [
        {"claim_text": "s1", "source_fact_ids": ["fact_engineering_platform_001"]},
        {"claim_text": "s2", "source_fact_ids": ["fact_governance_003"]},
        {"claim_text": "s3", "source_fact_ids": ["fact_engineering_platform_002"]},
        {"claim_text": "s4", "source_fact_ids": [FSA_CREDENTIAL_FACT_ID]},
        {"claim_text": "s5", "source_fact_ids": ["fact_consulting_001"]},
        {"claim_text": "s6", "source_fact_ids": ["fact_exec_002"]},
    ]
    compliance_ok, compliance_reason = check_exec_summary_display_override_compliance(
        natural_text,
        claim_ledger,
    )
    assert compliance_ok is True, compliance_reason
    assert _CANNED_21_WORD_SENTENCE.lower() not in natural_text.lower()

    # 5. Natural sentence maps to fact_engineering_platform_002
    natural_sent = "Software dependency graph analysis exposes architectural dependency chains."
    fids = _source_fact_ids_for_display_sentence(natural_sent)
    assert "fact_engineering_platform_002" in fids

    # 6. Polish does not force-overwrite natural dependency graph text with canned sentence
    parsed = {
        "resume_display_text": natural_text,
        "claim_ledger": [],
    }
    selected_facts = [
        {"fact_id": "fact_engineering_platform_001", "claim_text": "Agentic AI platform"},
        {"fact_id": "fact_governance_003", "claim_text": "Basel cut errors 40%"},
        {"fact_id": "fact_engineering_platform_002", "claim_text": "Graph intelligence"},
        {"fact_id": FSA_CREDENTIAL_FACT_ID, "claim_text": "FSA work"},
        {"fact_id": "fact_consulting_001", "claim_text": "Consulting"},
        {"fact_id": "fact_exec_002", "claim_text": "Scaled team 8 to 28"},
    ]
    polished, receipt = polish_executive_summary_judge_alignment(
        parsed, selected_facts=selected_facts
    )
    polished_text = str(polished.get("resume_display_text") or "")
    assert _CANNED_21_WORD_SENTENCE.lower() not in polished_text.lower()
    assert "dependency graph" in polished_text.lower()


def test_role_episode_bundle_lineage_no_cross_employer_misattribution() -> None:
    """R1.2: Verify zero cross-employer misattribution between IBM and Unify bundles."""
    repo_root = Path(__file__).resolve().parents[3]
    fact_inv = repo_root / "src" / "apps_rg" / "fact_inventory"

    unify_bundles_path = fact_inv / "unify_role_episode_bundles.json"
    ibm_bundles_path = fact_inv / "ibm_role_episode_bundles.json"

    with open(unify_bundles_path, "r", encoding="utf-8") as f:
        unify_bundles = json.load(f)
    with open(ibm_bundles_path, "r", encoding="utf-8") as f:
        ibm_bundles = json.load(f)

    # 1. Check Unify bundles
    unify_list = unify_bundles.get("bundles") or unify_bundles.get("role_episode_bundles", [])
    unify_map = {b["role_episode_bundle_id"]: b for b in unify_list}
    assert "reb_unify_dependency_graph_accelerator" in unify_map
    dep_bundle = unify_map["reb_unify_dependency_graph_accelerator"]
    assert dep_bundle["linked_source_fact_ids"] == ["fact_engineering_platform_002"]

    assert "reb_unify_distributed_ecosystem_engineering" in unify_map
    dist_bundle = unify_map["reb_unify_distributed_ecosystem_engineering"]
    assert dist_bundle["linked_source_fact_ids"] == ["fact_engineering_platform_005"]

    # 2. Check IBM bundles have ZERO references to fact_engineering_platform_002 or 005
    ibm_reb_list = ibm_bundles.get("bundles") or ibm_bundles.get("role_episode_bundles", [])
    for bundle in ibm_reb_list:
        bundle_id = bundle.get("role_episode_bundle_id", "")
        linked = bundle.get("linked_source_fact_ids", [])
        assert "fact_engineering_platform_002" not in linked, (
            f"IBM bundle {bundle_id} illegally contains Unify fact_engineering_platform_002"
        )
        assert "fact_engineering_platform_005" not in linked, (
            f"IBM bundle {bundle_id} illegally contains Unify fact_engineering_platform_005"
        )

    # Specifically verify the three IBM bundles previously affected
    ibm_map = {b["role_episode_bundle_id"]: b for b in ibm_reb_list}
    for target_id in (
        "reb_ibm_aws_modernization_architecture",
        "reb_ibm_offering_accelerator_management",
        "reb_ibm_devsecops_release_resilience",
    ):
        assert target_id in ibm_map
        assert "fact_engineering_platform_002" not in ibm_map[target_id].get("linked_source_fact_ids", [])


def test_multi_milestone_synthesis_preserves_revenue_metric_and_roots() -> None:
    """R2: Verify combined career milestone sentences preserve both roots and the $22M metric."""
    plan = {
        "allocation_plan_digest": "multi-milestone-digest",
        "facts": [
            {
                "fact_id": "reb_unify_platform_commercialization_leadership",
                "role_episode_bundle_id": "reb_unify_platform_commercialization_leadership",
                "claim_text": "Platform productization generated $22M in IP-led platform revenue and margin expansion.",
                "allowed_graph_evidence_ids": [
                    "reb_unify_platform_commercialization_leadership",
                    "metric_unify_22m_ip_led_revenue",
                ],
            },
            {
                "fact_id": "reb_insurtech_aws_migration_execution",
                "role_episode_bundle_id": "reb_insurtech_aws_migration_execution",
                "claim_text": "Led AWS modernization execution for monolithic policy administration workloads.",
                "allowed_graph_evidence_ids": [
                    "reb_insurtech_aws_migration_execution",
                    "exp_insurtech_001",
                ],
            },
        ],
        "allocation_assignments": [
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_rev_01",
                "root_id": "reb_unify_platform_commercialization_leadership",
                "fact_id": "fact_engineering_platform_006",
                "metric_outcome_id": "metric_unify_22m_ip_led_revenue",
                "metric_value": "22",
                "metric_unit": "USD_M",
                "root_bundle_theme": "Platform productization, IP-led revenue, margin expansion, team scale",
                "root_claim_text": "Platform productization, IP-led revenue, margin expansion, team scale",
                "claim_entailment_score": 0.95,
                "target_alignment_score": 0.95,
            },
            {
                "section_id": "executive_summary",
                "claim_unit_id": "cu_insurtech_02",
                "root_id": "reb_insurtech_aws_migration_execution",
                "fact_id": "exp_insurtech_001",
                "metric_outcome_id": "",
                "metric_value": "",
                "metric_unit": "",
                "root_bundle_theme": "AWS migration execution, wave sequencing, and insurtech platform modernization",
                "root_claim_text": "Led AWS modernization execution for monolithic policy administration workloads",
                "claim_entailment_score": 0.95,
                "target_alignment_score": 0.95,
            },
        ],
    }

    # Combined sentence fusing insurtech migration with $22M platform commercialization
    combined_sentence = (
        "That same platform discipline extended into insurtech core-system migration, moving monolithic "
        "policy administration workloads through classified migration waves while platform productization "
        "generated $22M in IP-led revenue and margin expansion."
    )
    parsed = {
        "resume_display_text": combined_sentence,
        "claim_ledger": [
            {
                "claim_text": combined_sentence,
                "source_fact_ids": [
                    "reb_insurtech_aws_migration_execution",
                    "reb_unify_platform_commercialization_leadership",
                    "metric_unify_22m_ip_led_revenue",
                ],
            }
        ],
        "selected_fact_plan": plan,
    }

    # 1. Causal tie-breaker retains both milestone roots
    repair_exec_summary_causal_multi_root_allocation_rows(parsed)
    row_fids = parsed["claim_ledger"][0]["source_fact_ids"]
    assert "reb_unify_platform_commercialization_leadership" in row_fids
    assert "reb_insurtech_aws_migration_execution" in row_fids
    assert "metric_unify_22m_ip_led_revenue" in row_fids

    # 2. Unallocated metric scrubbing does NOT scrub $22M
    repairs = repair_exec_summary_unallocated_metric_rows(parsed)
    assert repairs == []
    assert "$22M in IP-led revenue" in parsed["resume_display_text"]

    # 3. Perf sync helper preserves $22M when backed by platform commercialization
    candidate_sentence = "Generated $22M in IP-led revenue through reusable platform productization."
    rev_assign = plan["allocation_assignments"][0]
    replaced_sent, root_id, metric_id, _ = resolve_unallocated_metric_sentence_replacement(
        display_sentence=candidate_sentence,
        sentences=[candidate_sentence],
        index=0,
        raw_row={"claim_text": candidate_sentence, "source_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
        selected=[rev_assign],
        chosen=rev_assign,
        rank_fn=lambda a: (1, 1, 1.0, 1.0, "x"),
        extract_sig_fn=lambda s: [],
        tokens_fn=lambda s: set(s.lower().split()),
    )
    assert "$22M in IP-led revenue" in replaced_sent
    assert root_id == "reb_unify_platform_commercialization_leadership"
    assert metric_id == "metric_unify_22m_ip_led_revenue"
    assert "$22M" in replaced_sent

    # 4. Claim binding validator accepts multi-milestone executive summary sentence without causal merge errors
    failures = validate_claim_rows_against_resume_graph_allocation(
        section_id="executive_summary",
        claim_rows=parsed["claim_ledger"],
        selected_fact_plan=plan,
    )
    causal_failures = [f for f in failures if "causal_claim_merges_unrelated_graph_roots" in f]
    assert causal_failures == [], f"Unexpected causal merge failures: {causal_failures}"
    orphan_failures = [f for f in failures if "orphan_" in f]
    assert orphan_failures == [], f"Unexpected orphan failures: {orphan_failures}"
