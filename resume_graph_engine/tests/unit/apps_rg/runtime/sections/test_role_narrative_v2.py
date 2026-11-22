"""Bilateral positive and negative-control unit tests for role_narrative_v2."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.sections.role_narrative_v2 import (
    EMPLOYER_NARRATIVE_SPECS,
     SHARED_NARRATIVE_VOCAB_SUMMARY,
    bind_missing_ibm_narrative_theme_citations,
    build_narrative_mock_output,
    companion_bullets_as_list,
    cosine_echo_diagnostic_summary,
    decompose_ibm_narrative_claim_ledger_by_clause,
    enrich_unify_narrative_parsed_for_x2,
    get_employer_narrative_spec,
    normalize_ibm_narrative_parsed,
    normalize_unify_narrative_parsed,
    parse_narrative_model_json,
    pre_judge_failed_gate_ids,
    redact_banned_lexicon_from_attestation_change_log,
    redact_banned_lexicon_from_attestation_metadata,
    sha16,
    shell_jd_alignment,
)


def test_role_narrative_v2_specs_cover_all_five_employers_and_vocab_ssot() -> None:
    assert set(EMPLOYER_NARRATIVE_SPECS.keys()) == {
        "slalom_narrative",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "ey_narrative",
    }
    for sid in EMPLOYER_NARRATIVE_SPECS:
        spec = get_employer_narrative_spec(sid)
        assert spec.section_id == sid
        assert spec.max_words > 0 and spec.max_chars > 0
    assert SHARED_NARRATIVE_VOCAB_SUMMARY["strong_verbs"] >= 30
    assert SHARED_NARRATIVE_VOCAB_SUMMARY["authority_signals"] >= 20
    assert SHARED_NARRATIVE_VOCAB_SUMMARY["consulting_blocklist"] >= 10


def test_role_narrative_v2_zero_post_llm_prose_mutation_on_unify_and_ibm() -> None:
    raw_unify = (
        "Drove enterprise agentic AI platform architecture and GraphRAG runtime governance across Unify Consulting, "
        "scaling reusable delivery capabilities across regulated financial institutions."
    )
    unify_payload = {
        "selected_fact_plan": {"section_id": "unify_narrative", "facts": []},
        "allowed_fact_ids": ["bul_unify_001", "bul_unify_003", "bul_unify_006"],
        "jd_text": "Enterprise AI platform governance",
        "briefing": "Regulated banking modernization",
    }
    norm_u = normalize_unify_narrative_parsed(
        {
            "narrative_sentence": raw_unify,
            "claim_ledger": [{"claim_text": "partial", "source_fact_ids": ["bul_unify__001", "bul_unify_006"]}],
        },
        unify_payload,
        companion_text="- bul_unify_001: Architected agentic AI platform.",
        allow_prose_mutation=False,
    )
    assert norm_u is not None
    assert norm_u["narrative_sentence"] == raw_unify
    assert norm_u["claim_ledger"] == [{"claim_text": raw_unify, "source_fact_ids": ["bul_unify_001", "bul_unify_006"]}]
    assert norm_u["jd_alignment"]["targeting_only"] is True
    assert norm_u["jd_alignment"]["jd_used_as_proof"] is False

    raw_ibm = (
        "Anchored governed decision-support modernization at IBM through traceable data lineage and DevSecOps "
        "release resilience, establishing accountable operating visibility across regulated banking portfolios."
    )
    ibm_companion = (
        "- bul_ibm_001: Architected enterprise NLP and ML decision-support pipelines with data lineage.\n"
        "- bul_ibm_002: Directed enterprise decision-support data models and executive BI views.\n"
        "- bul_ibm_005: Engineered DevSecOps release resilience and automated security guardrails.\n"
    )
    ibm_payload = {
        "selected_fact_plan": {"section_id": "ibm_narrative", "facts": []},
        "allowed_fact_ids": ["bul_ibm_001", "bul_ibm_002", "bul_ibm_005"],
        "proof_pool_metadata": {"claim_evidence_source_type": "augmented_skills_graph"},
    }
    norm_ibm = normalize_ibm_narrative_parsed(
        {
            "narrative_sentence": raw_ibm,
            "claim_ledger": [{"claim_text": raw_ibm, "source_fact_ids": ["bul_ib_001"]}],
            "change_log": [{"operation": "scan", "detail": "checked mocked_runtime_slice and test-only"}],
            "gap_notes": ["checked mocked_runtime_slice"],
        },
        ibm_payload,
        companion_text=ibm_companion,
        allow_echo_repair=False,
    )
    assert norm_ibm is not None
    assert norm_ibm["narrative_sentence"] == raw_ibm
    assert "aws" not in norm_ibm["narrative_sentence"].lower()
    assert len(norm_ibm["claim_ledger"]) >= 2
    assert all(len(r["source_fact_ids"]) <= 2 for r in norm_ibm["claim_ledger"])
    assert "[lexicon-redacted]" in str(norm_ibm["change_log"])
    assert "[lexicon-redacted]" in str(norm_ibm["gap_notes"])


def test_role_narrative_v2_mock_builders_and_diagnostic_helpers() -> None:
    rp_u = {"selected_fact_plan": {"facts": [{"fact_id": "bul_unify_001"}]}, "allowed_fact_ids": ["bul_unify_001"]}
    mock_u = build_narrative_mock_output("unify_narrative", rp_u)
    assert "Unify Consulting" in mock_u["narrative_sentence"]
    mock_ibm = build_narrative_mock_output("ibm_narrative", {"selected_fact_plan": {"facts": []}, "allowed_fact_ids": ["bul_ibm_001", "bul_ibm_002", "bul_ibm_004"]})
    assert "IBM" in mock_ibm["narrative_sentence"]

    parsed, err = parse_narrative_model_json('```json\n{"narrative_sentence": "Owned platform.", "claim_ledger": []}\n```')
    assert err == "" and parsed is not None
    enriched = enrich_unify_narrative_parsed_for_x2(
        parsed,
        coverage={"covered": 1},
        input_payload_hash=sha16("in"),
        allowed_fact_ids={"bul_unify_001"},
    )
    assert enriched is not None and "output_payload_hash" in enriched

    bullets = companion_bullets_as_list("- bul_ibm_001: Architected enterprise NLP and ML decision-support pipelines.")
    diag = cosine_echo_diagnostic_summary("Architected enterprise NLP and ML decision-support pipelines.", bullets)
    assert "max_cosine=" in diag
    failed = pre_judge_failed_gate_ids([
        {"gate_id": "x2_narrative_word_budget", "pass": False},
        {"gate_id": "x2_x1d_required_judges_present", "pass": False},
    ])
    assert failed == ["x2_narrative_word_budget"]
    assert shell_jd_alignment()["targeting_only"] is True
