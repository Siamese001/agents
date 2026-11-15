"""Submodules for Unify bullets deterministic X2 gates."""
from __future__ import annotations

from apps_rg.runtime.validators.unify_x2.anchor_and_role_checks import (
    _combined_bullet_text,
    _mechanism_dense_bullet_ids,
    _mechanism_term_hits_in_text,
    _role_episode_metric_contract_active,
    _unify_metric_anchors_on_assigned_bullets,
)
from apps_rg.runtime.validators.unify_x2.constants import (
    FORBIDDEN_FACT_PREFIXES,
    METRIC_ANCHOR_BULLET_004,
    PROTECTED_BULLET_DEFAULT,
    REQUIRED_TOP_LEVEL,
    TEXT_COVERAGE_INTEGRITY_GATE_ID,
    UNIFY_BULLET_IDS,
    UNIFY_MECHANISM_STACK_TERMS,
    UNIFY_METRIC_ANCHOR_RULES,
    UNIFY_ROLE_EPISODE_GRAPH_GRANULARITY_GATE_ID,
    UNIFY_ROLE_EPISODE_GRAPH_TRAVERSAL_GATE_ID,
    UNIFY_ROLE_EPISODE_METRIC_DISTRIBUTION_GATE_ID,
    UNIFY_ROLE_EPISODE_METRIC_LINEAGE_GATE_ID,
    UNIFY_ROLE_EPISODE_METRIC_VISIBLE_GATE_ID,
    X2GateResult,
    _COVERAGE_WS_RE,
    _metric_raw_values,
)
from apps_rg.runtime.validators.unify_x2.coverage_checks import (
    _all_source_fact_ids,
    _norm_claim_ws,
    _unify_root_from_source_fact_ids,
    build_unify_bullets_text_claim_coverage,
    check_unify_bullets_text_claim_coverage_integrity,
)

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
    "_all_source_fact_ids",
    "_combined_bullet_text",
    "_mechanism_dense_bullet_ids",
    "_mechanism_term_hits_in_text",
    "_metric_raw_values",
    "_norm_claim_ws",
    "_role_episode_metric_contract_active",
    "_unify_metric_anchors_on_assigned_bullets",
    "_unify_root_from_source_fact_ids",
    "build_unify_bullets_text_claim_coverage",
    "check_unify_bullets_text_claim_coverage_integrity",
]
