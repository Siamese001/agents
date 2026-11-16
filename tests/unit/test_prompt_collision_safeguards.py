#!/usr/bin/env python3
"""Regression tests covering Waves 1-4 cross-prompt collision, worktree, SQLite, and scope guards."""
from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

from tools.hitl_governance import HITLDecisionStore
from tools.hook_dispatch import handle_pre_file_write, handle_pre_subagent_delegation
from tools.pr_governance_core.common import slugify_branch
from tools.prompt_scope_isolation import (
    PROMPT_STAGE_ALLOWED_WRITE_PATHS,
    evaluate_active_subagent_write_scope,
    evaluate_prompt_stage_write_scope,
    paths_overlap,
    register_and_check_subagent_scope,
    release_subagent_scope,
)
from tools.prune_merged_chat_worktrees import (
    SIDECAR_ACTIVE_LEASE_FILENAME,
    SIDECAR_LEASE_TTL_SECONDS,
    consolidate_single_sidecar_worktree,
    has_active_sidecar_lease,
    is_worktree_clean,
    write_sidecar_lease,
)
from tools.storage_worktree_hygiene import (
    ATOMIC_PROJECTION_SQLITE_NAMES,
    _storage_roots,
    inspect_sqlite_databases,
    remediate_sqlite_wal,
    run_six_pillar_hygiene_audit,
)
from tools.unified_agent_architecture import validate_delegation_contract
from tools.verify_graph_integrity_and_embeddings import verify_learned_sparse_and_colbert


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, timeout=15)


def _valid_contract(task_id: str, scope_in: list[str], scope_out: list[str] | None = None) -> dict[str, object]:
    return {
        "task_id": task_id,
        "parent_task_id": "wave-4",
        "objective": "Verify isolated delegation scope",
        "scope_in": scope_in,
        "scope_out": scope_out if scope_out is not None else ["docs/"],
        "allowed_tools": ["read_file", "edit_file"],
        "deliverable": "Verified diff",
        "definition_of_done": "Targeted tests pass",
        "budget": {"max_turns": 8, "timeout_seconds": 300},
        "escalation_rule": "Escalate on scope conflict",
    }


def _run_hook(fn, payload: dict[str, object], repo_root: Path) -> dict[str, object]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(payload, repo_root)
    return json.loads(buf.getvalue().strip())


def test_wave1_prompt_stage_manifests_and_write_scope(tmp_path: Path) -> None:
    """All 8 sidecar prompts declare stage isolation and write outside scope fails closed."""
    assert len(PROMPT_STAGE_ALLOWED_WRITE_PATHS) == 8
    prompt_files = sorted((REPO_ROOT / "automations" / "prompts").glob("agents_*_agent.md"))
    assert len(prompt_files) == 8
    for pf in prompt_files:
        text = pf.read_text(encoding="utf-8")
        assert "PYTHONDONTWRITEBYTECODE=1" in text, pf.name
        assert "-p no:cacheprovider" in text, pf.name
        assert "HEX6" in text, pf.name
        assert "AGY_SIDECAR_AGENT_ID=" in text, pf.name

    blocked_cross, reason_cross = evaluate_prompt_stage_write_scope(
        "agents/runtime/supervisor.py", tmp_path, agent_id="agents-storage-worktree-hygiene"
    )
    assert blocked_cross is False and "root-cause" in reason_cross

    allowed_own, _ = evaluate_prompt_stage_write_scope(
        "tools/storage_worktree_hygiene.py", tmp_path, agent_id="agents-storage-worktree-hygiene"
    )
    assert allowed_own is False

    allowed_ephemeral, _ = evaluate_prompt_stage_write_scope(
        "plans/fix-wave-123abc.md", tmp_path, agent_id="agents-storage-worktree-hygiene"
    )
    assert allowed_ephemeral is False

    blocked_unknown, _ = evaluate_prompt_stage_write_scope("tools/foo.py", tmp_path, agent_id="unknown-stage")
    assert blocked_unknown is False


def test_wave2_storage_worktree_isolation_and_atomic_sqlite(tmp_path: Path) -> None:
    """Worktree hygiene excludes primary root by default and keeps graph SQLite in DELETE mode."""
    primary = tmp_path / "primary"
    primary.mkdir()
    _git(primary, "init", "-b", "main")
    _git(primary, "config", "user.email", "test@example.com")
    _git(primary, "config", "user.name", "Test User")
    (primary / "README.md").write_text("root\n", encoding="utf-8")
    (primary / "scratch").mkdir()
    (primary / "scratch" / "primary_only.tmp").write_text("primary\n", encoding="utf-8")
    _git(primary, "add", "README.md")
    _git(primary, "commit", "-m", "init")

    wt = primary / ".worktrees" / "stage_wt"
    wt.parent.mkdir(parents=True, exist_ok=True)
    _git(primary, "worktree", "add", "-b", "chore/stage-wt", str(wt), "main")

    assert _storage_roots(wt, include_primary_root=False) == [wt.resolve()]
    assert _storage_roots(wt, include_primary_root=True) == [wt.resolve(), primary.resolve()]

    # Atomic graph SQLite target stays in DELETE journal mode with sidecars removed
    assert "augmented_skills_graph.sqlite" in ATOMIC_PROJECTION_SQLITE_NAMES
    db_dir = wt / "resume_graph_engine" / "artifacts" / "apps_rg" / "fact_inventory"
    db_dir.mkdir(parents=True, exist_ok=True)
    graph_db = db_dir / "augmented_skills_graph.sqlite"
    conn = sqlite3.connect(str(graph_db))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("CREATE TABLE graph_nodes (node_id TEXT PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()
    remediate_sqlite_wal(wt, include_primary_root=False)
    reports = inspect_sqlite_databases(wt, include_primary_root=False)
    assert len(reports) == 1
    assert reports[0]["journal_mode"] == "delete"
    assert not Path(str(graph_db) + "-wal").exists()

    with mock.patch("tools.storage_worktree_hygiene.validate_sidecar_separation", return_value={"is_clean": True}):
        audit = run_six_pillar_hygiene_audit(repo_root=wt, remediate=True, include_primary_root=False)
    assert audit["pillar_status"]["pillar_2_sqlite_integrity_wal"] == "PASS"
    assert (primary / "scratch" / "primary_only.tmp").exists()

    with pytest.raises(RuntimeError, match="read-only mode"):
        verify_learned_sparse_and_colbert(graph_db, read_only=True)


def test_wave3_lease_ttl_gitignored_protection_slug_and_hitl_concurrency(tmp_path: Path) -> None:
    """Zero-commit worktrees stay protected for full 7200s lease/plans, slugs disambiguate, HITL SQLite serializes."""
    assert slugify_branch("feat/fix-prompt-collisions") == "feat_fix_prompt_collisions"
    assert slugify_branch("feat/claude-guard") != slugify_branch("feat/gemini-guard")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / ".gitignore").write_text("plans/\nartifacts/\n.sidecar_active_run.lock\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "init")

    wt = repo / ".worktrees" / "sidecar_a"
    wt.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", "chore/agents-a", str(wt), "main")

    write_sidecar_lease(wt, "chore/agents-a")
    lease_path = wt / SIDECAR_ACTIVE_LEASE_FILENAME
    payload = json.loads(lease_path.read_text(encoding="utf-8"))
    assert payload["ppid"] == os.getppid()
    payload["pid"] = 999999
    payload["ppid"] = 999998
    lease_path.write_text(json.dumps(payload), encoding="utf-8")

    # Dead PID stays protected past old 1800s cutoff up to full SIDECAR_LEASE_TTL_SECONDS
    assert has_active_sidecar_lease(wt, now_ts=float(payload["started_at"]) + 3600.0) is True
    assert has_active_sidecar_lease(wt, now_ts=float(payload["started_at"]) + SIDECAR_LEASE_TTL_SECONDS + 10.0) is False

    # Branch mismatch against active lease raises RuntimeError
    with pytest.raises(RuntimeError, match="belongs to branch 'chore/agents-a'"):
        consolidate_single_sidecar_worktree(repo_root=repo, worktree_dir=wt, branch_name="chore/agents-b")

    # Even without lease, recent gitignored plan keeps is_worktree_clean False
    lease_path.unlink()
    assert is_worktree_clean(wt) is True
    (wt / "plans").mkdir(parents=True, exist_ok=True)
    (wt / "plans" / "wip-plan-abc123.md").write_text("# Plan\n", encoding="utf-8")
    assert is_worktree_clean(wt) is False
    old_ts = time.time() - SIDECAR_LEASE_TTL_SECONDS - 60.0
    os.utime(wt / "plans" / "wip-plan-abc123.md", (old_ts, old_ts))
    assert is_worktree_clean(wt) is True

    # Concurrent HITLDecisionStore transactions serialize without OperationalError
    hitl_db = tmp_path / "hitl.sqlite"
    store = HITLDecisionStore(db_path=hitl_db)

    def _worker(idx: int) -> bool:
        store.record_decision(
            decision_id=f"d-{idx}",
            task_id=f"t-{idx}",
            category="concurrency_test",
            options=["A", "B"],
            selected_option="A",
            operator_action="APPROVED",
            margin=0.1,
            calibrated_confidence=0.8,
        )
        return store.record_outcome(f"d-{idx}", "SUCCESS")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_worker, range(16)))
    assert all(results)


def test_wave4_subagent_scope_hooks_and_prompt_catalog_parity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prefix-aware scope overlap, inherit subagent leases, hook enforcement, and catalog refs stay consistent."""
    assert paths_overlap("agents/", "agents/context/router.py") is True
    assert paths_overlap("./tools/a.py", "tools/a.py") is True
    assert paths_overlap("outreach_engine/", "resume_engine/") is False

    carveout_contract = _valid_contract("sub-carveout", ["agents/"], ["agents/context/"])
    assert validate_delegation_contract(carveout_contract) == []
    bad_contract = _valid_contract("sub-overlap", ["agents/context/"], ["agents/"])
    assert any("DELEGATION_VIOLATION_SCOPE_OVERLAP" in err for err in validate_delegation_contract(bad_contract))

    ok1, _, _ = register_and_check_subagent_scope(tmp_path, _valid_contract("sub-1", ["agents/"]))
    assert ok1 is True
    ok2, _, _ = register_and_check_subagent_scope(tmp_path, _valid_contract("sub-2", ["agents/context/"]))
    assert ok2 is True
    ok_iso, _, _ = register_and_check_subagent_scope(
        tmp_path, _valid_contract("sub-iso", ["agents/context/"]), workspace_mode="branch"
    )
    assert ok_iso is True

    # Default /boost and /swarm workers are unrestricted across root-cause files and do not lock out parents
    blocked_sib, _ = evaluate_active_subagent_write_scope("agents/foo.py", tmp_path, task_id="other-sub")
    assert blocked_sib is False
    blocked_parent, _ = evaluate_active_subagent_write_scope("agents/foo.py", tmp_path, task_id="")
    assert blocked_parent is False
    blocked_out, _ = evaluate_active_subagent_write_scope("docs/foo.md", tmp_path, task_id="sub-1")
    assert blocked_out is False
    allowed_own, _ = evaluate_active_subagent_write_scope("agents/foo.py", tmp_path, task_id="sub-1")
    assert allowed_own is False

    # Opt-in exclusive_lock=True and enforce_strict_scope=True remain supported when explicitly requested
    strict_c1 = _valid_contract("strict-1", ["agents/"]) | {"exclusive_lock": True, "enforce_strict_scope": True}
    strict_c2 = _valid_contract("strict-2", ["agents/context/"]) | {"exclusive_lock": True}
    ok_s1, _, _ = register_and_check_subagent_scope(tmp_path, strict_c1)
    assert ok_s1 is True
    ok_s2, reason_s2, _ = register_and_check_subagent_scope(tmp_path, strict_c2)
    assert ok_s2 is False and "PARALLEL_SUBAGENT_SCOPE_CONFLICT" in reason_s2
    assert evaluate_active_subagent_write_scope("docs/foo.md", tmp_path, task_id="strict-1")[0] is True
    # Dead owner_pid on exclusive lease is automatically evicted rather than orphaning for 30-120 minutes
    scopes_json = tmp_path / ".local" / "governance" / "active_subagent_scopes.json"
    lease_data = json.loads(scopes_json.read_text(encoding="utf-8"))
    for entry in lease_data["leases"]:
        if entry["task_id"] == "strict-1":
            assert entry["owner_pid"] == os.getpid()
            entry["owner_pid"] = 999999
    scopes_json.write_text(json.dumps(lease_data), encoding="utf-8")
    ok_after_dead_pid, _, _ = register_and_check_subagent_scope(tmp_path, strict_c2)
    assert ok_after_dead_pid is True
    assert release_subagent_scope(tmp_path, "strict-2") is True

    # Edge cases: empty select_impacted_tests, explicit >4 batch size, and split-package model baseline inheritance
    from tools.adg_impact_tests import select_impacted_tests
    from tools.verify_commit import _MODEL_BASELINE_COUNTS, _resolve_model_baseline_count, check_architectural_governance

    empty_impact = select_impacted_tests([], repo_root=REPO_ROOT)
    assert empty_impact["batches"] == [] and empty_impact["total_selected"] == 0
    changed_sample = [
        "tools/hook_dispatch.py",
        "tools/validate_turn_gates.py",
        "tools/validate_implementation_plan.py",
        "tools/pr_governance.py",
        "tools/unified_agent_architecture.py",
    ]
    multi_impact = select_impacted_tests(changed_sample, repo_root=REPO_ROOT, max_files_per_batch=10)
    assert len(multi_impact["batches"][0]) == 10  # type: ignore[index]
    unbounded_impact = select_impacted_tests(changed_sample, repo_root=REPO_ROOT)
    assert len(unbounded_impact["batches"]) == 1 and len(unbounded_impact["batches"][0]) >= 10  # type: ignore[index]
    with mock.patch.dict(_MODEL_BASELINE_COUNTS, {"agents/legacy_mod.py": 2}, clear=True):
        assert _resolve_model_baseline_count("agents/legacy_mod.py") == 2
        assert _resolve_model_baseline_count("agents/legacy_mod/helper.py") == 2
        assert _resolve_model_baseline_count("agents/legacy_mod_pkg/helper.py") == 2
        assert _resolve_model_baseline_count("agents/unrelated_mod.py") == 0

        split_pkg = tmp_path / "split_repo" / "agents" / "legacy_mod"
        split_pkg.mkdir(parents=True)
        (split_pkg / "part_a.py").write_text('M1 = "gpt-4o"\n', encoding="utf-8")
        (split_pkg / "part_b.py").write_text('M2 = "claude-3-5-sonnet"\n', encoding="utf-8")
        _, ok_split_errs = check_architectural_governance([split_pkg / "part_b.py"], tmp_path / "split_repo")
        assert not [e for e in ok_split_errs if "[Model Neutrality]" in e]

        (split_pkg / "part_a.py").write_text('M1 = "gpt-4o"\nM2 = "claude-3-5-sonnet"\n', encoding="utf-8")
        (split_pkg / "part_b.py").write_text('M3 = "gpt-4o"\nM4 = "claude-3-5-sonnet"\n', encoding="utf-8")
        _, dup_split_errs = check_architectural_governance([split_pkg / "part_b.py"], tmp_path / "split_repo")
        model_bucket_errs = [e for e in dup_split_errs if "[Model Neutrality]" in e]
        assert len(model_bucket_errs) == 2

    for stage_prompt in sorted((REPO_ROOT / "automations" / "prompts").glob("agents_*_agent.md")):
        stage_txt = stage_prompt.read_text(encoding="utf-8")
        assert "max 1,000 words" not in stage_txt
        assert "up to 4 directly coupled test files" not in stage_txt
    assert "pairwise-disjoint" not in (REPO_ROOT / ".agents" / "rules" / "pr-governance.md").read_text(encoding="utf-8")
    assert "disjoint shard branches" not in (REPO_ROOT / "tools" / "pr_governance.py").read_text(encoding="utf-8")

    # Hook enforcement: contractless self on inherit and branch both allowed for /boost & /swarm; teamwork syncs request atomically
    allow_self = _run_hook(
        handle_pre_subagent_delegation,
        {"TypeName": "self", "Workspace": "inherit", "Prompt": "Edit something"},
        tmp_path,
    )
    assert allow_self["decision"] == "allow"

    allow_branch = _run_hook(
        handle_pre_subagent_delegation,
        {"TypeName": "self", "Workspace": "branch", "Prompt": "Edit safely in isolated clone"},
        tmp_path,
    )
    assert allow_branch["decision"] == "allow"

    allow_teamwork = _run_hook(
        handle_pre_subagent_delegation,
        {"TypeName": "teamwork", "Prompt": "Coordinate multi-file fix"},
        tmp_path,
    )
    assert allow_teamwork["decision"] == "allow"
    assert (tmp_path / ".agents" / "teamwork" / "ORIGINAL_REQUEST.md").read_text(encoding="utf-8") == "Coordinate multi-file fix\n"

    # File write hook allows known and custom stage root-cause writes and releases subagent leases cleanly
    monkeypatch.setenv("AGY_SIDECAR_AGENT_ID", "agents-storage-worktree-hygiene")
    allow_write_stage = _run_hook(handle_pre_file_write, {"Path": "agents/foo.py"}, tmp_path)
    assert allow_write_stage["decision"] == "allow"
    monkeypatch.setenv("AGY_SIDECAR_AGENT_ID", "custom-swarm-stage")
    allow_custom_stage = _run_hook(handle_pre_file_write, {"Path": "agents/foo.py"}, tmp_path)
    assert allow_custom_stage["decision"] == "allow"
    monkeypatch.delenv("AGY_SIDECAR_AGENT_ID", raising=False)
    allow_write_sub = _run_hook(handle_pre_file_write, {"Path": "agents/foo.py"}, tmp_path)
    assert allow_write_sub["decision"] == "allow"
    assert release_subagent_scope(tmp_path, "sub-1") is True
    assert release_subagent_scope(tmp_path, "sub-2") is True
    assert release_subagent_scope(tmp_path, "missing-id") is False

    # Reconciled apps_research prompt catalogs + skill doc
    profile = yaml.safe_load((REPO_ROOT / "apps_research/config/domain_contract/prompt_profile.company_brief.v1.yaml").read_text(encoding="utf-8"))
    assert (REPO_ROOT / profile["prompt_bom_ref"]).is_file()
    bom = yaml.safe_load((REPO_ROOT / "apps_research/prompt_assembly/prompt_bom.yaml").read_text(encoding="utf-8"))
    assert "apps_rg_targeting_brief_synthesis_v1" in bom["template_registry_refs"]
    tpl = yaml.safe_load((REPO_ROOT / "apps_research/prompt_assembly/templates/apps_rg_targeting_brief_synthesis_v1.yaml").read_text(encoding="utf-8"))
    md_prompt = (REPO_ROOT / "apps_research/config/prompts/apps_rg_targeting_brief_v1.md").read_text(encoding="utf-8")
    assert "BLOCKED: COMPANY_NOT_IDENTIFIABLE" in tpl["slot_bodies"]["R0"]
    assert "BLOCKED: COMPANY_NOT_IDENTIFIABLE_FROM_JD" not in tpl["slot_bodies"]["R0"]
    assert "BLOCKED: COMPANY_NOT_IDENTIFIABLE" in md_prompt
    skill_text = (REPO_ROOT / ".agents/skills/agent-subagent-orchestration/SKILL.md").read_text(encoding="utf-8")
    assert '"status": "SUCCESS"' in skill_text
