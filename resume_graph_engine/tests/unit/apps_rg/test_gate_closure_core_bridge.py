"""W2.2: apps_rg gate-closure map exports to core GateClosureMap."""

from __future__ import annotations

from apps_rg.runtime.judges.executive_summary_x1d_gate_closure_map import (
    EXECUTIVE_SUMMARY_GATE_CLOSURE_MAP,
    RECONCILIATION_POLICY_VERSION,
    core_gate_closure_map,
)


def test_core_gate_closure_map_non_empty() -> None:
    cmap = core_gate_closure_map()
    assert len(cmap.rules) == len(EXECUTIVE_SUMMARY_GATE_CLOSURE_MAP)
    assert cmap.version == RECONCILIATION_POLICY_VERSION


def test_core_map_gate_ids_match_ssot() -> None:
    apps_ids = {r.gate_id for r in EXECUTIVE_SUMMARY_GATE_CLOSURE_MAP}
    core_ids = {r.gate_id for r in core_gate_closure_map().rules}
    assert apps_ids == core_ids


def test_cross_section_gate_closures() -> None:
    from apps_rg.runtime.judges.executive_summary_x1d_gate_closure_map import (
        COMPETENCIES_GATE_CLOSURE_MAP,
        HEADLINE_GATE_CLOSURE_MAP,
        SECTION_GATE_CLOSURE_REGISTRY,
        finding_is_contract_invalid_under_gate_closures,
    )

    assert "headline" in SECTION_GATE_CLOSURE_REGISTRY
    assert "competencies" in SECTION_GATE_CLOSURE_REGISTRY
    assert len(HEADLINE_GATE_CLOSURE_MAP) > 0
    assert len(COMPETENCIES_GATE_CLOSURE_MAP) > 0

    # Headline test: word count out of range complaint suppressed when gate passed
    hl_gates = {"x2_headline_self_check_consistent": {"pass": True, "detail": "words=14"}}
    invalid, gate_id, ref = finding_is_contract_invalid_under_gate_closures(
        "Headline rejected because word count out of range",
        hl_gates,
        section_id="headline",
    )
    assert invalid is True
    assert gate_id == "x2_headline_self_check_consistent"

    # Competencies test: unsupported skill keyword suppressed when gate passed
    comp_gates = {"x2_competencies_source_fact_binding": {"pass": True, "detail": "grounded=100%"}}
    invalid, gate_id, ref = finding_is_contract_invalid_under_gate_closures(
        "Unsupported skill keyword found in competency list",
        comp_gates,
        section_id="competencies",
    )
    assert invalid is True
    assert gate_id == "x2_competencies_source_fact_binding"

