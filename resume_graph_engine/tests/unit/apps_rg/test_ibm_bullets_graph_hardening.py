"""Unit tests for IBM role episode bundles, facts, and insurance skill reachability."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import pytest

from apps_rg.repository_layout import apps_rg_package_root
from apps_rg.fact_inventory.augmented_skills_graph_sqlite import default_graph_sqlite_path
from apps_rg.fact_inventory.validate_graph_topology import validate_graph_topology
from apps_rg.runtime.sections.jd_fit_bundle_selection import select_jd_fit_slot_bundle_map

REPO = Path(__file__).resolve().parents[3]
APPS_RG_ROOT = apps_rg_package_root(REPO)
BUNDLES_PATH = APPS_RG_ROOT / "fact_inventory" / "ibm_role_episode_bundles.json"
LEDGER_PATH = APPS_RG_ROOT / "fact_inventory" / "master_skills_arsenal_ledger.json"
SQLITE_PATH = default_graph_sqlite_path(REPO)


@pytest.fixture(scope="module")
def bundles_data() -> dict:
    with open(BUNDLES_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def ledger_data() -> dict:
    with open(LEDGER_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def db_conn():
    conn = sqlite3.connect(str(SQLITE_PATH))
    yield conn
    conn.close()


def test_all_ibm_bundles_have_linked_source_facts(bundles_data: dict) -> None:
    bundles = bundles_data.get("bundles", [])
    assert len(bundles) == 10, f"Expected 10 IBM bundles, found {len(bundles)}"
    for b in bundles:
        bid = b.get("role_episode_bundle_id")
        facts = b.get("linked_source_fact_ids", [])
        assert len(facts) > 0, f"Bundle {bid} has empty linked_source_fact_ids"


def test_ibm_bundles_linked_to_regulated_financial_institutions_fluency(bundles_data: dict) -> None:
    bundles = bundles_data.get("bundles", [])
    target_skill = "skill_sr_regulated_financial_institutions_fluency"
    bundles_with_skill = [
        b.get("role_episode_bundle_id")
        for b in bundles
        if target_skill in (b.get("graph_skill_node_ids") or [])
    ]
    assert len(bundles_with_skill) >= 9, (
        f"Expected at least 9 IBM bundles to link {target_skill}, got {len(bundles_with_skill)}"
    )


def test_regulated_financial_institutions_fluency_allows_insurance_phrases(ledger_data: dict) -> None:
    skill_rows = ledger_data.get("skill_rows", [])
    row = next(
        (r for r in skill_rows if r.get("skill_id") == "skill_sr_regulated_financial_institutions_fluency"),
        None,
    )
    assert row is not None, "skill_sr_regulated_financial_institutions_fluency missing from ledger"
    phrases = row.get("allowed_phrases", [])
    assert "insurers" in phrases, f"'insurers' missing from allowed_phrases: {phrases}"
    assert "insurance carriers" in phrases, f"'insurance carriers' missing from allowed_phrases: {phrases}"


def test_sqlite_ibm_engagement_edges_evidenced_by_facts(db_conn: sqlite3.Connection) -> None:
    cursor = db_conn.cursor()
    bundles_cursor = cursor.execute("""
        SELECT DISTINCT source_node_id
        FROM graph_edges
        WHERE source_node_id LIKE 'reb_ibm_%'
          AND edge_type = 'engagement_evidenced_by_fact'
    """).fetchall()
    bundles_with_facts = {row[0] for row in bundles_cursor}
    assert len(bundles_with_facts) == 10, (
        f"Expected 10 IBM bundles with engagement_evidenced_by_fact edges, found {len(bundles_with_facts)}"
    )


def test_sqlite_skills_graph_topology_clean() -> None:
    report = validate_graph_topology(SQLITE_PATH, raise_on_error=False)
    assert report["status"] == "PASS", f"Topology validation failed: {report.get('violations')}"
    assert report["failed_invariants_count"] == 0


def test_jd_fit_bundle_selection_resolves_ibm_bullets() -> None:
    slot_map = select_jd_fit_slot_bundle_map("ibm_bullets", "insurance_it_strategy")
    assert len(slot_map) == 5
    assert slot_map["bul_ibm_001"] == "reb_ibm_aws_modernization_architecture"
    assert slot_map["bul_ibm_002"] == "reb_ibm_cognitive_business_decision_support"
