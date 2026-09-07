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


def evaluate_warn_policy(*, cross_gates: list[CrossSectionGateResult]) -> dict[str, Any]:
    warn_gates = [g for g in cross_gates if g.verdict == VERDICT_WARN]
    fail_gates = [g for g in cross_gates if g.verdict == VERDICT_FAIL]
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
    """Structural assembly: FAIL/UNKNOWN block; WARN does not block."""
    for g in cross_gates:
        if g.verdict in (VERDICT_FAIL, VERDICT_UNKNOWN):
            return False
    return True


def cross_section_product_pass(cross_gates: list[CrossSectionGateResult]) -> bool:
    """Product output requires no failed or unknown cross-section gate."""
    for g in cross_gates:
        if g.verdict in (VERDICT_FAIL, VERDICT_UNKNOWN):
            return False
    return True
