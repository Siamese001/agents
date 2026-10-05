"""Top-level pipeline materializing the augmented skills graph ledger into SQLite."""
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
from .lineage import validate_projection_source_authorities
from .edge_evidence import calibrate_edge_confidence, extract_edge_evidence
from .type_registry import (
    compute_type_registry_digest,
    get_edge_type_registry_rows,
    get_node_type_registry_rows,
)
from apps_rg.fact_inventory.semantic_units import populate_semantic_units

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
    build_run_id = ctx.get("build_run_id", "")
    builder_git_commit = ctx.get("builder_git_commit", "")
    build_inputs = ctx.get("build_inputs", [])
    semantic_contract_version = ctx.get("semantic_contract_version", "")

    maintenance_lock = _acquire_sqlite_maintenance_lock(out_path)
    expected_target_digest = _sqlite_projection_digest(out_path)
    try:
        _require_sidecar_free_atomic_target(out_path)
    except (OSError, RuntimeError):
        _release_sqlite_maintenance_lock(maintenance_lock)
        raise
    try:
        temp_path = _new_sibling_temp_db_path(out_path)
    except OSError:
        _release_sqlite_maintenance_lock(maintenance_lock)
        raise
    build_succeeded = False
    try:
        conn = _open_isolated_temp_graph_sqlite(
            temp_path=temp_path,
            canonical_target=out_path,
        )
    except (OSError, RuntimeError, sqlite3.Error):
        _cleanup_temp_sqlite(temp_path)
        _release_sqlite_maintenance_lock(maintenance_lock)
        raise
    try:
        for stmt in DDL_STATEMENTS:
            conn.execute(stmt)

        conn.executemany(
            """
            INSERT INTO node_type_registry (
                node_type, layer, description, is_canonical, is_traversable
            ) VALUES (
                :node_type, :layer, :description, :is_canonical, :is_traversable
            )
            """,
            get_node_type_registry_rows(),
        )
        conn.executemany(
            """
            INSERT INTO edge_type_registry (
                edge_type, src_type, tgt_type, assertion_type, layer,
                traversable, inverse_label, cardinality
            ) VALUES (
                :edge_type, :src_type, :tgt_type, :assertion_type, :layer,
                :traversable, :inverse_label, :cardinality
            )
            """,
            get_edge_type_registry_rows(),
        )

        for nr in node_rows.values():
            nr.setdefault("career_epoch", "")
            nr.setdefault("phase_ordinal", None)
            nr.setdefault("title", "")
            nr.setdefault("operating_context", "")
            nr.setdefault("employer", "")
            nr.setdefault("start_date", "")
            nr.setdefault("end_date", "")
            nr.setdefault("is_current", 0)
            nr.setdefault("origin_kind", "ledger_node")
            nr.setdefault("origin_ref", nr.get("node_id", ""))
            nr.setdefault("source_refs_json", "[]")
            nr.setdefault("authority_refs_json", "[]")
            nr.setdefault("build_run_id", build_run_id)

        node_types_by_id = {nid: str(r.get("node_type") or "") for nid, r in node_rows.items()}
        node_scores_by_id = {nid: r.get("confidence_score") for nid, r in node_rows.items()}
        all_edge_evidence_rows: list[dict[str, Any]] = []

        for er in edge_rows:
            er.setdefault("traversable", 1)
            ev_rows = extract_edge_evidence(
                er,
                node_types_by_id=node_types_by_id,
            )
            src_score = node_scores_by_id.get(str(er.get("source_node_id") or ""))
            calibrate_edge_confidence(er, ev_rows, source_node_score=src_score)
            all_edge_evidence_rows.extend(ev_rows)

        conn.executemany(
            """
            INSERT INTO graph_nodes (
                node_id, node_type, label, description, activation_status, support_level,
                confidence, confidence_score, confidence_tier, external_eligible,
                career_epoch, phase_ordinal,
                title, operating_context, employer, start_date, end_date, is_current,
                source_authority, origin_kind, origin_ref, source_refs_json,
                authority_refs_json, build_run_id, created_at, updated_at
            ) VALUES (
                :node_id, :node_type, :label, :description, :activation_status, :support_level,
                :confidence, :confidence_score, :confidence_tier, :external_eligible,
                :career_epoch, :phase_ordinal,
                :title, :operating_context, :employer, :start_date, :end_date, :is_current,
                :source_authority, :origin_kind, :origin_ref, :source_refs_json,
                :authority_refs_json, :build_run_id, :created_at, :updated_at
            )
            """,
            list(node_rows.values()),
        )
        conn.executemany(
            """
            INSERT INTO graph_edges (
                edge_id, source_node_id, target_node_id, edge_family, edge_type, weight,
                confidence, directional, evidence_status, section_fit, source_authority,
                rationale, projection_behavior, external_claim_policy, validation_status,
                edge_note, operator_note, business_story, technical_story,
                assertion_type, assertion_basis, assertion_basis_refs_json,
                canonical_assertion_text, lifecycle_disposition, semantic_contract_version,
                origin_kind, origin_ref, origin_artifact_sha256, derivation_rule_id,
                build_run_id, confidence_score, confidence_tier, confidence_method,
                traversable
            ) VALUES (
                :edge_id, :source_node_id, :target_node_id, :edge_family, :edge_type, :weight,
                :confidence, :directional, :evidence_status, :section_fit, :source_authority,
                :rationale, :projection_behavior, :external_claim_policy, :validation_status,
                :edge_note, :operator_note, :business_story, :technical_story,
                :assertion_type, :assertion_basis, :assertion_basis_refs_json,
                :canonical_assertion_text, :lifecycle_disposition, :semantic_contract_version,
                :origin_kind, :origin_ref, :origin_artifact_sha256, :derivation_rule_id,
                :build_run_id, :confidence_score, :confidence_tier, :confidence_method,
                :traversable
            )
            """,
            edge_rows,
        )
        conn.executemany(
            """
            INSERT INTO edge_evidence (
                edge_id, evidence_ref, evidence_node_id, evidence_kind,
                is_independent, source_doc, span, quote_sha256,
                human_confirmed, evidence_strength
            ) VALUES (
                :edge_id, :evidence_ref, :evidence_node_id, :evidence_kind,
                :is_independent, :source_doc, :span, :quote_sha256,
                :human_confirmed, :evidence_strength
            )
            """,
            all_edge_evidence_rows,
        )
        conn.executemany(
            """
            INSERT INTO skill_fact_links (
                skill_id, fact_id, support_level, claim_eligibility, source_trace,
                archive_trace, human_confirmed, external_eligible
            ) VALUES (
                :skill_id, :fact_id, :support_level, :claim_eligibility, :source_trace,
                :archive_trace, :human_confirmed, :external_eligible
            )
            """,
            skill_fact_rows,
        )
        conn.executemany(
            """
            INSERT INTO section_eligibility (
                node_id, section_id, allowed, claim_policy, reason, blocked_reason
            ) VALUES (
                :node_id, :section_id, :allowed, :claim_policy, :reason, :blocked_reason
            )
            """,
            section_rows,
        )
        conn.executemany(
            """
            INSERT INTO role_family_projection (
                role_family_id, projection_role_family_key, track_weight_profile,
                taxonomy_source, targeting_keywords, proof_policy_note
            ) VALUES (
                :role_family_id, :projection_role_family_key, :track_weight_profile,
                :taxonomy_source, :targeting_keywords, :proof_policy_note
            )
            """,
            projection_rows,
        )
        conn.executemany(
            """
            INSERT INTO c03_skill_selection_features (
                skill_id, pillar, subpillar, domain_id, career_track_id, career_epoch,
                phase_ordinal, skill_family, metric_bucket, role_family_weights,
                allowed_sections, source_fact_count, confidence, confidence_score,
                confidence_tier, activation_status,
                support_level, external_eligible, source_authority, source_trace, updated_at
            ) VALUES (
                :skill_id, :pillar, :subpillar, :domain_id, :career_track_id, :career_epoch,
                :phase_ordinal, :skill_family, :metric_bucket, :role_family_weights,
                :allowed_sections, :source_fact_count, :confidence, :confidence_score,
                :confidence_tier, :activation_status,
                :support_level, :external_eligible, :source_authority, :source_trace, :updated_at
            )
            """,
            selection_feature_rows,
        )
        conn.executemany(
            """
            INSERT INTO c03_role_family_skill_weights (
                skill_id, role_family_key, weight, source
            ) VALUES (
                :skill_id, :role_family_key, :weight, :source
            )
            """,
            role_family_skill_weight_rows,
        )
        conn.executemany(
            """
            INSERT INTO graph_paths (
                path_id, start_node_id, end_node_id, path_depth, path_signature,
                node_path_json, edge_path_json, edge_types_json, proof_fact_ids_json,
                metric_ids_json, section_ids_json, path_score, novelty_score,
                proof_strength_score, build_run_id, created_at
            ) VALUES (
                :path_id, :start_node_id, :end_node_id, :path_depth, :path_signature,
                :node_path_json, :edge_path_json, :edge_types_json, :proof_fact_ids_json,
                :metric_ids_json, :section_ids_json, :path_score, :novelty_score,
                :proof_strength_score, :build_run_id, :created_at
            )
            """,
            graph_index_rows["graph_paths"],
        )
        conn.executemany(
            """
            INSERT INTO graph_neighborhoods (
                center_node_id, neighbor_node_id, distance, connecting_path_json,
                edge_types_json, edge_ids_json, relationship_summary, neighbor_score,
                build_run_id
            ) VALUES (
                :center_node_id, :neighbor_node_id, :distance, :connecting_path_json,
                :edge_types_json, :edge_ids_json, :relationship_summary, :neighbor_score,
                :build_run_id
            )
            """,
            graph_index_rows["graph_neighborhoods"],
        )
        conn.executemany(
            """
            INSERT INTO graph_sibling_links (
                node_id, sibling_node_id, sibling_reason, shared_parent_node_id,
                shared_edge_type, parent_edge_id, sibling_edge_id, derivation_rule_id,
                sibling_score, build_run_id
            ) VALUES (
                :node_id, :sibling_node_id, :sibling_reason, :shared_parent_node_id,
                :shared_edge_type, :parent_edge_id, :sibling_edge_id, :derivation_rule_id,
                :sibling_score, :build_run_id
            )
            """,
            graph_index_rows["graph_sibling_links"],
        )
        conn.executemany(
            """
            INSERT INTO section_evidence_budget (
                section_id, role_family_key, max_metric_reuse, max_fact_family_reuse,
                required_node_types_json, preferred_edge_types_json,
                forbidden_metric_ids_json, preferred_metric_families_json
            ) VALUES (
                :section_id, :role_family_key, :max_metric_reuse, :max_fact_family_reuse,
                :required_node_types_json, :preferred_edge_types_json,
                :forbidden_metric_ids_json, :preferred_metric_families_json
            )
            """,
            graph_index_rows["section_evidence_budget"],
        )
        conn.execute(
            """
            INSERT INTO graph_build_runs (
                build_run_id, built_at, builder_git_commit, input_manifest_digest,
                semantic_contract_version, node_count, edge_count, path_count,
                neighborhood_count, sibling_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                build_run_id,
                ts,
                builder_git_commit,
                ctx.get("input_manifest_digest", ""),
                semantic_contract_version,
                len(node_rows),
                len(edge_rows),
                len(graph_index_rows["graph_paths"]),
                len(graph_index_rows["graph_neighborhoods"]),
                len(graph_index_rows["graph_sibling_links"]),
            ),
        )
        conn.executemany(
            """
            INSERT INTO graph_build_inputs (
                build_run_id, input_role, artifact_relpath, artifact_sha256, record_count
            ) VALUES (
                :build_run_id, :input_role, :artifact_relpath, :artifact_sha256, :record_count
            )
            """,
            build_inputs,
        )
        summary["build_run_id"] = build_run_id
        summary["builder_git_commit"] = builder_git_commit
        summary["semantic_contract_version"] = semantic_contract_version
        summary["canonical_graph_digest"] = ledger_hash
        summary["canonical_digest_kind"] = "canonical_payload_v1"
        summary["sqlite_graph_digest"] = compute_sqlite_graph_digest(conn)
        summary["sqlite_schema_digest"] = compute_sqlite_schema_digest(conn)
        summary["input_manifest_digest"] = ctx.get("input_manifest_digest", "")
        summary["type_registry_digest"] = compute_type_registry_digest()
        summary["edge_evidence_count"] = len(all_edge_evidence_rows)
        unit_summary = populate_semantic_units(
            conn,
            build_run_id=build_run_id,
            input_manifest_digest=summary["input_manifest_digest"],
        )
        summary.update(unit_summary)
        conn.execute(
            """
            INSERT INTO graph_metadata (
                graph_version, materialized_from, materialized_at, ledger_hash,
                graph_count_summary, authority_status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                gver,
                str(src_path.relative_to(root)) if src_path.is_relative_to(root) else str(src_path),
                ts,
                ledger_hash,
                json.dumps(summary, sort_keys=True),
                "augmented_skills_graph_authoritative",
            ),
        )
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()
        validate_projection_source_authorities(conn)
        require_graphdb_capability_schema(conn)
        validate_graphdb_capability_integrity(
            conn,
            expected_materializer_version=C03_SQLITE_MATERIALIZER_CODE_VERSION,
        )
        build_succeeded = True
    finally:
        conn.close()
        if not build_succeeded:
            _cleanup_temp_sqlite(temp_path)
            _release_sqlite_maintenance_lock(maintenance_lock)

    try:
        _replace_sqlite_projection_if_unchanged(
            target=out_path,
            replacement=temp_path,
            expected_digest=expected_target_digest,
        )
    except (OSError, RuntimeError):
        _cleanup_temp_sqlite(temp_path)
        raise
    finally:
        _release_sqlite_maintenance_lock(maintenance_lock)

    return {
        "sqlite_db_path": str(out_path),
        "graph_version": gver,
        "graph_hash": ledger_hash,
        "materialized_at": ts,
        "materialized_from": str(src_path),
        **summary,
        "tables_created": [
            "graph_nodes",
            "graph_edges",
            "skill_fact_links",
            "section_eligibility",
            "role_family_projection",
            "c03_skill_selection_features",
            "c03_role_family_skill_weights",
            "graph_paths",
            "graph_neighborhoods",
            "graph_sibling_links",
            "graph_build_runs",
            "graph_build_inputs",
            "edge_evidence",
            "resume_metric_usage",
            "section_evidence_budget",
            "graph_selection_rejections",
            "graph_edges_reverse",
            "v_partner_architecture_competency_candidates",
            "graph_metadata",
        ],
    }


__all__ = ["materialize_augmented_skills_graph_sqlite"]


if __name__ == "__main__":
    result = materialize_augmented_skills_graph_sqlite()
    print("Materialization complete:", result.get("sqlite_db_path"))
