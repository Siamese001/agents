"""Unmocked regression & counterfactual tests for DIE-parity graph hygiene, dedup, consolidation & promotion."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from apps_rg.fact_inventory.skills_graph.materializer import (
    materialize_augmented_skills_graph_sqlite,
)
from tools.apply_graph_hygiene_remediation import apply_graph_hygiene_remediation
from tools.audit_graph_hygiene_and_consolidation import (
    DEFAULT_GRAPH_REL,
    compute_string_similarity,
    normalize_text,
    run_graph_hygiene_audit,
    run_pre_promotion_regression_gates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_graph_hygiene_audit_runs_readonly_and_detects_real_clusters() -> None:
    report = run_graph_hygiene_audit(repo_root=REPO_ROOT)
    assert report["read_only"] is True
    assert report["schema_version"] == "agents.graph_hygiene_consolidation_audit.v1"
    assert report["baseline_counts"]["node_count"] > 300
    assert report["pre_promotion_regression_gates"]["status"] == "PASS"
    assert report["pre_promotion_regression_gates"]["fts_exact_active_parity"]["leaks"] == 0
    assert report["pre_promotion_regression_gates"]["quarantine_semantic_unit_isolation"]["leaks"] == 0

    cluster_ids = {c["cluster_id"] for c in report["hitl_clusters"]}
    # Real clusters must be surfaced until operator approves remediation
    assert "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS" in cluster_ids or "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS" in cluster_ids
    for c in report["hitl_clusters"]:
        assert c["council_debate"]["panel_mode"] == "hybrid_deterministic_council"
        assert c["item_count"] == len(c["items"]) > 0


def test_counterfactual_fts_and_quarantine_leak_triggers_fail_closed_gate(tmp_path: Path) -> None:
    sandbox_db = tmp_path / "augmented_skills_graph.sqlite"
    shutil.copy2(REPO_ROOT / DEFAULT_GRAPH_REL, sandbox_db)

    # Inject a synthetic quarantined node directly into graph_nodes_fts to prove fail-closed detection
    with sqlite3.connect(str(sandbox_db)) as conn:
        q_row = conn.execute(
            "SELECT node_id, node_type, label, description FROM graph_nodes "
            "WHERE activation_status = 'QUARANTINED_UNVERIFIED_SYNTHETIC' LIMIT 1"
        ).fetchone()
        assert q_row is not None
        conn.execute(
            "INSERT INTO graph_nodes_fts (node_id, node_type, label, description) VALUES (?, ?, ?, ?)",
            q_row,
        )
        conn.commit()

    gates = run_pre_promotion_regression_gates(sandbox_db)
    assert gates["status"] == "FAIL"
    assert gates["fts_exact_active_parity"]["status"] == "FAIL"
    assert gates["fts_exact_active_parity"]["leaks"] >= 1


def test_dry_run_remediation_never_mutates_graph_or_ledger() -> None:
    receipt = apply_graph_hygiene_remediation(
        repo_root=REPO_ROOT,
        apply_changes=False,
    )
    assert receipt["mode"] == "DRY_RUN"
    assert receipt["status"] == "DRY_RUN_READY"
    assert receipt["mutated"] is False
    assert len(receipt["projected_actions"]) > 0


def test_apply_remediation_requires_explicit_approved_clusters() -> None:
    with pytest.raises(ValueError, match="empty --approved-clusters"):
        apply_graph_hygiene_remediation(
            repo_root=REPO_ROOT,
            approved_clusters=(),
            apply_changes=True,
        )


def test_sandbox_apply_skill_twin_merge_and_draft_promotion_preserves_redirects(tmp_path: Path) -> None:
    sandbox_db = tmp_path / "augmented_skills_graph.sqlite"
    sandbox_ledger = tmp_path / "master_skills_arsenal_ledger.json"
    backup_dir = tmp_path / "backups"
    src_ledger = REPO_ROOT / "resume_graph_engine/src/apps_rg/fact_inventory/master_skills_arsenal_ledger.json"
    shutil.copy2(REPO_ROOT / DEFAULT_GRAPH_REL, sandbox_db)
    shutil.copy2(src_ledger, sandbox_ledger)

    pre = run_graph_hygiene_audit(repo_root=REPO_ROOT, db_path=sandbox_db)
    pre_twins = pre["baseline_counts"]["exact_skill_twins_count"]
    pre_drafts = pre["baseline_counts"]["draft_structural_count"]
    assert pre_twins > 0
    assert pre_drafts > 0

    receipt = apply_graph_hygiene_remediation(
        repo_root=REPO_ROOT,
        db_path=sandbox_db,
        ledger_path=sandbox_ledger,
        approved_clusters=[
            "CLUSTER-02A-EXACT-DUPLICATE-SKILL-TWINS",
            "CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS",
        ],
        apply_changes=True,
        skip_rematerialize=True,
        backup_dir=backup_dir,
    )
    assert receipt["status"] == "PASS"
    assert receipt["mutated"] is True
    assert (backup_dir / "master_skills_arsenal_ledger.json.bak").is_file()

    updated_ledger = json.loads(sandbox_ledger.read_text(encoding="utf-8"))
    redirects = updated_ledger.get("_graph_hygiene_redirects") or []
    assert len(redirects) == pre_twins
    assert receipt["applied_deltas"]["CLUSTER-05-DRAFT-STRUCTURAL-PROMOTIONS"]["promoted_nodes"] > 0

    # Rebuild SQLite from the consolidated sandbox ledger and verify zero-regression & twin reduction
    rebuilt_db = tmp_path / "rebuilt_graph.sqlite"
    materialize_augmented_skills_graph_sqlite(
        repo_root=REPO_ROOT / "resume_graph_engine",
        db_path=rebuilt_db,
        json_source_path=sandbox_ledger,
    )
    post = run_graph_hygiene_audit(repo_root=REPO_ROOT, db_path=rebuilt_db)
    assert post["pre_promotion_regression_gates"]["status"] == "PASS"
    assert post["baseline_counts"]["exact_skill_twins_count"] == 0
    assert post["baseline_counts"]["draft_structural_count"] < pre_drafts


def test_string_similarity_helper_matches_die_scan1_formula() -> None:
    n1 = normalize_text("Phase2 Gtm Presales")
    n2 = normalize_text("Gtm Presales Motion")
    sim, seq, jacc = compute_string_similarity(n1, n2)
    assert 0.65 <= sim <= 1.0
    assert sim == round(0.55 * seq + 0.45 * jacc, 4)
