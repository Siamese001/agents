"""Modular IBM bullets lane package decomposed into stage and repair submodules."""
from __future__ import annotations

from .frozen_allocation import (
    _IBM_FROZEN_ALLOCATION_DISPLAY_COMPOSITIONS,
    _bind_ibm_change_log_to_frozen_allocation,
    _canonicalize_bul_ibm_source_fact_id,
    _clamp_to_ibm_fact_scope,
    _count_intensities,
    _materialize_ibm_bullets_from_frozen_allocation,
    _normalize_fact_id_list,
    _normalize_ibm_claim_ledger,
    normalize_parsed_output,
)
from .lane_constants import (
    BRIEFING_DEFAULT,
    BULLET_ID_ALIASES,
    DEFAULT_INTENSITY_BY_BULLET,
    IBM_DEFAULT_DISTRIBUTION,
    IBM_MAX_OUTPUT_TOKENS,
    IBM_TEMP_DEFAULT,
    IBM_TEMP_RANGE,
    JD_TEXT_DEFAULT,
    LANE_KEY,
    PROMPT_ID,
    REPO_ROOT,
    TARGET_COMPANY_DEFAULT,
    TARGET_TITLE_DEFAULT,
    _find_repo_root,
    build_prompt_messages,
    build_runtime_payload,
    build_selected_fact_plan,
    extract_ibm_employment,
    load_base_resume,
    sha16,
    should_hydrate_ibm_bullets_from_canonical,
    write_json,
)
from .metric_repairs import (
    IBM_LOCKED_METRIC_CANONICAL,
    _HOLD_METRIC_TEXT_RE,
    _IBM_FOREIGN_METRIC_SCRUB_RE,
    _plan_metric_display_token,
    _scrub_foreign_ibm_metric_tokens,
    align_ibm_claim_ledger_from_canonical_facts,
    build_ibm_bullets_allowed_fact_packet,
    demote_gated_ibm_metrics,
    demote_hold_metrics,
    inject_ibm_locked_metric_anchors,
    repair_ibm_bullet_metric_anchors_from_plan,
    scrub_cross_slot_plan_metrics,
)
from .provider_io import (
    build_mock_output,
    bullets_display_text,
    infer_product_quality,
    parse_model_json,
    retry_provider_for_parse,
)
from .reselection_helpers import build_ibm_reselection_callbacks
from .stage_closeout import run_ibm_closeout_stage
from .stage_generation import run_ibm_generation_and_x2_stage
from .stage_ingress import run_ibm_ingress_stage, run_ibm_prompt_compile_stage
