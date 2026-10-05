"""Wave 1 verification tests for Edge Assertion and Lineage Contract (G1, G2, G6).

Covers Acceptance Criteria AC1.1 - AC1.6:
- AC1.1: 100% of edges in graph_edges carry typed assertion_type, assertion_basis,
         canonical_assertion_text, lifecycle_disposition, semantic_contract_version.
- AC1.2: Every edge_type maps to exactly one assertion_type in contract v2.
- AC1.3: 100% of edges and nodes carry lineage: origin_kind, origin_ref, build_run_id.
         graph_build_runs and graph_build_inputs are populated and valid.
- AC1.4: origin_kind='ledger_edge' and 'bundle_row' resolve to legitimate upstream sources.
- AC1.5: graph_neighborhoods preserves parallel edges (sum(len(edge_ids_json)) == 2 * |E|).
         graph_sibling_links and graph_paths carry lineage. Reverse view has all new columns.
- AC1.6: CHECK constraints enforce assertion and lineage invariants on SQLite insert.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from apps_rg.fact_inventory.skills_graph.schema import DDL_STATEMENTS

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
CONTRACT_PATH = ROOT / "src/apps_rg/fact_inventory/c03_graph_edge_semantic_contract.v2.json"
LEDGER_PATH = ROOT / "src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
BUNDLES_PATH = ROOT / "src/apps_rg/fact_inventory/slalom_role_episode_bundles.json"


@pytest.fixture(scope="module")
def db_conn() -> sqlite3.Connection:
    assert DB_PATH.is_file(), f"Augmented skills graph DB missing at {DB_PATH}"
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    yield conn
    conn.close()


def test_ac1_1_all_edges_have_typed_assertion_contract(db_conn: sqlite3.Connection) -> None:
    """AC1.1: 100% of edges have non-empty typed assertion contract columns."""
    allowed_assertion_types = {
        "STRUCTURAL_CONTAINMENT",
        "TAXONOMIC_ATTRIBUTION",
        "EVIDENTIAL_SUPPORT",
        "POLICY_ELIGIBILITY",
        "POLICY_RESTRICTION",
        "METRIC_BINDING",
        "TEMPORAL_SEQUENCE",
        "ASSOCIATIVE_BRIDGE",
    }
    allowed_bases = {
        "evidence_reference",
        "source_field_derivation",
        "taxonomy_rule",
        "policy_predicate",
        "non_causal_bridge",
        "operator_confirmation",
    }
    allowed_dispositions = {
        "ACTIVE_POLICY_GATED",
        "INTERNAL_TRAVERSAL_ONLY",
        "HELD_NON_ACTIVE_ENDPOINT",
        "HELD_INTEGRITY_GAP",
    }

    # Zero empty or NULL assertion fields
    empty_assertions = db_conn.execute(
        "SELECT count(*) FROM graph_edges WHERE assertion_type IS NULL OR assertion_type = ''"
    ).fetchone()[0]
    assert empty_assertions == 0

    empty_bases = db_conn.execute(
        "SELECT count(*) FROM graph_edges WHERE assertion_basis IS NULL OR assertion_basis = ''"
    ).fetchone()[0]
    assert empty_bases == 0

    empty_texts = db_conn.execute(
        "SELECT count(*) FROM graph_edges WHERE canonical_assertion_text IS NULL OR TRIM(canonical_assertion_text) = ''"
    ).fetchone()[0]
    assert empty_texts == 0

    # Version check
    non_v2 = db_conn.execute(
        "SELECT count(*) FROM graph_edges WHERE semantic_contract_version <> 'apps_rg.c03_graph_edge_semantic_contract.v2'"
    ).fetchone()[0]
    assert non_v2 == 0

    # Domain vocabulary checks
    db_assertion_types = {r[0] for r in db_conn.execute("SELECT DISTINCT assertion_type FROM graph_edges").fetchall()}
    assert db_assertion_types.issubset(allowed_assertion_types)
    assert len(db_assertion_types) == len(allowed_assertion_types)

    db_bases = {r[0] for r in db_conn.execute("SELECT DISTINCT assertion_basis FROM graph_edges").fetchall()}
    assert db_bases.issubset(allowed_bases)

    db_dispositions = {r[0] for r in db_conn.execute("SELECT DISTINCT lifecycle_disposition FROM graph_edges").fetchall()}
    assert db_dispositions.issubset(allowed_dispositions)


def test_ac1_2_every_edge_type_mapped_in_contract_v2(db_conn: sqlite3.Connection) -> None:
    """AC1.2: Every edge_type in the DB maps to exactly one assertion_type in contract v2."""
    assert CONTRACT_PATH.is_file(), f"Contract v2 missing at {CONTRACT_PATH}"
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    contract_mapping = contract["assertion_type_by_edge_type"]

    db_edge_types = [r[0] for r in db_conn.execute("SELECT DISTINCT edge_type FROM graph_edges ORDER BY edge_type").fetchall()]
    assert len(db_edge_types) == 37, f"Expected 37 distinct edge types, found {len(db_edge_types)}"

    for edge_type in db_edge_types:
        assert edge_type in contract_mapping, f"Edge type {edge_type} not mapped in contract v2"
        expected_assertion = contract_mapping[edge_type]
        mismatched = db_conn.execute(
            "SELECT count(*) FROM graph_edges WHERE edge_type = ? AND assertion_type <> ?",
            (edge_type, expected_assertion),
        ).fetchone()[0]
        assert mismatched == 0, f"Found mismatched assertion_type for edge_type {edge_type}"


def test_ac1_3_all_edges_and_nodes_carry_lineage_and_build_run(db_conn: sqlite3.Connection) -> None:
    """AC1.3: 100% of edges and nodes carry lineage and link to graph_build_runs."""
    # Runs table populated
    runs = db_conn.execute("SELECT build_run_id, built_at, builder_git_commit, input_manifest_digest FROM graph_build_runs").fetchall()
    assert len(runs) >= 1, "graph_build_runs must have at least 1 record"
    run_ids = {r[0] for r in runs}

    # Edges lineage
    empty_edge_lineage = db_conn.execute(
        "SELECT count(*) FROM graph_edges WHERE origin_ref = '' OR build_run_id = ''"
    ).fetchone()[0]
    assert empty_edge_lineage == 0

    unlinked_edge_runs = db_conn.execute(
        "SELECT count(*) FROM graph_edges WHERE build_run_id NOT IN (SELECT build_run_id FROM graph_build_runs)"
    ).fetchone()[0]
    assert unlinked_edge_runs == 0

    edge_kinds = {r[0] for r in db_conn.execute("SELECT DISTINCT origin_kind FROM graph_edges").fetchall()}
    assert edge_kinds.issubset({"ledger_edge", "bundle_row", "derived_projection"})

    # Nodes lineage
    empty_node_lineage = db_conn.execute(
        "SELECT count(*) FROM graph_nodes WHERE origin_ref = '' OR build_run_id = ''"
    ).fetchone()[0]
    assert empty_node_lineage == 0

    unlinked_node_runs = db_conn.execute(
        "SELECT count(*) FROM graph_nodes WHERE build_run_id NOT IN (SELECT build_run_id FROM graph_build_runs)"
    ).fetchone()[0]
    assert unlinked_node_runs == 0

    node_kinds = {r[0] for r in db_conn.execute("SELECT DISTINCT origin_kind FROM graph_nodes").fetchall()}
    assert node_kinds.issubset({"ledger_node", "bundle_row", "derived_projection"})


def test_ac1_3_build_inputs_tracking(db_conn: sqlite3.Connection) -> None:
    """AC1.3: graph_build_inputs tracks all ingestion artifacts with SHA256 hashes."""
    inputs = db_conn.execute(
        "SELECT build_run_id, input_role, artifact_relpath, artifact_sha256, record_count FROM graph_build_inputs"
    ).fetchall()
    assert len(inputs) >= 4, f"Expected at least 4 build inputs, found {len(inputs)}"

    roles = {r[1] for r in inputs}
    assert "canonical_graph_ledger" in roles or "primary_ledger" in roles
    assert "role_episode_bundle" in roles or "metric_bundles" in roles
    assert "edge_semantic_contract" in roles or "contract" in roles

    for row in inputs:
        sha = row[3]
        assert len(sha) == 64, f"Invalid SHA256 length for input {row[2]}: {sha}"
        assert int(sha, 16) > 0


def test_ac1_4_origin_kind_resolution_cross_check(db_conn: sqlite3.Connection) -> None:
    """AC1.4: origin_kind resolves to upstream source records."""
    assert LEDGER_PATH.is_file(), f"Ledger missing at {LEDGER_PATH}"
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    ledger_edge_ids = {e["edge_id"] for e in ledger.get("graph_edges", []) if "edge_id" in e}

    # All ledger_edge rows in graph_edges resolve to ledger edge IDs
    ledger_edges = db_conn.execute(
        "SELECT origin_ref FROM graph_edges WHERE origin_kind = 'ledger_edge'"
    ).fetchall()
    assert len(ledger_edges) > 0
    for (origin_ref,) in ledger_edges:
        assert origin_ref in ledger_edge_ids, f"origin_ref {origin_ref} not found in master ledger"

    # All bundle_row rows in graph_edges resolve to structured bundle refs
    bundle_edges = db_conn.execute(
        "SELECT origin_ref FROM graph_edges WHERE origin_kind = 'bundle_row'"
    ).fetchall()
    assert len(bundle_edges) > 0
    for (origin_ref,) in bundle_edges:
        assert "::" in origin_ref, f"Unexpected bundle_row origin_ref format (missing '::'): {origin_ref}"
        prefix, suffix = origin_ref.split("::", 1)
        assert len(prefix) > 0 and len(suffix) > 0


def test_ac1_5_neighborhoods_parallel_edges_and_sibling_lineage(db_conn: sqlite3.Connection) -> None:
    """AC1.5: graph_neighborhoods preserves parallel edges and graph_sibling_links retains lineage."""
    edge_count = db_conn.execute("SELECT count(*) FROM graph_edges").fetchone()[0]
    total_neigh_edges = db_conn.execute(
        "SELECT sum(json_array_length(edge_ids_json)) FROM graph_neighborhoods"
    ).fetchone()[0]
    # In an undirected or bidirectional neighborhood expansion, each directed edge appears twice
    assert total_neigh_edges == 2 * edge_count, (
        f"Expected total neighbor edge IDs {2 * edge_count}, found {total_neigh_edges}"
    )

    # No empty edge_ids_json
    empty_neigh_edges = db_conn.execute(
        "SELECT count(*) FROM graph_neighborhoods WHERE json_array_length(edge_ids_json) = 0"
    ).fetchone()[0]
    assert empty_neigh_edges == 0

    # Sibling links lineage
    empty_sibling_parent = db_conn.execute(
        "SELECT count(*) FROM graph_sibling_links WHERE parent_edge_id = ''"
    ).fetchone()[0]
    assert empty_sibling_parent == 0

    empty_sibling_rules = db_conn.execute(
        "SELECT count(*) FROM graph_sibling_links WHERE derivation_rule_id = ''"
    ).fetchone()[0]
    assert empty_sibling_rules == 0

    empty_path_runs = db_conn.execute(
        "SELECT count(*) FROM graph_paths WHERE build_run_id = ''"
    ).fetchone()[0]
    assert empty_path_runs == 0


def test_ac1_5_reverse_view_parity(db_conn: sqlite3.Connection) -> None:
    """AC1.5: graph_edges_reverse contains all new edge columns and exact row parity."""
    edge_count = db_conn.execute("SELECT count(*) FROM graph_edges").fetchone()[0]
    rev_count = db_conn.execute("SELECT count(*) FROM graph_edges_reverse").fetchone()[0]
    assert rev_count == edge_count, f"Reverse view count {rev_count} != edge count {edge_count}"

    rev_cols = {r[1] for r in db_conn.execute("PRAGMA table_info(graph_edges_reverse)").fetchall()}
    expected_new_cols = {
        "assertion_type",
        "assertion_basis",
        "assertion_basis_refs_json",
        "canonical_assertion_text",
        "lifecycle_disposition",
        "semantic_contract_version",
        "origin_kind",
        "origin_ref",
        "origin_artifact_sha256",
        "derivation_rule_id",
        "build_run_id",
    }
    assert expected_new_cols.issubset(rev_cols), f"Missing cols in reverse view: {expected_new_cols - rev_cols}"


def test_ac1_6_check_constraints_enforce_assertion_lineage_invariants() -> None:
    """AC1.6: CHECK constraints reject invalid assertion, lineage, and cross-field states."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    for ddl in DDL_STATEMENTS[:2]:
        conn.execute(ddl)

    # Insert valid nodes
    conn.executemany(
        "INSERT INTO graph_nodes (node_id, node_type, label, created_at, updated_at) VALUES (?, ?, ?, 't', 't')",
        [
            ("node_src", "skill", "Source Skill"),
            ("node_tgt", "fact", "Target Fact"),
        ],
    )
    conn.commit()

    # 1. Invalid assertion_type is rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO graph_edges (
                edge_id, source_node_id, target_node_id, edge_type, assertion_type,
                origin_ref, build_run_id
            ) VALUES ('e_bad_type', 'node_src', 'node_tgt', 'test_edge', 'BOGUS_ASSERTION_TYPE', 'ref1', 'run1')
            """
        )

    # 2. Invalid assertion_basis is rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO graph_edges (
                edge_id, source_node_id, target_node_id, edge_type, assertion_basis,
                origin_ref, build_run_id
            ) VALUES ('e_bad_basis', 'node_src', 'node_tgt', 'test_edge', 'bogus_basis', 'ref1', 'run1')
            """
        )

    # 3. Empty canonical_assertion_text is rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO graph_edges (
                edge_id, source_node_id, target_node_id, edge_type, canonical_assertion_text,
                origin_ref, build_run_id
            ) VALUES ('e_empty_text', 'node_src', 'node_tgt', 'test_edge', '   ', 'ref1', 'run1')
            """
        )

    # 4. Empty origin_ref is rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO graph_edges (
                edge_id, source_node_id, target_node_id, edge_type, origin_ref, build_run_id
            ) VALUES ('e_empty_ref', 'node_src', 'node_tgt', 'test_edge', '', 'run1')
            """
        )

    # 5. Empty build_run_id is rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO graph_edges (
                edge_id, source_node_id, target_node_id, edge_type, origin_ref, build_run_id
            ) VALUES ('e_empty_run', 'node_src', 'node_tgt', 'test_edge', 'ref1', '')
            """
        )

    # 6. EVIDENTIAL_SUPPORT with empty assertion_basis_refs_json is rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO graph_edges (
                edge_id, source_node_id, target_node_id, edge_type, assertion_type,
                assertion_basis_refs_json, origin_ref, build_run_id
            ) VALUES (
                'e_ev_empty', 'node_src', 'node_tgt', 'skill_supported_by_fact', 'EVIDENTIAL_SUPPORT',
                '[]', 'ref1', 'run1'
            )
            """
        )

    # 7. EVIDENTIAL_SUPPORT with non-empty assertion_basis_refs_json is accepted
    conn.execute(
        """
        INSERT INTO graph_edges (
            edge_id, source_node_id, target_node_id, edge_type, assertion_type,
            assertion_basis_refs_json, origin_ref, build_run_id
        ) VALUES (
            'e_ev_valid', 'node_src', 'node_tgt', 'skill_supported_by_fact', 'EVIDENTIAL_SUPPORT',
            '["fact_ref_001"]', 'ref1', 'run1'
        )
        """
    )
    conn.commit()

    # 8. POLICY_RESTRICTION with ACTIVE_POLICY_GATED disposition is rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO graph_edges (
                edge_id, source_node_id, target_node_id, edge_type, assertion_type,
                lifecycle_disposition, origin_ref, build_run_id
            ) VALUES (
                'e_pol_bad', 'node_src', 'node_tgt', 'test_policy', 'POLICY_RESTRICTION',
                'ACTIVE_POLICY_GATED', 'ref1', 'run1'
            )
            """
        )

    # 9. POLICY_RESTRICTION with INTERNAL_TRAVERSAL_ONLY disposition is accepted
    conn.execute(
        """
        INSERT INTO graph_edges (
            edge_id, source_node_id, target_node_id, edge_type, assertion_type,
            lifecycle_disposition, origin_ref, build_run_id
        ) VALUES (
            'e_pol_valid', 'node_src', 'node_tgt', 'test_policy', 'POLICY_RESTRICTION',
            'INTERNAL_TRAVERSAL_ONLY', 'ref1', 'run1'
        )
        """
    )
    conn.commit()
    conn.close()
