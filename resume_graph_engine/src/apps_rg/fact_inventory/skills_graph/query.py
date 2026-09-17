"""Authoritative query and career phase traversal over materialized skills graph."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .schema import EMPLOYMENT_PHASES, EPOCH_LABELS, EPOCH_ORDINAL, ORDINAL_TO_EPOCH
from .constants import CONFIDENCE_GRADE_RANK, canonical_career_epoch_and_ordinal
from .storage import open_graph_sqlite

def get_skills_by_career_phase(
    conn: sqlite3.Connection | None = None,
    *,
    phase_ordinal: int | None = None,
    epoch_id: str | None = None,
    min_confidence: str = "LOW",
    section_id: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Retrieve skills, supporting assertions, connective edges, and calibrated confidence for a career phase.

    Args:
        conn: Optional active SQLite connection to augmented_skills_graph.sqlite.
        phase_ordinal: 1..6 phase number.
        epoch_id: Canonical career epoch ID (e.g. 'epoch_agentic_ai_runtime_architecture').
        min_confidence: Minimum skill confidence grade ('LOW', 'MEDIUM', 'HIGH'). Default 'LOW'.
        section_id: Optional resume section filter ('executive_summary', 'experience', etc.).
        repo_root: Optional repository root path.

    Returns:
        Structured dictionary containing:
          - career_phase: metadata for the epoch
          - skills: list of matching skills with attributes and fact/metric links
          - supporting_assertions: proof facts, metric outcomes, and employment nodes
          - edges: connective edges for skills in this phase
          - calibrated_confidence_summary: quantitative breakdown of confidence and eligibility
    """
    if phase_ordinal is not None:
        if phase_ordinal not in ORDINAL_TO_EPOCH:
            raise ValueError(f"Invalid phase_ordinal {phase_ordinal}. Must be between 1 and 6.")
        resolved_epoch = ORDINAL_TO_EPOCH[phase_ordinal]
        resolved_ordinal = phase_ordinal
    elif epoch_id is not None:
        norm_epoch = str(epoch_id or "").strip()
        if norm_epoch not in EPOCH_ORDINAL:
            raise ValueError(
                f"Invalid epoch_id {epoch_id}. Must be one of {sorted(EPOCH_ORDINAL.keys())}."
            )
        resolved_epoch = norm_epoch
        resolved_ordinal = EPOCH_ORDINAL[norm_epoch]
    else:
        raise ValueError("Either phase_ordinal or epoch_id must be provided.")

    close_conn = False
    if conn is None:
        conn = open_graph_sqlite(repo_root=repo_root)
        close_conn = True

    try:
        min_rank = CONFIDENCE_GRADE_RANK.get(min_confidence.upper(), 1)

        # 1. Fetch career phase metadata
        epoch_row = conn.execute(
            """
            SELECT node_id, node_type, label, description, activation_status, confidence, phase_ordinal
            FROM graph_nodes
            WHERE node_id = ?
            """,
            (resolved_epoch,),
        ).fetchone()

        epoch_label = EPOCH_LABELS.get(resolved_epoch, resolved_epoch)
        if epoch_row:
            career_phase_meta = {
                "epoch_id": epoch_row[0],
                "label": epoch_row[2] or epoch_label,
                "description": epoch_row[3] or f"Career phase {resolved_ordinal}: {epoch_label}",
                "activation_status": epoch_row[4] or "ACTIVE",
                "confidence": epoch_row[5] or "HIGH",
                "phase_ordinal": epoch_row[6] if epoch_row[6] is not None else resolved_ordinal,
            }
        else:
            career_phase_meta = {
                "epoch_id": resolved_epoch,
                "label": epoch_label,
                "description": f"Career phase {resolved_ordinal}: {epoch_label}",
                "activation_status": "ACTIVE",
                "confidence": "HIGH",
                "phase_ordinal": resolved_ordinal,
            }

        # 2. Fetch skills
        query = """
            SELECT 
                f.skill_id, n.label, n.description, f.career_epoch, f.phase_ordinal,
                f.pillar, f.subpillar, f.domain_id, f.metric_bucket, f.confidence,
                f.support_level, f.activation_status, f.external_eligible,
                f.source_fact_count, f.allowed_sections
            FROM c03_skill_selection_features f
            JOIN graph_nodes n ON n.node_id = f.skill_id
            WHERE (f.phase_ordinal = ? OR f.career_epoch = ?)
        """
        params: list[Any] = [resolved_ordinal, resolved_epoch]

        if section_id:
            query += """
                AND EXISTS (
                    SELECT 1 FROM section_eligibility se
                    WHERE se.node_id = f.skill_id AND se.section_id = ? AND se.allowed = 1
                )
            """
            params.append(section_id)

        query += " ORDER BY f.confidence DESC, f.skill_id ASC"
        skill_rows = conn.execute(query, tuple(params)).fetchall()

        skills: list[dict[str, Any]] = []
        skill_ids: list[str] = []
        conf_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "BLOCKED": 0}
        external_eligible_count = 0

        for r in skill_rows:
            sid = r[0]
            conf = str(r[9] or "LOW").upper()
            rank = CONFIDENCE_GRADE_RANK.get(conf, 1)
            if rank < min_rank:
                continue

            skill_ids.append(sid)
            conf_counts[conf] = conf_counts.get(conf, 0) + 1
            if r[12]:
                external_eligible_count += 1

            skills.append({
                "skill_id": sid,
                "label": r[1],
                "description": r[2],
                "career_epoch": r[3],
                "phase_ordinal": r[4],
                "pillar": r[5],
                "subpillar": r[6],
                "domain_id": r[7],
                "metric_bucket": r[8],
                "confidence": conf,
                "confidence_numeric": 0.90 if conf == "HIGH" else (0.75 if conf == "MEDIUM" else 0.50),
                "support_level": r[10],
                "activation_status": r[11],
                "external_eligible": int(r[12] or 0),
                "source_fact_count": int(r[13] or 0),
                "allowed_sections": json.loads(r[14]) if r[14] else [],
            })

        # 3. Supporting assertions: facts, metrics, employments
        supporting_facts: list[dict[str, Any]] = []
        supporting_metrics: list[dict[str, Any]] = []
        supporting_employments: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        if skill_ids:
            # Fact links
            placeholders = ",".join("?" for _ in skill_ids)
            fact_rows = conn.execute(
                f"""
                SELECT DISTINCT fn.node_id, fn.node_type, fn.label, fn.description,
                                fn.activation_status, fn.support_level, fn.confidence,
                                l.skill_id
                FROM skill_fact_links l
                JOIN graph_nodes fn ON fn.node_id = l.fact_id
                WHERE l.skill_id IN ({placeholders})
                ORDER BY fn.node_id
                """,
                tuple(skill_ids),
            ).fetchall()

            seen_facts: set[str] = set()
            for fr in fact_rows:
                if fr[0] not in seen_facts:
                    seen_facts.add(fr[0])
                    supporting_facts.append({
                        "node_id": fr[0],
                        "node_type": fr[1],
                        "label": fr[2],
                        "description": fr[3],
                        "activation_status": fr[4],
                        "support_level": fr[5],
                        "confidence": fr[6],
                        "linked_skill_id": fr[7],
                    })

            # Connective edges
            edge_rows = conn.execute(
                f"""
                SELECT edge_id, source_node_id, target_node_id, edge_type, weight,
                       confidence, evidence_status, rationale, external_claim_policy
                FROM graph_edges
                WHERE source_node_id = ? OR target_node_id = ?
                   OR source_node_id IN ({placeholders})
                   OR target_node_id IN ({placeholders})
                """,
                (resolved_epoch, resolved_epoch, *skill_ids, *skill_ids),
            ).fetchall()

            for er in edge_rows:
                edges.append({
                    "edge_id": er[0],
                    "source_node_id": er[1],
                    "target_node_id": er[2],
                    "edge_type": er[3],
                    "weight": er[4],
                    "confidence": er[5],
                    "evidence_status": er[6],
                    "rationale": er[7],
                    "external_claim_policy": er[8],
                })

            # Metric nodes
            metric_rows = conn.execute(
                f"""
                SELECT DISTINCT mn.node_id, mn.node_type, mn.label, mn.description, mn.confidence
                FROM graph_edges e
                JOIN graph_nodes mn ON (mn.node_id = e.target_node_id OR mn.node_id = e.source_node_id)
                WHERE (e.source_node_id IN ({placeholders}) OR e.target_node_id IN ({placeholders}))
                  AND mn.node_type IN ('metric', 'metric_outcome', 'metric_bucket')
                """,
                (*skill_ids, *skill_ids),
            ).fetchall()
            for mr in metric_rows:
                supporting_metrics.append({
                    "node_id": mr[0],
                    "node_type": mr[1],
                    "label": mr[2],
                    "description": mr[3],
                    "confidence": mr[4],
                })

        # Employment nodes matching this phase
        emp_ids = [
            eid for eid, (min_p, max_p) in EMPLOYMENT_PHASES.items()
            if min_p <= resolved_ordinal <= max_p
        ]
        if emp_ids:
            emp_placeholders = ",".join("?" for _ in emp_ids)
            emp_rows = conn.execute(
                f"""
                SELECT node_id, node_type, label, description, activation_status, confidence
                FROM graph_nodes
                WHERE node_id IN ({emp_placeholders})
                """,
                tuple(emp_ids),
            ).fetchall()
            for em in emp_rows:
                supporting_employments.append({
                    "node_id": em[0],
                    "node_type": em[1],
                    "label": em[2],
                    "description": em[3],
                    "activation_status": em[4],
                    "confidence": em[5],
                })

        # 4. Calibrated confidence summary
        total_filtered = len(skills)
        calibrated_avg = (
            round(
                (conf_counts["HIGH"] * 0.92 + conf_counts["MEDIUM"] * 0.70 + conf_counts["LOW"] * 0.35)
                / max(total_filtered, 1),
                3,
            )
            if total_filtered > 0
            else 0.0
        )

        return {
            "career_phase": career_phase_meta,
            "skills": skills,
            "supporting_assertions": {
                "facts": supporting_facts,
                "metrics": supporting_metrics,
                "employment_nodes": supporting_employments,
                "employments": supporting_employments,
            },
            "edges": edges,
            "calibrated_confidence_summary": {
                "total_skills": total_filtered,
                "high_confidence_count": conf_counts["HIGH"],
                "medium_confidence_count": conf_counts["MEDIUM"],
                "low_confidence_count": conf_counts["LOW"],
                "blocked_count": conf_counts["BLOCKED"],
                "external_eligible_count": external_eligible_count,
                "calibrated_average_confidence": calibrated_avg,
                "average_confidence": calibrated_avg,
            },
        }
    finally:
        if close_conn:
            conn.close()


__all__ = ["get_skills_by_career_phase"]
