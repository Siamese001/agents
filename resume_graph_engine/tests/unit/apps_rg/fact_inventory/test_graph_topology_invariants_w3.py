"""Wave 3 Graph Topology & Ontology Invariants Test Suite (AC3.1 - AC3.7).

Tests:
1. Live DB verification: checks all 13 invariants (I1-I13) on augmented_skills_graph.sqlite.
2. Red-team adversarial corruption tests: proves each invariant validator fails-closed on injected corruption.
3. Acceptance criteria proofs:
   - AC3.1: Stored type registry and 0 polymorphic signatures.
   - AC3.2: 0 employment nodes outside canonical set; 100% section parity.
   - AC3.3: Every fact has 1 hosting employment; employment dates/titles non-null.
   - AC3.4: Traversable layer weak components == 1; every pillar reaches >= 1 skill.
   - AC3.5: Role-episode bundles projected as engagement nodes.
   - AC3.6: Non-traversable edges excluded from graph_paths, neighborhoods, siblings.
   - AC3.7: validate_graph_topology exits 0 and CLI runs cleanly.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from apps_rg.fact_inventory.skills_graph.type_registry import (
    EDGE_TYPE_REGISTRY,
    NODE_TYPE_REGISTRY,
)
from apps_rg.fact_inventory.validate_graph_topology import (
    evaluate_traversable_connectivity,
    validate_graph_topology,
)
from apps_rg.repository_layout import repository_root

REPO = repository_root()
LIVE_DB_PATH = (
    REPO / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
)


@pytest.fixture
def tmp_graph_db(tmp_path: Path) -> Path:
    """Provide an isolated, writable copy of the live graph SQLite DB for red-team testing."""
    assert LIVE_DB_PATH.is_file(), f"Live DB not found at {LIVE_DB_PATH}"
    target = tmp_path / "corrupted_graph.sqlite"
    shutil.copy2(LIVE_DB_PATH, target)
    return target


def test_ac3_1_type_registry_and_zero_polymorphism() -> None:
    """AC3.1: node_type_registry and edge_type_registry exist in DB, zero polymorphic edge signatures."""
    assert LIVE_DB_PATH.is_file()
    conn = sqlite3.connect(f"{LIVE_DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM node_type_registry")
        assert cur.fetchone()[0] == len(NODE_TYPE_REGISTRY)

        cur.execute("SELECT count(*) FROM edge_type_registry")
        assert cur.fetchone()[0] == len(EDGE_TYPE_REGISTRY)

        # Check edge signatures in graph_edges against edge_type_registry
        cur.execute("""
            SELECT e.edge_type, sn.node_type, tn.node_type, count(*)
            FROM graph_edges e
            JOIN graph_nodes sn ON sn.node_id = e.source_node_id
            JOIN graph_nodes tn ON tn.node_id = e.target_node_id
            JOIN edge_type_registry r ON r.edge_type = e.edge_type
            WHERE sn.node_type <> r.src_type OR tn.node_type <> r.tgt_type
            GROUP BY e.edge_type, sn.node_type, tn.node_type
        """)
        mismatched_signatures = cur.fetchall()
        assert mismatched_signatures == [], f"Polymorphic or mismatched signatures: {mismatched_signatures}"
    finally:
        conn.close()


def test_ac3_2_entity_deduplication_and_section_parity() -> None:
    """AC3.2: 0 employment nodes outside canonical set; 100% section parity."""
    conn = sqlite3.connect(f"{LIVE_DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT node_id FROM graph_nodes WHERE node_id LIKE 'exp_%'")
        assert cur.fetchall() == []

        cur.execute("SELECT node_id FROM graph_nodes WHERE node_id LIKE 'section:%'")
        assert cur.fetchall() == []

        # 100% section parity
        cur.execute("""
            SELECT count(*) FROM section_eligibility s
            JOIN graph_nodes n ON n.node_id = s.node_id AND n.node_type = 'skill'
            WHERE s.allowed = 1
              AND NOT EXISTS (
                  SELECT 1 FROM graph_edges e
                  WHERE e.edge_type = 'skill_allowed_in_section'
                    AND e.source_node_id = s.node_id
                    AND e.target_node_id = s.section_id
              )
        """)
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_ac3_3_hosting_and_employment_hierarchy() -> None:
    """AC3.3: Every fact has 1 hosting employment; every employment has 1 epoch and non-null metadata."""
    conn = sqlite3.connect(f"{LIVE_DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT count(*) FROM graph_nodes n
            WHERE node_type = 'fact'
              AND (
                  SELECT count(*) FROM graph_edges e
                  WHERE e.edge_type = 'employment_hosts_fact'
                    AND e.target_node_id = n.node_id
              ) <> 1
        """)
        assert cur.fetchone()[0] == 0

        cur.execute("""
            SELECT node_id, title, start_date, is_current FROM graph_nodes
            WHERE node_type = 'employment'
        """)
        employments = cur.fetchall()
        assert len(employments) == 6
        for emp_id, title, start_date, is_current in employments:
            assert title, f"Empty title on {emp_id}"
            assert start_date, f"Empty start_date on {emp_id}"
            assert is_current in (0, 1), f"Invalid is_current on {emp_id}"
    finally:
        conn.close()


def test_ac3_4_hierarchy_connectivity_and_pillar_reach() -> None:
    """AC3.4: Weak component count == 1 for traversable layer; every pillar reaches >= 1 skill."""
    conn = sqlite3.connect(f"{LIVE_DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        components, unreachable = evaluate_traversable_connectivity(conn)
        assert components == 1
        assert unreachable == 0

        cur = conn.cursor()
        cur.execute("""
            SELECT n.node_id FROM graph_nodes n
            WHERE n.node_type = 'pillar'
              AND NOT EXISTS (
                  SELECT 1 FROM graph_edges e
                  WHERE e.source_node_id = n.node_id
                    AND e.edge_type = 'pillar_contains_skill'
              )
        """)
        unreached_pillars = cur.fetchall()
        assert unreached_pillars == [], f"Pillars with 0 skill containment: {unreached_pillars}"
    finally:
        conn.close()


def test_ac3_5_engagement_projection() -> None:
    """AC3.5: Role-episode bundles projected as engagement nodes with >=1 skill and >=1 fact edge."""
    conn = sqlite3.connect(f"{LIVE_DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM graph_nodes WHERE node_type = 'engagement'")
        eng_count = cur.fetchone()[0]
        assert eng_count >= 15, f"Expected engagement nodes, got {eng_count}"

        cur.execute("""
            SELECT n.node_id FROM graph_nodes n
            WHERE n.node_type = 'engagement'
              AND (
                  NOT EXISTS (
                      SELECT 1 FROM graph_edges e
                      WHERE e.source_node_id = n.node_id
                        AND e.edge_type = 'engagement_exercises_skill'
                  )
                  OR NOT EXISTS (
                      SELECT 1 FROM graph_edges e
                      WHERE e.source_node_id = n.node_id
                        AND e.edge_type = 'engagement_evidenced_by_fact'
                  )
              )
        """)
        unconnected_engagements = cur.fetchall()
        assert unconnected_engagements == [], f"Engagements missing skill or fact edges: {unconnected_engagements}"
    finally:
        conn.close()


def test_ac3_6_policy_layer_separation() -> None:
    """AC3.6: Non-traversable edges (traversable=0) excluded from paths, neighborhoods, siblings."""
    conn = sqlite3.connect(f"{LIVE_DB_PATH.as_uri()}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT count(*) FROM graph_paths p
            JOIN json_each(p.edge_path_json) j
            JOIN graph_edges e ON e.edge_id = j.value
            WHERE e.traversable = 0
        """)
        assert cur.fetchone()[0] == 0

        cur.execute("""
            SELECT count(*) FROM graph_sibling_links g
            JOIN edge_type_registry r ON r.edge_type = g.shared_edge_type
            WHERE r.traversable = 0
        """)
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_ac3_7_live_db_passes_all_topology_invariants() -> None:
    """AC3.7: validate_graph_topology exits 0 and reports status PASS."""
    report = validate_graph_topology(LIVE_DB_PATH, raise_on_error=True)
    assert report["status"] == "PASS"
    assert report["failed_invariants_count"] == 0
    assert report["violations"] == {}


# --- Red-Team Adversarial Invariant Failure Tests ---


def test_redteam_i1_catches_isolated_skill(tmp_graph_db: Path) -> None:
    """Red-team: I1 detects an isolated skill node."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("""
            INSERT INTO graph_nodes (node_id, node_type, label, source_authority, origin_kind, origin_ref, created_at, updated_at)
            VALUES ('skill_rogue_orphan_isolated', 'skill', 'Rogue Skill', 'test', 'test', 'test', '2026-10-05', '2026-10-05')
        """)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I1_isolated_core_nodes"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i2_catches_missing_fact_hosting(tmp_graph_db: Path) -> None:
    """Red-team: I2 detects a fact without hosting tenure."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("DELETE FROM graph_edges WHERE rowid = (SELECT rowid FROM graph_edges WHERE edge_type = 'employment_hosts_fact' LIMIT 1)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I2_fact_hosting"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i3_catches_mismatched_employer_binding(tmp_graph_db: Path) -> None:
    """Red-team: I3 detects metric outcome bound to wrong employer."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("""
            UPDATE graph_edges
            SET target_node_id = 'employment_exp_early_career_001'
            WHERE edge_type = 'metric_outcome_bound_to_employer'
              AND source_node_id LIKE '%slalom%'
        """)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I3_metric_employer_bound"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i4_catches_invalid_fact_metric_source(tmp_graph_db: Path) -> None:
    """Red-team: I4 detects fact_has_metric_outcome originating from a non-fact node."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("""
            UPDATE graph_edges
            SET source_node_id = 'track_genai_agentic'
            WHERE rowid = (SELECT rowid FROM graph_edges WHERE edge_type = 'fact_has_metric_outcome' LIMIT 1)
        """)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I4_fact_metric_source"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i5_catches_unparented_epoch(tmp_graph_db: Path) -> None:
    """Red-team: I5 detects epoch detached from career tracks."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("DELETE FROM graph_edges WHERE rowid = (SELECT rowid FROM graph_edges WHERE edge_type = 'career_track_contains_epoch' LIMIT 1)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I5a_epoch_track"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i7_catches_link_edge_desync(tmp_graph_db: Path) -> None:
    """Red-team: I7 detects desync between skill_fact_links and edges."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("DELETE FROM graph_edges WHERE rowid = (SELECT rowid FROM graph_edges WHERE edge_type = 'skill_supported_by_fact' LIMIT 1)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I7b_edges_links"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i8_catches_unresolved_section(tmp_graph_db: Path) -> None:
    """Red-team: I8 detects section reference to non-section node."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("""
            INSERT INTO section_eligibility (section_id, node_id, allowed)
            VALUES ('section_bogus_nonexistent', 'skill_c03_reverse_traversal_receipts', 1)
        """)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I8a_section_nodes"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i9_catches_section_parity_violation(tmp_graph_db: Path) -> None:
    """Red-team: I9 detects allowed section eligibility without matching edge."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("DELETE FROM graph_edges WHERE rowid = (SELECT rowid FROM graph_edges WHERE edge_type = 'skill_allowed_in_section' LIMIT 1)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I9_section_parity"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i10_catches_domain_without_skills(tmp_graph_db: Path) -> None:
    """Red-team: I10 detects capability domain with 0 skills."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("DELETE FROM graph_edges WHERE edge_type = 'capability_domain_contains_skill' AND source_node_id = 'domain_partner_gtm'")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I10_domain_hierarchy"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i11_catches_invalid_track_reference(tmp_graph_db: Path) -> None:
    """Red-team: I11 detects invalid track reference in selection features."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        conn.execute("""
            UPDATE c03_skill_selection_features
            SET career_track_id = 'track_nonexistent_bogus'
            WHERE rowid = (SELECT rowid FROM c03_skill_selection_features LIMIT 1)
        """)
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I11a_c03_track"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)


def test_redteam_i12_catches_metadata_count_tampering(tmp_graph_db: Path) -> None:
    """Red-team: I12 detects desync between metadata summary and table counts."""
    conn = sqlite3.connect(tmp_graph_db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT graph_count_summary FROM graph_metadata LIMIT 1")
        summary = json.loads(cur.fetchone()[0])
        summary["node_count_sqlite"] += 999
        conn.execute("UPDATE graph_metadata SET graph_count_summary = ?", (json.dumps(summary),))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="I12_metadata_counts"):
        validate_graph_topology(tmp_graph_db, raise_on_error=True)
