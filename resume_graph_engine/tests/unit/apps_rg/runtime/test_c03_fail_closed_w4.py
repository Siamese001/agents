"""Tests for Wave 4 Fail-Closed Runtime and C0.3 Receipts (AC4.4, AC4.5, AC4.6).

Verifies:
- AC4.4: Every C0.3 binding receipt contains path_confidence, evidence_ids and build_run_id.
- AC4.5: After one production run, graph_selection_rejections and resume_metric_usage contain >0 rows.
- AC4.6: Stale or missing DB -> C03GraphProjectionUnavailableError. No rematerialization happens on runtime path.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import pytest

from apps_rg.fact_inventory.skills_graph.storage import default_graph_sqlite_path, _repo_root
from apps_rg.runtime.c0.c02_evidence_fetch import fetch_c02_evidence_atoms
from apps_rg.runtime.c0.c03_graph_expansion import expand_c03_graph_bindings
from apps_rg.runtime.c03_graph_sqlite_context import (
    require_c03_graph_sqlite,
    assemble_c03_graph_sqlite_context,
)
from apps_rg.runtime.c0.c03_errors import C03GraphProjectionUnavailableError
from tests.unit.apps_rg.test_c0_evidence_room import _pool, REPO


def test_ac4_4_c03_binding_receipts_fields() -> None:
    """AC4.4: Every C0.3 binding receipt contains path_confidence, evidence_ids and build_run_id."""
    atoms = fetch_c02_evidence_atoms(section_id="competencies", pool=_pool(), repo_root=REPO)["atoms"]
    c03 = expand_c03_graph_bindings(
        section_id="competencies",
        atoms=atoms,
        repo_root=REPO,
        strict_ranked_selection=False,
        run_id="test_ac4_4_run",
    )
    bindings = c03.get("bindings") or []
    assert len(bindings) > 0, "No bindings produced by expand_c03_graph_bindings"

    for b in bindings:
        assert "path_confidence" in b, f"path_confidence missing from binding {b.get('fact_id')}"
        assert isinstance(b["path_confidence"], (int, float))
        assert "evidence_ids" in b, f"evidence_ids missing from binding {b.get('fact_id')}"
        assert isinstance(b["evidence_ids"], list)
        assert len(b["evidence_ids"]) >= 1, f"evidence_ids empty for binding {b.get('fact_id')}"
        assert "build_run_id" in b, f"build_run_id missing from binding {b.get('fact_id')}"
        assert str(b["build_run_id"]).strip() != ""


def test_ac4_5_selection_rejections_and_metric_usage_rows() -> None:
    """AC4.5: After one production run, graph_selection_rejections and resume_metric_usage contain >0 rows."""
    atoms = fetch_c02_evidence_atoms(section_id="competencies", pool=_pool(), repo_root=REPO)["atoms"]
    run_id = "test_ac4_5_audit_run"
    c03 = expand_c03_graph_bindings(
        section_id="competencies",
        atoms=atoms,
        repo_root=REPO,
        strict_ranked_selection=False,
        run_id=run_id,
    )
    db_path = c03.get("graph_context_ref") or default_graph_sqlite_path(_repo_root())
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        rejections_count = cur.execute(
            "SELECT COUNT(*) FROM graph_selection_rejections WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]
        metric_usage_count = cur.execute(
            "SELECT COUNT(*) FROM resume_metric_usage WHERE run_id = ?",
            (run_id,),
        ).fetchone()[0]

        assert rejections_count > 0, f"graph_selection_rejections has 0 rows for run {run_id}"
        assert metric_usage_count > 0, f"resume_metric_usage has 0 rows for run {run_id}"
    finally:
        conn.close()


def test_ac4_6_stale_or_missing_db_fails_closed(tmp_path: Path) -> None:
    """AC4.6: Stale or missing DB -> C03GraphProjectionUnavailableError. No rematerialization on runtime path."""
    non_existent = tmp_path / "non_existent_graph.sqlite"

    # Missing database must fail closed with C03GraphProjectionUnavailableError
    with pytest.raises(C03GraphProjectionUnavailableError, match="projection unavailable"):
        require_c03_graph_sqlite(REPO, non_existent)

    # Empty/corrupt database must also fail closed
    empty_db = tmp_path / "empty_graph.sqlite"
    sqlite3.connect(empty_db).close()
    with pytest.raises(C03GraphProjectionUnavailableError, match="projection unavailable"):
        require_c03_graph_sqlite(REPO, empty_db)

    # assemble_c03_graph_sqlite_context must fail closed without creating or modifying the missing DB
    with pytest.raises(C03GraphProjectionUnavailableError):
        assemble_c03_graph_sqlite_context(
            repo_root=REPO,
            db_path=non_existent,
            section_id="competencies",
            role_family_key="SVP_ENGINEERING_AI_PLATFORM",
        )
    assert not non_existent.exists(), "Runtime call must NOT rematerialize missing DB"
