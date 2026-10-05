"""Adversarial red-team test suite for Slalom graph augmentation safety gates."""
from __future__ import annotations

import re
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

FORBIDDEN_CLIENT_PATTERNS = [
    r"\bnextera\b",
    r"\bnee\b",
    r"\bfpl\b",
    r"florida power",
    r"\blillian\b",
    r"andy k",
    r"muschett",
    r"421[,.]?344",
]


@pytest.mark.unit
def test_adversarial_client_name_leak_detection() -> None:
    """Verify that redaction scan detects deliberate client name injections."""
    leak_examples = [
        "Delivered multi-agent pipeline for NextEra Energy analytics.",
        "Integrated AWS Bedrock with NEE IT architecture standards.",
        "Managed delivery with FPL engineering leads on site.",
        "SOW capped at $421,344 with Florida Power and Light.",
    ]
    for leak in leak_examples:
        detected = any(re.search(pat, leak, re.IGNORECASE) for pat in FORBIDDEN_CLIENT_PATTERNS)
        assert detected, f"Redaction scanner failed to detect leak: {leak}"


@pytest.mark.unit
def test_adversarial_clean_proposal_has_zero_leaks() -> None:
    """Verify that current staged proposal contains zero client name leaks."""
    content = PROPOSAL_PATH.read_text(encoding="utf-8")
    for pat in FORBIDDEN_CLIENT_PATTERNS:
        match = re.search(pat, content, re.IGNORECASE)
        assert match is None, f"Found forbidden pattern '{pat}' in proposal: {match.group(0) if match else ''}"


@pytest.mark.unit
def test_adversarial_pk_collision_rejection(tmp_path: Path) -> None:
    """Verify that inserting duplicate node_id raises SQLite IntegrityError."""
    tmp_db = tmp_path / "test_collision.sqlite"
    tmp_db.write_bytes(LIVE_DB_PATH.read_bytes())

    conn = sqlite3.connect(tmp_db)
    cur = conn.cursor()

    with pytest.raises(sqlite3.IntegrityError):
        cur.execute(
            """
            INSERT INTO graph_nodes (node_id, node_type, label, description, activation_status, support_level, confidence, external_eligible, career_epoch, phase_ordinal, source_authority, created_at, updated_at)
            VALUES ('fact_slalom_001', 'fact', 'duplicate', 'duplicate', 'ACTIVE_CONFIRMED', 'EVIDENCE_BOUND', 'HIGH', 1, '', 4, 'test', 'now', 'now')
            """
        )
    conn.close()


@pytest.mark.unit
def test_adversarial_orphan_foreign_key_detection(tmp_path: Path) -> None:
    """Verify that edge pointing to non-existent node fails foreign key check."""
    tmp_db = tmp_path / "test_orphan.sqlite"
    tmp_db.write_bytes(LIVE_DB_PATH.read_bytes())

    conn = sqlite3.connect(tmp_db)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO graph_edges (edge_id, source_node_id, target_node_id, edge_family, edge_type, weight, confidence, directional, evidence_status, source_authority, business_story, technical_story)
        VALUES ('edge_broken_test', 'fact_slalom_9999_nonexistent', 'metric_slalom_visual_asset_intelligence_sow_delivery', 'fact_metric', 'fact_has_metric_outcome', 1.0, 0.9, 1, 'TEST', 'test', 'b', 't')
        """
    )
    conn.commit()

    cur.execute("PRAGMA foreign_key_check;")
    violations = cur.fetchall()
    conn.close()

    assert len(violations) > 0, "PRAGMA foreign_key_check failed to catch orphan node reference!"
