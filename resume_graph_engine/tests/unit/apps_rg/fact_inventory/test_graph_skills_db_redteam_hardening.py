"""Acceptance and regression tests for Graph Skills DB red-team hardening."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps_rg.fact_inventory.augmented_skills_graph_sqlite import (
    _acquire_sqlite_maintenance_lock,
    _check_and_reclaim_stale_lock,
    _release_sqlite_maintenance_lock,
    _sqlite_maintenance_lock_path,
    default_graph_sqlite_path,
)
from apps_rg.fact_inventory.claim_proof_split_policy import (
    claim_text_violates_i0_display_policy,
)
from apps_rg.runtime.c0.c03_sqlite_graph_selection import (
    select_c03_sqlite_graph_candidates,
)
from apps_rg.runtime.c03_graph_sqlite_context import (
    assemble_c03_graph_sqlite_context,
)

REPO = Path(__file__).resolve().parents[4]


def test_c03_context_prioritizes_role_weighted_skills() -> None:
    db_path = default_graph_sqlite_path(REPO)
    if not db_path.is_file():
        pytest.skip(f"Canonical SQLite database not found at {db_path}")

    bundle = assemble_c03_graph_sqlite_context(
        role_family_key="SVP_ENGINEERING_AI_PLATFORM",
        section_id="executive_summary",
        selected_fact_ids=["fact_engineering_platform_001"],
        repo_root=REPO,
    )
    receipt = bundle.get("receipt") or {}
    selected_nodes = receipt.get("selected_nodes") or []
    skill_nodes = [n for n in selected_nodes if n.get("node_type") == "skill"]
    assert skill_nodes, "Expected at least one skill node in context assembly"

    # Top 5 skills must NOT be actuarial software or FSA fellowship for an SVP AI Platform role
    top_5_ids = [s["node_id"] for s in skill_nodes[:5]]
    assert "skill_actuarial_actuarial_software" not in top_5_ids
    assert "skill_actuarial_fsa_fellowship" not in top_5_ids


def test_maintenance_lock_reclaims_stale_dead_pid(tmp_path: Path) -> None:
    fake_db = tmp_path / "test_db.sqlite"
    lock_path = _sqlite_maintenance_lock_path(fake_db)

    # Simulate an orphaned lock left behind by a dead process PID (99999999)
    lock_path.write_text("pid=99999999\n", encoding="ascii")
    assert lock_path.is_file()

    # Acquisition should detect the dead PID and reclaim the lock safely
    acquired_lock = _acquire_sqlite_maintenance_lock(fake_db)
    try:
        assert acquired_lock == lock_path
        assert lock_path.is_file()
        content = lock_path.read_text(encoding="ascii")
        assert f"pid={os.getpid()}" in content
    finally:
        _release_sqlite_maintenance_lock(acquired_lock)
    assert not lock_path.exists()


def test_in_memory_metric_usage_applies_penalties() -> None:
    db_path = default_graph_sqlite_path(REPO)
    if not db_path.is_file():
        pytest.skip(f"Canonical SQLite database not found at {db_path}")

    # Baseline call with no in-memory usage
    baseline = select_c03_sqlite_graph_candidates(
        section_id="executive_summary",
        selected_fact_ids=["fact_engineering_platform_001"],
        role_family_key="SVP_ENGINEERING_AI_PLATFORM",
        repo_root=REPO,
        max_skills_per_fact=2,
    )
    assert baseline["selected_candidates"]
    top_skill = baseline["selected_candidates"][0]["skill_id"]

    # Call with high in-memory usage on top_skill
    penalized = select_c03_sqlite_graph_candidates(
        section_id="executive_summary",
        selected_fact_ids=["fact_engineering_platform_001"],
        role_family_key="SVP_ENGINEERING_AI_PLATFORM",
        repo_root=REPO,
        max_skills_per_fact=2,
        in_memory_metric_usage={top_skill: 10},
    )
    assert penalized["selected_candidates"]
    # Either top_skill was penalized (prior_metric_usage_penalty present)
    # or it was demoted below another candidate because of the heavy penalty
    penalized_top = next((c for c in penalized["selected_candidates"] if c["skill_id"] == top_skill), None)
    if penalized_top:
        assert "prior_metric_usage_penalty" in penalized_top.get("penalties", {})
    else:
        assert penalized["selected_candidates"][0]["skill_id"] != top_skill


def test_display_policy_handles_zero_width_spaces() -> None:
    # Text with zero-width spaces (\u200b) attempting to evade substring checks
    evasive_text = "Experienced in fsa\u200b credential and multi-agent\u200b orchestration"
    violations = claim_text_violates_i0_display_policy(evasive_text)
    assert any("fsa credential" in v or "multi-agent orchestration" in v for v in violations)
