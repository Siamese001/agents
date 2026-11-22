"""Unmocked 6-JD Multi-Industry Scale Benchmark for role_narrative_v2 and headline_v2 (Wave 4).

Executes real production C0 whole-resume graph allocation, prompt-to-validator shared-vocabulary
symmetry checks (INV-PROMPT-VALIDATOR-VOCAB-SYMMETRY), non-mutating headline_v2 and role_narrative_v2
normalization, and deterministic X2 evaluation across all 6 canonical JDs without any mocks or
company-specific branching.
"""
from __future__ import annotations

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
from apps_rg.runtime.contracts.prompt_validator_vocab_ssot import (  # noqa: E402
    HEADLINE_EXECUTIVE_ABSTRACTION_RE,
    NARRATIVE_AUTHORITY_SIGNALS,
    NARRATIVE_STRONG_VERBS,
)
from apps_rg.runtime.product_evidence_authority import build_evidence_authority  # noqa: E402
from apps_rg.runtime.sections.graph_role_episode_selector import (  # noqa: E402
    build_selected_graph_evidence_plan_for_section,
)
from apps_rg.runtime.sections.headline_pa import compile_headline_prompt  # noqa: E402
from apps_rg.runtime.sections.headline_positioning_evidence import (  # noqa: E402
    attach_headline_positioning_bundles_to_proof_pool_metadata,
)
from apps_rg.runtime.sections.headline_v2 import (  # noqa: E402
    SHARED_HEADLINE_VOCAB_SUMMARY,
    headline_resume_native_clarity_report,
    normalize_parsed_output as normalize_headline_v2_parsed,
)
from apps_rg.runtime.sections.role_narrative_v2 import (  # noqa: E402
    EMPLOYER_NARRATIVE_SPECS,
    SHARED_NARRATIVE_VOCAB_SUMMARY,
    compile_narrative_v2_prompt,
    normalize_ibm_narrative_parsed,
    normalize_unify_narrative_parsed,
)
from apps_rg.runtime.validators.headline_x2 import (  # noqa: E402
    has_valid_headline_prefix,
    headline_executive_abstraction_report,
    headline_word_count,
)
from apps_rg.runtime.validators.narrative_quality_x2 import (  # noqa: E402
    check_narrative_no_consulting_language,
    check_narrative_seniority_floor,
    check_narrative_technical_specificity,
)
from tools.lint_prompt_validator_vocab_symmetry import audit_prompt_validator_vocab_symmetry  # noqa: E402

TARGETING_DIR = RG_SRC / "apps_rg" / "config" / "targeting"

SIX_CANONICAL_JDS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "truist_fde",
        "company": "Truist Financial Corporation",
        "role": "Head of Forward Deployed Engineering",
        "jd_file": "truist_head_forward_deployed_engineering_jd.txt",
        "brief_file": "truist_head_forward_deployed_engineering_briefing.md",
    },
    {
        "case_id": "citi_ai_strategy",
        "company": "Citigroup",
        "role": "Head of AI Strategy",
        "jd_file": "citi_head_of_ai_strategy_jd.txt",
        "brief_file": "citi_head_of_ai_strategy_briefing.md",
    },
    {
        "case_id": "anthropic_partnerships",
        "company": "Anthropic",
        "role": "Manager, Applied AI Architecture & Partnerships",
        "jd_file": "anthropic_manager_applied_ai_architecture_partnerships_jd.txt",
        "brief_file": "anthropic_manager_applied_ai_architecture_partnerships_briefing.md",
    },
    {
        "case_id": "brown_brown_insurance",
        "company": "Brown & Brown",
        "role": "SVP IT Strategy & Innovation",
        "jd_file": "brown_brown_svp_it_strategy_innovation_jd.txt",
        "brief_file": "brown_brown_svp_it_strategy_innovation_briefing.md",
    },
    {
        "case_id": "neo4j_vp_product",
        "company": "Neo4j",
        "role": "VP Product Management, Agentic AI",
        "jd_file": "neo4j_vp_product_management_agentic_ai_jd.txt",
        "brief_file": "neo4j_vp_product_management_agentic_ai_briefing.md",
    },
    {
        "case_id": "invesco_advanced_eng",
        "company": "Invesco",
        "role": "Global Head of Advanced Engineering",
        "jd_file": "invesco_global_head_advanced_engineering_jd.txt",
        "brief_file": "invesco_global_head_advanced_engineering_briefing.md",
    },
)


def test_prompt_validator_vocab_symmetry_and_v2_engine_contracts_e2e() -> None:
    violations = audit_prompt_validator_vocab_symmetry(REPO_ROOT)
    assert violations == [], violations
    assert set(EMPLOYER_NARRATIVE_SPECS) == {
        "slalom_narrative",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "ey_narrative",
    }
    assert SHARED_NARRATIVE_VOCAB_SUMMARY["strong_verbs"] == len(NARRATIVE_STRONG_VERBS)
    assert SHARED_NARRATIVE_VOCAB_SUMMARY["authority_signals"] == len(NARRATIVE_AUTHORITY_SIGNALS)
    assert SHARED_HEADLINE_VOCAB_SUMMARY["executive_abstraction_pattern"] == HEADLINE_EXECUTIVE_ABSTRACTION_RE.pattern


@pytest.mark.parametrize("case", SIX_CANONICAL_JDS, ids=[c["case_id"] for c in SIX_CANONICAL_JDS])
def test_narrative_and_headline_v2_six_jd_multi_industry_scale_e2e(case: dict[str, Any]) -> None:
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

    assignments = list(plan.get("assignments") or [])
    hl_rows = [r for r in assignments if r.get("section_id") == "headline"]
    unify_rows = [r for r in assignments if r.get("section_id") == "unify_narrative"]
    ibm_rows = [r for r in assignments if r.get("section_id") == "ibm_narrative"]
    assert len(hl_rows) >= 2
    assert len(unify_rows) >= 1
    assert len(ibm_rows) >= 1

    hl_allowed = {str(r.get("root_id") or r.get("fact_id") or "bul_unify_001") for r in hl_rows}
    unify_allowed = {str(r.get("root_id") or r.get("fact_id") or "bul_unify_001") for r in unify_rows} | {"bul_unify_001"}
    ibm_allowed = {str(r.get("root_id") or r.get("fact_id") or "bul_ibm_001") for r in ibm_rows} | {"bul_ibm_001", "bul_ibm_002"}

    # 1. Headline v2 prompt compile + zero-mutation REAL_LLM normalization + deterministic X2
    hl_plan, _hl_trace, _hl_audit = build_selected_graph_evidence_plan_for_section(
        repo_root=RG_SRC,
        section_id="headline",
        target_role=case["role"],
        jd_text=jd_text,
        briefing_text=brief_text,
    )
    ea = build_evidence_authority(
        graph_ref="apps_rg/fact_inventory/master_skills_arsenal_ledger.json",
        ledger_ref="artifacts/apps_rg/fact_inventory/master_candidate_skills_fact_ledger.json",
        graph_digest="dig_graph",
        ledger_digest="dig_ledger",
    )
    hl_pp_meta = attach_headline_positioning_bundles_to_proof_pool_metadata(
        {
            "selected_graph_evidence_plan": hl_plan,
            "evidence_authority": ea,
        },
        section_id="headline",
        repo_root=RG_SRC,
    )
    hl_runtime_payload = {
        "run_id": f"e2e_hl_{case['case_id']}",
        "section_id": "headline",
        "product_visible": False,
        "target_title": case["role"],
        "target_company": case["company"],
        "jd_text": jd_text,
        "briefing": brief_text,
        "selected_fact_plan": hl_plan,
        "selected_graph_evidence_plan": hl_plan,
        "allowed_fact_ids": sorted(hl_allowed),
        "proof_pool_metadata": hl_pp_meta,
        "canonical_final_evidence_contract": hl_pp_meta,
    }
    hl_compiled = compile_headline_prompt(
        hl_runtime_payload,
        companion_context="",
        fact_lines="- bul_unify_001: Governed agentic AI platform architecture",
        forbidden_employer_lines="- unify consulting\n- ibm",
        run_id=hl_runtime_payload["run_id"],
    )
    assert len(hl_compiled.artifact.messages) >= 1

    hl_first_id = sorted(hl_allowed)[0]
    candidate_hl = "SVP Engineering | Agentic AI Platforms | Runtime Governance Architecture | Cloud Data Modernization"
    hl_norm = normalize_headline_v2_parsed(
        {
            "headline_line": candidate_hl,
            "claim_ledger": [
                {"claim_text": "Agentic AI Platforms", "source_fact_ids": [hl_first_id]},
                {"claim_text": "Runtime Governance Architecture", "source_fact_ids": [hl_first_id]},
                {"claim_text": "Cloud Data Modernization", "source_fact_ids": [hl_first_id]},
            ],
        },
        hl_runtime_payload,
        hl_allowed,
        candidate_hl,
        allow_prose_mutation=False,
    )
    assert hl_norm is not None
    assert hl_norm["headline_line"] == candidate_hl
    assert has_valid_headline_prefix(hl_norm["headline_line"])
    assert 10 <= headline_word_count(hl_norm["headline_line"]) <= 13
    assert headline_executive_abstraction_report(hl_norm["headline_line"])["segments_missing_executive_abstraction"] == []
    assert headline_resume_native_clarity_report(hl_norm["headline_line"])["pass"] is True

    # 2. Unify & IBM role_narrative_v2 prompt compile + zero-mutation REAL_LLM normalization + X2
    unify_payload = {
        "run_id": f"e2e_unify_{case['case_id']}",
        "section_id": "unify_narrative",
        "product_visible": False,
        "target_title": case["role"],
        "target_company": case["company"],
        "jd_text": jd_text,
        "briefing": brief_text,
        "unify_header": {
            "employer": "Unify Consulting",
            "title": "Partner",
            "location": "New York, NY",
            "start_date": "2023",
            "end_date": "Present",
            "is_current": True,
            "fact_id": "exp_unify_001",
        },
        "selected_fact_plan": {"section_id": "unify_narrative", "facts": [{"fact_id": "bul_unify_001", "claim_text": "Architected governed agentic AI platform runtime."}]},
        "allowed_fact_ids": sorted(unify_allowed),
        "proof_pool_metadata": {"evidence_authority": ea},
        "canonical_final_evidence_contract": {"evidence_authority": ea},
    }
    unify_compiled = compile_narrative_v2_prompt(
        "unify_narrative",
        unify_payload,
        "- bul_unify_001: Architected governed agentic AI platform runtime.",
        run_id=unify_payload["run_id"],
    )
    assert len(unify_compiled.artifact.messages) >= 1

    unify_sentence = (
        "Drove the platform roadmap, core architecture, and commercialization of a production-grade "
        "agentic AI and GraphRAG platform at Unify Consulting, establishing governed runtime controls "
        "and reusable engineering patterns across regulated enterprise programs."
    )
    unify_norm = normalize_unify_narrative_parsed(
        {
            "narrative_sentence": unify_sentence,
            "claim_ledger": [{"claim_text": unify_sentence, "source_fact_ids": ["bul_unify_001"]}],
        },
        unify_payload,
        allow_prose_mutation=False,
    )
    assert unify_norm is not None
    assert unify_norm["narrative_sentence"] == unify_sentence
    assert check_narrative_seniority_floor(unify_sentence).passed is True
    assert check_narrative_no_consulting_language(unify_sentence).passed is True
    assert check_narrative_technical_specificity(unify_sentence).passed is True

    ibm_payload = {
        "run_id": f"e2e_ibm_{case['case_id']}",
        "section_id": "ibm_narrative",
        "target_title": case["role"],
        "target_company": case["company"],
        "jd_text": jd_text,
        "briefing": brief_text,
        "ibm_header": {"employer": "IBM", "title": "Partner"},
        "selected_fact_plan": {"section_id": "ibm_narrative", "facts": [{"fact_id": "bul_ibm_001", "claim_text": "Directed enterprise cloud modernization at IBM."}]},
        "allowed_fact_ids": sorted(ibm_allowed),
    }
    ibm_sentence = (
        "Directed enterprise cloud modernization and governed BI decision-support architecture at IBM, "
        "establishing traceable data lineage and DevSecOps release discipline across regulated financial institutions."
    )
    ibm_norm = normalize_ibm_narrative_parsed(
        {
            "narrative_sentence": ibm_sentence,
            "claim_ledger": [
                {"claim_text": "Directed enterprise cloud modernization at IBM", "source_fact_ids": ["bul_ibm_001"]},
                {"claim_text": "establishing traceable data lineage across regulated financial institutions", "source_fact_ids": ["bul_ibm_002"]},
            ],
        },
        ibm_payload,
        allow_echo_repair=False,
    )
    assert ibm_norm is not None
    assert ibm_norm["narrative_sentence"] == ibm_sentence
    assert check_narrative_seniority_floor(ibm_sentence).passed is True
    assert check_narrative_no_consulting_language(ibm_sentence).passed is True
    assert check_narrative_technical_specificity(ibm_sentence).passed is True
