#!/usr/bin/env python3
"""Modularize augmented_skills_graph_sqlite.py into apps_rg.fact_inventory.skills_graph sub-package."""

import ast
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILE = REPO_ROOT / "resume_graph_engine/src/apps_rg/fact_inventory/augmented_skills_graph_sqlite.py"
PKG_DIR = REPO_ROOT / "resume_graph_engine/src/apps_rg/fact_inventory/skills_graph"

def main() -> None:
    src_text = subprocess.run(
        ["git", "show", "HEAD:resume_graph_engine/src/apps_rg/fact_inventory/augmented_skills_graph_sqlite.py"],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=30
    ).stdout
    tree = ast.parse(src_text)
    lines = src_text.splitlines(keepends=True)

    funcs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs[node.name] = "".join(lines[node.lineno - 1:node.end_lineno])

    if PKG_DIR.exists():
        shutil.rmtree(PKG_DIR)
    PKG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. schema.py: lines 43 to 150 (types) and lines 392 to 726 (DDL_STATEMENTS)
    types_code = "".join(lines[42:150])
    ddl_code = "".join(lines[391:726])
    schema_code = f'''"""Database DDL statements and registered graph types / epochs."""
from __future__ import annotations

{types_code}

{ddl_code}

__all__ = [
    "CANONICAL_NODE_TYPES",
    "RAW_TO_CANONICAL_NODE_TYPE",
    "CANONICAL_CAREER_EPOCHS",
    "EPOCH_ORDINAL",
    "ORDINAL_TO_EPOCH",
    "EPOCH_LABELS",
    "P6_SKILLS",
    "LEGACY_SKILL_EPOCHS",
    "EMPLOYMENT_PHASES",
    "DDL_STATEMENTS",
]
'''
    (PKG_DIR / "schema.py").write_text(schema_code, encoding="utf-8")

    # 2. constants.py
    top_consts = "".join(lines[37:41])
    sig_funcs = "\n\n".join([
        funcs["canonical_career_epoch_and_ordinal"],
        funcs["project_registered_graph_node_type"],
        funcs["projected_registered_graph_edge_signatures"],
        funcs["projected_graph_edge_signature_report"],
    ])
    policy_consts = "".join(lines[264:390])
    constants_code = f'''"""Constants, career epoch mappings, and signature reporting for skills graph."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    REGISTERED_GRAPH_EDGE_SIGNATURES,
    default_arsenal_ledger_path,
    derive_registered_graph_endpoint_types,
    skill_row_eligible_for_external_claim,
    validate_arsenal_ledger_shape,
)
from .schema import (
    CANONICAL_NODE_TYPES,
    EPOCH_LABELS,
    EPOCH_ORDINAL,
    LEGACY_SKILL_EPOCHS,
    ORDINAL_TO_EPOCH,
    P6_SKILLS,
    RAW_TO_CANONICAL_NODE_TYPE,
)

{top_consts}

{sig_funcs}

{policy_consts}

__all__ = [
    "REPO_REL_DB",
    "C03_SQLITE_MATERIALIZER_CODE_VERSION",
    "canonical_career_epoch_and_ordinal",
    "project_registered_graph_node_type",
    "projected_registered_graph_edge_signatures",
    "projected_graph_edge_signature_report",
    "POLICY_EDGE_SOURCE_KEYS",
    "FORBIDDEN_SKILL_NODE_IDS",
    "NON_PROMOTE_ACTIVATION",
    "EXTERNAL_ACTIVE_STATUSES",
    "CONFIDENCE_GRADES",
    "BLOCKED_SUPPORT_LEVELS",
    "BLOCKED_EXTERNAL_CLAIM_POLICIES",
    "CONFIDENCE_GRADE_RANK",
    "CANDIDATE_LEDGER_REL_PATH",
    "ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS",
    "HUMAN_CONFIRM_REQUIRED_ALLOWED_RESUME_USE",
    "THEME_AGENTIC_SKILL_IDS",
    "OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS",
    "OPERATOR_ARCHIVE_PROMOTION_BY_SKILL",
    "FORBIDDEN_PROMOTION_SKILL_SUBSTRINGS",
]
'''
    (PKG_DIR / "constants.py").write_text(constants_code, encoding="utf-8")

    # 3. storage.py
    storage_func_names = [
        "_repo_root",
        "_utc_now",
        "_sha256_hex",
        "_sqlite_sidecar_paths",
        "_new_sibling_temp_db_path",
        "_open_isolated_temp_graph_sqlite",
        "_cleanup_temp_sqlite",
        "_require_sidecar_free_atomic_target",
        "_sqlite_projection_digest",
        "_sqlite_maintenance_lock_path",
        "_is_pid_alive",
        "_check_and_reclaim_stale_lock",
        "_acquire_sqlite_maintenance_lock",
        "_release_sqlite_maintenance_lock",
        "_replace_sqlite_projection_if_unchanged",
        "default_graph_sqlite_path",
        "open_graph_sqlite",
        "load_graph_metadata_row",
    ]
    storage_code = f'''"""SQLite connection, maintenance locking, atomic replacement, and path resolution."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apps_rg.repository_layout import repository_root
from .constants import REPO_REL_DB

{chr(10).join(funcs[name] for name in storage_func_names)}

__all__ = {storage_func_names!r}
'''
    (PKG_DIR / "storage.py").write_text(storage_code, encoding="utf-8")

    # 4. classification.py
    class_func_names = [
        "infer_node_type_from_id",
        "resolve_node_type",
        "canonical_node_type",
        "_is_skill_id",
        "default_candidate_fact_ledger_path",
    ]
    class_code = f'''"""Node type resolution and basic classification."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .schema import CANONICAL_NODE_TYPES, RAW_TO_CANONICAL_NODE_TYPE
from .constants import (
    CANDIDATE_LEDGER_REL_PATH,
    FORBIDDEN_SKILL_NODE_IDS,
    POLICY_EDGE_SOURCE_KEYS,
    THEME_AGENTIC_SKILL_IDS,
)
from .storage import _repo_root

{chr(10).join(funcs[name] for name in class_func_names)}

__all__ = {class_func_names!r}
'''
    (PKG_DIR / "classification.py").write_text(class_code, encoding="utf-8")

    # 5. promotions.py
    promo_func_names = [
        "derive_confidence_grade",
        "cap_derived_grade_for_candidate_facts",
        "resolve_confidence_grade",
        "confidence_grade_for_skill_row",
        "classify_skill_archive_promotion",
        "load_candidate_fact_promotion_registry",
        "parse_human_confirmed_archive_promotion",
        "has_valid_human_confirmed_archive_promotion",
        "skill_links_only_engineering_candidate_pending_confirm",
        "audit_candidate_fact_promotions",
        "audit_theme_skill_promotion_decisions",
        "build_skill_rows_by_id",
        "_reject_operator_promotion_reason",
        "_sync_skill_row_to_payload_collections",
        "_rewire_skill_fact_edges",
        "apply_operator_archive_promotions",
    ]
    promo_code = f'''"""Candidate fact promotion registry, audit decisions, and operator archive promotion."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from apps_rg.fact_inventory.master_skills_arsenal_ledger import skill_row_eligible_for_external_claim
from .constants import (
    BLOCKED_EXTERNAL_CLAIM_POLICIES,
    BLOCKED_SUPPORT_LEVELS,
    CANDIDATE_LEDGER_REL_PATH,
    CONFIDENCE_GRADES,
    CONFIDENCE_GRADE_RANK,
    ENGINEERING_PLATFORM_CANDIDATE_FACT_IDS,
    FORBIDDEN_PROMOTION_SKILL_SUBSTRINGS,
    FORBIDDEN_SKILL_NODE_IDS,
    HUMAN_CONFIRM_REQUIRED_ALLOWED_RESUME_USE,
    NON_PROMOTE_ACTIVATION,
    OPERATOR_ARCHIVE_PROMOTION_BY_SKILL,
    OPERATOR_CONFIRMED_ARCHIVE_FACT_IDS,
    THEME_AGENTIC_SKILL_IDS,
)
from .classification import (
    _is_skill_id,
    canonical_node_type,
    default_candidate_fact_ledger_path,
)
from .storage import _repo_root, _utc_now

{chr(10).join(funcs[name] for name in promo_func_names)}

__all__ = {promo_func_names!r}
'''
    (PKG_DIR / "promotions.py").write_text(promo_code, encoding="utf-8")

    # 6. graph_builder.py
    gb_func_names = [
        "collect_high_and_exec_summary_counts",
        "_confidence_from_skill_row",
        "_confidence_from_node",
        "_policy_rule_node_id",
        "_redirect_edge_source",
        "_dedupe_edge_rows",
        "_ensure_policy_nodes",
        "_executive_summary_eligibility",
        "collect_graph_counts",
        "_skill_external_eligible",
        "_external_eligible_node",
        "_parse_section_id",
        "_ensure_fact_node",
        "_resolve_projection_pillar_hints",
    ]
    gb_code = f'''"""Graph node and edge builders, policy nodes, and external claim eligibility."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    ROLE_FAMILY_TRACK_WEIGHTS,
    SENIOR_ROLE_TAXONOMY_IDS,
    TAXONOMY_TO_PROJECTION_ROLE,
)
from .schema import CANONICAL_NODE_TYPES
from .constants import (
    BLOCKED_EXTERNAL_CLAIM_POLICIES,
    BLOCKED_SUPPORT_LEVELS,
    CONFIDENCE_GRADES,
    EXTERNAL_ACTIVE_STATUSES,
    FORBIDDEN_SKILL_NODE_IDS,
    NON_PROMOTE_ACTIVATION,
    POLICY_EDGE_SOURCE_KEYS,
    canonical_career_epoch_and_ordinal,
    project_registered_graph_node_type,
    skill_row_eligible_for_external_claim,
)
from .classification import (
    canonical_node_type,
    infer_node_type_from_id,
    resolve_node_type,
)
from .promotions import (
    build_skill_rows_by_id,
    confidence_grade_for_skill_row,
    derive_confidence_grade,
    load_candidate_fact_promotion_registry,
    resolve_confidence_grade,
)

{chr(10).join(funcs[name] for name in gb_func_names)}

__all__ = {gb_func_names!r}
'''
    (PKG_DIR / "graph_builder.py").write_text(gb_code, encoding="utf-8")

    # 7. materializer_ingress.py
    mat_src = funcs["materialize_augmented_skills_graph_sqlite"]
    mat_lines = mat_src.splitlines(keepends=True)
    r_tree = ast.parse(mat_src)
    r_func = r_tree.body[0]

    stmt1 = r_func.body[1]
    stmt34 = r_func.body[34]
    ingress_body = "".join(mat_lines[stmt1.lineno - 1:stmt34.end_lineno])

    ingress_code = f'''"""Ingress stage for skills graph materialization: nodes, edges, promotions."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from apps_rg.fact_inventory.augmented_skills_graph import (
    graph_version_from_payload,
    load_augmented_skills_graph,
)
from apps_rg.fact_inventory.master_skills_arsenal_ledger import (
    REGISTERED_GRAPH_EDGE_SIGNATURES,
    default_arsenal_ledger_path,
    derive_registered_graph_endpoint_types as _orig_derive_registered_graph_endpoint_types,
    skill_row_eligible_for_external_claim,
    validate_arsenal_ledger_shape,
)
from apps_rg.fact_inventory.metric_outcome_materializer import (
    metric_outcome_node_and_edge_rows,
)
from .schema import (
    CANONICAL_NODE_TYPES,
    EMPLOYMENT_PHASES,
    EPOCH_ORDINAL,
)
from .constants import (
    FORBIDDEN_SKILL_NODE_IDS,
    NON_PROMOTE_ACTIVATION,
    canonical_career_epoch_and_ordinal,
    project_registered_graph_node_type,
    projected_graph_edge_signature_report,
    projected_registered_graph_edge_signatures,
)
from .storage import (
    _repo_root,
    _require_sidecar_free_atomic_target,
    _sha256_hex,
    _utc_now,
    default_graph_sqlite_path,
)
from .classification import (
    _is_skill_id,
    infer_node_type_from_id,
    resolve_node_type,
)
from .promotions import (
    build_skill_rows_by_id,
    confidence_grade_for_skill_row,
    has_valid_human_confirmed_archive_promotion,
    load_candidate_fact_promotion_registry,
)
from .graph_builder import (
    _confidence_from_node,
    _dedupe_edge_rows,
    _ensure_fact_node,
    _ensure_policy_nodes,
    _executive_summary_eligibility,
    _parse_section_id,
    _redirect_edge_source,
    _skill_external_eligible,
)

def _get_derive_registered_graph_endpoint_types():
    facade = sys.modules.get("apps_rg.fact_inventory.augmented_skills_graph_sqlite")
    return getattr(facade, "derive_registered_graph_endpoint_types", _orig_derive_registered_graph_endpoint_types)

def run_materializer_ingress(
    *,
    graph: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    db_path: Path | None = None,
    json_source_path: Path | None = None,
) -> dict[str, Any]:
    """Execute materializer ingress: parse payload, assemble nodes, edges, promotions."""
    derive_registered_graph_endpoint_types = _get_derive_registered_graph_endpoint_types()
{ingress_body}
    return {{
        "root": root,
        "out_path": out_path,
        "payload": payload,
        "src_path": src_path,
        "ledger_hash": ledger_hash,
        "gver": gver,
        "ts": ts,
        "skill_rows_by_id": skill_rows_by_id,
        "node_rows": node_rows,
        "edge_rows": edge_rows,
        "skill_fact_rows": skill_fact_rows,
        "section_rows": section_rows,
        "projected_signature_report": projected_signature_report,
    }}

__all__ = ["run_materializer_ingress"]
'''
    (PKG_DIR / "materializer_ingress.py").write_text(ingress_code, encoding="utf-8")

    # 8. materializer_indexing.py
    stmt35 = r_func.body[35]
    stmt51 = r_func.body[51]
    indexing_body = "".join(mat_lines[stmt35.lineno - 1:stmt51.end_lineno])

    indexing_code = f'''"""Indexing stage: metric outcomes, clusters, selection features, and evidence budgets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.candidate_fact_ledger import load_master_role_family_taxonomy
from apps_rg.fact_inventory.graph_metric_heterogeneity_policy import (
    POLICY_VERSION as C03_METRIC_POLICY_VERSION,
    metric_bucket_for_row,
)
from apps_rg.fact_inventory.graph_sqlite_path_index import (
    GRAPH_INDEX_SCHEMA_VERSION,
    build_graph_index_rows,
)
from apps_rg.fact_inventory.track_weighted_graph_expansion import (
    ROLE_FAMILY_TRACK_WEIGHTS,
    SENIOR_ROLE_TAXONOMY_IDS,
)
from .constants import (
    C03_SQLITE_MATERIALIZER_CODE_VERSION,
    FORBIDDEN_SKILL_NODE_IDS,
    canonical_career_epoch_and_ordinal,
)
from .classification import _is_skill_id
from .graph_builder import _resolve_projection_pillar_hints

def run_materializer_indexing(ctx: dict[str, Any]) -> None:
    """Compute metric outcomes, clusters, section features, and graph summary."""
    root = ctx["root"]
    repo_root = root
    out_path = ctx["out_path"]
    payload = ctx["payload"]
    skill_rows_by_id = ctx["skill_rows_by_id"]
    node_rows = ctx["node_rows"]
    edge_rows = ctx["edge_rows"]
    section_rows = ctx["section_rows"]
    skill_fact_rows = ctx["skill_fact_rows"]
    projected_signature_report = ctx["projected_signature_report"]
    ts = ctx["ts"]
    gver = ctx["gver"]
    ledger_hash = ctx["ledger_hash"]
    src_path = ctx["src_path"]

{indexing_body}

    ctx["selection_feature_rows"] = selection_feature_rows
    ctx["role_family_skill_weight_rows"] = role_family_skill_weight_rows
    ctx["projection_rows"] = projection_rows
    ctx["graph_index_rows"] = graph_index_rows
    ctx["summary"] = summary

__all__ = ["run_materializer_indexing"]
'''
    (PKG_DIR / "materializer_indexing.py").write_text(indexing_code, encoding="utf-8")

    # 9. materializer.py
    stmt52 = r_func.body[52]
    stmt_end = r_func.body[-1]
    exec_body = "".join(mat_lines[stmt52.lineno - 1:stmt_end.end_lineno])

    mat_code = f'''"""Top-level pipeline materializing the augmented skills graph ledger into SQLite."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from apps_rg.fact_inventory.graph_sqlite_path_index import (
    compute_sqlite_graph_digest,
    compute_sqlite_schema_digest,
    require_graphdb_capability_schema,
    validate_graphdb_capability_integrity,
)
from .schema import DDL_STATEMENTS
from .constants import C03_SQLITE_MATERIALIZER_CODE_VERSION
from . import storage
from .storage import (
    _acquire_sqlite_maintenance_lock,
    _cleanup_temp_sqlite,
    _new_sibling_temp_db_path,
    _release_sqlite_maintenance_lock,
    _require_sidecar_free_atomic_target,
    _sqlite_projection_digest,
)
from .materializer_ingress import run_materializer_ingress
from .materializer_indexing import run_materializer_indexing

def _get_open_isolated_temp_graph_sqlite():
    facade = sys.modules.get("apps_rg.fact_inventory.augmented_skills_graph_sqlite")
    return getattr(facade, "_open_isolated_temp_graph_sqlite", storage._open_isolated_temp_graph_sqlite)

def _get_replace_sqlite_projection_if_unchanged():
    facade = sys.modules.get("apps_rg.fact_inventory.augmented_skills_graph_sqlite")
    return getattr(facade, "_replace_sqlite_projection_if_unchanged", storage._replace_sqlite_projection_if_unchanged)

def materialize_augmented_skills_graph_sqlite(
    *,
    graph: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    db_path: Path | None = None,
    json_source_path: Path | None = None,
) -> dict[str, Any]:
    """Build SQLite DB from augmented skills graph JSON. Returns materialization summary."""
    _open_isolated_temp_graph_sqlite = _get_open_isolated_temp_graph_sqlite()
    _replace_sqlite_projection_if_unchanged = _get_replace_sqlite_projection_if_unchanged()

    ctx = run_materializer_ingress(
        graph=graph,
        repo_root=repo_root,
        db_path=db_path,
        json_source_path=json_source_path,
    )
    run_materializer_indexing(ctx)

    out_path = ctx["out_path"]
    node_rows = ctx["node_rows"]
    edge_rows = ctx["edge_rows"]
    skill_fact_rows = ctx["skill_fact_rows"]
    section_rows = ctx["section_rows"]
    selection_feature_rows = ctx["selection_feature_rows"]
    role_family_skill_weight_rows = ctx["role_family_skill_weight_rows"]
    projection_rows = ctx["projection_rows"]
    graph_index_rows = ctx["graph_index_rows"]
    summary = ctx["summary"]
    ledger_hash = ctx["ledger_hash"]
    gver = ctx["gver"]
    src_path = ctx["src_path"]
    ts = ctx["ts"]
    root = ctx["root"]

{exec_body}

__all__ = ["materialize_augmented_skills_graph_sqlite"]
'''
    (PKG_DIR / "materializer.py").write_text(mat_code, encoding="utf-8")

    # 10. validation.py
    val_funcs = [
        "validate_materialized_sqlite",
        "validate_hardened_materialized_sqlite",
    ]
    val_code = f'''"""Database validation and constraint verification for materialized SQLite."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from apps_rg.fact_inventory.augmented_skills_graph import load_augmented_skills_graph
from apps_rg.fact_inventory.graph_sqlite_path_index import (
    validate_graphdb_capability_integrity,
)
from .schema import EPOCH_ORDINAL
from .constants import CONFIDENCE_GRADE_RANK
from .promotions import load_candidate_fact_promotion_registry, resolve_confidence_grade
from .graph_builder import collect_graph_counts
from .storage import (
    _repo_root,
    default_graph_sqlite_path,
    load_graph_metadata_row,
    open_graph_sqlite,
)

{chr(10).join(funcs[name] for name in val_funcs)}

__all__ = {val_funcs!r}
'''
    (PKG_DIR / "validation.py").write_text(val_code, encoding="utf-8")

    # 11. query.py
    query_code = f'''"""Authoritative query and career phase traversal over materialized skills graph."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .schema import EMPLOYMENT_PHASES, EPOCH_LABELS, EPOCH_ORDINAL, ORDINAL_TO_EPOCH
from .constants import CONFIDENCE_GRADE_RANK, canonical_career_epoch_and_ordinal
from .storage import open_graph_sqlite

{funcs["get_skills_by_career_phase"]}

__all__ = ["get_skills_by_career_phase"]
'''
    (PKG_DIR / "query.py").write_text(query_code, encoding="utf-8")

    # 12. __init__.py
    init_code = '''"""Modular skills graph SQLite package."""
from __future__ import annotations

from .schema import *
from .constants import *
from .storage import *
from .classification import *
from .promotions import *
from .graph_builder import *
from .materializer_ingress import *
from .materializer_indexing import *
from .materializer import *
from .validation import *
from .query import *
'''
    (PKG_DIR / "__init__.py").write_text(init_code, encoding="utf-8")

    # 13. augmented_skills_graph_sqlite.py facade
    facade_code = '''"""Materialize augmented_skills_graph (JSON ledger) into SQLite for C0.3 context lookup.

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
'''
    SOURCE_FILE.write_text(facade_code, encoding="utf-8")

    print("Skills graph decomposition complete! Line counts:")
    all_ok = True
    for py_file in sorted(PKG_DIR.glob("*.py")):
        loc = len(py_file.read_text(encoding="utf-8").splitlines())
        status = "OK" if loc <= 600 else "EXCEEDS 600"
        if loc > 600:
            all_ok = False
        print(f"  {py_file.name:30s}: {loc:4d} lines [{status}]")
    facade_loc = len(SOURCE_FILE.read_text(encoding="utf-8").splitlines())
    facade_status = "OK" if facade_loc <= 600 else "EXCEEDS 600"
    print(f"  {'augmented_skills_graph_sqlite.py':30s}: {facade_loc:4d} lines [{facade_status}]")
    assert all_ok, "Some skills_graph files exceed 600 LOC!"
    assert facade_loc <= 600, "augmented_skills_graph_sqlite.py exceeds 600 LOC!"
    print("All file budget assertions passed!")

if __name__ == "__main__":
    main()
