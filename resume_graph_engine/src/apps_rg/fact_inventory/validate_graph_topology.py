"""Validate Graph Topology & Ontology Invariants (Wave 3 / AC3.7).

Enforces the 13 zero-row structural invariants defined in report 06:
- I1: No isolated core knowledge or evidence nodes (allowlisting non-graph projection/policy types).
- I2: Every fact hosted by exactly one employment tenure (employment_hosts_fact).
- I3: Metric outcome fact parent is hosted by the bound employer.
- I4: Fact_has_metric_outcome source node is strictly of type fact or locked_bullet.
- I5: Every career_epoch and employment tenure attached to a career track.
- I6: Skill career_epoch attribute agrees with epoch_contains_skill edge.
- I7: Parity between skill_fact_links and skill_supported_by_fact edges.
- I8: Every section reference in eligibility and edges resolves to a node of type 'section'.
- I9: 100% parity between section_eligibility (allowed=1) and skill_allowed_in_section edges.
- I10: Capability domains have parent hierarchy and contain >= 1 skill.
- I11: C03 selection features and role family skill weights reference real nodes in graph_nodes.
- I12: Metadata summary counts match actual table row counts.
- I13: Traversable layer forms exactly 1 weakly-connected component, with 100% of skills reachable from tracks.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from apps_rg.repository_layout import repository_root

INVARIANT_QUERIES: dict[str, str] = {
    "I1_isolated_core_nodes": """
        SELECT count(*) FROM graph_nodes n
        WHERE n.node_type NOT IN ('role_family', 'policy', 'policy_rule', 'section', 'graph_ref')
          AND NOT EXISTS (
              SELECT 1 FROM graph_edges e
              WHERE n.node_id IN (e.source_node_id, e.target_node_id)
          )
    """,
    "I2_fact_hosting": """
        SELECT count(*) FROM graph_nodes n
        WHERE node_type = 'fact'
          AND (
              SELECT count(*) FROM graph_edges e
              WHERE e.edge_type = 'employment_hosts_fact'
                AND e.target_node_id = n.node_id
          ) <> 1
    """,
    "I3_metric_employer_bound": """
        SELECT count(*) FROM graph_edges a
        JOIN graph_edges b ON a.target_node_id = b.source_node_id
          AND b.edge_type = 'metric_outcome_bound_to_employer'
        JOIN graph_nodes f ON f.node_id = a.source_node_id
          AND f.node_type = 'fact'
        WHERE a.edge_type = 'fact_has_metric_outcome'
          AND NOT EXISTS (
              SELECT 1 FROM graph_edges h
              WHERE h.edge_type = 'employment_hosts_fact'
                AND h.source_node_id = b.target_node_id
                AND h.target_node_id = f.node_id
          )
    """,
    "I4_fact_metric_source": """
        SELECT count(*) FROM graph_edges e
        JOIN graph_nodes s ON s.node_id = e.source_node_id
        WHERE e.edge_type = 'fact_has_metric_outcome'
          AND s.node_type NOT IN ('fact', 'locked_bullet')
    """,
    "I5a_epoch_track": """
        SELECT count(*) FROM graph_nodes n
        WHERE node_type = 'career_epoch'
          AND NOT EXISTS (
              SELECT 1 FROM graph_edges e
              WHERE e.edge_type = 'career_track_contains_epoch'
                AND e.target_node_id = n.node_id
          )
    """,
    "I5b_emp_track": """
        SELECT count(*) FROM graph_nodes n
        WHERE node_type = 'employment'
          AND NOT EXISTS (
              SELECT 1 FROM graph_edges e
              WHERE e.edge_type = 'employment_in_career_track'
                AND e.source_node_id = n.node_id
          )
    """,
    "I6_skill_epoch_attr": """
        SELECT count(*) FROM graph_nodes s
        JOIN graph_edges e ON e.target_node_id = s.node_id
          AND e.edge_type = 'epoch_contains_skill'
        WHERE s.node_type = 'skill'
          AND s.career_epoch <> e.source_node_id
    """,
    "I7a_links_edges": """
        SELECT count(*) FROM graph_edges e
        WHERE e.edge_type = 'skill_supported_by_fact'
          AND NOT EXISTS (
              SELECT 1 FROM skill_fact_links l
              WHERE l.skill_id = e.source_node_id
                AND l.fact_id = e.target_node_id
          )
    """,
    "I7b_edges_links": """
        SELECT count(*) FROM skill_fact_links l
        WHERE l.claim_eligibility = 1
          AND NOT EXISTS (
              SELECT 1 FROM graph_edges e
              WHERE e.source_node_id = l.skill_id
                AND e.target_node_id = l.fact_id
          )
    """,
    "I8a_section_nodes": """
        SELECT count(*) FROM section_eligibility s
        LEFT JOIN graph_nodes n ON n.node_id = s.section_id
        WHERE s.section_id <> '*'
          AND (n.node_type IS NULL OR n.node_type <> 'section')
    """,
    "I8b_section_edges": """
        SELECT count(*) FROM graph_edges e
        JOIN graph_nodes t ON t.node_id = e.target_node_id
        WHERE e.edge_type = 'metric_outcome_section_eligible'
          AND t.node_type <> 'section'
    """,
    "I9_section_parity": """
        SELECT count(*) FROM section_eligibility s
        JOIN graph_nodes n ON n.node_id = s.node_id
          AND n.node_type = 'skill'
        WHERE s.allowed = 1
          AND NOT EXISTS (
              SELECT 1 FROM graph_edges e
              WHERE e.edge_type = 'skill_allowed_in_section'
                AND e.source_node_id = s.node_id
                AND e.target_node_id = s.section_id
          )
    """,
    "I10_domain_hierarchy": """
        SELECT count(*) FROM graph_nodes n
        WHERE node_type = 'capability_domain'
          AND (
              NOT EXISTS (SELECT 1 FROM graph_edges e WHERE e.target_node_id = n.node_id)
              OR NOT EXISTS (
                  SELECT 1 FROM graph_edges e
                  WHERE e.source_node_id = n.node_id
                    AND e.edge_type = 'capability_domain_contains_skill'
              )
          )
    """,
    "I11a_c03_track": """
        SELECT count(*) FROM c03_skill_selection_features
        WHERE career_track_id NOT IN (
            SELECT node_id FROM graph_nodes WHERE node_type = 'career_track'
        )
    """,
    "I11b_c03_roles": """
        SELECT count(*) FROM c03_role_family_skill_weights
        WHERE role_family_key NOT IN (
            SELECT node_id FROM graph_nodes WHERE node_type = 'role_family'
        )
    """,
    "I12_metadata_counts": """
        SELECT count(*) FROM graph_metadata
        WHERE json_extract(graph_count_summary, '$.node_count_sqlite') <> (SELECT count(*) FROM graph_nodes)
           OR json_extract(graph_count_summary, '$.edge_count_sqlite') <> (SELECT count(*) FROM graph_edges)
    """,
}


def evaluate_traversable_connectivity(conn: sqlite3.Connection) -> tuple[int, int]:
    """Check weak component count of traversable layer and reachability of skills from tracks (I13)."""
    cur = conn.cursor()
    cur.execute("SELECT node_id, node_type FROM graph_nodes")
    all_nodes = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute(
        "SELECT source_node_id, target_node_id FROM graph_edges WHERE COALESCE(traversable, 1) = 1"
    )
    adj: dict[str, set[str]] = {}
    for u, v in cur.fetchall():
        adj.setdefault(u, set()).add(v)
        adj.setdefault(v, set()).add(u)

    traversable_types = {
        "skill",
        "fact",
        "metric_outcome",
        "employment",
        "career_epoch",
        "career_track",
        "pillar",
        "capability_domain",
        "engagement",
        "locked_bullet",
        "certification",
        "concept",
        "repo_evidence",
        "metric",
        "metric_bucket",
    }
    nodes_to_check = {
        nid
        for nid, ntype in all_nodes.items()
        if ntype in traversable_types and nid in adj
    }

    visited: set[str] = set()
    components = 0
    for start in nodes_to_check:
        if start not in visited:
            components += 1
            q = deque([start])
            visited.add(start)
            while q:
                curr = q.popleft()
                for neighbor in adj.get(curr, ()):
                    if neighbor in nodes_to_check and neighbor not in visited:
                        visited.add(neighbor)
                        q.append(neighbor)

    track_ids = [nid for nid, ntype in all_nodes.items() if ntype == "career_track"]
    reachable_from_tracks: set[str] = set()
    for trk in track_ids:
        q = deque([trk])
        reachable_from_tracks.add(trk)
        while q:
            curr = q.popleft()
            for neighbor in adj.get(curr, ()):
                if neighbor not in reachable_from_tracks:
                    reachable_from_tracks.add(neighbor)
                    q.append(neighbor)

    unreachable_skills = [
        nid
        for nid, ntype in all_nodes.items()
        if ntype == "skill" and nid not in reachable_from_tracks
    ]
    return components, len(unreachable_skills)


def validate_graph_topology(
    db_or_conn: Path | str | sqlite3.Connection,
    *,
    raise_on_error: bool = True,
) -> dict[str, Any]:
    """Validate all 13 graph topology invariants against target SQLite DB."""
    if isinstance(db_or_conn, (str, Path)):
        db_path = Path(db_or_conn).resolve()
        if not db_path.is_file():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        uri = f"{db_path.as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        should_close = True
    else:
        conn = db_or_conn
        should_close = False

    results: dict[str, int] = {}
    violations: dict[str, int] = {}

    try:
        cur = conn.cursor()
        for name, sql in INVARIANT_QUERIES.items():
            cur.execute(sql)
            row = cur.fetchone()
            count = int(row[0]) if row else 0
            results[name] = count
            if count > 0:
                violations[name] = count

        components, unreachable_skills = evaluate_traversable_connectivity(conn)
        results["I13a_weak_components"] = components
        results["I13b_unreachable_skills"] = unreachable_skills

        if components != 1:
            violations["I13a_weak_components"] = components
        if unreachable_skills > 0:
            violations["I13b_unreachable_skills"] = unreachable_skills

    finally:
        if should_close:
            conn.close()

    status = "FAIL" if violations else "PASS"
    report = {
        "status": status,
        "results": results,
        "violations": violations,
        "total_invariants_checked": len(INVARIANT_QUERIES) + 2,
        "failed_invariants_count": len(violations),
    }

    if raise_on_error and status == "FAIL":
        raise ValueError(
            f"Graph topology validation failed with {len(violations)} violations: {json.dumps(violations, indent=2)}"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Graph Topology Invariants (Wave 3)")
    parser.add_argument(
        "--db",
        type=Path,
        default=repository_root(Path(__file__))
        / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite",
        help="Path to SQLite database",
    )
    parser.add_argument("--read-only", action="store_true", default=True, help="Open in read-only mode")
    args = parser.parse_args()

    try:
        report = validate_graph_topology(args.db, raise_on_error=False)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "PASS" else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
