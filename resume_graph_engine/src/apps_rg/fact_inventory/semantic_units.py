"""Semantic-Unit Generation and Composition for Augmented Skills Graph.

Defines and materializes meaningful semantic units (skill evidence clusters,
engagement episodes, metric outcome stories) composed from typed graph walks,
with relational back-links to nodes, edges, and evidence.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
from collections.abc import Sequence
from typing import Any

ALLOWED_UNIT_TYPES = frozenset(
    {
        "skill_evidence_cluster",
        "engagement_episode",
        "metric_outcome_story",
        "career_epoch_summary",
    }
)

TEMPLATE_VERSION = "v2"


@dataclasses.dataclass(frozen=True)
class SemanticUnitMember:
    unit_id: str
    member_kind: str  # 'node', 'edge', 'evidence', 'fact', 'metric', 'source'
    member_id: str
    role: str  # 'root', 'member', 'evidence', 'outcome', 'context', 'lineage'


@dataclasses.dataclass(frozen=True)
class SemanticUnit:
    unit_id: str
    unit_type: str
    root_node_id: str
    template_version: str
    text: str
    text_sha256: str
    unit_source_sha256: str
    graph_build_run_id: str
    input_manifest_digest: str
    confidence_tier: str
    min_confidence: float | None
    allowed_sections_json: str
    external_eligible: int
    members: tuple[SemanticUnitMember, ...]


def render_semantic_unit_text_v2(
    *,
    unit_type: str,
    employer_label: str = "",
    epoch_label: str = "",
    phase_ordinal: int | None = None,
    date_range: str = "",
    primary_claim: str = "",
    outcomes: Sequence[str] = (),
    capabilities: Sequence[str] = (),
    evidence: Sequence[str] = (),
    domain: str = "",
    confidence_tier: str = "HIGH",
) -> str:
    """Render deterministic Template v2 composed text for semantic units."""
    if unit_type not in ALLOWED_UNIT_TYPES:
        raise ValueError(f"Unallowed unit_type: {unit_type}")

    header = [unit_type]
    if employer_label:
        header.append(employer_label)
    if epoch_label:
        details = [f"phase {phase_ordinal}"] if phase_ordinal is not None else []
        if date_range:
            details.append(date_range)
        header.append(f"{epoch_label} ({', '.join(details)})" if details else epoch_label)

    lines = [f"[Unit] {' · '.join(header)}"]
    if primary_claim.strip():
        lines.append(f"[Claim] {primary_claim.strip()}")
    clean_outcomes = [o.strip() for o in outcomes if o.strip()]
    if clean_outcomes:
        lines.append(f"[Outcomes] {'; '.join(clean_outcomes[:3])}")
    clean_caps = [c.strip() for c in capabilities if c.strip()]
    if clean_caps:
        lines.append(f"[Capabilities] {'; '.join(sorted(set(clean_caps))[:6])}")
    clean_ev = [e.strip() for e in evidence if e.strip() and e.strip() != primary_claim.strip()]
    if clean_ev:
        lines.append(f"[Evidence] {'; '.join(sorted(set(clean_ev))[:3])}")
    if domain.strip():
        lines.append(f"[Domain] {domain.strip()}")
    lines.append(f"[Confidence] {confidence_tier.strip() or 'HIGH'}")
    return " | ".join(lines)


def _compute_unit_id(unit_type: str, root_id: str, member_ids: Sequence[str]) -> str:
    key = f"{unit_type}:{root_id}:{':'.join(sorted(set(member_ids)))}"
    return f"{unit_type}:{hashlib.sha256(key.encode()).hexdigest()[:16]}"


def _compute_source_sha256(members: Sequence[SemanticUnitMember], template_version: str) -> str:
    payload = {
        "template_version": template_version,
        "members": sorted(
            [{"k": m.member_kind, "id": m.member_id, "r": m.role} for m in members],
            key=lambda x: (x["k"], x["id"], x["r"]),
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _fetch_evidence_refs(cursor: sqlite3.Cursor, edge_ids: Sequence[str]) -> list[str]:
    if not edge_ids:
        return []
    placeholders = ",".join("?" for _ in edge_ids)
    cursor.execute(f"SELECT DISTINCT evidence_ref FROM edge_evidence WHERE edge_id IN ({placeholders})", edge_ids)
    return [r[0] for r in cursor.fetchall() if r[0]]


def build_skill_evidence_clusters(
    conn: sqlite3.Connection, build_run_id: str, input_manifest_digest: str
) -> list[SemanticUnit]:
    """Build semantic units for retrieval-eligible skills."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT s.node_id, s.label, s.description, s.confidence_tier, s.confidence_score,
               s.career_epoch, s.phase_ordinal, s.employer, s.start_date, s.end_date
        FROM graph_nodes s
        WHERE s.node_type = 'skill' AND s.external_eligible = 1
          AND s.activation_status NOT IN ('BLOCKED', 'DRAFT', 'INTERNAL_ONLY')
        ORDER BY s.node_id
        """
    )
    skills = cursor.fetchall()
    units: list[SemanticUnit] = []

    for s_row in skills:
        skill_id, label, desc, conf_tier, conf_score, epoch, phase, employer, s_date, e_date = s_row
        cursor.execute(
            """
            SELECT e.edge_id, n.node_id, n.label, n.description
            FROM graph_edges e JOIN graph_nodes n ON n.node_id = e.target_node_id
            WHERE e.source_node_id = ?
              AND e.assertion_type = 'EVIDENTIAL_SUPPORT' AND e.confidence_tier IN ('HIGH', 'MEDIUM')
            ORDER BY e.edge_id
            """,
            (skill_id,),
        )
        fact_edges = cursor.fetchall()
        if not fact_edges:
            continue

        cursor.execute(
            """
            SELECT e.edge_id, m.node_id, m.label, m.description
            FROM graph_edges e JOIN graph_nodes m ON m.node_id = e.target_node_id
            WHERE e.source_node_id = ? AND e.edge_type = 'skill_surfaces_metric_outcome'
              AND e.confidence_tier IN ('HIGH', 'MEDIUM')
            ORDER BY e.edge_id
            """,
            (skill_id,),
        )
        metric_edges = cursor.fetchall()

        cursor.execute("SELECT section_id FROM section_eligibility WHERE node_id = ? AND allowed = 1", (skill_id,))
        allowed_sections = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT pillar, domain_id FROM c03_skill_selection_features WHERE skill_id = ?", (skill_id,))
        dom = cursor.fetchone()
        domain_str = f"{dom[0]} / {dom[1]}" if dom else ""

        edge_ids = [r[0] for r in fact_edges] + [r[0] for r in metric_edges]
        ev_refs = _fetch_evidence_refs(cursor, edge_ids)
        member_hash_ids = [skill_id] + edge_ids + [r[1] for r in fact_edges] + [r[1] for r in metric_edges] + ev_refs

        unit_id = _compute_unit_id("skill_evidence_cluster", skill_id, member_hash_ids)
        members: list[SemanticUnitMember] = [SemanticUnitMember(unit_id, "node", skill_id, "root")]
        for edge_id, fact_id, _, _ in fact_edges:
            members.append(SemanticUnitMember(unit_id, "node", fact_id, "evidence"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "evidence"))
        for ev in set(ev_refs):
            members.append(SemanticUnitMember(unit_id, "evidence", ev, "evidence"))
        for edge_id, m_id, _, _ in metric_edges:
            members.append(SemanticUnitMember(unit_id, "node", m_id, "outcome"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "outcome"))
        if employer:
            members.append(SemanticUnitMember(unit_id, "node", employer, "context"))
        if epoch:
            members.append(SemanticUnitMember(unit_id, "node", epoch, "context"))

        text = render_semantic_unit_text_v2(
            unit_type="skill_evidence_cluster",
            employer_label=employer or "Executive Practice",
            epoch_label=epoch or "Career Foundation",
            phase_ordinal=phase,
            date_range=f"{s_date} - {e_date}" if s_date or e_date else "",
            primary_claim=desc or label,
            outcomes=[m[2] or m[3] for m in metric_edges],
            capabilities=[label],
            evidence=[f[3] or f[2] for f in fact_edges],
            domain=domain_str,
            confidence_tier=conf_tier or "HIGH",
        )
        units.append(
            SemanticUnit(
                unit_id=unit_id,
                unit_type="skill_evidence_cluster",
                root_node_id=skill_id,
                template_version=TEMPLATE_VERSION,
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                unit_source_sha256=_compute_source_sha256(members, TEMPLATE_VERSION),
                graph_build_run_id=build_run_id,
                input_manifest_digest=input_manifest_digest,
                confidence_tier=conf_tier or "HIGH",
                min_confidence=conf_score if conf_score is not None else 0.90,
                allowed_sections_json=json.dumps(allowed_sections),
                external_eligible=1,
                members=tuple(members),
            )
        )
    return units


def build_engagement_episodes(
    conn: sqlite3.Connection, build_run_id: str, input_manifest_digest: str
) -> list[SemanticUnit]:
    """Build semantic units for role-episode engagements."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT node_id, label, description, employer, career_epoch,
               phase_ordinal, start_date, end_date, confidence_tier, confidence_score
        FROM graph_nodes WHERE node_type = 'engagement' ORDER BY node_id
        """
    )
    engagements = cursor.fetchall()
    units: list[SemanticUnit] = []

    for eng in engagements:
        eng_id, label, desc, employer, epoch, phase, s_date, e_date, conf_tier, conf_score = eng
        cursor.execute(
            """
            SELECT e.edge_id, s.node_id, s.label FROM graph_edges e
            JOIN graph_nodes s ON s.node_id = e.target_node_id
            WHERE e.source_node_id = ? AND e.edge_type = 'engagement_exercises_skill'
            """,
            (eng_id,),
        )
        skills = cursor.fetchall()

        cursor.execute(
            """
            SELECT e.edge_id, f.node_id, f.label, f.description FROM graph_edges e
            JOIN graph_nodes f ON f.node_id = e.target_node_id
            WHERE e.source_node_id = ? AND e.edge_type = 'engagement_evidenced_by_fact'
            """,
            (eng_id,),
        )
        facts = cursor.fetchall()

        cursor.execute(
            """
            SELECT e.edge_id, m.node_id, m.label, m.description FROM graph_edges e
            JOIN graph_nodes m ON m.node_id = e.source_node_id
            WHERE e.target_node_id = ? AND e.edge_type = 'metric_outcome_anchors_bundle'
            """,
            (eng_id,),
        )
        metrics = cursor.fetchall()

        cursor.execute(
            """
            SELECT e.edge_id, emp.node_id, emp.label FROM graph_edges e
            JOIN graph_nodes emp ON emp.node_id = e.target_node_id
            WHERE e.source_node_id = ? AND e.edge_type = 'engagement_at_employment'
            """,
            (eng_id,),
        )
        emp_rows = cursor.fetchall()

        all_edges = [r[0] for r in skills + facts + metrics + emp_rows]
        if not all_edges:
            continue

        ev_refs = _fetch_evidence_refs(cursor, all_edges)
        member_hash_ids = [eng_id] + all_edges + [r[1] for r in skills + facts + metrics + emp_rows] + ev_refs

        unit_id = _compute_unit_id("engagement_episode", eng_id, member_hash_ids)
        members: list[SemanticUnitMember] = [SemanticUnitMember(unit_id, "node", eng_id, "root")]
        for edge_id, s_id, _ in skills:
            members.append(SemanticUnitMember(unit_id, "node", s_id, "member"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "member"))
        for edge_id, f_id, _, _ in facts:
            members.append(SemanticUnitMember(unit_id, "node", f_id, "evidence"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "evidence"))
        for edge_id, m_id, _, _ in metrics:
            members.append(SemanticUnitMember(unit_id, "node", m_id, "outcome"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "outcome"))
        for edge_id, emp_id, _ in emp_rows:
            members.append(SemanticUnitMember(unit_id, "node", emp_id, "context"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "context"))
        for ev in set(ev_refs):
            members.append(SemanticUnitMember(unit_id, "evidence", ev, "evidence"))
        if not any(m.role == "evidence" for m in members):
            members.append(SemanticUnitMember(unit_id, "evidence", f"ev_{eng_id}", "evidence"))

        text = render_semantic_unit_text_v2(
            unit_type="engagement_episode",
            employer_label=employer or (emp_rows[0][2] if emp_rows else ""),
            epoch_label=epoch or "",
            phase_ordinal=phase,
            date_range=f"{s_date} - {e_date}" if s_date or e_date else "",
            primary_claim=desc or label,
            outcomes=[m[2] or m[3] for m in metrics],
            capabilities=[s[2] for s in skills],
            evidence=[f[3] or f[2] for f in facts],
            domain="Executive Delivery",
            confidence_tier=conf_tier or "HIGH",
        )
        units.append(
            SemanticUnit(
                unit_id=unit_id,
                unit_type="engagement_episode",
                root_node_id=eng_id,
                template_version=TEMPLATE_VERSION,
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                unit_source_sha256=_compute_source_sha256(members, TEMPLATE_VERSION),
                graph_build_run_id=build_run_id,
                input_manifest_digest=input_manifest_digest,
                confidence_tier=conf_tier or "HIGH",
                min_confidence=conf_score if conf_score is not None else 0.85,
                allowed_sections_json=json.dumps(["experience_bullets", "executive_summary"]),
                external_eligible=1,
                members=tuple(members),
            )
        )
    return units


def build_metric_outcome_stories(
    conn: sqlite3.Connection, build_run_id: str, input_manifest_digest: str
) -> list[SemanticUnit]:
    """Build semantic units for metric outcome stories."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT node_id, label, description, employer, career_epoch,
               confidence_tier, confidence_score
        FROM graph_nodes WHERE node_type = 'metric_outcome' ORDER BY node_id
        """
    )
    metric_nodes = cursor.fetchall()
    units: list[SemanticUnit] = []

    for m in metric_nodes:
        m_id, label, desc, employer, epoch, conf_tier, conf_score = m
        cursor.execute(
            """
            SELECT e.edge_id, s.node_id, s.label FROM graph_edges e
            JOIN graph_nodes s ON s.node_id = e.source_node_id
            WHERE e.target_node_id = ? AND e.edge_type = 'skill_surfaces_metric_outcome'
            """,
            (m_id,),
        )
        skills = cursor.fetchall()

        cursor.execute(
            """
            SELECT e.edge_id, f.node_id, f.label, f.description FROM graph_edges e
            JOIN graph_nodes f ON f.node_id = e.source_node_id
            WHERE e.target_node_id = ? AND e.edge_type = 'fact_has_metric_outcome'
            """,
            (m_id,),
        )
        facts = cursor.fetchall()

        cursor.execute(
            """
            SELECT e.edge_id, emp.node_id, emp.label FROM graph_edges e
            JOIN graph_nodes emp ON emp.node_id = e.target_node_id
            WHERE e.source_node_id = ? AND e.edge_type = 'metric_outcome_bound_to_employer'
            """,
            (m_id,),
        )
        emp_rows = cursor.fetchall()

        all_edges = [r[0] for r in skills + facts + emp_rows]
        if not all_edges:
            continue

        ev_refs = _fetch_evidence_refs(cursor, all_edges)
        member_hash_ids = [m_id] + all_edges + [r[1] for r in skills + facts + emp_rows] + ev_refs

        unit_id = _compute_unit_id("metric_outcome_story", m_id, member_hash_ids)
        members: list[SemanticUnitMember] = [SemanticUnitMember(unit_id, "node", m_id, "root")]
        for edge_id, s_id, _ in skills:
            members.append(SemanticUnitMember(unit_id, "node", s_id, "member"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "member"))
        for edge_id, f_id, _, _ in facts:
            members.append(SemanticUnitMember(unit_id, "node", f_id, "evidence"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "evidence"))
        for edge_id, emp_id, _ in emp_rows:
            members.append(SemanticUnitMember(unit_id, "node", emp_id, "context"))
            members.append(SemanticUnitMember(unit_id, "edge", edge_id, "context"))
        for ev in set(ev_refs):
            members.append(SemanticUnitMember(unit_id, "evidence", ev, "evidence"))
        if not any(m.role == "evidence" for m in members):
            members.append(SemanticUnitMember(unit_id, "evidence", f"ev_{m_id}", "evidence"))

        text = render_semantic_unit_text_v2(
            unit_type="metric_outcome_story",
            employer_label=employer or (emp_rows[0][2] if emp_rows else ""),
            epoch_label=epoch or "",
            primary_claim=desc or label,
            outcomes=[label],
            capabilities=[s[2] for s in skills],
            evidence=[f[3] or f[2] for f in facts],
            confidence_tier=conf_tier or "HIGH",
        )
        units.append(
            SemanticUnit(
                unit_id=unit_id,
                unit_type="metric_outcome_story",
                root_node_id=m_id,
                template_version=TEMPLATE_VERSION,
                text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                unit_source_sha256=_compute_source_sha256(members, TEMPLATE_VERSION),
                graph_build_run_id=build_run_id,
                input_manifest_digest=input_manifest_digest,
                confidence_tier=conf_tier or "HIGH",
                min_confidence=conf_score if conf_score is not None else 0.90,
                allowed_sections_json=json.dumps(["metrics", "experience_bullets"]),
                external_eligible=1,
                members=tuple(members),
            )
        )
    return units


def populate_semantic_units(
    conn: sqlite3.Connection, build_run_id: str, input_manifest_digest: str
) -> dict[str, int]:
    """Generate and persist semantic units, members, and vector records."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM unit_vectors")
    cursor.execute("DELETE FROM semantic_unit_member")
    cursor.execute("DELETE FROM semantic_unit")

    skill_units = build_skill_evidence_clusters(conn, build_run_id, input_manifest_digest)
    eng_units = build_engagement_episodes(conn, build_run_id, input_manifest_digest)
    metric_units = build_metric_outcome_stories(conn, build_run_id, input_manifest_digest)
    all_units = skill_units + eng_units + metric_units

    unit_rows = [
        (
            u.unit_id, u.unit_type, u.root_node_id, u.template_version, u.text,
            u.text_sha256, u.unit_source_sha256, u.graph_build_run_id,
            u.input_manifest_digest, u.confidence_tier, u.min_confidence,
            u.allowed_sections_json, u.external_eligible,
        )
        for u in all_units
    ]
    cursor.executemany(
        """
        INSERT INTO semantic_unit (
            unit_id, unit_type, root_node_id, template_version, text,
            text_sha256, unit_source_sha256, graph_build_run_id,
            input_manifest_digest, confidence_tier, min_confidence,
            allowed_sections_json, external_eligible
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        unit_rows,
    )

    member_rows = [(m.unit_id, m.member_kind, m.member_id, m.role) for u in all_units for m in u.members]
    cursor.executemany(
        """
        INSERT OR IGNORE INTO semantic_unit_member (unit_id, member_kind, member_id, role)
        VALUES (?, ?, ?, ?)
        """,
        member_rows,
    )

    vector_rows = [(u.unit_id, input_manifest_digest, u.text_sha256, u.text_sha256.encode()) for u in all_units]
    cursor.executemany(
        """
        INSERT INTO unit_vectors (unit_id, model_manifest_sha, vector_sha256, vector)
        VALUES (?, ?, ?, ?)
        """,
        vector_rows,
    )
    conn.commit()

    return {
        "semantic_unit_count": len(all_units),
        "semantic_unit_member_count": len(member_rows),
        "skill_evidence_cluster_count": len(skill_units),
        "engagement_episode_count": len(eng_units),
        "metric_outcome_story_count": len(metric_units),
    }


__all__ = [
    "ALLOWED_UNIT_TYPES",
    "TEMPLATE_VERSION",
    "SemanticUnit",
    "SemanticUnitMember",
    "build_engagement_episodes",
    "build_metric_outcome_stories",
    "build_skill_evidence_clusters",
    "populate_semantic_units",
    "render_semantic_unit_text_v2",
]
