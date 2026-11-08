"""Unit tests verifying the Asymmetric Granularity Architecture for the Skills Graph.

SSOT Policies:
- INV-PROJECTION-PURITY: augmented_skills_graph.sqlite is strictly an ephemeral derived projection and must be read-only during agent traversal.
- INV-MANIFEST-FRESHNESS: Skills graph projection must match the cryptographic SHA-256 digest of upstream source ledgers or fail closed upon load.
- INV-CONFIDENCE-TIER: Confidence scores are categorized into discrete tiers, rejecting unmapped floating-point drift.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    materialize_augmented_skills_graph_sqlite,
    open_graph_sqlite,
)
from apps_rg.fact_inventory.skills_graph.lineage import (
    compute_input_manifest_digest,
)

ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = ROOT / "resume_graph_engine"


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    """Materialize a clean test projection of the skills graph."""
    db = tmp_path / "test_skills_graph.sqlite"
    materialize_augmented_skills_graph_sqlite(repo_root=REPO_ROOT, db_path=db)
    return db


def test_skills_graph_read_only_purity(sqlite_db: Path) -> None:
    """Verify that opening the skills graph in read-only mode blocks any mutating SQL."""
    conn = open_graph_sqlite(repo_root=REPO_ROOT, db_path=sqlite_db, read_only=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match=r"readonly database|attempt to write a readonly database"):
            conn.execute("INSERT INTO graph_nodes (node_id, node_type, label, created_at, updated_at) VALUES ('test_node', 'skill', 'Test', '2026-11-08', '2026-11-08')")
    finally:
        conn.close()


def test_skills_graph_omits_die_runtime_mutation_tables(sqlite_db: Path) -> None:
    """Verify that the skills graph schema omits DIE dynamic tables like entity_redirect and history triggers."""
    conn = open_graph_sqlite(repo_root=REPO_ROOT, db_path=sqlite_db, read_only=True)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "entity_redirect" not in tables, "Skills graph must not contain dynamic entity_redirect table."
        assert "canonical_graph_nodes_history" not in tables, "Skills graph must not contain living history tables."
        
        triggers = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()}
        history_triggers = [t for t in triggers if "history" in t.lower() or "redirect" in t.lower()]
        assert not history_triggers, f"Skills graph must not contain runtime mutation triggers: {history_triggers}"
    finally:
        conn.close()


def test_skills_graph_discrete_confidence_tiers(sqlite_db: Path) -> None:
    """Verify that all nodes adhere to discrete confidence tiers, rejecting unmapped scores."""
    allowed_tiers = {"HIGH", "MEDIUM", "LOW", "UNSCORED", "NOT_APPLICABLE"}
    conn = open_graph_sqlite(repo_root=REPO_ROOT, db_path=sqlite_db, read_only=True)
    try:
        rows = conn.execute("SELECT node_id, confidence_tier, confidence_score FROM graph_nodes").fetchall()
        assert len(rows) > 0, "graph_nodes must not be empty."
        for node_id, tier, score in rows:
            assert tier in allowed_tiers, f"Node {node_id} has invalid confidence tier: {tier}"
            if score is not None:
                assert 0.0 <= score <= 1.0, f"Node {node_id} has out-of-range confidence score: {score}"
    finally:
        conn.close()


def test_skills_graph_manifest_freshness_digest(sqlite_db: Path) -> None:
    """Verify that the compiled projection matches the input manifest digest of upstream source ledgers."""
    expected_digest = compute_input_manifest_digest(REPO_ROOT)
    conn = open_graph_sqlite(repo_root=REPO_ROOT, db_path=sqlite_db, read_only=True)
    try:
        row = conn.execute("SELECT input_manifest_digest FROM graph_build_runs ORDER BY built_at DESC LIMIT 1").fetchone()
        assert row is not None, "graph_build_runs must contain at least one build record."
        stored_digest = str(row[0]).strip()
        assert stored_digest == expected_digest, f"Manifest mismatch: stored={stored_digest}, expected={expected_digest}"
    finally:
        conn.close()
