"""Mandatory apps_rg run outputs.

Every apps_rg run must leave numbered human-facing artifacts:

* ``01_BCG_executive_output.md`` - decision-oriented RCA and implementation plan.
* ``02_output_bisect.md`` - prior-pass/current-failure attempt, gate, judge, and causal bisect.
* ``02_section_lane_summary_table.md`` - operational ledger of what ran.

This module is a backward-compatible facade re-exporting from
``apps_rg.runtime.outputs``.
"""
from __future__ import annotations

from apps_rg.runtime.outputs.constants import *
from apps_rg.runtime.outputs.helpers import *
from apps_rg.runtime.outputs.judge_parsers import *
from apps_rg.runtime.outputs.research_context import *
from apps_rg.runtime.outputs.section_lane_tables import *
from apps_rg.runtime.outputs.resume_inline import *
from apps_rg.runtime.outputs.causal_plan import *
from apps_rg.runtime.outputs.causal_allocation import *
from apps_rg.runtime.outputs.bcg_forensics import *
from apps_rg.runtime.outputs.bcg_inline_output import *
from apps_rg.runtime.outputs.markdown_renderer import *
from apps_rg.runtime.outputs.proof_verifier import *
from apps_rg.runtime.outputs.manifest_builder import *
from apps_rg.runtime.outputs.evidence_exporter import *

# Re-export all functions explicitly for backward compatibility
_utc_now = _utc_now
_load_json = _load_json
_repo_rel = _repo_rel
_write_text = _write_text
_read_text = _read_text
_as_list = _as_list
_x2_summary_doc = _x2_summary_doc
_score_text = _score_text
_judge_rows_from_blob = _judge_rows_from_blob
_normalize_judge_record = _normalize_judge_record
_judge_failure_records = _judge_failure_records
_failed_dimension_codes = _failed_dimension_codes
_judge_failure_text_from_judges = _judge_failure_text_from_judges
_judge_failure_evidence = _judge_failure_evidence
_resolve_display = _resolve_display
_row_from_single_section = _row_from_single_section
_status_bucket = _status_bucket
_classify_failure = _classify_failure
_section_record_from_row = _section_record_from_row
_collect_section_records = _collect_section_records
_count_sections = _count_sections
_result_summary = _result_summary
_final_resume_output_required = _final_resume_output_required
_load_provider_call_records = _load_provider_call_records
_cache_preflight = _cache_preflight
_first_nonempty = _first_nonempty
_briefing_blob = _briefing_blob
_short_digest = _short_digest
_payload_dict = _payload_dict
_artifact_input_value = _artifact_input_value
_resolve_input_ref = _resolve_input_ref
_first_existing_json = _first_existing_json
_research_handoff_receipt = _research_handoff_receipt
_research_artifact_dirs = _research_artifact_dirs
_research_handoff_v2 = _research_handoff_v2
_apps_research_gate_context = _apps_research_gate_context
_research_source_class = _research_source_class
_research_x2_cell = _research_x2_cell
_research_x3_cell = _research_x3_cell
_research_briefing_context = _research_briefing_context
_research_briefing_row = _research_briefing_row
_section_by_id = _section_by_id
_judge_model_score_cell = _judge_model_score_cell
_judge_retry_fallback_cell = _judge_retry_fallback_cell
_provider_cell = _provider_cell
_pooling_selector_cell = _pooling_selector_cell
_secondary_provider_cell = _secondary_provider_cell
_section_lane_abs_dir = _section_lane_abs_dir
_lane_provider_proof = _lane_provider_proof
_lane_provider_attempted = _lane_provider_attempted
_lane_primary_provider = _lane_primary_provider
_lane_primary_model = _lane_primary_model
_lane_generation_status = _lane_generation_status
_generation_ordered_section_ids = _generation_ordered_section_ids
_build_section_lane_table = _build_section_lane_table
_exact_key_order = _exact_key_order
_validate_row_keys = _validate_row_keys
_inline_required_output_shape_errors = _inline_required_output_shape_errors
_non_authorized_section_ids = _non_authorized_section_ids
_resume_inline_authorization = _resume_inline_authorization
_blocked_resume_inline_text = _blocked_resume_inline_text
_resume_inline_source = _resume_inline_source
_authorized_resume_inline_text = _authorized_resume_inline_text
_resume_inline_text = _resume_inline_text
_inline_output_gates = _inline_output_gates
_top_rca_sections = _top_rca_sections
_root_cause = _root_cause
_implementation_plan = _implementation_plan
_failed_gate_ids = _failed_gate_ids
_gate_reason = _gate_reason
_pre_run_reason = _pre_run_reason
_allocation_row = _allocation_row
_causal_allocation = _causal_allocation
_validated_plan_items = _validated_plan_items
_validated_causal_allocation = _validated_causal_allocation
_render_causal_allocation_lines = _render_causal_allocation_lines
_recommended_action = _recommended_action
_markdown_table_escape = _markdown_table_escape
_wide_markdown_code_cell = _wide_markdown_code_cell
_render_section_lane_table_lines = _render_section_lane_table_lines
_render_resume_inline_lines = _render_resume_inline_lines
_research_row = _research_row
_bcg_row = _bcg_row
_active_bcg_evidence = _active_bcg_evidence
_forensic_gate = _forensic_gate
_forensic_artifacts = _forensic_artifacts
_output_bisect_sections = _output_bisect_sections
_forensic_artifact_by_section = _forensic_artifact_by_section
_forensic_evidence_map_rows = _forensic_evidence_map_rows
_truthy_signal = _truthy_signal
_clean_pass_hardening_rows = _clean_pass_hardening_rows
_build_bcg_recommendations = _build_bcg_recommendations
_build_bcg_recommended_next_moves = _build_bcg_recommended_next_moves
_bcg_truth_errors = _bcg_truth_errors
_bcg_forensics_truth_errors = _bcg_forensics_truth_errors
_build_bcg_issue_tree = _build_bcg_issue_tree
_build_inline_required_output = _build_inline_required_output
_render_locked_bcg_from_inline = _render_locked_bcg_from_inline
_render_mandatory_markdown = _render_mandatory_markdown
_render_bcg_markdown = _render_bcg_markdown
_render_bcg_markdown_locked = _render_bcg_markdown_locked
build_mandatory_run_output = build_mandatory_run_output
validate_mandatory_output_bundle = validate_mandatory_output_bundle
_sealed_additional_artifacts = _sealed_additional_artifacts
emit_mandatory_run_outputs = emit_mandatory_run_outputs
main = main

__all__ = [
    "BCG_EXECUTIVE_OUTPUT_MD",
    "MANDATORY_RUN_OUTPUT_JSON",
    "MANDATORY_RUN_OUTPUT_MD",
    "MANDATORY_OUTPUT_HARD_STOP_GATE_ID",
    "build_mandatory_run_output",
    "emit_mandatory_run_outputs",
    "validate_mandatory_output_bundle",
]
