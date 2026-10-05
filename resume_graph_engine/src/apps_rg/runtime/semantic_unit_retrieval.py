"""Semantic-Unit Runtime Retrieval and Subgraph Expansion Engine.

Provides hybrid retrieval from semantic units back into traversable subgraphs
using the Wave 4 CTE traversal engine, with fail-closed freshness checks and
governed activation gate enforcement.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from apps_rg.runtime.graph_traversal import TraversalPath, traverse

ACTIVATION_STATUS_BLOCKED = "BLOCKED_HUMAN_REVIEW_INPUTS"
RUNTIME_AUTHORITATIVE_STORE = "semantic_unit_relational_projection"


class SemanticUnitError(RuntimeError):
    """Base error for semantic-unit runtime retrieval."""


class SemanticUnitStaleGraphError(SemanticUnitError):
    """Raised when semantic unit freshness digest does not match live graph digest."""


class SemanticUnitActivationBlockedError(SemanticUnitError):
    """Raised when un-reviewed semantic unit vectors are activated without review authority."""


def check_semantic_unit_freshness(conn: sqlite3.Connection) -> str:
    """Verify that stored semantic units match the current graph build digest."""
    cursor = conn.cursor()
    cursor.execute("SELECT graph_count_summary FROM graph_metadata ORDER BY rowid DESC LIMIT 1")
    row = cursor.fetchone()
    if not row or not row[0]:
        raise SemanticUnitStaleGraphError("graph_metadata is missing; cannot verify freshness")

    try:
        summary = json.loads(row[0])
    except Exception as exc:
        raise SemanticUnitStaleGraphError(f"corrupt graph_count_summary: {exc}") from exc

    expected_digest = summary.get("input_manifest_digest", "")

    cursor.execute("SELECT DISTINCT input_manifest_digest FROM semantic_unit")
    digests = [r[0] for r in cursor.fetchall() if r[0]]
    if not digests:
        raise SemanticUnitStaleGraphError("semantic_unit table is empty or missing digest")

    if any(d != expected_digest for d in digests):
        raise SemanticUnitStaleGraphError(
            f"semantic unit digest mismatch: expected '{expected_digest}', observed '{digests[0]}'"
        )

    return expected_digest


def assert_semantic_unit_activation_status(*, allow_unqualified: bool = False) -> dict[str, Any]:
    """Enforce fail-closed activation policy per W9 human review governance."""
    if not allow_unqualified:
        raise SemanticUnitActivationBlockedError(
            f"production activation is {ACTIVATION_STATUS_BLOCKED}: "
            "requires 912 primary human review inputs and 456 adjudications"
        )
    return {
        "status": ACTIVATION_STATUS_BLOCKED,
        "runtime_authoritative_store": RUNTIME_AUTHORITATIVE_STORE,
        "is_unqualified_override": True,
    }


def retrieve_semantic_units(
    conn: sqlite3.Connection,
    *,
    unit_type: str | None = None,
    section_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Retrieve semantic units matching optional unit_type and section filters."""
    check_semantic_unit_freshness(conn)
    cursor = conn.cursor()
    query = """
        SELECT unit_id, unit_type, root_node_id, template_version, text,
               text_sha256, confidence_tier, min_confidence, allowed_sections_json
        FROM semantic_unit
        WHERE external_eligible = 1
    """
    params: list[Any] = []
    if unit_type:
        query += " AND unit_type = ?"
        params.append(unit_type)
    query += " ORDER BY min_confidence DESC, unit_id LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    results: list[dict[str, Any]] = []

    for r in rows:
        allowed_sections = []
        try:
            allowed_sections = json.loads(r[8]) if r[8] else []
        except Exception:
            pass

        if section_id and allowed_sections and section_id not in allowed_sections:
            continue

        results.append(
            {
                "unit_id": r[0],
                "unit_type": r[1],
                "root_node_id": r[2],
                "template_version": r[3],
                "text": r[4],
                "text_sha256": r[5],
                "confidence_tier": r[6],
                "min_confidence": r[7],
                "allowed_sections": allowed_sections,
            }
        )

    return results


def expand_semantic_unit_subgraph(
    conn: sqlite3.Connection,
    unit_id: str,
) -> dict[str, Any]:
    """Expand a semantic unit back into traversable subgraphs via traverse()."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT member_kind, member_id, role
        FROM semantic_unit_member
        WHERE unit_id = ?
        ORDER BY member_kind, member_id
        """,
        (unit_id,),
    )
    members = cursor.fetchall()
    if not members:
        raise SemanticUnitError(f"semantic unit not found: {unit_id}")

    cursor.execute("SELECT unit_type, root_node_id FROM semantic_unit WHERE unit_id = ?", (unit_id,))
    unit_info = cursor.fetchone()
    unit_type, root_node_id = (unit_info[0], unit_info[1]) if unit_info else ("", "")

    node_members = [m[1] for m in members if m[0] == "node"]
    edge_members = [m[1] for m in members if m[0] == "edge"]
    evidence_ids = [m[1] for m in members if m[0] == "evidence"]

    paths: list[TraversalPath] = []
    if unit_type == "skill_evidence_cluster":
        # Journey 1: skill -> fact -> metric -> employer
        steps_multi = ("skill_supported_by_fact", "fact_has_metric_outcome", "metric_outcome_bound_to_employer")
        try:
            paths = traverse(conn, seeds=[root_node_id], allowed_steps=steps_multi, max_depth=3)
        except Exception:
            pass

        if not paths:
            # Fallback to direct evidential edge for this unit
            cursor.execute(
                """
                SELECT DISTINCT e.edge_type FROM semantic_unit_member m
                JOIN graph_edges e ON e.edge_id = m.member_id
                WHERE m.unit_id = ? AND m.member_kind = 'edge'
                """,
                (unit_id,),
            )
            ev_types = [r[0] for r in cursor.fetchall() if r[0]]
            step_type = ev_types[0] if ev_types else "skill_supported_by_fact"
            paths = traverse(conn, seeds=[root_node_id], allowed_steps=(step_type,), max_depth=1)

    elif unit_type == "engagement_episode":
        # Journey: engagement -> skill or engagement -> fact
        steps = ("engagement_exercises_skill",)
        try:
            paths = traverse(conn, seeds=[root_node_id], allowed_steps=steps, max_depth=1)
        except Exception:
            pass
        if not paths:
            steps_fact = ("engagement_evidenced_by_fact",)
            paths = traverse(conn, seeds=[root_node_id], allowed_steps=steps_fact, max_depth=1)

    elif unit_type == "metric_outcome_story":
        # Journey: metric -> employer
        steps = ("metric_outcome_bound_to_employer",)
        try:
            paths = traverse(conn, seeds=[root_node_id], allowed_steps=steps, max_depth=1)
        except Exception:
            pass
        if not paths:
            cursor.execute(
                """
                SELECT DISTINCT e.edge_type FROM semantic_unit_member m
                JOIN graph_edges e ON e.edge_id = m.member_id
                WHERE m.unit_id = ? AND m.member_kind = 'edge'
                """,
                (unit_id,),
            )
            m_types = [r[0] for r in cursor.fetchall() if r[0]]
            step_type = m_types[0] if m_types else "metric_outcome_bound_to_employer"
            paths = traverse(conn, seeds=[root_node_id], allowed_steps=(step_type,), max_depth=1)

    return {
        "unit_id": unit_id,
        "unit_type": unit_type,
        "root_node_id": root_node_id,
        "member_nodes": node_members,
        "member_edges": edge_members,
        "evidence_ids": evidence_ids,
        "paths": paths,
        "path_count": len(paths),
    }


__all__ = [
    "ACTIVATION_STATUS_BLOCKED",
    "RUNTIME_AUTHORITATIVE_STORE",
    "SemanticUnitActivationBlockedError",
    "SemanticUnitError",
    "SemanticUnitStaleGraphError",
    "assert_semantic_unit_activation_status",
    "check_semantic_unit_freshness",
    "expand_semantic_unit_subgraph",
    "retrieve_semantic_units",
]
