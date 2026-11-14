"""Constants, lexical primitives, and gate result model for Unify bullets X2 gates."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from apps_rg.runtime.contracts.metric_lexical_primitives import (
    COVERAGE_WS_RE as _COVERAGE_WS_RE,
    unify_metric_raw_values as _metric_raw_values,
)

TEXT_COVERAGE_INTEGRITY_GATE_ID = "x2_text_claim_coverage_integrity"

UNIFY_BULLET_IDS = (
    "bul_unify_001",
    "bul_unify_002",
    "bul_unify_003",
    "bul_unify_004",
    "bul_unify_005",
    "bul_unify_006",
)
PROTECTED_BULLET_DEFAULT = "bul_unify_006"
METRIC_ANCHOR_BULLET_004 = "bul_unify_004"
UNIFY_ROLE_EPISODE_METRIC_LINEAGE_GATE_ID = "x2_unify_each_bullet_approved_metric_outcome_lineage"
UNIFY_ROLE_EPISODE_METRIC_VISIBLE_GATE_ID = "x2_unify_each_bullet_metric_outcome_surface_visible"
UNIFY_ROLE_EPISODE_METRIC_DISTRIBUTION_GATE_ID = "x2_unify_metric_outcomes_distributed_by_slot"
UNIFY_ROLE_EPISODE_GRAPH_TRAVERSAL_GATE_ID = "x2_unify_graph_traversal_sufficiency"
UNIFY_ROLE_EPISODE_GRAPH_GRANULARITY_GATE_ID = "x2_unify_graph_granularity_gates"
FORBIDDEN_FACT_PREFIXES = (
    "bul_ibm_",
    "bul_insurtech_",
    "bul_ey_",
    "exp_ibm_",
    "exp_insurtech_",
    "exp_ey_",
)

# Mechanism stack vocabulary (narrative anti-pattern; at most one bullet may be mechanism-dense).
UNIFY_MECHANISM_STACK_TERMS: tuple[str, ...] = (
    "deterministic routing",
    "multi-agent orchestration",
    "graphrag",
    "sandboxed execution",
    "policy gating",
    "validation controls",
    "replayable execution traces",
    "replayable traces",
)

# Metric ownership: REQUIRED_ANCHOR on canonical bullet; SUPPRESS_IF_DUPLICATIVE applies to narrative lane.
UNIFY_METRIC_ANCHOR_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("six months", "three weeks"), "bul_unify_004"),
    (("$22m", "$22 m"), "bul_unify_006"),
    (("20%", "20 %"), "bul_unify_006"),
    (("8", "28"), "bul_unify_006"),
)

REQUIRED_TOP_LEVEL = {
    "bullets",
    "selected_fact_plan",
    "claim_ledger",
    "jd_alignment",
    "gap_notes",
    "change_log",
    "self_check",
}


@dataclass
class X2GateResult:
    """Deterministic X2 gate outcome row."""

    gate_id: str
    gate_type: str
    pass_: bool
    observed_value: Any
    threshold: Any
    failure_reason: str | None
    evidence_ref: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize gate outcome using JSON key ``pass``."""
        data = asdict(self)
        data["pass"] = data.pop("pass_")
        return data


__all__ = [
    "FORBIDDEN_FACT_PREFIXES",
    "METRIC_ANCHOR_BULLET_004",
    "PROTECTED_BULLET_DEFAULT",
    "REQUIRED_TOP_LEVEL",
    "TEXT_COVERAGE_INTEGRITY_GATE_ID",
    "UNIFY_BULLET_IDS",
    "UNIFY_MECHANISM_STACK_TERMS",
    "UNIFY_METRIC_ANCHOR_RULES",
    "UNIFY_ROLE_EPISODE_GRAPH_GRANULARITY_GATE_ID",
    "UNIFY_ROLE_EPISODE_GRAPH_TRAVERSAL_GATE_ID",
    "UNIFY_ROLE_EPISODE_METRIC_DISTRIBUTION_GATE_ID",
    "UNIFY_ROLE_EPISODE_METRIC_LINEAGE_GATE_ID",
    "UNIFY_ROLE_EPISODE_METRIC_VISIBLE_GATE_ID",
    "X2GateResult",
    "_COVERAGE_WS_RE",
    "_metric_raw_values",
]
