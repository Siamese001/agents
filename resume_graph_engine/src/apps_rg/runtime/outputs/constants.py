"""Constants and schema definitions for mandatory run outputs."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from apps_rg.runtime.final_resume_outputs import (
    build_final_resume_output_contract,
    emit_final_resume_product_outputs,
)
from apps_rg.runtime.full_run_section_status import (
    FINAL_AGGREGATION_LANE,
    LANE_DISPLAY_TXT_CANDIDATES,
    LaneSectionStatusRow,
    collect_full_run_section_status,
)
from apps_rg.runtime.l7_audit_output import emit_l7_audit_ability_output
from apps_rg.runtime.mandatory_outputs import (
    CLOSEOUT_MANDATORY_OUTPUT_PROFILE,
    MANDATORY_OUTPUT_COMMIT_MANIFEST,
    PRODUCT_MANDATORY_OUTPUT_PROFILE,
    apply_mandatory_closeout_state,
    begin_mandatory_output_transaction,
    seal_mandatory_output_bundle,
    validate_mandatory_output_seal,
)
from apps_rg.runtime.output_bisect import render_output_bisect
from apps_rg.runtime.run_output_contract import (
    APPS_RG_MANDATORY_RUN_OUTPUT_JSON,
    APPS_RG_MANDATORY_RUN_OUTPUT_MD,
    BCG_EXECUTIVE_OUTPUT_MD,
    FINAL_RESUME_ASSEMBLY_JSON_RELPATH,
    FINAL_RESUME_DOCX_RELPATH,
    FINAL_RESUME_OUTPUT_JSON,
    FINAL_RESUME_OUTPUT_TXT,
    FULL_RUN_SECTION_STATUS_JSON,
    L7_AUDIT_ABILITY_OUTPUT_MD,
    OUTPUT_BISECT_MD,
    REVIEW_BUNDLE_FILENAME,
)
from apps_rg.runtime.runtime_proof_layout import find_repo_root
from apps_rg.runtime.section_failure_forensics import (
    E2E_SECTION_FORENSICS_GATE_ID,
    SECTION_FAILURE_FORENSICS_DIR,
    emit_section_failure_forensics,
    validate_section_failure_rca,
)
from apps_rg.prerequisites.briefing_validator import validate_apps_research_handoff

MANDATORY_RUN_OUTPUT_JSON = APPS_RG_MANDATORY_RUN_OUTPUT_JSON
MANDATORY_RUN_OUTPUT_MD = APPS_RG_MANDATORY_RUN_OUTPUT_MD
MANDATORY_OUTPUT_HARD_STOP_GATE_ID = "APPS_RG_MANDATORY_OUTPUTS_INCOMPLETE"

INLINE_REQUIRED_OUTPUT_SCHEMA_VERSION = "apps_rg.inline_required_output.v1"
INLINE_REQUIRED_OUTPUT_SECTION_ORDER = (
    "bcg",
    "section_lane_summary_table",
    "resume_docx_full_version_inline",
)
BCG_LOCKED_SECTION_ORDER = (
    "executive_answer",
    "p0_p1_px_recommendations",
    "board_level_readout",
    "issue_tree",
    "recommended_next_move",
    "evidence_map",
)
BCG_OUTPUT_KEYS = ("title", "section_order", *BCG_LOCKED_SECTION_ORDER)
SECTION_LANE_TABLE_COLUMNS = (
    "order",
    "section",
    "research_source_class",
    "r1a",
    "r1b",
    "lane_record",
    "provider_call_attempted",
    "primary_provider",
    "primary_model_observed",
    "pooling_selector_llm",
    "secondary_provider",
    "secondary_model_observed",
    "generation_status",
    "judges_run",
    "judge_models_scores",
    "judge_retry_fallback",
    "x2",
    "x3",
    "past_fail_blocker",
    "display_output",
    "l6_evidence",
)
INLINE_REQUIRED_OUTPUT_TOP_LEVEL_KEYS = (
    "schema_version",
    "immutable_section_order",
    "bcg",
    "section_lane_summary_table",
    "resume_docx_full_version_inline",
)
BCG_RECOMMENDATION_COLUMNS = ("priority", "recommendation", "evidence", "gate_outcome")
BCG_BOARD_READOUT_COLUMNS = ("question", "answer")
BCG_RECOMMENDATION_ROW_KEYS = BCG_RECOMMENDATION_COLUMNS
BCG_BOARD_READOUT_ROW_KEYS = BCG_BOARD_READOUT_COLUMNS
BCG_ISSUE_TREE_ROW_KEYS = (
    "section",
    "classification",
    "root_cause",
    "evidence",
    "causal_allocation",
    "required_implementation_plan",
)
BCG_EVIDENCE_MAP_ROW_KEYS = ("label", "path")
BCG_NESTED_TABLE_KEYS = ("columns", "rows")
SECTION_LANE_TABLE_KEYS = ("title", "columns", "rows")
RESUME_DOCX_INLINE_KEYS = ("title", "source", "text")
APPS_RG_OUTPUT_MANIFEST = "apps_rg_output_manifest.json"

_PRODUCT_OUTPUT_ARTIFACTS = (
    FINAL_RESUME_OUTPUT_TXT,
    FINAL_RESUME_OUTPUT_JSON,
    FINAL_RESUME_DOCX_RELPATH,
    FINAL_RESUME_ASSEMBLY_JSON_RELPATH,
    APPS_RG_OUTPUT_MANIFEST,
)

__all__ = [
    "BCG_EXECUTIVE_OUTPUT_MD",
    "APPS_RG_MANDATORY_RUN_OUTPUT_JSON",
    "APPS_RG_MANDATORY_RUN_OUTPUT_MD",
    "FINAL_RESUME_ASSEMBLY_JSON_RELPATH",
    "FINAL_RESUME_DOCX_RELPATH",
    "FINAL_RESUME_OUTPUT_JSON",
    "FINAL_RESUME_OUTPUT_TXT",
    "FULL_RUN_SECTION_STATUS_JSON",
    "L7_AUDIT_ABILITY_OUTPUT_MD",
    "OUTPUT_BISECT_MD",
    "REVIEW_BUNDLE_FILENAME",
    "MANDATORY_RUN_OUTPUT_JSON",
    "MANDATORY_RUN_OUTPUT_MD",
    "MANDATORY_OUTPUT_HARD_STOP_GATE_ID",
    "INLINE_REQUIRED_OUTPUT_SCHEMA_VERSION",
    "INLINE_REQUIRED_OUTPUT_SECTION_ORDER",
    "BCG_LOCKED_SECTION_ORDER",
    "BCG_OUTPUT_KEYS",
    "SECTION_LANE_TABLE_COLUMNS",
    "INLINE_REQUIRED_OUTPUT_TOP_LEVEL_KEYS",
    "BCG_RECOMMENDATION_COLUMNS",
    "BCG_BOARD_READOUT_COLUMNS",
    "BCG_RECOMMENDATION_ROW_KEYS",
    "BCG_BOARD_READOUT_ROW_KEYS",
    "BCG_ISSUE_TREE_ROW_KEYS",
    "BCG_EVIDENCE_MAP_ROW_KEYS",
    "BCG_NESTED_TABLE_KEYS",
    "SECTION_LANE_TABLE_KEYS",
    "RESUME_DOCX_INLINE_KEYS",
    "APPS_RG_OUTPUT_MANIFEST",
    "_PRODUCT_OUTPUT_ARTIFACTS",
    "FINAL_AGGREGATION_LANE",
    "LANE_DISPLAY_TXT_CANDIDATES",
    "LaneSectionStatusRow",
    "collect_full_run_section_status",
    "emit_l7_audit_ability_output",
    "CLOSEOUT_MANDATORY_OUTPUT_PROFILE",
    "MANDATORY_OUTPUT_COMMIT_MANIFEST",
    "PRODUCT_MANDATORY_OUTPUT_PROFILE",
    "apply_mandatory_closeout_state",
    "begin_mandatory_output_transaction",
    "seal_mandatory_output_bundle",
    "validate_mandatory_output_seal",
    "render_output_bisect",
    "find_repo_root",
    "E2E_SECTION_FORENSICS_GATE_ID",
    "SECTION_FAILURE_FORENSICS_DIR",
    "emit_section_failure_forensics",
    "validate_section_failure_rca",
    "build_final_resume_output_contract",
    "emit_final_resume_product_outputs",
    "validate_apps_research_handoff",
]
