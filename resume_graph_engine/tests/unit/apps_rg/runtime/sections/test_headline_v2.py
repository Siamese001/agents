"""Unit tests for greenfield headline_v2 engine (Wave 3)."""
from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.contracts.prompt_validator_vocab_ssot import (
    APPROVED_HEADLINE_SENIORITY_PREFIXES,
    HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS,
    HEADLINE_EXECUTIVE_ABSTRACTION_RE,
    HEADLINE_FORBIDDEN_PLUMBING_LABELS,
)
from apps_rg.runtime.sections.headline_v2 import (
    SHARED_HEADLINE_VOCAB_SUMMARY,
    build_headline_lane_args,
    build_mock_output,
    candidate_3word_subsequences,
    ensure_claim_ledger,
    headline_resume_native_clarity_report,
    normalize_parsed_output,
)


def test_headline_v2_loc_budget_and_shared_vocab_symmetry() -> None:
    pkg_dir = Path(__file__).resolve().parents[5] / "src" / "apps_rg" / "runtime" / "sections" / "headline_v2"
    py_files = sorted(pkg_dir.glob("*.py"))
    assert len(py_files) == 6
    total_loc = 0
    for f in py_files:
        loc = sum(1 for _ in f.open(encoding="utf-8"))
        assert loc <= 600, f"{f.name} exceeded 600 LOC ({loc})"
        total_loc += loc
    assert total_loc <= 1100, f"headline_v2 total LOC {total_loc} exceeded 1,100"
    assert SHARED_HEADLINE_VOCAB_SUMMARY["approved_seniority_prefixes"] == APPROVED_HEADLINE_SENIORITY_PREFIXES
    assert SHARED_HEADLINE_VOCAB_SUMMARY["executive_abstraction_nouns"] == HEADLINE_EXECUTIVE_ABSTRACTION_NOUNS
    assert SHARED_HEADLINE_VOCAB_SUMMARY["executive_abstraction_pattern"] == HEADLINE_EXECUTIVE_ABSTRACTION_RE.pattern
    assert SHARED_HEADLINE_VOCAB_SUMMARY["forbidden_plumbing_labels"] == HEADLINE_FORBIDDEN_PLUMBING_LABELS


def test_headline_v2_enforce_zero_post_llm_prose_mutation_on_real_llm() -> None:
    raw_hl = "SVP Engineering | Governed Runtime Spine | Alliance Co-Sell | Enterprise Partner Enablement"
    doc = {
        "headline_line": raw_hl,
        "claim_ledger": [
            {"claim_text": "Governed Runtime Spine", "source_fact_ids": ["bul_unify_001"]},
            {"claim_text": "Alliance Co-Sell", "source_fact_ids": ["bul_unify_002"]},
            {"claim_text": "Enterprise Partner Enablement", "source_fact_ids": ["bul_unify_003"]},
        ],
    }
    norm = normalize_parsed_output(
        doc,
        {"selected_fact_plan": {"section_id": "headline", "facts": []}},
        {"bul_unify_001", "bul_unify_002", "bul_unify_003"},
        raw_hl,
        allow_prose_mutation=False,
    )
    assert norm is not None
    assert norm["headline_line"] == raw_hl
    assert len(norm["claim_ledger"]) == 3


def test_headline_v2_clarity_and_ledger_segment_coercion() -> None:
    hl = "SVP Engineering | Agentic AI Platforms | Distributed AI Infrastructure | Governed Enterprise Systems"
    report = headline_resume_native_clarity_report(hl)
    assert report["pass"] is True
    assert report["opaque_segments"] == []
    parsed = {"claim_ledger": ["bul_unify_001", "bul_unify_002"]}
    ensure_claim_ledger(hl, parsed, {"bul_unify_001", "bul_unify_002"})
    assert len(parsed["claim_ledger"]) == 3
    mock_out = build_mock_output({"selected_fact_plan": {"section_id": "headline", "facts": []}, "allowed_fact_ids": ["bul_unify_001"]})
    assert mock_out["headline_line"].startswith("SVP Engineering | ")
    assert candidate_3word_subsequences("Three Lines Governance") == ["Regulated Insurance Governance"]
    args = build_headline_lane_args(provider="external_claude", temperature=0.35, x1d_judges="gemini_pro", mock_judges=False, target_title="SVP", target_company="Truist", jd_text="JD", briefing="Brief")
    assert args.provider == "external_claude"
