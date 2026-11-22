"""Public facade for headline_lane delegating to headline_v2 (<=120 LOC)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from apps_rg.runtime.claim_ledger.headline_claim_ledger import (
    _headline_positioning_segments,
    build_headline_canonical_claim_ledger_v2,
    build_headline_text_claim_coverage,
    normalize_headline_claim_ledger,
)
from apps_rg.runtime.exit.headline_x3 import aggregate_x3 as _aggregate_headline_x3
from apps_rg.runtime.judges.headline_x1d import run_headline_judges
from apps_rg.runtime.runtime_proof_layout import finalize_runtime_proof_run, prepare_runtime_proof_run_dir, proof_bucket_for_provider, rel_posix
from apps_rg.runtime.sections.companion_lane_context import build_resume_support_blob, load_companion_context
from apps_rg.runtime.sections.headline_pa import compile_headline_prompt
from apps_rg.runtime.sections.headline_v2 import (
    BRIEFING_DEFAULT,
    CONTENT_SIGNAL_REPAIR_LIVE_MAX_ATTEMPTS,
    CONTENT_SIGNAL_REPAIR_MAX_ATTEMPTS,
    HEADLINE_JSON_OUTPUT_STATUSES as _HEADLINE_JSON_OUTPUT_STATUSES,
    HEADLINE_MAX_OUTPUT_TOKENS,
    HEADLINE_SELF_CHECK_PROOF_KEYS as _HEADLINE_SELF_CHECK_PROOF_KEYS,
    HEADLINE_TEMP_DEFAULT,
    JD_TEXT_DEFAULT,
    LANE_KEY,
    PROMPT_ID,
    RELEASE_HEADLINE_CONTENT_SIGNAL_REPAIR_ENABLED,
    REPO_ROOT as _DEFAULT_REPO_ROOT,
    TARGET_COMPANY_DEFAULT,
    TARGET_TITLE_DEFAULT,
    TRACE_RUNTIME_PATH_DEFAULT,
    apply_headline_content_signal_repair,
    bind_headline_graph_skill_lineage,
    build_headline_allowed_fact_packet,
    build_headline_lane_args,
    build_mock_output,
    build_prompt_messages,
    build_runtime_payload as _build_runtime_payload,
    build_selected_fact_plan,
    candidate_3word_subsequences,
    coerce_segment_claim_ledger_rows as _coerce_segment_claim_ledger_rows,
    collect_employer_names_lower,
    content_signal_repair_enabled,
    content_signal_repair_env_state,
    deterministic_headline_word_count_expand,
    ensure_claim_ledger,
    extract_candidate_name_tokens,
    headline_graph_binding_repair_state as _headline_graph_binding_repair_state,
    headline_graph_content_contract_active as _headline_graph_content_contract_active,
    headline_proof_bundle_labels,
    headline_resume_native_clarity_report,
    infer_product_quality,
    normalize_parsed_output,
    parse_model_json,
    resolve_canonical_source_fact_id as _resolve_canonical_source_fact_id,
    resolve_content_signal_repair_max_attempts,
    retry_headline_content_signal,
    retry_headline_proof_shape,
    retry_headline_word_and_pipe,
    retry_provider_for_parse,
    rewrite_machine_headline_segments as _rewrite_machine_headline_segments,
    run_headline_v2,
    sha16,
    snapshot_needs_headline_proof_retry,
    snapshot_raw_jd_alignment,
    sync_selected_fact_plan_required_ids,
    write_json,
    write_x2_gate_outputs,
)
from apps_rg.runtime.sections.headline_v2.blind_judge_and_loop import _compact_headline_repair_anchor
from apps_rg.runtime.sections.headline_v2.prompt_and_generate import _rewrite_partner_enablement_segment
from apps_rg.runtime.sections.lane_base_resume import load_base_resume
from apps_rg.runtime.sections.resume_employment_bullets import collect_employment_bullets
from apps_rg.runtime.sections.section_generation import build_section_request, generate_section, tag_reasoning_lane
from apps_rg.runtime.sections.section_product_shape_ssot import HEADLINE_WORD_MAX, HEADLINE_WORD_MIN
from apps_rg.runtime.shadow.headline_l6 import build_l6_shadow_package, emit_headline_l6_shadow_learning_outputs
from apps_rg.runtime.validators.headline_positioning_x2 import (
    GOVERNANCE_SIGNAL_FAMILIES,
    POSITIONING_FAMILY_FLOOR,
    governance_signal_families_matched,
    headline_positioning_consumption_active,
    narrowing_labels_found,
    positioning_families_matched,
)
from apps_rg.runtime.validators.headline_quality_x2 import POSITIONING_FAMILIES
from apps_rg.runtime.validators.headline_x2 import (
    evaluate_headline_literal_grounding,
    has_valid_headline_prefix,
    headline_executive_abstraction_report,
    headline_runtime_self_check_truth,
    headline_segment_theme_overlap_issues,
    headline_word_count,
    polish_claim_text_when_headline_has_no_metrics,
    recite_canonical_segments_to_bundle_facts,
    repair_headline_segment_citations_for_grounding,
    run_headline_x2_gates,
    validate_raw_headline_claim_ledger,
)
from apps_rg.runtime.w3_execution_path_labels import BUCKET_GOVERNED_PA_L2_EXIT, PLAN_SLUG, validate_bucket

W3_EXECUTION_PATH_BUCKET = BUCKET_GOVERNED_PA_L2_EXIT
W3_EXECUTION_PATH_PLAN_SLUG = PLAN_SLUG
validate_bucket(W3_EXECUTION_PATH_BUCKET, context=__name__)
REPO_ROOT = _DEFAULT_REPO_ROOT


def build_runtime_payload(*, base_json_path: Path, base_hash: str, selected_fact_plan: dict[str, Any], allowed_fact_ids: set[str], target_title: str, target_company: str, jd_text: str, briefing: str) -> dict[str, Any]:
    return _build_runtime_payload(base_json_path=base_json_path, base_hash=base_hash, selected_fact_plan=selected_fact_plan, allowed_fact_ids=allowed_fact_ids, target_title=target_title, target_company=target_company, jd_text=jd_text, briefing=briefing, repo_root=REPO_ROOT)


def run_headline_execution(args: SimpleNamespace, *, artifact_dir_override: Path | None = None, trace_runtime_path: str = TRACE_RUNTIME_PATH_DEFAULT, print_output: bool = True) -> dict[str, Any]:
    return run_headline_v2(args, artifact_dir_override=artifact_dir_override, trace_runtime_path=trace_runtime_path, print_output=print_output, repo_root_override=REPO_ROOT)


def run_headline_lane_execution(args: SimpleNamespace, *, artifact_dir_override: Path | None = None) -> dict[str, Any]:
    return run_headline_execution(args, artifact_dir_override=artifact_dir_override, trace_runtime_path=TRACE_RUNTIME_PATH_DEFAULT, print_output=False)
