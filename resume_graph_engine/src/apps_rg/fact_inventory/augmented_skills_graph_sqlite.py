"""Materialize augmented_skills_graph (JSON ledger) into SQLite for C0.3 context lookup.

Graph rows organize/route capabilities — they are not claim proof. Facts remain proof substrate.

This module is a backward-compatible facade re-exporting from
``apps_rg.fact_inventory.skills_graph``.
"""
from __future__ import annotations

from apps_rg.fact_inventory.augmented_skills_graph import (
    graph_version_from_payload,
    load_augmented_skills_graph,
)
from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    REGISTERED_GRAPH_EDGE_SIGNATURES,
    default_arsenal_ledger_path,
    derive_registered_graph_endpoint_types,
    skill_row_eligible_for_external_claim,
    validate_arsenal_ledger_shape,
)
from apps_rg.fact_inventory.skills_graph.constants import (
    BLOCKED_EXTERNAL_CLAIM_POLICIES,
    BLOCKED_SUPPORT_LEVELS,
    C03_SQLITE_MATERIALIZER_CODE_VERSION,
    CANDIDATE_LEDGER_REL_PATH,
    CONFIDENCE_GRADES,
    CONFIDENCE_GRADE_RANK,
    ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS,
    EXTERNAL_ACTIVE_STATUSES,
    FORBIDDEN_PROMOTION_SKILL_SUBSTRINGS,
    FORBIDDEN_SKILL_NODE_IDS,
    HUMAN_CONFIRM_REQUIRED_ALLOWED_RESUME_USE,
    NON_PROMOTE_ACTIVATION,
    OPERATOR_ARCHIVE_PROMOTION_BY_SKILL,
    OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS,
    POLICY_EDGE_SOURCE_KEYS,
    REPO_REL_DB,
    THEME_AGENTIC_SKILL_IDS,
    canonical_career_epoch_and_ordinal,
    project_registered_graph_node_type,
    projected_graph_edge_signature_report,
    projected_registered_graph_edge_signatures,
)
from apps_rg.fact_inventory.skills_graph.classification import (
    _is_skill_id,
    canonical_node_type,
    default_candidate_fact_ledger_path,
    infer_node_type_from_id,
    resolve_node_type,
)
from apps_rg.fact_inventory.skills_graph.graph_builder import (
    _confidence_from_node,
    _confidence_from_skill_row,
    _dedupe_edge_rows,
    _ensure_fact_node,
    _ensure_policy_nodes,
    _executive_summary_eligibility,
    _external_eligible_node,
    _parse_section_id,
    _policy_rule_node_id,
    _redirect_edge_source,
    _resolve_projection_pillar_hints,
    _skill_external_eligible,
    collect_graph_counts,
    collect_high_and_exec_summary_counts,
)
from apps_rg.fact_inventory.skills_graph.materializer import (
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.fact_inventory.skills_graph.promotions import (
    _reject_operator_promotion_reason,
    _rewire_skill_fact_edges,
    _sync_skill_row_to_payload_collections,
    apply_operator_archive_promotions,
    audit_candidate_fact_promotions,
    audit_theme_skill_promotion_decisions,
    build_skill_rows_by_id,
    cap_derived_grade_for_candidate_facts,
    classify_skill_archive_promotion,
    confidence_grade_for_skill_row,
    derive_confidence_grade,
    has_valid_human_confirmed_archive_promotion,
    load_candidate_fact_promotion_registry,
    parse_human_confirmed_archive_promotion,
    resolve_confidence_grade,
    skill_links_only_engineering_candidate_pending_confirm,
)
from apps_rg.fact_inventory.skills_graph.query import (
    get_skills_by_career_phase,
)
from apps_rg.fact_inventory.skills_graph.schema import (
    CANONICAL_CAREER_EPOCHS,
    CANONICAL_NODE_TYPES,
    DDL_STATEMENTS,
    EMPLOYMENT_PHASES,
    EPOCH_LABELS,
    EPOCH_ORDINAL,
    LEGACY_SKILL_EPOCHS,
    ORDINAL_TO_EPOCH,
    P6_SKILLS,
    RAW_TO_CANONICAL_NODE_TYPE,
)
from apps_rg.fact_inventory.skills_graph.storage import (
    _acquire_sqlite_maintenance_lock,
    _check_and_reclaim_stale_lock,
    _cleanup_temp_sqlite,
    _is_pid_alive,
    _new_sibling_temp_db_path,
    _open_isolated_temp_graph_sqlite,
    _release_sqlite_maintenance_lock,
    _replace_sqlite_projection_if_unchanged,
    _repo_root,
    _require_sidecar_free_atomic_target,
    _sha256_hex,
    _sqlite_maintenance_lock_path,
    _sqlite_projection_digest,
    _sqlite_sidecar_paths,
    _utc_now,
    default_graph_sqlite_path,
    load_graph_metadata_row,
    open_graph_sqlite,
)
from apps_rg.fact_inventory.skills_graph.validation import (
    validate_hardened_materialized_sqlite,
    validate_materialized_sqlite,
)
from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    ROLE_FAMILY_TRACK_WEIGHTS,
    SENIOR_ROLE_TAXONOMY_IDS,
    TAXONOMY_TO_PROJECTION_ROLE,
)
from apps_rg.repository_layout import repository_root

__all__ = [
    "CANONICAL_CAREER_EPOCHS",
    "EPOCH_ORDINAL",
    "ORDINAL_TO_EPOCH",
    "EPOCH_LABELS",
    "P6_SKILLS",
    "LEGACY_SKILL_EPOCHS",
    "EMPLOYMENT_PHASES",
    "canonical_career_epoch_and_ordinal",
    "get_skills_by_career_phase",
    "CANONICAL_NODE_TYPES",
    "C03_SQLITE_MATERIALIZER_CODE_VERSION",
    "DDL_STATEMENTS",
    "CONFIDENCE_GRADES",
    "RAW_TO_CANONICAL_NODE_TYPE",
    "ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS",
    "OPERATOR_ARCHIVE_PROMOTION_BY_SKILL",
    "OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS",
    "THEME_AGENTIC_SKILL_IDS",
    "apply_operator_archive_promotions",
    "audit_candidate_fact_promotions",
    "audit_theme_skill_promotion_decisions",
    "build_skill_rows_by_id",
    "canonical_node_type",
    "classify_skill_archive_promotion",
    "collect_high_and_exec_summary_counts",
    "confidence_grade_for_skill_row",
    "default_candidate_fact_ledger_path",
    "default_graph_sqlite_path",
    "derive_confidence_grade",
    "has_valid_human_confirmed_archive_promotion",
    "load_candidate_fact_promotion_registry",
    "load_graph_metadata_row",
    "materialize_augmented_skills_graph_sqlite",
    "open_graph_sqlite",
    "collect_graph_counts",
    "project_registered_graph_node_type",
    "projected_graph_edge_signature_report",
    "projected_registered_graph_edge_signatures",
    "resolve_confidence_grade",
    "validate_hardened_materialized_sqlite",
    "validate_materialized_sqlite",
]
