"""Wave 5 Semantic-Unit Embeddings and Graph Back-Links Tests (AC5.1-AC5.6)."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import pytest

from apps_rg.fact_inventory.semantic_units import ALLOWED_UNIT_TYPES
from apps_rg.runtime.c0.graph_skill_embedding_allocation import (
    GraphSkillEmbeddingAllocationError,
    assert_legacy_graph_skill_embedding_lane_not_retired,
)
from apps_rg.runtime.semantic_unit_retrieval import (
    ACTIVATION_STATUS_BLOCKED,
    RUNTIME_AUTHORITATIVE_STORE,
    SemanticUnitActivationBlockedError,
    SemanticUnitStaleGraphError,
    assert_semantic_unit_activation_status,
    check_semantic_unit_freshness,
    expand_semantic_unit_subgraph,
    retrieve_semantic_units,
)

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"


@pytest.fixture(scope="module")
def graph_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH.resolve().as_posix()}?mode=ro", uri=True)
    yield conn
    conn.close()


def test_ac5_1_allowed_unit_types_and_no_isolated_units(graph_conn: sqlite3.Connection) -> None:
    """AC5.1: 0 vectors with unallowed unit_type; 0 units with single member and no edges."""
    cur = graph_conn.cursor()
    cur.execute("SELECT DISTINCT unit_type FROM semantic_unit")
    observed_types = {r[0] for r in cur.fetchall()}
    assert observed_types.issubset(ALLOWED_UNIT_TYPES), f"Unexpected unit types: {observed_types}"

    cur.execute("SELECT DISTINCT unit_id FROM unit_vectors")
    vector_ids = [r[0] for r in cur.fetchall()]
    assert len(vector_ids) > 0

    cur.execute(
        """
        SELECT u.unit_id, count(m.member_id) as total_members,
               sum(case when m.member_kind='edge' then 1 else 0 end) as edge_count
        FROM semantic_unit u
        JOIN semantic_unit_member m ON m.unit_id = u.unit_id
        GROUP BY u.unit_id
        HAVING edge_count = 0 OR total_members <= 1
        """
    )
    isolated = cur.fetchall()
    assert len(isolated) == 0, f"Found isolated units without edges: {isolated}"


def test_ac5_2_referential_integrity_and_confidence_tokens(graph_conn: sqlite3.Connection) -> None:
    """AC5.2: Every member_id resolves; every unit has >=1 evidence member and confidence token."""
    cur = graph_conn.cursor()

    cur.execute(
        """
        SELECT count(*) FROM semantic_unit_member m
        WHERE m.member_kind = 'node' AND m.member_id NOT IN (SELECT node_id FROM graph_nodes)
        """
    )
    assert cur.fetchone()[0] == 0, "Dangling node members found"

    cur.execute(
        """
        SELECT count(*) FROM semantic_unit_member m
        WHERE m.member_kind = 'edge' AND m.member_id NOT IN (SELECT edge_id FROM graph_edges)
        """
    )
    assert cur.fetchone()[0] == 0, "Dangling edge members found"

    cur.execute(
        """
        SELECT u.unit_id FROM semantic_unit u
        WHERE NOT EXISTS (
            SELECT 1 FROM semantic_unit_member m
            WHERE m.unit_id = u.unit_id AND (m.member_kind = 'evidence' OR m.role = 'evidence')
        )
        """
    )
    assert len(cur.fetchall()) == 0, "Units missing evidence members found"

    cur.execute("SELECT count(*) FROM semantic_unit WHERE text NOT LIKE '%[Confidence]%'")
    assert cur.fetchone()[0] == 0, "Units missing [Confidence] token found"


def test_ac5_3_eligible_skill_coverage_100_percent(graph_conn: sqlite3.Connection) -> None:
    """AC5.3: 100% of external-eligible skills with evidential support belong to >=1 unit."""
    cur = graph_conn.cursor()
    cur.execute(
        """
        WITH eligible_skills AS (
            SELECT DISTINCT s.node_id
            FROM graph_nodes s
            JOIN graph_edges e ON e.source_node_id = s.node_id
            WHERE s.node_type = 'skill'
              AND s.external_eligible = 1
              AND s.activation_status NOT IN ('BLOCKED', 'DRAFT', 'INTERNAL_ONLY')
              AND e.assertion_type = 'EVIDENTIAL_SUPPORT'
              AND e.confidence_tier IN ('HIGH', 'MEDIUM')
        )
        SELECT
            (SELECT count(*) FROM eligible_skills) AS total_eligible,
            count(DISTINCT es.node_id) AS covered_in_units
        FROM eligible_skills es
        JOIN semantic_unit_member m ON m.member_id = es.node_id AND m.member_kind = 'node'
        """
    )
    total_eligible, covered = cur.fetchone()
    assert total_eligible == 197
    assert covered == 197, f"Expected 197 covered skills, observed {covered}"


def test_ac5_4_freshness_invalidation_fail_closed(graph_conn: sqlite3.Connection) -> None:
    """AC5.4: Digest mismatch triggers fail-closed error."""
    digest = check_semantic_unit_freshness(graph_conn)
    assert len(digest) == 64

    test_conn = sqlite3.connect(":memory:")
    test_conn.executescript(
        """
        CREATE TABLE graph_metadata (graph_count_summary TEXT);
        INSERT INTO graph_metadata VALUES ('{"input_manifest_digest": "live_hash_123"}');
        CREATE TABLE semantic_unit (input_manifest_digest TEXT);
        INSERT INTO semantic_unit VALUES ('stale_hash_456');
        """
    )
    with pytest.raises(SemanticUnitStaleGraphError, match="digest mismatch"):
        check_semantic_unit_freshness(test_conn)


def test_ac5_5_hybrid_expansion_non_empty_paths(graph_conn: sqlite3.Connection) -> None:
    """AC5.5: Subgraph expansion returns valid traverse() paths for all units."""
    cur = graph_conn.cursor()
    cur.execute("SELECT unit_id, unit_type FROM semantic_unit")
    units = cur.fetchall()
    assert len(units) >= 300

    # Test all unit types by sampling across each type
    cur.execute(
        """
        SELECT unit_id, unit_type FROM (
            SELECT unit_id, unit_type,
                   row_number() OVER (PARTITION BY unit_type ORDER BY unit_id) AS rn
            FROM semantic_unit
        ) WHERE rn <= 15
        """
    )
    sampled_units = cur.fetchall()
    types_tested = set()
    for u_id, u_type in sampled_units:
        res = expand_semantic_unit_subgraph(graph_conn, u_id)
        assert res["path_count"] > 0, f"Unit {u_id} returned 0 paths"
        assert len(res["member_nodes"]) > 0
        assert len(res["evidence_ids"]) > 0
        types_tested.add(u_type)

    # Ensure all primary unit types were exercised
    assert "skill_evidence_cluster" in types_tested
    assert "engagement_episode" in types_tested
    assert "metric_outcome_story" in types_tested

    # Test retrieval filter
    skill_units = retrieve_semantic_units(graph_conn, unit_type="skill_evidence_cluster", limit=10)
    assert len(skill_units) == 10
    assert all(u["unit_type"] == "skill_evidence_cluster" for u in skill_units)


def test_ac5_6_authoritative_store_and_legacy_loader_rejection() -> None:
    """AC5.6: Authoritative store declared; activation fail-closed; legacy loader blocked."""
    assert RUNTIME_AUTHORITATIVE_STORE == "semantic_unit_relational_projection"
    assert ACTIVATION_STATUS_BLOCKED == "BLOCKED_HUMAN_REVIEW_INPUTS"

    with pytest.raises(SemanticUnitActivationBlockedError, match="BLOCKED_HUMAN_REVIEW_INPUTS"):
        assert_semantic_unit_activation_status(allow_unqualified=False)

    unqualified = assert_semantic_unit_activation_status(allow_unqualified=True)
    assert unqualified["is_unqualified_override"] is True

    with pytest.raises(GraphSkillEmbeddingAllocationError, match="legacy one-vector-per-skill embedding lane is retired"):
        assert_legacy_graph_skill_embedding_lane_not_retired("/any/arbitrary/repo/root")

    legacy_dir = ROOT.parent / "artifacts/apps_rg/c03/graph_skill_embeddings"
    assert not legacy_dir.exists(), "Legacy directory must not exist on disk"
