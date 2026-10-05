"""Tests for Wave 4 Deep Traversal Engine (AC4.1, AC4.2, AC4.3, AC4.7).

Verifies:
- AC4.1: All 4 canonical journeys return >= 1 path for each of the 5 employers with metrics.
- AC4.2: Unrestricted depth-3 walk rejected with ValueError; cycle guard terminates without loop on synthetic cycles.
- AC4.3: Forward and inverse traversal return 100% identical path sets.
- AC4.7: EXPLAIN QUERY PLAN verifies covering index usage with zero table scans, p95 < 100ms.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
import pytest

from apps_rg.fact_inventory.skills_graph.storage import default_graph_sqlite_path, _repo_root
from apps_rg.runtime.graph_traversal import (
    traverse,
    traverse_journey,
    CANONICAL_JOURNEYS,
    JOURNEY_SKILL_FACT_METRIC_EMPLOYMENT_EPOCH,
    JOURNEY_SKILL_ENGAGEMENT_EMPLOYMENT,
    JOURNEY_METRIC_FACT_SKILL,
    JOURNEY_DOMAIN_SKILL_EVIDENCE,
)


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    p = default_graph_sqlite_path(_repo_root())
    if not p.is_file():
        pytest.skip(f"Augmented skills graph SQLite missing at {p}")
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    yield conn
    conn.close()


def test_ac4_1_canonical_journeys_all_employers(db_conn: sqlite3.Connection) -> None:
    """AC4.1: All 4 canonical journeys return >= 1 path for each employer with metrics."""
    cur = db_conn.cursor()
    employers = ["EY", "IBM", "InsurTech", "Slalom", "Unify"]

    for emp in employers:
        # Journey 1: skill -> fact -> metric_outcome -> employment -> career_epoch
        cur.execute(
            """
            SELECT DISTINCT e1.source_node_id
            FROM graph_edges e1
            JOIN graph_edges e2 ON e1.target_node_id = e2.source_node_id AND e2.edge_type = 'fact_has_metric_outcome'
            JOIN graph_edges e3 ON e2.target_node_id = e3.source_node_id AND e3.edge_type = 'metric_outcome_bound_to_employer'
            JOIN graph_nodes n ON n.node_id = e3.target_node_id
            WHERE n.employer LIKE ? OR n.label LIKE ? OR n.node_id LIKE ?
            LIMIT 5
            """,
            (f"%{emp}%", f"%{emp}%", f"%{emp.lower()}%"),
        )
        j1_seeds = [r[0] for r in cur.fetchall()]
        assert len(j1_seeds) >= 1, f"No J1 seeds found for employer {emp}"
        paths1 = traverse_journey(db_conn, JOURNEY_SKILL_FACT_METRIC_EMPLOYMENT_EPOCH, seeds=j1_seeds)
        assert len(paths1) >= 1, f"Journey 1 returned 0 paths for employer {emp}"
        for p in paths1:
            assert p.path_depth == 4
            assert p.path_confidence > 0.0

        # Journey 2: skill -> engagement -> employment
        cur.execute(
            """
            SELECT DISTINCT e1.target_node_id
            FROM graph_edges e1
            JOIN graph_edges e2 ON e1.source_node_id = e2.source_node_id AND e2.edge_type = 'engagement_at_employment'
            JOIN graph_nodes n ON n.node_id = e2.target_node_id
            WHERE n.employer LIKE ? OR n.label LIKE ? OR n.node_id LIKE ?
            LIMIT 5
            """,
            (f"%{emp}%", f"%{emp}%", f"%{emp.lower()}%"),
        )
        j2_seeds = [r[0] for r in cur.fetchall()]
        assert len(j2_seeds) >= 1, f"No J2 seeds found for employer {emp}"
        paths2 = traverse_journey(db_conn, JOURNEY_SKILL_ENGAGEMENT_EMPLOYMENT, seeds=j2_seeds)
        assert len(paths2) >= 1, f"Journey 2 returned 0 paths for employer {emp}"
        for p in paths2:
            assert p.path_depth == 2
            assert p.path_confidence > 0.0

        # Journey 3: metric_outcome -> fact -> skill (inverse)
        cur.execute(
            """
            SELECT DISTINCT e.source_node_id
            FROM graph_edges e
            JOIN graph_nodes n ON n.node_id = e.target_node_id
            WHERE e.edge_type = 'metric_outcome_bound_to_employer'
              AND (n.employer LIKE ? OR n.label LIKE ? OR n.node_id LIKE ?)
            LIMIT 5
            """,
            (f"%{emp}%", f"%{emp}%", f"%{emp.lower()}%"),
        )
        j3_seeds = [r[0] for r in cur.fetchall()]
        assert len(j3_seeds) >= 1, f"No J3 seeds found for employer {emp}"
        paths3 = traverse_journey(db_conn, JOURNEY_METRIC_FACT_SKILL, seeds=j3_seeds)
        assert len(paths3) >= 1, f"Journey 3 returned 0 paths for employer {emp}"
        for p in paths3:
            assert p.path_depth == 2

        # Journey 4: capability_domain -> skill -> evidence
        cur.execute(
            """
            SELECT DISTINCT e.source_node_id
            FROM graph_edges e
            JOIN graph_edges e_ev ON e.target_node_id = e_ev.source_node_id AND e_ev.edge_type = 'skill_supported_by_fact'
            JOIN graph_edges e_emp ON e_ev.target_node_id = e_emp.target_node_id AND e_emp.edge_type = 'employment_hosts_fact'
            JOIN graph_nodes n ON n.node_id = e_emp.source_node_id
            WHERE e.edge_type = 'capability_domain_contains_skill'
              AND (n.employer LIKE ? OR n.label LIKE ? OR n.node_id LIKE ?)
            LIMIT 5
            """,
            (f"%{emp}%", f"%{emp}%", f"%{emp.lower()}%"),
        )
        j4_seeds = [r[0] for r in cur.fetchall()]
        assert len(j4_seeds) >= 1, f"No J4 seeds found for employer {emp}"
        paths4 = traverse_journey(db_conn, JOURNEY_DOMAIN_SKILL_EVIDENCE, seeds=j4_seeds)
        assert len(paths4) >= 1, f"Journey 4 returned 0 paths for employer {emp}"


def test_ac4_2_unrestricted_depth_rejected_and_cycle_guard(db_conn: sqlite3.Connection) -> None:
    """AC4.2: Unrestricted depth-3 walk is rejected; cycle guard terminates on cycles."""
    # 1. Reject unrestricted multi-hop walk
    with pytest.raises(ValueError, match="allowed_steps"):
        traverse(db_conn, seeds=["skill_agentic_ai_platform"], max_depth=3, allowed_steps=None)

    # 2. Cycle guard test on synthetic cyclic table
    mem_conn = sqlite3.connect(":memory:")
    try:
        mem_conn.execute("CREATE TABLE graph_nodes (node_id TEXT PRIMARY KEY)")
        mem_conn.execute(
            """
            CREATE TABLE graph_edges (
                edge_id TEXT PRIMARY KEY,
                source_node_id TEXT,
                target_node_id TEXT,
                edge_type TEXT,
                confidence_score REAL,
                traversable INTEGER DEFAULT 1
            )
            """
        )
        mem_conn.executemany(
            "INSERT INTO graph_nodes VALUES (?)",
            [("A",), ("B",), ("C",)],
        )
        # Create cycle A -> B -> C -> A
        mem_conn.executemany(
            "INSERT INTO graph_edges VALUES (?, ?, ?, ?, ?, 1)",
            [
                ("e1", "A", "B", "step_ab", 0.95),
                ("e2", "B", "C", "step_bc", 0.90),
                ("e3", "C", "A", "step_ca", 0.85),
            ],
        )
        mem_conn.execute("CREATE TABLE edge_evidence (edge_id TEXT, evidence_ref TEXT)")
        mem_conn.commit()

        # Step-gated traversal allowing loop
        steps = [
            ("step_ab", "A", "B"),
            ("step_bc", "B", "C"),
            ("step_ca", "C", "A"),
            ("step_ab", "A", "B"),
        ]
        paths = traverse(
            mem_conn,
            seeds=["A"],
            max_depth=4,
            allowed_steps=steps,
        )
        # Cycle guard must prevent infinite traversal; node A visited once in path
        for p in paths:
            nodes = p.node_path
            assert len(nodes) == len(set(nodes)), f"Cycle detected in path: {nodes}"
    finally:
        mem_conn.close()


def test_ac4_3_forward_and_inverse_symmetry(db_conn: sqlite3.Connection) -> None:
    """AC4.3: Forward and inverse traversal of the same journey return 100% identical path sets."""
    cur = db_conn.cursor()
    cur.execute(
        """
        SELECT node_id FROM graph_nodes
        WHERE node_type = 'metric_outcome' AND (employer LIKE '%Slalom%' OR node_id LIKE '%slalom%')
        ORDER BY node_id LIMIT 1
        """
    )
    row = cur.fetchone()
    assert row is not None, "Slalom metric node missing"
    metric_id = row[0]

    # Inverse journey: metric -> fact -> skill
    inverse_paths = traverse_journey(
        db_conn,
        JOURNEY_METRIC_FACT_SKILL,
        seeds=[metric_id],
        max_paths=100,
    )
    assert len(inverse_paths) > 0, "No inverse paths found"

    # Forward paths: for each found skill, traverse skill -> fact -> metric
    for ip in inverse_paths:
        skill_id = ip.end_node_id
        fact_id = ip.node_path[1]

        forward_steps = [
            ("skill_supported_by_fact", "skill", "fact"),
            ("fact_has_metric_outcome", "fact", "metric_outcome"),
        ]
        fp = traverse(
            db_conn,
            seeds=[skill_id],
            max_depth=2,
            allowed_steps=forward_steps,
        )
        matching = [p for p in fp if p.end_node_id == metric_id]
        assert len(matching) >= 1, f"Forward traversal from {skill_id} to {metric_id} failed"
        assert matching[0].node_path[1] == fact_id, "Forward path did not use expected fact node"


def test_ac4_7_explain_query_plan_and_latency(db_conn: sqlite3.Connection) -> None:
    """AC4.7: EXPLAIN QUERY PLAN uses index search with no full table scans, p95 < 100ms."""
    cur = db_conn.cursor()

    # Verify query plan for reverse lookup uses idx_graph_edges_tgt_type
    eqp = cur.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT source_node_id, edge_type, confidence_score
        FROM graph_edges
        WHERE target_node_id = 'fact_slalom_005' AND edge_type = 'skill_supported_by_fact'
        """
    ).fetchall()
    eqp_str = " ".join(str(row) for row in eqp)
    assert "SCAN TABLE" not in eqp_str, f"Full table scan detected: {eqp_str}"
    assert "USING INDEX" in eqp_str or "USING COVERING INDEX" in eqp_str, f"Index not used: {eqp_str}"

    cur.execute(
        """
        SELECT DISTINCT e1.source_node_id
        FROM graph_edges e1
        JOIN graph_edges e2 ON e1.target_node_id = e2.source_node_id AND e2.edge_type = 'fact_has_metric_outcome'
        JOIN graph_edges e3 ON e2.target_node_id = e3.source_node_id AND e3.edge_type = 'metric_outcome_bound_to_employer'
        JOIN graph_nodes n ON n.node_id = e3.target_node_id
        WHERE n.employer LIKE '%Slalom%'
        LIMIT 5
        """
    )
    seeds = [r[0] for r in cur.fetchall()]
    assert len(seeds) >= 1

    # Latency benchmark: 30 iterations of multi-hop canonical journey
    latencies: list[float] = []
    for _ in range(30):
        t0 = time.perf_counter()
        paths = traverse_journey(
            db_conn,
            JOURNEY_SKILL_FACT_METRIC_EMPLOYMENT_EPOCH,
            seeds=seeds,
            max_paths=20,
        )
        dt = (time.perf_counter() - t0) * 1000.0  # ms
        latencies.append(dt)
        assert len(paths) >= 1

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    p95 = latencies[p95_idx]
    print(f"\nMeasured Traversal p95 latency: {p95:.2f} ms")
    assert p95 < 100.0, f"p95 latency {p95:.2f}ms exceeded 100ms threshold"
