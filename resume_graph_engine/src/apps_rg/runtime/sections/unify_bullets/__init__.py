"""Modular Unify bullets lane package decomposed into stage and surface submodules."""
from __future__ import annotations

from .lane_constants import (
    BRIEFING_DEFAULT,
    BULLET_ID_ALIASES,
    JD_TEXT_DEFAULT,
    LANE_KEY,
    PROMPT_ID,
    PROMPT_TEMPLATE,
    REPO_ROOT,
    TARGET_COMPANY_DEFAULT,
    TARGET_TITLE_DEFAULT,
    UNIFY_MAX_OUTPUT_TOKENS,
    UNIFY_TEMP_DEFAULT,
    UNIFY_TEMP_RANGE,
    _find_repo_root,
    build_runtime_payload,
    build_selected_fact_plan,
    extract_unify_employment,
    load_base_resume,
    sha16,
    write_json,
)
from .metric_surfaces import (
    _SURFACE_NORM_RE,
    _append_metric_surface_clause,
    _authoritative_selected_fact_plan,
    _canonicalize_unify_gate_metric_text,
    _enforce_unify_metric_outcome_surfaces,
    _ensure_change_log_entry,
    _ensure_selected_plan_metric_ids,
    _metric_raw_traces_to_plan_or_outcomes,
    _metric_surface_tokens,
    _metric_token_visible_in_text,
    _plan_metric_raw_for_slot,
    _runtime_selected_fact_plan,
    _selected_fact_plan_has_runtime_facts,
    _selected_metric_ids_for_slot,
    _selected_plan_metric_ids_for_slot,
    _slot_metric_allowlist,
    _surface_norm,
    _unify_metric_outcome_nodes,
    _unify_metric_raw_values,
)
from .normalization import (
    _UNIFY_ARCHIVE_PARAPHRASE_REPAIRS,
    _UNIFY_EVIDENCE_DENSITY_REPAIRS,
    _UNIFY_SENIORITY_TENSE_REPAIRS,
    _canonicalize_bul_w7_unify_source_fact_id,
    _clamp_unify_sources_to_slot,
    _legacy_unify_to_ledger_id_map,
    _normalize_unify_claim_ledger,
    _normalize_unify_source_fact_id_list,
    _remap_unify_id,
    _unify_slot_bound_source_scope,
)
from .provider_io import (
    _clamp_mock_bullet_text,
    build_mock_output,
    build_prompt_messages,
    bullets_display_text,
    enrich_unify_parsed_for_x2,
    infer_unify_bullets_product_quality,
    parse_model_json,
    retry_provider_for_parse,
)
from .repairs import (
    _claim_text_by_unify_slot,
    _repair_protected_unify_bullet_metrics,
    _repair_unify_archive_verbatim_overlap,
    _repair_unify_bullet_evidence_density,
    _repair_unify_bullet_seniority_tense,
    _sync_unify_claim_ledger_to_bullets,
    normalize_unify_parsed_without_ledger_synthesis,
)
from .reselection_helpers import build_unify_reselection_callbacks
from .stage_closeout import run_unify_closeout_stage
from .stage_generation import run_unify_generation_and_x2_stage
from .stage_ingress import run_unify_ingress_stage, run_unify_prompt_compile_stage
