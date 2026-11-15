"""Submodules for IBM employment bullet deterministic X2 gates."""
from __future__ import annotations

from apps_rg.runtime.validators.ibm_x2.constants import (
    CORE_METRIC_TOKENS,
    IBM_BULLET_GRAPH_SKILL_NODE_IDS_GATE_ID,
    IBM_BULLET_IDS,
    IBM_BULLET_METRIC_SOURCE_GATE_ID,
    IBM_METRIC_ANCHOR_RULES,
    REQUIRED_TOP_LEVEL,
    TAXONOMY_LABEL_PREFIX_PATTERN,
    TEXT_COVERAGE_INTEGRITY_GATE_ID,
    UNIFY_RUNTIME_TERM_PATTERNS,
    X2GateResult,
    _COVERAGE_WS_RE,
    _SEMANTIC_OVERLAP_STOPWORDS,
    _SEMANTIC_OVERLAP_TOKEN_RE,
    semantic_overlap_tokens,
)
from apps_rg.runtime.validators.ibm_x2.coverage_checks import (
    _all_source_fact_ids,
    _ibm_root_from_source_fact_ids,
    _norm_claim_ws,
    build_ibm_bullets_text_claim_coverage,
    check_ibm_bullets_text_claim_coverage_integrity,
)
from apps_rg.runtime.validators.ibm_x2.metric_and_overlap_checks import (
    _combined_bullet_text,
    _ibm_metric_anchors_on_assigned_bullets,
    _metric_granularity_ok,
    _taxonomy_prefix_violations,
    ibm_bullet_text_has_taxonomy_label_prefix,
    ibm_cross_bullet_semantic_overlap_violations,
)

__all__ = [
    "CORE_METRIC_TOKENS",
    "IBM_BULLET_GRAPH_SKILL_NODE_IDS_GATE_ID",
    "IBM_BULLET_IDS",
    "IBM_BULLET_METRIC_SOURCE_GATE_ID",
    "IBM_METRIC_ANCHOR_RULES",
    "REQUIRED_TOP_LEVEL",
    "TAXONOMY_LABEL_PREFIX_PATTERN",
    "TEXT_COVERAGE_INTEGRITY_GATE_ID",
    "UNIFY_RUNTIME_TERM_PATTERNS",
    "X2GateResult",
    "_COVERAGE_WS_RE",
    "_SEMANTIC_OVERLAP_STOPWORDS",
    "_SEMANTIC_OVERLAP_TOKEN_RE",
    "_all_source_fact_ids",
    "_combined_bullet_text",
    "_ibm_metric_anchors_on_assigned_bullets",
    "_ibm_root_from_source_fact_ids",
    "_metric_granularity_ok",
    "_norm_claim_ws",
    "_taxonomy_prefix_violations",
    "build_ibm_bullets_text_claim_coverage",
    "check_ibm_bullets_text_claim_coverage_integrity",
    "ibm_bullet_text_has_taxonomy_label_prefix",
    "ibm_cross_bullet_semantic_overlap_violations",
    "semantic_overlap_tokens",
]
