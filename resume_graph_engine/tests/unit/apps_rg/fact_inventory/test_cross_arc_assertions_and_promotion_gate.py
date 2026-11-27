"""Wave 2 verification tests for Canonical Skills Arsenal, Cross-Arc Assertions, and Promotion Gate."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from apps_rg.fact_inventory.skills_graph.promotions import promote_operator_confirmed_skill_rows
from tools.graph_hygiene_judge_v3 import (
    JudgeV3ProvenanceError,
    verify_promotion_judge_receipt,
)

ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = ROOT.parent
DB_PATH = ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    assert DB_PATH.is_file(), f"Augmented skills graph DB missing at {DB_PATH}"
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    yield conn
    conn.close()


def test_w2_humanized_labels_aliases_and_internal_quarantine(db_conn: sqlite3.Connection) -> None:
    """Zero snake_case labels on external-eligible skills; aliases populated; internal mechanics quarantined."""
    snake_external = db_conn.execute(
        """
        SELECT node_id, label FROM graph_nodes
        WHERE node_type = 'skill'
          AND external_eligible = 1
          AND label LIKE '%\\_%' ESCAPE '\\'
        """
    ).fetchall()
    assert len(snake_external) == 0, f"Found snake_case external skill labels: {snake_external[:10]}"

    alias_count = db_conn.execute("SELECT COUNT(*) FROM skill_lexical_aliases").fetchone()[0]
    assert alias_count >= 500, f"Expected >=500 skill_lexical_aliases rows, found {alias_count}"

    acronym_pairs = db_conn.execute(
        "SELECT COUNT(*) FROM skill_lexical_aliases WHERE TRIM(acronym_pair) <> ''"
    ).fetchone()[0]
    assert acronym_pairs >= 20

    # Repo-internal mechanics must not be externally eligible
    internal_leaks = db_conn.execute(
        """
        SELECT node_id FROM graph_nodes
        WHERE node_id IN (
            'skill_x1_x2_x3_exit_control',
            'skill_unify_agentic_l0_route_policy_dispatch',
            'skill_c03_metric_heterogeneity_selection',
            'skill_c03_reverse_traversal_receipts',
            'skill_c03_sibling_skill_rejection_reasoning'
        ) AND external_eligible = 1
        """
    ).fetchall()
    assert len(internal_leaks) == 0, f"Internal mechanics leaked externally: {internal_leaks}"


def test_w2_cross_arc_assertions_and_edge_completeness(db_conn: sqlite3.Connection) -> None:
    """Zero approved_by_graph_presence, zero blank edge_family/validation_status, cross-arc edges backed by facts."""
    legacy_policy = db_conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE external_claim_policy = 'approved_by_graph_presence'"
    ).fetchone()[0]
    assert legacy_policy == 0

    blank_family = db_conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE TRIM(COALESCE(edge_family, '')) = ''"
    ).fetchone()[0]
    assert blank_family == 0

    blank_val = db_conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE TRIM(COALESCE(validation_status, '')) = ''"
    ).fetchone()[0]
    assert blank_val == 0

    cont_count = db_conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE edge_type = 'demonstrates_continuity_from'"
    ).fetchone()[0]
    quant_count = db_conn.execute(
        "SELECT COUNT(*) FROM graph_edges WHERE edge_type = 'transfers_quantitative_rigor_to'"
    ).fetchone()[0]
    assert cont_count >= 4
    assert quant_count >= 4

    # Every cross-arc edge must have >= 2 verified fact_id witnesses in edge_evidence
    weak_cross_arc = db_conn.execute(
        """
        SELECT ge.edge_id, COUNT(DISTINCT ee.evidence_node_id) AS witness_cnt
        FROM graph_edges ge
        LEFT JOIN edge_evidence ee
          ON ee.edge_id = ge.edge_id
         AND ee.evidence_kind = 'fact'
         AND TRIM(ee.evidence_node_id) <> ''
        WHERE ge.edge_type IN ('demonstrates_continuity_from', 'transfers_quantitative_rigor_to')
        GROUP BY ge.edge_id
        HAVING witness_cnt < 2
        """
    ).fetchall()
    assert len(weak_cross_arc) == 0, f"Cross-arc edges lacking dual fact witnesses: {weak_cross_arc}"


def test_w2_fail_closed_promotion_and_dual_judge_receipt(tmp_path: Path, db_conn: sqlite3.Connection) -> None:
    """promote_operator_confirmed_skill_rows never fabricates fact links; judge receipt verifier fails closed."""
    unbacked = {
        "skill_unbacked_test": {
            "skill_id": "skill_unbacked_test",
            "activation_status": "DRAFT",
            "support_level": "INTERNAL_ONLY",
            "confidence_grade": "LOW",
            "fact_id_links": [],
            "operator_hygiene_decision": "PROMOTE_EXTERNAL",
        }
    }
    out = promote_operator_confirmed_skill_rows(unbacked)
    assert out["skill_unbacked_test"]["fact_id_links"] == []
    assert out["skill_unbacked_test"]["activation_status"] == "DRAFT"

    # Unify regulated AI governance bundle must bind fact_rag_insurance_001
    rag_eng = db_conn.execute(
        """
        SELECT COUNT(*) FROM graph_edges
        WHERE edge_type = 'engagement_evidenced_by_fact'
          AND source_node_id = 'reb_unify_regulated_enterprise_ai_governance'
          AND target_node_id = 'fact_rag_insurance_001'
        """
    ).fetchone()[0]
    assert rag_eng == 1

    # Fail-closed judge receipt verification
    missing_receipt = tmp_path / "missing.json"
    with pytest.raises(JudgeV3ProvenanceError):
        verify_promotion_judge_receipt(missing_receipt)

    single_family = tmp_path / "single.json"
    single_family.write_text(
        json.dumps({"passed": True, "status": "PASS", "judge_families": ["google"], "artifact_sha256": "abc"}),
        encoding="utf-8",
    )
    with pytest.raises(JudgeV3ProvenanceError):
        verify_promotion_judge_receipt(single_family, expected_artifact_sha256="abc")

    valid_receipt = tmp_path / "valid.json"
    valid_receipt.write_text(
        json.dumps(
            {
                "passed": True,
                "status": "PASS",
                "judge_families": ["google", "openai"],
                "artifact_sha256": "abc123",
            }
        ),
        encoding="utf-8",
    )
    res = verify_promotion_judge_receipt(valid_receipt, expected_artifact_sha256="abc123")
    assert res["verified"] is True
    assert res["judge_families"] == ["google", "openai"]
