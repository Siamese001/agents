"""Structured gate-closure map for executive-summary X1D reconcile (SSOT).

String fragments are compatibility shims; stable finding codes are authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RECONCILIATION_POLICY_VERSION = "executive_summary_gate_closure_v2"


@dataclass(frozen=True)
class GateClosureRecord:
    gate_id: str
    closed_axis: str
    forbidden_finding_codes: tuple[str, ...]
    allowed_residual_finding_codes: tuple[str, ...]
    fragment_shims: tuple[str, ...]
    required_gate_status: str = "pass"
    evidence_ref_required: bool = True


# Residual quality dimensions — never suppressed by gate-closure reconcile.
RESIDUAL_QUALITY_FINDING_CODES: frozenset[str] = frozenset(
    {
        "residual_executive_clarity",
        "residual_narrative_coherence",
        "residual_commercial_fit",
        "residual_unsupported_phrasing",
        "residual_weak_synthesis",
    }
)

RESIDUAL_QUALITY_FRAGMENT_SHIMS: tuple[tuple[str, str], ...] = (
    ("residual_executive_clarity", "unclear executive positioning"),
    ("residual_executive_clarity", "executive positioning is unclear"),
    ("residual_narrative_coherence", "weak narrative coherence"),
    ("residual_narrative_coherence", "narrative coherence is weak"),
    ("residual_commercial_fit", "poor commercial fit"),
    ("residual_commercial_fit", "weak commercial fit"),
    ("residual_unsupported_phrasing", "unsupported phrasing"),
    ("residual_weak_synthesis", "weak synthesis"),
)


EXECUTIVE_SUMMARY_GATE_CLOSURE_MAP: tuple[GateClosureRecord, ...] = (
    GateClosureRecord(
        gate_id="x2_exec_summary_no_credential_dump",
        closed_axis="credential_metric_inventory",
        forbidden_finding_codes=(
            "credential_metric_stack_despite_gate_pass",
            "credential_inventory_despite_gate_pass",
        ),
        allowed_residual_finding_codes=("residual_executive_clarity", "residual_weak_synthesis"),
        fragment_shims=(
            "metric/credential stack",
            "credential inventory despite passing the deterministic gate",
            "credential inventory despite passing",
            "credential/certification inventory",
            "credential dump",
        ),
    ),
    GateClosureRecord(
        gate_id="x2_exec_summary_evidence_utilization",
        closed_axis="evidence_utilization",
        forbidden_finding_codes=(
            "unused_facts_penalty_despite_util_gate_pass",
            "penalize under-use when util gate passed",
        ),
        allowed_residual_finding_codes=("residual_weak_synthesis",),
        fragment_shims=(
            "penalize under-use",
            "unused_fact_ids",
            "under-use of allowed_fact_packet",
        ),
    ),
    GateClosureRecord(
        gate_id="x2_exec_summary_no_mechanism_inventory",
        closed_axis="mechanism_inventory",
        forbidden_finding_codes=("mechanism_inventory_despite_gate_pass",),
        allowed_residual_finding_codes=(),
        fragment_shims=(
            "mechanism inventory",
            "comma-chain architecture dump",
        ),
    ),
    GateClosureRecord(
        gate_id="x2_exec_summary_sentence_count_6",
        closed_axis="sentence_count",
        forbidden_finding_codes=("sentence_count_penalty_despite_gate_pass",),
        allowed_residual_finding_codes=(),
        fragment_shims=(
            "fewer than six sentences",
            "sentence count",
        ),
    ),
    GateClosureRecord(
        gate_id="x2_executive_summary_judge_packet_display_override_parity",
        closed_axis="display_override_substrate_authority",
        forbidden_finding_codes=(
            "display_override_phrase_flagged_as_unsupported",
            "display_override_phrase_flagged_as_inferential_stretch",
            "fsa_chartered_extends_beyond_fact_scope",
        ),
        allowed_residual_finding_codes=("residual_executive_clarity",),
        fragment_shims=(
            "fsa-chartered actuarial work",
            "informing data governance and ai strategy",
            "extends beyond fact_quant_hpc_003",
            "extends beyond fact_engineering_platform_002",
            "over-extends fact_quant_hpc_003",
            "not directly supported by that fact",
            "mild inferential stretch",
            "transformation visibility across enterprise complexity",
            "the fact does not explicitly state fsa",
            "fact does not explicitly contain",
        ),
    ),
)


HEADLINE_GATE_CLOSURE_MAP: tuple[GateClosureRecord, ...] = (
    GateClosureRecord(
        gate_id="x2_headline_fixed_prefix",
        closed_axis="fixed_prefix",
        forbidden_finding_codes=(
            "fixed_prefix_missing_despite_gate_pass",
            "missing_svp_prefix_despite_gate_pass",
        ),
        allowed_residual_finding_codes=("residual_executive_clarity",),
        fragment_shims=(
            "does not start with svp",
            "missing svp engineering prefix",
            "fixed prefix missing",
            "must start with svp",
        ),
    ),
    GateClosureRecord(
        gate_id="x2_headline_executive_length",
        closed_axis="headline_length",
        forbidden_finding_codes=("headline_length_penalty_despite_gate_pass",),
        allowed_residual_finding_codes=(),
        fragment_shims=(
            "headline too long",
            "exceeds maximum characters",
            "headline character length",
        ),
    ),
    GateClosureRecord(
        gate_id="x2_headline_self_check_consistent",
        closed_axis="headline_structure_self_check",
        forbidden_finding_codes=("headline_structure_penalty_despite_gate_pass",),
        allowed_residual_finding_codes=("residual_executive_clarity",),
        fragment_shims=(
            "fewer than four segments",
            "pipe separator count",
            "segment count is not 4",
            "word count out of range",
            "separator count",
        ),
    ),
    GateClosureRecord(
        gate_id="x2_headline_no_title_inflation",
        closed_axis="title_inflation",
        forbidden_finding_codes=("title_inflation_penalty_despite_gate_pass",),
        allowed_residual_finding_codes=(),
        fragment_shims=(
            "title inflation at target",
            "claims target title directly",
            "target title inflation",
        ),
    ),
)


COMPETENCIES_GATE_CLOSURE_MAP: tuple[GateClosureRecord, ...] = (
    GateClosureRecord(
        gate_id="x2_competencies_source_fact_binding",
        closed_axis="competencies_grounding",
        forbidden_finding_codes=("competency_ungrounded_despite_gate_pass",),
        allowed_residual_finding_codes=("residual_commercial_fit",),
        fragment_shims=(
            "competency not in allowed facts",
            "unsupported skill keyword",
        ),
    ),
)


SECTION_GATE_CLOSURE_REGISTRY: dict[str, tuple[GateClosureRecord, ...]] = {
    "executive_summary": EXECUTIVE_SUMMARY_GATE_CLOSURE_MAP,
    "headline": HEADLINE_GATE_CLOSURE_MAP,
    "competencies": COMPETENCIES_GATE_CLOSURE_MAP,
}


def _gate_pass_with_evidence(
    gate_id: str,
    deterministic_gate_summary: dict[str, Any],
) -> tuple[bool, str | None]:
    entry = deterministic_gate_summary.get(gate_id)
    if not isinstance(entry, dict):
        return False, None
    if not entry.get("pass"):
        return False, None
    detail = str(entry.get("detail") or "ok")
    return True, f"deterministic_gate_summary.{gate_id}.pass=true detail={detail!r}"


def classify_finding_code(
    finding_text: str,
    section_id: str | None = None,
) -> str | None:
    """Map finding prose to a stable code (forbidden or residual)."""
    blob = str(finding_text or "").strip().lower()
    if not blob:
        return None
    for code, fragment in RESIDUAL_QUALITY_FRAGMENT_SHIMS:
        if fragment in blob:
            return code
    closure_maps: list[tuple[GateClosureRecord, ...]]
    if section_id and section_id in SECTION_GATE_CLOSURE_REGISTRY:
        closure_maps = [SECTION_GATE_CLOSURE_REGISTRY[section_id]]
    else:
        closure_maps = list(SECTION_GATE_CLOSURE_REGISTRY.values())
    for cmap in closure_maps:
        for record in cmap:
            for fragment in record.fragment_shims:
                if fragment.lower() in blob:
                    return record.forbidden_finding_codes[0]
    return None


def finding_is_contract_invalid_under_gate_closures(
    finding_text: str,
    deterministic_gate_summary: dict[str, Any],
    section_id: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """Return (invalid, suppressing_gate_id, evidence_ref) when finding may be suppressed."""
    code = classify_finding_code(finding_text, section_id=section_id)
    if code is None:
        return False, None, None
    if code in RESIDUAL_QUALITY_FINDING_CODES:
        return False, None, None
    closure_maps: list[tuple[GateClosureRecord, ...]]
    if section_id and section_id in SECTION_GATE_CLOSURE_REGISTRY:
        closure_maps = [SECTION_GATE_CLOSURE_REGISTRY[section_id]]
    else:
        closure_maps = list(SECTION_GATE_CLOSURE_REGISTRY.values())
    for cmap in closure_maps:
        for record in cmap:
            if code not in record.forbidden_finding_codes:
                continue
            ok, evidence_ref = _gate_pass_with_evidence(record.gate_id, deterministic_gate_summary)
            if ok:
                return True, record.gate_id, evidence_ref
    return False, None, None


def core_gate_closure_map():
    """Export apps_rg closure map in the panel harness shape."""
    from apps_rg.runtime.judges.x1d_panel_harness import (
        GateClosureMap,
        GateClosureRule,
    )

    rules = tuple(
        GateClosureRule(
            gate_id=record.gate_id,
            forbidden_finding_codes=frozenset(record.forbidden_finding_codes),
        )
        for record in EXECUTIVE_SUMMARY_GATE_CLOSURE_MAP
    )
    return GateClosureMap(rules=rules, version=RECONCILIATION_POLICY_VERSION)


__all__ = [
    "COMPETENCIES_GATE_CLOSURE_MAP",
    "EXECUTIVE_SUMMARY_GATE_CLOSURE_MAP",
    "GateClosureRecord",
    "HEADLINE_GATE_CLOSURE_MAP",
    "RECONCILIATION_POLICY_VERSION",
    "RESIDUAL_QUALITY_FINDING_CODES",
    "SECTION_GATE_CLOSURE_REGISTRY",
    "classify_finding_code",
    "core_gate_closure_map",
    "finding_is_contract_invalid_under_gate_closures",
]

