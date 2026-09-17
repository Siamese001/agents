"""Adversarial Red Team Verification Suite for Graph Skills, Career Phases, and Document Unit Embeddings.

Verifies:
1. Career epoch completeness & activation (6 active epochs, 1..6 ordinals, HIGH confidence).
2. Authoritative skills-by-career-phase retrieval API (phases 1..6 return skills, facts, metrics, employments, edges, calibrated confidence).
3. Document unit embedding architecture & singleton prohibition (per-node vectors forbidden, multi-node clusters only).
4. Fact vector career phase lineage & node grounding (bootstrap atoms carry career_phase_refs and graph_node_refs).
5. SQLite schema projection, index integrity, and direct SQL phase filtering.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    EPOCH_LABELS,
    EPOCH_ORDINAL,
    ORDINAL_TO_EPOCH,
    canonical_career_epoch_and_ordinal,
    get_skills_by_career_phase,
    materialize_augmented_skills_graph_sqlite,
)
from apps_rg.fact_inventory.c03_graph_evidence_cluster_registry import (
    GRAPH_PATH,
    REGISTRY_PATH,
    get_clusters_by_career_phase,
)
from apps_rg.runtime.c0.c02_evidence_fetch import (
    _atom_from_ledger_row,
    _atom_from_manifest_row,
)
from apps_rg.runtime.fact_vectors_bootstrap import build_base_resume_employment_atoms

ROOT = Path(__file__).resolve().parents[4]
ENGINE_ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ENGINE_ROOT / GRAPH_PATH
REGISTRY_FILE = ENGINE_ROOT / REGISTRY_PATH
SQLITE_PATH = (
    ENGINE_ROOT
    / "artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite"
)


@pytest.fixture(scope="module")
def graph_data() -> dict:
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cluster_registry() -> dict:
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sqlite_conn() -> sqlite3.Connection:
    if not SQLITE_PATH.is_file():
        conn = materialize_augmented_skills_graph_sqlite(
            sqlite_db_path=SQLITE_PATH, repo_root=ENGINE_ROOT
        )
        yield conn
        conn.close()
    else:
        conn = sqlite3.connect(str(SQLITE_PATH))
        yield conn
        conn.close()


def test_career_epoch_completeness_and_activation(graph_data: dict, sqlite_conn: sqlite3.Connection) -> None:
    """Test 1: All 6 career epochs are present, mapped 1..6, and projected as ACTIVE with HIGH confidence in SQLite."""
    epoch_nodes = [
        node
        for node in graph_data.get("graph_nodes", [])
        if node.get("node_type") == "career_epoch"
    ]
    assert len(epoch_nodes) == 6, f"Expected exactly 6 career epochs, got {len(epoch_nodes)}"

    seen_epochs = set()
    for node in epoch_nodes:
        nid = node["node_id"]
        assert nid in EPOCH_ORDINAL, f"Unexpected epoch node ID: {nid}"
        seen_epochs.add(nid)

    assert len(seen_epochs) == 6
    assert set(EPOCH_ORDINAL.keys()) == seen_epochs

    # Check that in the authoritative SQLite layer, all 6 canonical epochs are ACTIVE with HIGH confidence and 1..6 ordinals
    cursor = sqlite_conn.cursor()
    cursor.execute(
        f"""
        SELECT node_id, activation_status, confidence, phase_ordinal
        FROM graph_nodes
        WHERE node_type = 'career_epoch' AND node_id IN ({','.join('?' for _ in EPOCH_ORDINAL)})
        """,
        tuple(EPOCH_ORDINAL.keys()),
    )
    sqlite_epochs = cursor.fetchall()
    assert len(sqlite_epochs) == 6
    seen_ordinals = set()
    for nid, status, conf, ordinal in sqlite_epochs:
        assert status == "ACTIVE", f"SQLite Epoch {nid} must be ACTIVE"
        assert conf == "HIGH", f"SQLite Epoch {nid} must have HIGH confidence"
        assert ordinal == EPOCH_ORDINAL[nid], f"SQLite Epoch {nid} has wrong ordinal {ordinal}"
        seen_ordinals.add(ordinal)
    assert seen_ordinals == {1, 2, 3, 4, 5, 6}

    # Verify no skill is tagged with deprecated legacy epoch names
    deprecated = {"epoch_ibm_client_partner_consulting", "epoch_unify_chief_ai_officer"}
    for skill in graph_data.get("skill_rows", []):
        ep, ord_val = canonical_career_epoch_and_ordinal(
            skill["skill_id"], skill.get("career_epoch")
        )
        assert ep not in deprecated, f"Skill {skill['skill_id']} has deprecated epoch {ep}"
        if ep != "cross_career":
            assert ord_val in {1, 2, 3, 4, 5, 6}, f"Skill {skill['skill_id']} has invalid ordinal {ord_val}"
        else:
            assert ord_val is None


def test_skills_by_career_phase_retrieval_and_assertion_support(sqlite_conn: sqlite3.Connection) -> None:
    """Test 2: Authoritative retrieval API returns full skill graph, assertions, edges, and calibrated confidence."""
    for phase in range(1, 7):
        result = get_skills_by_career_phase(sqlite_conn, phase_ordinal=phase)

        # 1. Career phase metadata
        phase_meta = result["career_phase"]
        assert phase_meta["phase_ordinal"] == phase
        assert phase_meta["epoch_id"] == ORDINAL_TO_EPOCH[phase]
        assert phase_meta["label"] == EPOCH_LABELS[ORDINAL_TO_EPOCH[phase]]
        assert phase_meta["activation_status"] == "ACTIVE"
        assert phase_meta["confidence"] == "HIGH"

        # 2. Skills list
        skills = result["skills"]
        assert len(skills) > 0, f"Phase {phase} returned 0 skills"
        for s in skills:
            assert s["phase_ordinal"] == phase
            assert s["career_epoch"] == ORDINAL_TO_EPOCH[phase]
            assert s["skill_id"].startswith("skill_")
            assert s["confidence_numeric"] > 0.0

        # 3. Supporting assertions
        assertions = result["supporting_assertions"]
        facts = assertions["facts"]
        metrics = assertions["metrics"]
        employments = assertions["employments"]
        assert len(facts) > 0, f"Phase {phase} must have supporting fact assertions"
        assert len(employments) > 0, f"Phase {phase} must have linked employment nodes"

        # 4. Connective edges
        edges = result["edges"]
        assert len(edges) > 0, f"Phase {phase} must have connective edges"
        assert all(e["edge_type"] and e["edge_id"] for e in edges)
        assert all(e["evidence_status"] in {"validated", "ACTIVE_CONFIRMED", "approved_graph_ssot"} for e in edges)

        # 5. Calibrated confidence summary
        conf_summary = result["calibrated_confidence_summary"]
        assert conf_summary["total_skills"] == len(skills)
        assert conf_summary["average_confidence"] > 0.50
        assert (
            conf_summary["high_confidence_count"]
            + conf_summary["medium_confidence_count"]
            + conf_summary["low_confidence_count"]
        ) == len(skills)


def test_document_unit_embedding_architecture_and_singleton_prohibition(cluster_registry: dict, graph_data: dict) -> None:
    """Test 3: Document units strictly forbid singleton/per-node embeddings; clusters cover all phases."""
    policy = cluster_registry.get("materialization_policy", {})
    assert policy.get("logical_retrieval_unit") == "graph_evidence_cluster"
    assert policy.get("per_node_vector_default_forbidden") is True
    assert policy.get("one_future_vector_per_cluster") is True

    # Check all active clusters are multi-node (>= 2 members)
    for c in cluster_registry["clusters"]:
        assert len(c["member_node_ids"]) >= 2, f"Cluster {c['cluster_id']} must have >= 2 members"
        assert c["future_vector_count"] == 1

    # Check that singletons are strictly held and non-embeddable
    singletons = [
        h for h in cluster_registry["held_candidates"]
        if "SINGLETON_NOT_EMBEDDABLE" in (h.get("hold_reasons") or [])
    ]
    assert len(singletons) > 0
    assert all("canonical_embedding_text" not in h for h in singletons)

    # Check get_clusters_by_career_phase coverage across phases 1..6
    for phase in range(1, 7):
        clusters = get_clusters_by_career_phase(cluster_registry, phase_ordinal=phase, graph=graph_data)
        assert len(clusters) > 0, f"Phase {phase} must have document unit clusters"
        for c in clusters:
            assert c["logical_retrieval_unit"] == "graph_evidence_cluster"
            assert c["singleton_embedding_forbidden"] is True
            assert c["per_node_vectors_forbidden"] is True
            assert phase in c["phase_ordinals"]


def test_fact_vector_bootstrap_career_phase_lineage() -> None:
    """Test 4: Fact vector atoms are grounded in career phase lineage and graph employment nodes."""
    atoms, summary = build_base_resume_employment_atoms(repo_root=ENGINE_ROOT)
    assert len(atoms) > 0, "Expected base resume employment atoms"

    for atom in atoms:
        refs = atom.get("career_phase_refs")
        nodes = atom.get("graph_node_refs")
        assert refs and len(refs) > 0, f"Atom {atom['fact_id']} missing career_phase_refs"
        assert nodes and len(nodes) > 0, f"Atom {atom['fact_id']} missing graph_node_refs"
        # Validate that referenced epochs are in the canonical 6 epochs
        assert all(ref in EPOCH_ORDINAL for ref in refs), f"Invalid career phase ref in {atom['fact_id']}"

    # Verify c02_evidence_fetch helpers populate career phase lineage
    ledger_atom = _atom_from_ledger_row(
        {"candidate_fact_id": "test_fact_01", "company": "Unify Consulting", "claim_text": "Agentic AI"},
        section_id="unify_bullets",
    )
    assert "epoch_agentic_ai_runtime_architecture" in ledger_atom["career_phase_refs"]
    assert "employment_exp_unify_001" in ledger_atom["graph_node_refs"]

    manifest_atom = _atom_from_manifest_row(
        {
            "embed_allowed": True,
            "candidate_fact_atom": "IBM Cloud Modernization",
            "source_resume_variant": "IBM Partner Resume",
        },
        section_id="ibm_bullets",
    )
    assert manifest_atom is not None
    assert "epoch_cloud_data_platform_engineering" in manifest_atom["career_phase_refs"]
    assert "employment_exp_ibm_001" in manifest_atom["graph_node_refs"]


def test_sqlite_career_phase_schema_and_indexing(sqlite_conn: sqlite3.Connection) -> None:
    """Test 5: SQLite schema projection, indexing, and direct SQL phase filtering."""
    cursor = sqlite_conn.cursor()

    # Check columns in graph_nodes
    cursor.execute("PRAGMA table_info(graph_nodes)")
    nodes_cols = {row[1] for row in cursor.fetchall()}
    assert "career_epoch" in nodes_cols
    assert "phase_ordinal" in nodes_cols

    # Check columns in c03_skill_selection_features
    cursor.execute("PRAGMA table_info(c03_skill_selection_features)")
    feat_cols = {row[1] for row in cursor.fetchall()}
    assert "career_epoch" in feat_cols
    assert "phase_ordinal" in feat_cols

    # Check indexes exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cursor.fetchall()}
    assert "idx_graph_nodes_phase" in indexes
    assert "idx_graph_nodes_epoch" in indexes
    assert "idx_c03_skill_selection_phase" in indexes
    assert "idx_c03_skill_selection_epoch" in indexes

    # Query counts by phase_ordinal from SQLite
    for phase in range(1, 7):
        cursor.execute(
            "SELECT count(*) FROM c03_skill_selection_features WHERE phase_ordinal = ?",
            (phase,),
        )
        count = cursor.fetchone()[0]
        assert count > 0, f"Expected skills for phase {phase} in SQLite, got 0"
