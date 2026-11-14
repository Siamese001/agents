"""Modular cross-section X2 aggregation package."""

from __future__ import annotations

from apps_rg.runtime.aggregation.cross_section.gate_runner import run_cross_section_x2_gates
from apps_rg.runtime.aggregation.cross_section.graph_coherence import (
    build_cross_section_graph_coherence_receipt,
    check_cross_section_graph_coherence,
    check_cross_section_pillar_coherence,
)
from apps_rg.runtime.aggregation.cross_section.models import (
    APP_X2_QUALITY_AUTHORITY_SCOPE,
    EM_DASH,
    GRAPH_COHERENCE_MIN_ACTIVE_SECTIONS,
    GRAPH_COHERENCE_MIN_UNIQUE_SKILLS,
    METRIC_PATTERN,
    SECTION_PRIORITY,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    VERDICT_WARN,
    CrossSectionGateResult,
)
from apps_rg.runtime.aggregation.cross_section.overlap_and_reports import (
    all_claims_empty,
    build_cross_section_warn_resolution_report,
    build_overlap_artifacts,
    cross_section_fail_gate_ids,
    cross_section_gates_all_pass,
)

__all__ = [
    "APP_X2_QUALITY_AUTHORITY_SCOPE",
    "CrossSectionGateResult",
    "EM_DASH",
    "GRAPH_COHERENCE_MIN_ACTIVE_SECTIONS",
    "GRAPH_COHERENCE_MIN_UNIQUE_SKILLS",
    "METRIC_PATTERN",
    "SECTION_PRIORITY",
    "VERDICT_FAIL",
    "VERDICT_PASS",
    "VERDICT_UNKNOWN",
    "VERDICT_WARN",
    "all_claims_empty",
    "build_cross_section_graph_coherence_receipt",
    "build_cross_section_warn_resolution_report",
    "build_overlap_artifacts",
    "check_cross_section_graph_coherence",
    "check_cross_section_pillar_coherence",
    "cross_section_fail_gate_ids",
    "cross_section_gates_all_pass",
    "run_cross_section_x2_gates",
]
