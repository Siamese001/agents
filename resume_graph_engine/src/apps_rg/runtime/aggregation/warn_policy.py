"""WARN handling policy for cross-section X2 product output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps_rg.runtime.aggregation.cross_section_x2 import (
    VERDICT_FAIL,
    VERDICT_UNKNOWN,
    VERDICT_WARN,
    CrossSectionGateResult,
)

POLICY_SCHEMA = "apps_rg.aggregation_warn_policy.v1"


OVERLAP_FAIL_CLOSED_GATE_IDS: frozenset[str] = frozenset({
    "x2_overlap_engine",
    "x2_cross_section_near_duplicate",
    "x2_cross_section_section_intent_conflict",
    "x2_cross_section_repeated_metric",
    "x2_cross_section_exact_duplicate",
})


def evaluate_warn_policy(*, cross_gates: list[CrossSectionGateResult]) -> dict[str, Any]:
    warn_gates = [g for g in cross_gates if g.verdict == VERDICT_WARN and g.gate_id not in OVERLAP_FAIL_CLOSED_GATE_IDS]
    fail_gates = [
        g for g in cross_gates
        if g.verdict == VERDICT_FAIL or (g.verdict == VERDICT_WARN and g.gate_id in OVERLAP_FAIL_CLOSED_GATE_IDS)
    ]
    unknown_gates = [g for g in cross_gates if g.verdict == VERDICT_UNKNOWN]

    structural_cross_section_pass = not fail_gates and not unknown_gates
    # Warnings remain visible in the evaluation output but are advisory.  A
    # completed run is withheld only for an actual failed or unknown gate.
    product_blocked_by_warn = bool(fail_gates) or bool(unknown_gates)

    return {
        "schema": POLICY_SCHEMA,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rules": {
            "WARN_visible_but_nonblocking_for_product": True,
            "WARN_permitted_for_structural_assembly": structural_cross_section_pass,
            "FAIL_and_UNKNOWN_block_structural_and_product": True,
        },
        "warn_gate_ids": [g.gate_id for g in warn_gates],
        "fail_gate_ids": [g.gate_id for g in fail_gates],
        "unknown_gate_ids": [g.gate_id for g in unknown_gates],
        "structural_cross_section_eligible": structural_cross_section_pass,
        "product_allow_blocked_by_cross_section": product_blocked_by_warn,
    }


def cross_section_structural_pass(cross_gates: list[CrossSectionGateResult]) -> bool:
    """Structural assembly: FAIL/UNKNOWN block; overlap gates also fail-closed on WARN."""
    for g in cross_gates:
        if g.verdict in (VERDICT_FAIL, VERDICT_UNKNOWN):
            return False
        if g.verdict == VERDICT_WARN and g.gate_id in OVERLAP_FAIL_CLOSED_GATE_IDS:
            return False
    return True


def cross_section_product_pass(cross_gates: list[CrossSectionGateResult]) -> bool:
    """Product output requires no failed or unknown cross-section gate; overlap gates never pass on WARN."""
    for g in cross_gates:
        if g.verdict in (VERDICT_FAIL, VERDICT_UNKNOWN):
            return False
        if g.verdict == VERDICT_WARN and g.gate_id in OVERLAP_FAIL_CLOSED_GATE_IDS:
            return False
    return True
