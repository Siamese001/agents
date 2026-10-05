"""E2E verification test for Slalom graph augmentation staged proposal."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EXTRACTION_DIR = REPO_ROOT / "resume_graph_engine/artifacts/apps_rg/slalom_extraction"
PROPOSAL_PATH = EXTRACTION_DIR / "slalom_graph_delta_proposal.json"


def find_live_db_path() -> Path:
    p = REPO_ROOT / "resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
    if p.exists():
        return p
    main_p = Path("/Users/amitayer/Git/agents/resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite")
    if main_p.exists():
        return main_p
    return p


LIVE_DB_PATH = find_live_db_path()


@pytest.mark.unit
def test_slalom_proposal_schema_and_dryrun_integrity(tmp_path: Path) -> None:
    """Verify that staged proposal validates against schema, applies cleanly on copy, and live DB satisfies integrity."""
    assert PROPOSAL_PATH.exists(), f"Proposal missing: {PROPOSAL_PATH}"
    proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))

    nodes = proposal.get("nodes", [])
    edges = proposal.get("edges", [])

    assert len(nodes) == 8, f"Expected 8 staged nodes, got {len(nodes)}"
    assert len(edges) == 4, f"Expected 4 staged edges, got {len(edges)}"

    # Determine baseline database for dry-run
    backup_candidates = sorted((LIVE_DB_PATH.parent / "backups").glob("augmented_skills_graph.sqlite.bak_*"))

    conn_check = sqlite3.connect(LIVE_DB_PATH)
    cur_check = conn_check.cursor()
    cur_check.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_id = 'fact_slalom_005';")
    already_promoted = (cur_check.fetchone()[0] == 1)
    conn_check.close()

    # If backups exist or DB is unpromoted, run dry-run application
    source_db_for_dryrun = backup_candidates[0] if (already_promoted and backup_candidates) else LIVE_DB_PATH
    if not already_promoted or backup_candidates:
        tmp_db = tmp_path / "test_augmented_graph.sqlite"
        tmp_db.write_bytes(source_db_for_dryrun.read_bytes())

        conn = sqlite3.connect(tmp_db)
        cur = conn.cursor()

        for n in nodes:
            if n["staged_status"] == "ENRICH_EXISTING":
                cur.execute(
                    """
                    UPDATE graph_nodes 
                    SET label = ?, description = ?, activation_status = ?, support_level = ?, confidence = ?, source_authority = ?, updated_at = '2026-10-05T08:47:00Z'
                    WHERE node_id = ?
                    """,
                    (n["label"], n["description"], n["activation_status"], n["support_level"], n["confidence"], n["source_authority"], n["node_id"]),
                )
                assert cur.rowcount == 1, f"Failed to enrich existing node {n['node_id']}"
            else:
                cur.execute(
                    """
                    INSERT INTO graph_nodes (node_id, node_type, label, description, activation_status, support_level, confidence, external_eligible, career_epoch, phase_ordinal, source_authority, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-10-05T08:47:00Z', '2026-10-05T08:47:00Z')
                    """,
                    (n["node_id"], n["node_type"], n["label"], n["description"], n["activation_status"], n["support_level"], n["confidence"], n["external_eligible"], n["career_epoch"], n["phase_ordinal"], n["source_authority"]),
                )

        for e in edges:
            cur.execute(
                """
                INSERT INTO graph_edges (edge_id, source_node_id, target_node_id, edge_family, edge_type, weight, confidence, directional, evidence_status, source_authority, business_story, technical_story)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (e["edge_id"], e["source_node_id"], e["target_node_id"], e["edge_family"], e["edge_type"], e["weight"], e["confidence"], e["directional"], e["evidence_status"], e["source_authority"], e["business_story"], e["technical_story"]),
            )

        conn.commit()

        cur.execute("PRAGMA integrity_check;")
        integrity = cur.fetchall()
        assert integrity == [("ok",)], f"Integrity check failed: {integrity}"

        cur.execute("PRAGMA foreign_key_check;")
        fk_violations = cur.fetchall()
        assert len(fk_violations) == 0, f"Foreign key violations found: {fk_violations}"

        conn.close()

    # In all cases, verify that the live database itself satisfies integrity and contains all proposal elements
    conn_live = sqlite3.connect(LIVE_DB_PATH)
    cur_live = conn_live.cursor()
    cur_live.execute("PRAGMA integrity_check;")
    assert cur_live.fetchall() == [("ok",)]
    cur_live.execute("PRAGMA foreign_key_check;")
    assert len(cur_live.fetchall()) == 0

    if already_promoted:
        for n in nodes:
            cur_live.execute("SELECT node_id, label, support_level FROM graph_nodes WHERE node_id = ?", (n["node_id"],))
            row = cur_live.fetchone()
            assert row is not None, f"Node {n['node_id']} not found in live database"
            assert row[1] == n["label"], f"Node {n['node_id']} label mismatch: {row[1]} vs {n['label']}"
        for e in edges:
            cur_live.execute("SELECT edge_id FROM graph_edges WHERE edge_id = ?", (e["edge_id"],))
            assert cur_live.fetchone() is not None, f"Edge {e['edge_id']} not found in live database"
    conn_live.close()
