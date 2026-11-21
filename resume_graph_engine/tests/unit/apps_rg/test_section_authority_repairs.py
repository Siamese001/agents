"""Unit tests for sibling-lane display sanitizers and X2 rigor-critical gate registration."""

from __future__ import annotations

from pathlib import Path

from apps_rg.runtime.sections.executive_summary_v2.x2_invariants import (
    run_executive_summary_v2_x2_gates,
)
from apps_rg.runtime.sections.section_authority_repairs import (
    prune_competencies_rigor_failing_terms,
    sanitize_ibm_narrative_display_text,
)
from apps_rg.runtime.validators.ibm_narrative_x2 import run_ibm_narrative_x2_gates
from tests.unit.apps_rg.section_rigor.lane_registry import spec_for_lane


def test_sanitize_ibm_meta_disclaimer() -> None:
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


def test_prune_low_rigor_competency_terms() -> None:
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


def test_run_x2_gates_includes_rigor_critical_executive_summary_gates(tmp_path: Path) -> None:
    _ = tmp_path
    text = (
        "Enterprise AI and Cloud Architecture Leader with 20+ years scaling regulated transformations across Fortune 500 banking platforms. "
        "Built and led Slalom's 100+ person Cloud and AI practice generating $45M+ in portfolio value across regulated data systems. "
        "Architected multi-agent RAG governance and AWS modernization blueprints for Tier-1 financial institutions, cutting cycle times by 40%."
    )
    gates = run_executive_summary_v2_x2_gates(
        resume_display_text=text,
        claim_ledger=[
            {"claim_text": "s1", "source_fact_ids": ["bul_unify_001"]},
            {"claim_text": "s2", "source_fact_ids": ["bul_unify_001"]},
            {"claim_text": "s3", "source_fact_ids": ["bul_unify_001"]},
        ],
        parsed_output={"resume_display_text": text},
        allowed_fact_ids={"bul_unify_001"},
        verified_numbers=frozenset({"20", "500", "100", "45m", "$45m", "40%"}),
        verified_corpus_lower="20+ years fortune 500 100+ $45m+ 40% slalom aws",
        target_company="Truist",
        jd_text="banking fde",
        x1d_judges=[],
    )
    present = {g["gate_id"] for g in gates}
    crit = spec_for_lane("executive_summary").critical_gates
    c0 = {"x2_c0_metrics_artifact_present", "x2_c0_support_status_gate"}
    missing = sorted(g for g in crit if g not in present and g not in c0)
    assert not missing, f"missing rigor gates in run_executive_summary_v2_x2_gates: {missing}"


def test_run_headline_x2_always_emits_text_claim_coverage_gate() -> None:
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


def test_run_ibm_narrative_x2_includes_meta_disclaimer_gate() -> None:
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


def test_patch_log_stream_resolves_without_name_error(monkeypatch) -> None:
    import sys as _sys
    from apps_rg.runtime.orchestration.patch_run import _patch_log_stream

    monkeypatch.setenv("APPS_RG_WHOLE_RUN_ENVELOPE", "1")
    assert _patch_log_stream() is _sys.stderr
    monkeypatch.delenv("APPS_RG_WHOLE_RUN_ENVELOPE", raising=False)
    assert _patch_log_stream() is _sys.stdout
