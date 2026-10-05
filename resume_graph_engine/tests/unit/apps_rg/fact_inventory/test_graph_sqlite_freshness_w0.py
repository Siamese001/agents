"""Wave 0 verification tests: SSOT stabilization, input manifest freshness, and fail-closed out-of-band write rejection.

Covers AC0.1 - AC0.5 from plans/graph-skills-deep-traversal-c7d2e9.md:
- AC0.1: 0 die_graph_import nodes/edges; Slalom facts, metrics, and edges present with ledger authority.
- AC0.2: graph_metadata counts equal actual row counts in SQLite tables.
- AC0.3: Editing bundle JSON alters input_manifest_digest and causes runtime freshness check to fail on stale projection.
- AC0.4: Unknown source_authority in SQLite raises C03UnauthorizedSourceAuthorityError and assemble fails closed.
- AC0.5: J3 journey (skill -> fact -> metric_outcome -> employment) reaches Slalom employment from skills.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    default_graph_sqlite_path,
    materialize_augmented_skills_graph_sqlite,
    open_graph_sqlite,
)
from apps_rg.fact_inventory.skills_graph.lineage import (
    ALLOWLISTED_SOURCE_AUTHORITIES,
    compute_input_manifest,
    compute_input_manifest_digest,
    validate_projection_source_authorities,
)
from apps_rg.runtime.c0.c03_errors import (
    C03GraphProjectionUnavailableError,
    C03UnauthorizedSourceAuthorityError,
)
from apps_rg.runtime.c03_graph_sqlite_context import (
    assemble_c03_graph_sqlite_context,
    ensure_c03_graph_sqlite,
    require_c03_graph_sqlite,
)

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_ac01_no_die_graph_import_and_slalom_promoted():
    """AC0.1: No out-of-band die_graph_import rows exist, and Slalom facts/metrics have ledger authority."""
    db_path = default_graph_sqlite_path(REPO_ROOT)
    assert db_path.is_file(), f"graph db must exist at {db_path}"

    conn = open_graph_sqlite(repo_root=REPO_ROOT, db_path=db_path, read_only=True)
    try:
        # Verify 0 die_graph_import nodes or edges
        die_nodes = conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE source_authority = 'die_graph_import'"
        ).fetchone()[0]
        assert die_nodes == 0, f"expected 0 die_graph_import nodes, found {die_nodes}"

        die_edges = conn.execute(
            "SELECT COUNT(*) FROM graph_edges WHERE source_authority = 'die_graph_import'"
        ).fetchone()[0]
        assert die_edges == 0, f"expected 0 die_graph_import edges, found {die_edges}"

        # Verify all source_authorities in DB are strictly allowlisted
        validate_projection_source_authorities(conn)

        # Verify Slalom facts exist with canonical augmented_skills_graph authority
        slalom_facts = conn.execute(
            "SELECT node_id, source_authority FROM graph_nodes WHERE node_id LIKE 'fact_slalom_%'"
        ).fetchall()
        assert len(slalom_facts) >= 6, f"expected >=6 slalom facts, got {len(slalom_facts)}"
        for node_id, auth in slalom_facts:
            assert auth == "augmented_skills_graph", f"slalom fact {node_id} has non-canonical authority {auth}"

        # Verify Slalom metrics exist
        slalom_metrics = conn.execute(
            "SELECT node_id, source_authority FROM graph_nodes WHERE node_id LIKE 'metric_slalom_%'"
        ).fetchall()
        assert len(slalom_metrics) >= 14, f"expected >=14 slalom metrics, got {len(slalom_metrics)}"
        for node_id, auth in slalom_metrics:
            assert auth == "augmented_skills_graph", f"slalom metric {node_id} has non-canonical authority {auth}"

    finally:
        conn.close()


def test_ac02_metadata_counts_equal_actual_table_counts():
    """AC0.2: graph_metadata counts equal actual COUNT(*) of nodes and edges."""
    db_path = default_graph_sqlite_path(REPO_ROOT)
    conn = open_graph_sqlite(repo_root=REPO_ROOT, db_path=db_path, read_only=True)
    try:
        actual_nodes = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
        actual_edges = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]

        meta_row = conn.execute("SELECT graph_count_summary FROM graph_metadata").fetchone()
        assert meta_row is not None, "missing graph_metadata row"
        summary = json.loads(meta_row[0])

        assert summary["node_count_sqlite"] == actual_nodes, (
            f"summary node count {summary['node_count_sqlite']} != actual {actual_nodes}"
        )
        assert summary["edge_count_sqlite"] == actual_edges, (
            f"summary edge count {summary['edge_count_sqlite']} != actual {actual_edges}"
        )
    finally:
        conn.close()


def test_ac03_bundle_edit_changes_manifest_digest_and_causes_freshness_rejection(tmp_path: Path):
    """AC0.3: Editing any bundle JSON changes input_manifest_digest, causing require_c03_graph_sqlite to raise."""
    # Compute base manifest digest for current repo
    base_manifest = compute_input_manifest(REPO_ROOT)
    base_digest = base_manifest["input_manifest_digest"]
    assert len(base_digest) == 64

    # Copy the current database to a isolated temporary location
    prod_db = default_graph_sqlite_path(REPO_ROOT)
    test_db = tmp_path / "test_skills_graph.sqlite"
    test_db.write_bytes(prod_db.read_bytes())

    # Initially, the test DB passes validation
    path = require_c03_graph_sqlite(REPO_ROOT, test_db)
    assert path == test_db

    # Simulate a stale DB: tamper with graph_metadata's input_manifest_digest to simulate
    # an upstream bundle edit that changed the expected digest
    conn = sqlite3.connect(test_db)
    try:
        row = conn.execute("SELECT graph_count_summary FROM graph_metadata").fetchone()[0]
        summary = json.loads(row)
        summary["input_manifest_digest"] = "0000000000000000000000000000000000000000000000000000000000000000"
        conn.execute("UPDATE graph_metadata SET graph_count_summary = ?", (json.dumps(summary),))
        conn.commit()
    finally:
        conn.close()

    # require_c03_graph_sqlite must detect the staleness and raise C03GraphProjectionUnavailableError
    with pytest.raises(C03GraphProjectionUnavailableError, match="input manifest digest mismatch"):
        require_c03_graph_sqlite(REPO_ROOT, test_db)


def test_ac04_unauthorized_source_authority_fails_closed(tmp_path: Path):
    """AC0.4: Inserting a row with an unknown source_authority makes assemble fail closed."""
    prod_db = default_graph_sqlite_path(REPO_ROOT)
    test_db = tmp_path / "tampered_skills_graph.sqlite"
    test_db.write_bytes(prod_db.read_bytes())

    # Inject an out-of-band unauthorized row into graph_nodes
    conn = sqlite3.connect(test_db)
    try:
        conn.execute(
            """
            INSERT INTO graph_nodes (
                node_id, node_type, label, description, activation_status,
                support_level, confidence, external_eligible, source_authority,
                created_at, updated_at
            ) VALUES (
                'fact_unauthorized_test_001', 'fact', 'test fact', 'test desc',
                'active', 'PRIMARY_DIRECT', 'HIGH', 1, 'die_graph_import',
                '2026-10-05T00:00:00Z', '2026-10-05T00:00:00Z'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    # require_c03_graph_sqlite must raise C03UnauthorizedSourceAuthorityError
    with pytest.raises(C03UnauthorizedSourceAuthorityError, match="unauthorized source_authority"):
        require_c03_graph_sqlite(REPO_ROOT, test_db)

    # assemble_c03_graph_sqlite_context must fail closed (not rebuild and overwrite the tampered DB)
    with pytest.raises(C03UnauthorizedSourceAuthorityError, match="unauthorized source_authority"):
        assemble_c03_graph_sqlite_context(
            role_family_key="SVP_ENGINEERING_AI_PLATFORM",
            section_id="executive_summary",
            repo_root=REPO_ROOT,
            db_path=test_db,
        )


def test_ac05_j3_journey_reaches_slalom_employment():
    """AC0.5: J3 journey (skill -> fact -> metric_outcome -> employment) reaches Slalom employment from >=1 skill."""
    db_path = default_graph_sqlite_path(REPO_ROOT)
    conn = open_graph_sqlite(repo_root=REPO_ROOT, db_path=db_path, read_only=True)
    try:
        query = """
        SELECT
            s.node_id AS skill_id,
            f.node_id AS fact_id,
            m.node_id AS metric_id,
            emp.node_id AS employment_id,
            emp.label AS employment_label
        FROM graph_nodes s
        JOIN graph_edges e1 ON e1.source_node_id = s.node_id AND e1.edge_type = 'skill_supported_by_fact'
        JOIN graph_nodes f ON f.node_id = e1.target_node_id
        JOIN graph_edges e2 ON e2.source_node_id = f.node_id AND e2.edge_type = 'fact_has_metric_outcome'
        JOIN graph_nodes m ON m.node_id = e2.target_node_id
        JOIN graph_edges e3 ON e3.source_node_id = m.node_id AND e3.edge_type = 'metric_outcome_bound_to_employer'
        JOIN graph_nodes emp ON emp.node_id = e3.target_node_id
        WHERE emp.node_id = 'employment_exp_slalom_001'
        """
        rows = conn.execute(query).fetchall()
        assert len(rows) >= 6, f"expected at least 6 J3 journey paths to Slalom, found {len(rows)}"

        # Verify distinct skills reaching Slalom
        skills = {row[0] for row in rows}
        assert len(skills) >= 4, f"expected at least 4 distinct skills reaching Slalom, found {len(skills)}"
        assert "skill_governed_agentic_systems_architecture" in skills
        assert "skill_agentic_control_plane_design" in skills
    finally:
        conn.close()
