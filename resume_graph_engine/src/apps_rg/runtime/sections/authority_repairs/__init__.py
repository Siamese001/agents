"""Decomposed deterministic section display authority repair modules."""
from __future__ import annotations

from .causal_allocation import (
    _compact_source_fact_ids_for_sentence,
    _source_fact_relevance_score,
    repair_exec_summary_causal_multi_metric_rows,
    repair_exec_summary_causal_multi_root_allocation_rows,
    repair_exec_summary_cross_fact_conflation_rows,
    repair_exec_summary_unallocated_metric_rows,
)
from .citation_and_mechanism import (
    _MECHANISM_INVENTORY_REWRITES,
    _brushstroke_required_groups,
    _expand_short_exec_summary_sentence,
    _normalize_mechanism_repair_text,
    _repair_mechanism_inventory_sentence,
    repair_exec_summary_mechanism_inventory_sentences,
    repair_exec_summary_thin_sentence_weave,
    repair_required_brushstroke_citations_from_materialized_sentences,
)
from .credential_and_shape import (
    _CITATION_REPAIR_STOPWORDS,
    _SOURCE_FACT_TOKEN_STOPWORDS,
    _TOKEN_RE,
    _citation_repair_tokens,
    _exec_summary_shape_ok,
    _fact_support_text,
    _first_sentence_of_claim,
    _sentence_fails_credential_dump,
    repair_exec_summary_orphan_rows_with_unused_required_facts,
    strip_exec_summary_credential_dump_sentences,
    strip_target_company_tailoring_sentences,
)
from .display_orchestrator import apply_exec_summary_display_authority_repairs
from .section_sanitizers import (
    _IBM_CAREER_BRIDGE_RE,
    _IBM_META_TAIL_RE,
    prune_competencies_rigor_failing_terms,
    sanitize_ibm_narrative_display_text,
)

__all__ = [
    "apply_exec_summary_display_authority_repairs",
    "prune_competencies_rigor_failing_terms",
    "repair_exec_summary_causal_multi_metric_rows",
    "repair_exec_summary_causal_multi_root_allocation_rows",
    "repair_exec_summary_cross_fact_conflation_rows",
    "repair_exec_summary_mechanism_inventory_sentences",
    "repair_exec_summary_orphan_rows_with_unused_required_facts",
    "repair_exec_summary_thin_sentence_weave",
    "repair_exec_summary_unallocated_metric_rows",
    "repair_required_brushstroke_citations_from_materialized_sentences",
    "sanitize_ibm_narrative_display_text",
    "strip_exec_summary_credential_dump_sentences",
    "strip_target_company_tailoring_sentences",
]
