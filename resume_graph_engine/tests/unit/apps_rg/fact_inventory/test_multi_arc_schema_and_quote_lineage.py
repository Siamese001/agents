"""Wave 1 verification tests for Multi-Arc Temporal Schema, Credentials, and Quote Lineage."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from apps_rg.fact_inventory.validate_graph_topology import validate_graph_topology
from apps_rg.repository_layout import resolve_apps_rg_path

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    assert DB_PATH.is_file(), f"Augmented skills graph DB missing at {DB_PATH}"
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    yield conn
    conn.close()


def test_w1_multi_arc_junction_tables_and_slalom_coverage(db_conn: sqlite3.Connection) -> None:
    """skill_epoch_links and skill_employment_links materialize multi-employer and Slalom spans."""
    epoch_links = db_conn.execute("SELECT COUNT(*) FROM skill_epoch_links").fetchone()[0]
    emp_links = db_conn.execute("SELECT COUNT(*) FROM skill_employment_links").fetchone()[0]
    assert epoch_links >= 200
    assert emp_links >= 200

    slalom_skills = db_conn.execute(
        """
        SELECT COUNT(DISTINCT skill_id)
        FROM skill_employment_links
        WHERE employment_id = 'employment_exp_slalom_001'
          AND last_exercised_date = '2026-06'
        """
    ).fetchone()[0]
    assert slalom_skills >= 60, f"Expected >=60 Slalom skills, found {slalom_skills}"

    multi_emp_skills = db_conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT skill_id FROM skill_employment_links
            GROUP BY skill_id HAVING COUNT(DISTINCT employment_id) >= 2
        )
        """
    ).fetchone()[0]
    assert multi_emp_skills >= 30, f"Expected >=30 multi-employer skills, found {multi_emp_skills}"

    span_populated = db_conn.execute(
        """
        SELECT COUNT(*) FROM c03_skill_selection_features
        WHERE span_start_ordinal IS NOT NULL
          AND span_end_ordinal IS NOT NULL
          AND epoch_recurrence_count >= 1
          AND json_array_length(employers_json) >= 1
        """
    ).fetchone()[0]
    total_feats = db_conn.execute("SELECT COUNT(*) FROM c03_skill_selection_features").fetchone()[0]
    assert span_populated == total_feats and total_feats > 200


def test_w1_sequential_spine_and_temporal_hydration(db_conn: sqlite3.Connection) -> None:
    """Sequential epoch/employment spine edges and phase_ordinal hydration hold."""
    ep_edges = db_conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE edge_type = 'epoch_precedes_epoch'"
    ).fetchone()[0]
    emp_edges = db_conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE edge_type = 'employment_precedes_employment'"
    ).fetchone()[0]
    assert ep_edges == 5
    assert emp_edges == 5

    null_fact_ordinals = db_conn.execute(
        "SELECT COUNT(*) FROM graph_nodes WHERE node_type = 'fact' AND phase_ordinal IS NULL"
    ).fetchone()[0]
    null_eng_ordinals = db_conn.execute(
        "SELECT COUNT(*) FROM graph_nodes WHERE node_type = 'engagement' AND phase_ordinal IS NULL"
    ).fetchone()[0]
    assert null_fact_ordinals == 0
    assert null_eng_ordinals == 0


def test_w1_missing_verified_facts_and_credentials_materialized(db_conn: sqlite3.Connection) -> None:
    """5 verified facts + 6 base-resume credentials materialize cleanly; 0 TraderSense facts."""
    required_facts = (
        "fact_quant_act_004",
        "fact_data_analytics_004",
        "fact_sales_accounts_004",
        "fact_sales_accounts_005",
        "fact_customer_success_001",
    )
    present_facts = {
        r[0]
        for r in db_conn.execute(
            f"SELECT node_id FROM graph_nodes WHERE node_type='fact' AND node_id IN ({','.join('?' for _ in required_facts)})",
            required_facts,
        ).fetchall()
    }
    assert present_facts == set(required_facts)

    banned = db_conn.execute(
        "SELECT COUNT(*) FROM graph_nodes WHERE node_id IN ('fact_quant_hpc_002', 'fact_partnerships_gtm_005')"
    ).fetchone()[0]
    assert banned == 0

    required_creds = (
        "cert_fsa_001",
        "cert_aws_sa_pro_001",
        "cert_aws_cml_001",
        "cert_databricks_lakehouse_001",
        "edu_columbia_ms_001",
        "edu_brown_ba_001",
    )
    cred_rows = db_conn.execute(
        f"SELECT node_id, external_eligible FROM graph_nodes WHERE node_type='certification' AND node_id IN ({','.join('?' for _ in required_creds)})",
        required_creds,
    ).fetchall()
    assert len(cred_rows) == 6
    assert all(int(r[1]) == 1 for r in cred_rows)

    cred_edges = db_conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE edge_type = 'credential_validates_domain'"
    ).fetchone()[0]
    assert cred_edges >= 6


def test_w1_quote_lineage_build_inputs_and_base_resume_seal(db_conn: sqlite3.Connection) -> None:
    """All graph_build_inputs record_count > 0, edge_evidence carries verbatim quotes, and base resume is sealed."""
    zero_record_inputs = db_conn.execute(
        "SELECT COUNT(*) FROM graph_build_inputs WHERE record_count <= 0"
    ).fetchone()[0]
    assert zero_record_inputs == 0

    base_resume_input = db_conn.execute(
        "SELECT COUNT(*) FROM graph_build_inputs WHERE input_role = 'base_resume'"
    ).fetchone()[0]
    assert base_resume_input == 1

    quoted_fact_evidence = db_conn.execute(
        """
        SELECT COUNT(*) FROM edge_evidence
        WHERE evidence_kind IN ('fact', 'locked_bullet', 'certification', 'metric_outcome', 'employment')
          AND TRIM(source_doc) <> ''
          AND length(quote_sha256) = 64
        """
    ).fetchone()[0]
    assert quoted_fact_evidence >= 500

    br_path = resolve_apps_rg_path(ROOT, "resume", "base", "amit_ayer_base_resume_v1.json")
    br_data = json.loads(br_path.read_text(encoding="utf-8"))
    assert not str(br_data.get("base_resume_json_hash") or "").startswith("sha256:pending")
    assert len(str(br_data.get("base_resume_json_hash") or "").removeprefix("sha256:")) == 64

    report = validate_graph_topology(db_conn, raise_on_error=False)
    assert report["status"] == "PASS", f"Topology validation failed: {report['violations']}"
