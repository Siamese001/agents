"""IBM narrative display contracts: meta-disclaimer ban and clause-level ledger."""

from __future__ import annotations

from apps_rg.runtime.validators.ibm_narrative_x2 import (
    check_ibm_narrative_claim_ledger_clause_decomposition,
    ibm_narrative_mechanism_support_observation,
    ibm_narrative_material_fact_ids_for_sentence,
    run_ibm_narrative_x2_gates,
)
from apps_rg.runtime.validators.resume_narrative_display_x2 import (
    check_ibm_narrative_no_meta_disclaimer_in_display,
)


def test_meta_disclaimer_patterns_fail_display_gate():
    bad_samples = [
        "At IBM, led cloud work without claiming IBM delivered agentic products.",
        "At IBM, led cloud work without asserting IBM shipped agentic platform products.",
        "At IBM, led cloud work, not claiming IBM built agentic platforms.",
        "At IBM, led cloud work, not asserting IBM built agentic platforms.",
        "At IBM, led cloud work and did not claim IBM delivered agentic products.",
        "At IBM, led cloud work and did not assert IBM delivered agentic products.",
    ]
    for sample in bad_samples:
        ok, hits = check_ibm_narrative_no_meta_disclaimer_in_display(sample)
        assert ok is False, sample
        assert hits


def test_clean_narrative_passes_meta_disclaimer_gate():
    good = (
        "At IBM, led enterprise-scale cloud, data, lineage, and observability foundations for regulated "
        "financial services, establishing reliability and governance discipline for governed analytics delivery."
    )
    ok, hits = check_ibm_narrative_no_meta_disclaimer_in_display(good)
    assert ok is True
    assert not hits


def test_clause_decomposition_rejects_career_bridge_and_loose_union():
    narrative = (
        "At IBM, led cloud foundations, establishing discipline that supported later production AI "
        "platform leadership in subsequent roles."
    )
    ledger = [
        {
            "claim_text": narrative,
            "source_fact_ids": ["bul_ibm_001", "bul_ibm_002", "bul_ibm_003", "bul_ibm_004"],
        }
    ]
    ok, detail = check_ibm_narrative_claim_ledger_clause_decomposition(narrative, ledger)
    assert ok is False
    assert detail.get("reason") in {
        "career_bridge_phrase_without_allowed_fact_class",
        "loose_source_fact_id_union",
        "multi_clause_sentence_requires_multiple_ledger_rows",
    }


def test_clause_decomposition_accepts_per_clause_rows():
    narrative = (
        "At IBM, led enterprise-scale cloud, data, lineage, and observability foundations for regulated "
        "financial services, establishing reliability and governance discipline for governed analytics delivery."
    )
    ledger = [
        {
            "claim_text": (
                "At IBM, led enterprise-scale cloud, data, lineage, and observability foundations "
                "for regulated financial services"
            ),
            "source_fact_ids": ["bul_ibm_001", "bul_ibm_004"],
        },
        {
            "claim_text": "establishing reliability and governance discipline for governed analytics delivery",
            "source_fact_ids": ["bul_ibm_003"],
        },
    ]
    ok, detail = check_ibm_narrative_claim_ledger_clause_decomposition(narrative, ledger)
    assert ok is True
    assert detail.get("reason") == "ok"


def test_x2_gate_ids_include_meta_disclaimer_and_clause_decomposition():
    gates = run_ibm_narrative_x2_gates(
        narrative_sentence=(
            "At IBM, led enterprise-scale cloud, data, lineage, and observability foundations for regulated "
            "financial services, establishing reliability and governance discipline for governed analytics delivery."
        ),
        parsed_output={},
        claim_ledger=[
            {
                "claim_text": (
                    "At IBM, led enterprise-scale cloud, data, lineage, and observability foundations "
                    "for regulated financial services"
                ),
                "source_fact_ids": ["bul_ibm_001", "bul_ibm_004"],
            },
            {
                "claim_text": "establishing reliability and governance discipline for governed analytics delivery",
                "source_fact_ids": ["bul_ibm_003"],
            },
        ],
        jd_text="",
        runtime_generation_status="MOCKED",
        companion_bullet_texts="",
        companion_bullets_status="MISSING",
        companion_aware=False,
    )
    gate_ids = {g.gate_id for g in gates}
    assert "x2_ibm_narrative_no_meta_disclaimer_in_display" in gate_ids
    assert "x2_ibm_narrative_claim_ledger_clause_decomposition" in gate_ids
    assert "x2_ibm_narrative_requires_finalized_bullets" in gate_ids


def test_dynamic_companion_blocks_mechanism_absent_from_cited_bullets():
    narrative = (
        "Drove microservices modernization for regulated clients at IBM, establishing governed "
        "delivery discipline for repeatable enterprise programs."
    )
    ledger = [
        {
            "claim_text": narrative,
            "source_fact_ids": ["bul_ibm_001", "bul_ibm_002"],
        }
    ]
    companion = (
        "- bul_ibm_001: Led IBM-AWS alliance co-sell motions for financial-services pursuits.\n"
        "- bul_ibm_002: Built decision-support data models and BI views."
    )
    gates = run_ibm_narrative_x2_gates(
        narrative_sentence=narrative,
        parsed_output={"narrative_sentence": narrative, "claim_ledger": ledger},
        claim_ledger=ledger,
        jd_text="",
        runtime_generation_status="REAL_LLM",
        companion_bullet_texts=companion,
        companion_bullets_status="ACCEPTED_FINALIZED",
        provider_requested="external_openai",
        provider_attempted="external_openai",
        raw_output="{}",
        x1d_judges=[],
        allowed_fact_ids=["bul_ibm_001", "bul_ibm_002"],
    )
    by_id = {gate.gate_id: gate for gate in gates}
    assert (
        by_id[
            "x2_ibm_narrative_mechanisms_supported_by_cited_companion_bullets"
        ].pass_
        is False
    )
    assert "microservices" in by_id[
        "x2_ibm_narrative_mechanisms_supported_by_cited_companion_bullets"
    ].observed_value["unsupported_mechanisms"]


def test_dynamic_companion_accepts_mechanism_from_cited_bullet():
    narrative = (
        "Drove AWS alliance execution for regulated clients at IBM, establishing governed "
        "delivery discipline for repeatable enterprise programs."
    )
    ledger = [{"claim_text": narrative, "source_fact_ids": ["bul_ibm_001"]}]
    companion = "- bul_ibm_001: Led IBM-AWS alliance co-sell motions for financial-services pursuits."
    gates = run_ibm_narrative_x2_gates(
        narrative_sentence=narrative,
        parsed_output={"narrative_sentence": narrative, "claim_ledger": ledger},
        claim_ledger=ledger,
        jd_text="",
        runtime_generation_status="REAL_LLM",
        companion_bullet_texts=companion,
        companion_bullets_status="ACCEPTED_FINALIZED",
        provider_requested="external_openai",
        provider_attempted="external_openai",
        raw_output="{}",
        x1d_judges=[],
        allowed_fact_ids=["bul_ibm_001"],
    )
    by_id = {gate.gate_id: gate for gate in gates}
    assert by_id[
        "x2_ibm_narrative_mechanisms_supported_by_cited_companion_bullets"
    ].pass_ is True


def test_dynamic_theme_mapping_resolves_partnership_through_alliance_synonym():
    companion = (
        "- bul_ibm_001: Led IBM-AWS alliance co-sell motions for financial-services pursuits.\n"
        "- bul_ibm_005: Led technical discovery and solution mapping for enterprise pursuits."
    )

    themes = ibm_narrative_material_fact_ids_for_sentence(
        "Championed AWS partnership execution at IBM.",
        companion,
    )

    assert "bul_ibm_001" in themes
    assert not any(value.startswith("unsupported_companion_theme:") for value in themes)


def test_mechanism_support_observation_maps_pipeline_to_its_actual_bullet() -> None:
    companion = (
        "- bul_ibm_001: Led IBM-AWS alliance co-sell motions.\n"
        "- bul_ibm_002: Built decision-support BI views.\n"
        "- bul_ibm_004: Owned pipeline governance across enterprise pursuits."
    )
    observation = ibm_narrative_mechanism_support_observation(
        "Drove AWS and BI work at IBM, establishing pipeline discipline.",
        [
            {
                "claim_text": "AWS and BI work",
                "source_fact_ids": ["bul_ibm_001", "bul_ibm_002"],
            }
        ],
        companion,
    )

    assert observation["support_by_mechanism"] == {
        "aws": ["bul_ibm_001"],
        "bi": ["bul_ibm_002"],
        "pipeline": ["bul_ibm_004"],
    }
    assert observation["unsupported_mechanisms"] == ["pipeline"]


def test_dynamic_theme_mapping_uses_one_current_support_root_per_phrase():
    companion = (
        "- bul_ibm_001: Led IBM-AWS alliance co-sell motions for financial-services modernization.\n"
        "- bul_ibm_002: Connected modernization programs to executive decisions.\n"
        "- bul_ibm_003: Mapped enterprise financial-services pursuits.\n"
        "- bul_ibm_005: Built financial-services modernization reference architectures."
    )

    detected = ibm_narrative_material_fact_ids_for_sentence(
        "Led financial-services modernization and alliance execution at IBM.",
        companion,
    )

    assert detected == frozenset({"bul_ibm_001", "bul_ibm_002"})


def test_dynamic_theme_mapping_marks_phrase_absent_from_current_companion():
    companion = "- bul_ibm_001: Led IBM-AWS alliance co-sell motions."

    detected = ibm_narrative_material_fact_ids_for_sentence(
        "Led regulated financial programs at IBM.",
        companion,
    )

    assert "unsupported_companion_theme:regulated_financial" in detected
