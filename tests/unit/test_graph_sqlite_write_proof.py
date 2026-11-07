"""Unit tests for Wave 3 5-check physical SQLite write proof and rollback gate."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from apps_rg.fact_inventory.skills_graph.materializer import (
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.fact_inventory.skills_graph.storage import (
    _replace_sqlite_projection_if_unchanged,
    _sqlite_projection_digest,
    verify_sqlite_physical_write_proof,
)


def _rg_root() -> Path:
    return Path(__file__).resolve().parents[2] / "resume_graph_engine"


def test_five_check_physical_write_proof_passes_on_materialized_db(tmp_path: Path) -> None:
    db_path = tmp_path / "augmented_skills_graph.sqlite"
    materialize_augmented_skills_graph_sqlite(
        repo_root=_rg_root(),
        db_path=db_path,
    )
    proof = verify_sqlite_physical_write_proof(db_path)
    assert proof["status"] == "PASS"
    assert int(proof["size_bytes"]) >= 100
    assert len(str(proof["sha256"])) == 64
    assert proof["header_magic_valid"] is True
    assert proof["integrity_check"] == "ok"
    assert proof["query_only_readback"] is True
    assert int(proof["node_count"]) > 0
    assert int(proof["edge_count"]) > 0


def test_corrupt_replacement_aborts_swap_and_preserves_target_bytes(tmp_path: Path) -> None:
    target_db = tmp_path / "augmented_skills_graph.sqlite"
    materialize_augmented_skills_graph_sqlite(
        repo_root=_rg_root(),
        db_path=target_db,
    )
    original_bytes = target_db.read_bytes()
    original_sha256 = hashlib.sha256(original_bytes).hexdigest()
    expected_digest = _sqlite_projection_digest(target_db)

    corrupt_replacement = tmp_path / ".augmented_skills_graph.sqlite.corrupt.tmp"
    corrupt_replacement.write_bytes(b"NOT_SQLITE_HEADER" + b"\x00" * 256)

    with pytest.raises(RuntimeError, match="SQLite physical write proof failed"):
        _replace_sqlite_projection_if_unchanged(
            target=target_db,
            replacement=corrupt_replacement,
            expected_digest=expected_digest,
        )

    assert not corrupt_replacement.exists()
    assert hashlib.sha256(target_db.read_bytes()).hexdigest() == original_sha256

    empty_replacement = tmp_path / ".augmented_skills_graph.sqlite.empty.tmp"
    conn = sqlite3.connect(str(empty_replacement))
    try:
        conn.execute("CREATE TABLE graph_nodes (node_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE graph_edges (edge_id TEXT PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(RuntimeError, match="non-positive row counts"):
        _replace_sqlite_projection_if_unchanged(
            target=target_db,
            replacement=empty_replacement,
            expected_digest=expected_digest,
        )

    assert not empty_replacement.exists()
    assert hashlib.sha256(target_db.read_bytes()).hexdigest() == original_sha256
