"""Modular role-episode lane package decomposed into stage and binding submodules."""
from __future__ import annotations

from .bullet_normalization import (
    _deterministic_graph_bullet_render,
    _fact_id_from_row,
    _normalize_bullets,
    _repair_role_episode_bullet_evidence_density,
    _source_fact_ids_from_bullets,
)
from .lane_config import (
    MAX_OUTPUT_TOKENS,
    REPO_ROOT,
    ROLE_EPISODE_FINAL_BULLET_COUNT,
    ROLE_EPISODE_FINAL_MATERIALIZED_SELECTION_CONTRACT,
    ROLE_EPISODE_GRAPH_BULLET_RENDERER_VERSION,
    ROLE_EPISODE_MAX_OUTPUT_TOKENS_BY_SECTION,
    ROLE_EPISODE_PROOF_TEXT_RENDERER_VERSION,
    ROLE_EPISODE_X2_GATE_IDS_BY_RUN_FUNCTION,
    ROLE_EPISODE_X2_RUN_FUNCTION_BY_SECTION,
    RoleEpisodeLaneConfig,
    _ROLE_EPISODE_EVIDENCE_DENSITY_REPAIRS,
    _ROLE_LANES,
    _X1D_WIRING_GATE_IDS,
    _compact_text,
    _facts_from_plan,
    _json_hash,
    _max_output_tokens_for_lane,
    _normalize_source_ids,
    _role_header,
    _sentence,
    build_role_episode_lane_args,
)
from .lane_generation import run_role_episode_generation_stage
from .lane_ingress import _write_blocked_artifacts, run_role_episode_ingress_stage
from .materialization import (
    _claim_ledger_from_bullets,
    _display_text,
    _llm_generation_status,
    _materialize_bullet_generation,
    _normalize_role_episode_bullet_pool_parsed,
    _parse_json_object,
    _reconcile_final_materialized_selection_gate,
)
from .narrative_binding import (
    _NARRATIVE_LEDGER_STOPWORDS,
    _NARRATIVE_SOURCE_BINDING_PATTERNS,
    _TARGETING_ONLY_EXPERIENCE_MARKERS,
    _TARGETING_ONLY_TAIL_REPAIRS,
    _narrative_from_parsed,
    _narrative_ledger_tokens,
    _narrative_source_ids_for_claim,
    _parsed_claim_ledger_source_ids_for_narrative,
    _strip_targeting_only_experience_claims,
    _targeting_only_experience_hits,
    _valid_source_ids_without_fallback,
)
from .prompt_compiler import (
    _blocked_provider_result,
    _compiled_prompt,
    _prompt_object,
    _role_episode_evidence_block,
)
from .proof_selection import (
    _MODEL_SURFACE_NON_ANCHOR_TOKENS,
    _PROOF_FACT_COMPOSITION_CONNECTIVES,
    _PROOF_FACT_SURFACE_COMPOSITIONS,
    _model_bullet_surface_binding,
    _ordered_ids_from_bullets,
    _ordered_ids_from_bullets_with_contract,
    _proof_authorized_bullets_from_selection,
    _proof_authorized_bullets_from_selection_with_contract,
    _proof_authorized_narrative_from_selection,
    _proof_fact_by_id,
    _proof_fact_composition_is_bound,
    _proof_fact_surface_tokens,
    _proof_fact_text,
    _source_ids_from_parsed_claim_ledger,
)
from .x2_gates import (
    _display_text_for_x2,
    _display_text_is_proof_authorized,
    _has_first_person,
    _judge_rows,
    _selected_fact_plan_authorized_texts,
    _x2_gate,
    _x2_gates,
    run_ey_bullets_x2_gates,
    run_ey_narrative_x2_gates,
    run_insurtech_bullets_x2_gates,
    run_insurtech_narrative_x2_gates,
    run_role_episode_x2_gates,
    run_slalom_bullets_x2_gates,
    run_slalom_narrative_x2_gates,
)
