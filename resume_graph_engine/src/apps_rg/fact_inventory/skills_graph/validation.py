"""Database validation and constraint verification for materialized SQLite."""
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

def validate_materialized_sqlite(
    *,
    graph: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Integrity checks: counts, duplicate IDs, FK-like edge/link refs."""
    root = repo_root or _repo_root()
    payload = graph or load_augmented_skills_graph(repo_root=root)
    path = db_path or default_graph_sqlite_path(root)
    if not path.is_file():
        return {"status": "FAIL", "reason": "sqlite_missing", "sqlite_db_path": str(path)}

    from apps_rg.fact_inventory.graph_sqlite_path_index import (
        SIBLING_NODE_TYPES,
        SKILL_FACT_EVIDENCE_NODE_TYPES,
    )

    sibling_node_types_sql = ",".join(f"'{node_type}'" for node_type in sorted(SIBLING_NODE_TYPES))
    evidence_node_types_sql = ",".join(
        f"'{node_type}'" for node_type in sorted(SKILL_FACT_EVIDENCE_NODE_TYPES)
    )

    gm = payload.get("graph_metadata") if isinstance(payload.get("graph_metadata"), dict) else {}
    expected_nodes = int(gm.get("node_count") or 0)
    expected_edges_meta = int(gm.get("edge_count") or 0)
    expected_edges = (
        len(
            {
                str(e.get("edge_id"))
                for e in payload.get("graph_edges") or []
                if isinstance(e, dict) and e.get("edge_id")
            }
        )
        or expected_edges_meta
    )

    conn = open_graph_sqlite(repo_root=root, db_path=path)
    try:
        meta = load_graph_metadata_row(conn)
        meta_summary = (
            meta.get("graph_count_summary") if isinstance(meta.get("graph_count_summary"), dict) else {}
        )
        expected_edges = int(meta_summary.get("edge_count_sqlite") or expected_edges)
        node_count = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
        dup_nodes = conn.execute(
            "SELECT node_id, COUNT(*) c FROM graph_nodes GROUP BY node_id HAVING c > 1"
        ).fetchall()
        dup_edges = conn.execute(
            "SELECT edge_id, COUNT(*) c FROM graph_edges GROUP BY edge_id HAVING c > 1"
        ).fetchall()
        broken_edges = conn.execute(
            """
            SELECT e.edge_id, e.source_node_id, e.target_node_id FROM graph_edges e
            LEFT JOIN graph_nodes s ON s.node_id = e.source_node_id
            LEFT JOIN graph_nodes t ON t.node_id = e.target_node_id
            WHERE s.node_id IS NULL OR t.node_id IS NULL
            """
        ).fetchall()
        dup_triple = conn.execute(
            """
            SELECT source_node_id, target_node_id, edge_type, COUNT(*) c
            FROM graph_edges
            GROUP BY source_node_id, target_node_id, edge_type
            HAVING c > 1
            """
        ).fetchall()
        node_type_eq_id = conn.execute("SELECT node_id FROM graph_nodes WHERE node_type = node_id").fetchall()
        bogus_skill_nodes = conn.execute(
            """
            SELECT node_id FROM graph_nodes
            WHERE node_id IN ('skill_id_never_source_fact_id', 'skill_projection_not_proof')
            """
        ).fetchall()
        draft_external = conn.execute(
            """
            SELECT node_id, activation_status FROM graph_nodes
            WHERE node_type = 'skill' AND external_eligible = 1
              AND activation_status IN (
                'DRAFT','INTERNAL_ONLY','USER_CONFIRMED_PENDING_SOURCE',
                'DO_NOT_PROMOTE','BLOCKED'
              )
            """
        ).fetchall()
        active_ext_no_link = conn.execute(
            """
            SELECT n.node_id FROM graph_nodes n
            WHERE n.node_type = 'skill' AND n.external_eligible = 1
              AND n.activation_status IN ('ACTIVE','ACTIVE_CONFIRMED')
              AND NOT EXISTS (
                SELECT 1 FROM skill_fact_links l WHERE l.skill_id = n.node_id
              )
            """
        ).fetchall()
        exec_summary_bad = conn.execute(
            """
            SELECT se.node_id, se.allowed, se.blocked_reason, n.confidence, n.support_level
            FROM section_eligibility se
            JOIN graph_nodes n ON n.node_id = se.node_id
            WHERE se.section_id = 'executive_summary' AND se.allowed = 1
              AND n.node_type = 'skill'
              AND (
                n.confidence IS NULL OR n.confidence = '' OR n.confidence = 'MEDIUM'
                OR n.confidence NOT IN ('HIGH')
              )
            """
        ).fetchall()
        exec_summary_medium_allowed = conn.execute(
            """
            SELECT node_id FROM section_eligibility
            WHERE section_id = 'executive_summary' AND allowed = 1
              AND claim_policy LIKE '%medium%'
              AND claim_policy NOT LIKE '%hitl_approved%'
            """
        ).fetchall()
        broad_ref = conn.execute(
            """
            SELECT node_id FROM graph_nodes
            WHERE source_authority LIKE '%broad_skills_ledger%'
            """
        ).fetchall()
        exec_summary_non_high_blocked = conn.execute(
            """
            SELECT se.node_id, n.confidence FROM section_eligibility se
            JOIN graph_nodes n ON n.node_id = se.node_id
            WHERE se.section_id = 'executive_summary' AND se.allowed = 1
              AND n.node_type = 'skill'
              AND n.confidence IN ('MEDIUM', 'LOW', 'BLOCKED')
            """
        ).fetchall()
        broken_links = conn.execute(
            f"""
            SELECT l.skill_id, l.fact_id FROM skill_fact_links l
            LEFT JOIN graph_nodes sk ON sk.node_id = l.skill_id
            LEFT JOIN graph_nodes fa ON fa.node_id = l.fact_id
            WHERE sk.node_id IS NULL OR sk.node_type <> 'skill'
               OR fa.node_id IS NULL
               OR fa.node_type NOT IN ({evidence_node_types_sql})
            """
        ).fetchall()
        broken_selection_features = conn.execute(
            """
            SELECT f.skill_id FROM c03_skill_selection_features f
            LEFT JOIN graph_nodes n ON n.node_id = f.skill_id AND n.node_type = 'skill'
            WHERE n.node_id IS NULL
            """
        ).fetchall()
        blank_metric_buckets = conn.execute(
            """
            SELECT skill_id FROM c03_skill_selection_features
            WHERE metric_bucket IS NULL OR metric_bucket = ''
            """
        ).fetchall()
        validated_edges_missing_rationale = conn.execute(
            """
            SELECT edge_id FROM graph_edges
            WHERE LOWER(validation_status) = 'validated'
              AND COALESCE(rationale, '') = ''
            """
        ).fetchall()
        broken_paths = conn.execute(
            """
            SELECT p.path_id FROM graph_paths p
            LEFT JOIN graph_nodes s ON s.node_id = p.start_node_id
            LEFT JOIN graph_nodes e ON e.node_id = p.end_node_id
            WHERE s.node_id IS NULL OR e.node_id IS NULL
            """
        ).fetchall()
        broken_siblings = conn.execute(
            f"""
            SELECT s.node_id, s.sibling_node_id FROM graph_sibling_links s
            LEFT JOIN graph_nodes n
              ON n.node_id = s.node_id
             AND n.node_type IN ({sibling_node_types_sql})
            LEFT JOIN graph_nodes p
              ON p.node_id = s.sibling_node_id
             AND p.node_type IN ({sibling_node_types_sql})
            WHERE n.node_id IS NULL OR p.node_id IS NULL
            """
        ).fetchall()
        skill_fact_count = conn.execute("SELECT COUNT(*) FROM skill_fact_links").fetchone()[0]
        section_elig_count = conn.execute("SELECT COUNT(*) FROM section_eligibility").fetchone()[0]
        rf_count = conn.execute("SELECT COUNT(*) FROM role_family_projection").fetchone()[0]
        c03_feature_count = conn.execute("SELECT COUNT(*) FROM c03_skill_selection_features").fetchone()[0]
        c03_role_weight_count = conn.execute("SELECT COUNT(*) FROM c03_role_family_skill_weights").fetchone()[
            0
        ]
        graph_path_count = conn.execute("SELECT COUNT(*) FROM graph_paths").fetchone()[0]
        graph_neighborhood_count = conn.execute("SELECT COUNT(*) FROM graph_neighborhoods").fetchone()[0]
        graph_sibling_link_count = conn.execute("SELECT COUNT(*) FROM graph_sibling_links").fetchone()[0]
        section_budget_count = conn.execute("SELECT COUNT(*) FROM section_evidence_budget").fetchone()[0]
        epoch_nodes = conn.execute(
            """
            SELECT node_id, activation_status, confidence, phase_ordinal
            FROM graph_nodes
            WHERE node_type = 'career_epoch'
            """
        ).fetchall()
        skills_missing_phase = conn.execute(
            """
            SELECT skill_id FROM c03_skill_selection_features
            WHERE (phase_ordinal IS NULL OR phase_ordinal NOT BETWEEN 1 AND 6)
              AND career_epoch <> 'cross_career'
            """
        ).fetchall()
    finally:
        conn.close()

    issues: list[str] = []
    found_epoch_ids = set()
    for eid, act, conf, ord_val in epoch_nodes:
        found_epoch_ids.add(eid)
        if eid in EPOCH_ORDINAL:
            if act != "ACTIVE":
                issues.append(f"epoch_node_not_active:{eid}:{act}")
            if conf != "HIGH":
                issues.append(f"epoch_node_not_high_confidence:{eid}:{conf}")
            if ord_val != EPOCH_ORDINAL[eid]:
                issues.append(f"epoch_node_ordinal_mismatch:{eid}:{ord_val}!={EPOCH_ORDINAL[eid]}")
    missing_epochs = set(EPOCH_ORDINAL) - found_epoch_ids
    if missing_epochs:
        issues.append(f"missing_canonical_epochs:{sorted(missing_epochs)}")
    if skills_missing_phase:
        issues.append(f"skills_missing_phase_ordinal:{len(skills_missing_phase)}")
    if dup_nodes:
        issues.append(f"duplicate_node_ids:{len(dup_nodes)}")
    if dup_edges:
        issues.append(f"duplicate_edge_ids:{len(dup_edges)}")
    if dup_triple:
        issues.append(f"duplicate_edge_triples:{len(dup_triple)}")
    if broken_edges:
        issues.append(f"broken_edge_refs:{len(broken_edges)}")
    if broken_links:
        issues.append(f"broken_skill_fact_links:{len(broken_links)}")
    if broken_selection_features:
        issues.append(f"broken_c03_skill_selection_features:{len(broken_selection_features)}")
    if blank_metric_buckets:
        issues.append(f"blank_c03_metric_buckets:{len(blank_metric_buckets)}")
    if validated_edges_missing_rationale:
        issues.append(f"validated_edges_missing_rationale:{len(validated_edges_missing_rationale)}")
    if broken_paths:
        issues.append(f"broken_graph_paths:{len(broken_paths)}")
    if broken_siblings:
        issues.append(f"broken_graph_sibling_links:{len(broken_siblings)}")
    if node_type_eq_id:
        issues.append(f"node_type_equals_node_id:{len(node_type_eq_id)}")
    if bogus_skill_nodes:
        issues.append(f"bogus_policy_skill_nodes:{len(bogus_skill_nodes)}")
    if draft_external:
        issues.append(f"draft_external_eligible:{len(draft_external)}")
    if active_ext_no_link:
        issues.append(f"active_external_without_fact_link:{len(active_ext_no_link)}")
    if exec_summary_bad:
        issues.append(f"executive_summary_non_high_allowed:{len(exec_summary_bad)}")
    if exec_summary_medium_allowed:
        issues.append(f"executive_summary_medium_without_hitl:{len(exec_summary_medium_allowed)}")
    if exec_summary_non_high_blocked:
        issues.append(f"executive_summary_non_high_grade_allowed:{len(exec_summary_non_high_blocked)}")
    if broad_ref:
        issues.append(f"broad_skills_ledger_authority_leak:{len(broad_ref)}")
    if edge_count != expected_edges:
        issues.append(f"edge_count_mismatch:{edge_count}!={expected_edges}")

    status = "PASS" if not issues else "FAIL"
    return {
        "status": status,
        "issues": issues,
        "sqlite_db_path": str(path),
        "graph_version": meta["graph_version"],
        "graph_hash": meta["ledger_hash"],
        "c03_sqlite_materializer_code_version": meta_summary.get("c03_sqlite_materializer_code_version"),
        "node_count": node_count,
        "edge_count": edge_count,
        "expected_node_count_json": expected_nodes,
        "expected_edge_count_json": expected_edges,
        "expected_edge_count_metadata": expected_edges_meta,
        "skill_fact_link_count": skill_fact_count,
        "section_eligibility_count": section_elig_count,
        "role_family_projection_count": rf_count,
        "c03_skill_selection_feature_count": c03_feature_count,
        "c03_role_family_skill_weight_count": c03_role_weight_count,
        "graph_path_count": graph_path_count,
        "graph_neighborhood_count": graph_neighborhood_count,
        "graph_sibling_link_count": graph_sibling_link_count,
        "section_evidence_budget_count": section_budget_count,
        "validated_edges_missing_rationale_count": len(validated_edges_missing_rationale),
        "broad_skills_ledger_status": "non_authority",
        "dup_triple_count": len(dup_triple),
        "orphan_edge_count": len(broken_edges),
    }

def validate_hardened_materialized_sqlite(
    *,
    graph: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Strict post-harden validation with SQL assertions required by materialization receipt."""
    root = repo_root or _repo_root()
    payload = graph or load_augmented_skills_graph(repo_root=root)
    base = validate_materialized_sqlite(graph=payload, repo_root=root, db_path=db_path)
    path = Path(str(base["sqlite_db_path"]))
    conn = open_graph_sqlite(repo_root=root, db_path=path)
    try:
        counts = {
            "nodes": conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0],
            "edges": conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0],
            "pillars": conn.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE node_type IN ('pillar','capability_domain')"
            ).fetchone()[0],
            "skills": conn.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_type = 'skill'").fetchone()[
                0
            ],
            "active_skills": conn.execute(
                """
                SELECT COUNT(*) FROM graph_nodes
                WHERE node_type='skill' AND activation_status IN ('ACTIVE','ACTIVE_CONFIRMED')
                """
            ).fetchone()[0],
            "draft_skills": conn.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE node_type='skill' AND activation_status='DRAFT'"
            ).fetchone()[0],
            "phase_bridges": conn.execute(
                "SELECT COUNT(*) FROM graph_edges WHERE edge_type='pillar_phase_bridge'"
            ).fetchone()[0],
        }
        anthropic = conn.execute(
            """
            SELECT proof_policy_note, targeting_keywords FROM role_family_projection
            WHERE role_family_id = 'ANTHROPIC_PARTNERSHIPS_APPLIED_AI'
            """
        ).fetchone()
    finally:
        conn.close()

    p0_fixed = [
        "orphan_policy_targets_materialized",
        "canonical_node_type_inference",
        "bogus_policy_strings_not_skill_nodes",
        "executive_summary_high_confidence_gate",
    ]
    p1_fixed = [
        "dedupe_edge_id_and_triple",
        "external_eligible_requires_active_and_fact_link",
        "fact_ref_node_typing_exp_bul_cert",
        "anthropic_role_family_pillar_profile",
        "customer_stakeholder_cs_primary_guardrails",
        "airline_anchor_internal_only",
    ]
    conn = open_graph_sqlite(repo_root=root, db_path=path)
    try:
        exec_allowed_sample = conn.execute(
            """
            SELECT se.node_id, n.confidence, n.support_level, n.activation_status,
                   n.external_eligible,
                   (SELECT COUNT(*) FROM skill_fact_links l WHERE l.skill_id = n.node_id) AS fact_links
            FROM section_eligibility se
            JOIN graph_nodes n ON n.node_id = se.node_id
            WHERE se.section_id = 'executive_summary' AND se.allowed = 1
              AND n.node_type = 'skill'
            ORDER BY se.node_id
            LIMIT 25
            """
        ).fetchall()
        skill_support_dist = conn.execute(
            """
            SELECT support_level, COUNT(*) FROM graph_nodes
            WHERE node_type = 'skill' GROUP BY support_level ORDER BY 2 DESC
            """
        ).fetchall()
        skill_confidence_dist = conn.execute(
            """
            SELECT confidence, COUNT(*) FROM graph_nodes
            WHERE node_type = 'skill' GROUP BY confidence ORDER BY 2 DESC
            """
        ).fetchall()
        high_skill_count = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE node_type='skill' AND confidence='HIGH'"
        ).fetchone()[0]
        exec_allowed_count = conn.execute(
            """
            SELECT COUNT(*) FROM section_eligibility se
            JOIN graph_nodes n ON n.node_id = se.node_id
            WHERE se.section_id='executive_summary' AND se.allowed=1 AND n.node_type='skill'
            """
        ).fetchone()[0]
        forbidden_high = conn.execute(
            """
            SELECT node_id, activation_status, support_level FROM graph_nodes
            WHERE node_type='skill' AND confidence='HIGH'
              AND (
                activation_status IN (
                  'DRAFT','INTERNAL_ONLY','USER_CONFIRMED_PENDING_SOURCE'
                )
                OR support_level IN (
                  'REPO_EVIDENCE_PORTFOLIO','INTERNAL_ONLY',
                  'USER_CONFIRMED_PENDING_SOURCE'
                )
              )
            """
        ).fetchall()
        high_without_fact_link = conn.execute(
            """
            SELECT n.node_id FROM graph_nodes n
            WHERE n.node_type='skill' AND n.confidence='HIGH'
              AND NOT EXISTS (
                SELECT 1 FROM skill_fact_links l WHERE l.skill_id = n.node_id
              )
            """
        ).fetchall()
    finally:
        conn.close()

    override_violations: list[dict[str, Any]] = []
    registry = load_candidate_fact_promotion_registry(root)
    for row in payload.get("skill_rows") or []:
        if not isinstance(row, dict) or not row.get("skill_id"):
            continue
        resolved = resolve_confidence_grade(
            row,
            has_fact_link=bool(row.get("fact_id_links")),
            candidate_registry=registry,
        )
        derived = str(row.get("confidence_grade_derived") or resolved["derived_grade"] or "").upper()
        effective = str(row.get("confidence_grade") or resolved["effective_grade"] or "").upper()
        if (
            derived
            and effective
            and CONFIDENCE_GRADE_RANK.get(effective, -1) > CONFIDENCE_GRADE_RANK.get(derived, -1)
            and not resolved["human_confirmed_archive_promotion"]
        ):
            override_violations.append(
                {
                    "skill_id": row.get("skill_id"),
                    "derived": derived,
                    "effective": effective,
                    "reason": "effective_exceeds_derived_without_human_confirmation",
                }
            )

    issues = list(base.get("issues") or [])
    if high_skill_count > 0 and exec_allowed_count == 0:
        issues.append("executive_summary_allowed_empty_despite_high_skills")
    if anthropic and "hyperscaler_marketplace" not in str(anthropic[0]):
        issues.append("anthropic_profile_missing_marketplace_note")
    if anthropic and "pillar_applied_ai_partner_architecture" not in str(anthropic[1]):
        issues.append("anthropic_profile_missing_applied_ai_pillar")
    if forbidden_high:
        issues.append(f"forbidden_high_skill_promotions:{len(forbidden_high)}")
    if high_without_fact_link:
        issues.append(f"high_skills_without_fact_links:{len(high_without_fact_link)}")
    if override_violations:
        issues.append(f"confidence_override_without_human_confirm:{len(override_violations)}")

    status = "PASS" if not issues else "FAIL"
    return {
        **base,
        "status": status,
        "issues": issues,
        "confidence_override_guardrail": {
            "violations_count": len(override_violations),
            "violations_sample": override_violations[:10],
            "candidate_facts_do_not_auto_promote": True,
            "rule": (
                "explicit confidence_grade above derived requires human_confirmed_archive_promotion metadata"
            ),
        },
        "forbidden_high_skill_promotions": forbidden_high,
        "high_skills_without_fact_links": high_without_fact_link,
        "counts": counts,
        "counts_json": collect_graph_counts(payload),
        "p0_fixed": p0_fixed,
        "p1_fixed": p1_fixed,
        "next_blocker": issues[0] if issues else "none",
        "sql_validation_queries_run": [
            "orphan_edges_zero",
            "duplicate_edge_id_zero",
            "duplicate_edge_triple_zero",
            "node_type_not_equal_node_id",
            "no_bogus_policy_skill_nodes",
            "no_draft_external_eligible",
            "active_external_has_skill_fact_link",
            "executive_summary_high_confidence_grade_only",
            "executive_summary_medium_low_blocked",
            "no_broad_skills_ledger_authority",
            "no_forbidden_high_skill_promotions",
            "no_high_without_fact_links",
            "confidence_override_guardrail_enforced",
        ],
        "skill_support_level_dist": skill_support_dist,
        "skill_confidence_grade_dist": skill_confidence_dist,
        "executive_summary_allowed_count": exec_allowed_count,
        "executive_summary_allowed_sample": [
            {
                "node_id": r[0],
                "confidence_grade": r[1],
                "support_level": r[2],
                "activation_status": r[3],
                "external_eligible": r[4],
                "fact_link_count": r[5],
            }
            for r in exec_allowed_sample
        ],
        "high_skill_count": high_skill_count,
    }


__all__ = ['validate_materialized_sqlite', 'validate_hardened_materialized_sqlite']
