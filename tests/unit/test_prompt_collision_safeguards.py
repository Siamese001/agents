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
    assert blocked_cross is True and "PROMPT_STAGE_SCOPE_VIOLATION" in reason_cross

    allowed_own, _ = evaluate_prompt_stage_write_scope(
        "tools/storage_worktree_hygiene.py", tmp_path, agent_id="agents-storage-worktree-hygiene"
    )
    assert allowed_own is False

    allowed_ephemeral, _ = evaluate_prompt_stage_write_scope(
        "plans/fix-wave-123abc.md", tmp_path, agent_id="agents-storage-worktree-hygiene"
    )
    assert allowed_ephemeral is False

    blocked_unknown, _ = evaluate_prompt_stage_write_scope("tools/foo.py", tmp_path, agent_id="unknown-stage")
    assert blocked_unknown is True


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

    bad_contract = _valid_contract("sub-overlap", ["agents/"], ["agents/context/"])
    assert any("DELEGATION_VIOLATION_SCOPE_OVERLAP" in err for err in validate_delegation_contract(bad_contract))

    ok1, _, _ = register_and_check_subagent_scope(tmp_path, _valid_contract("sub-1", ["agents/"]))
    assert ok1 is True
    ok2, reason2, _ = register_and_check_subagent_scope(tmp_path, _valid_contract("sub-2", ["agents/context/"]))
    assert ok2 is False and "PARALLEL_SUBAGENT_SCOPE_CONFLICT" in reason2
    ok_iso, _, _ = register_and_check_subagent_scope(
        tmp_path, _valid_contract("sub-iso", ["agents/context/"]), workspace_mode="branch"
    )
    assert ok_iso is True

    blocked_sib, _ = evaluate_active_subagent_write_scope("agents/foo.py", tmp_path, task_id="other-sub")
    assert blocked_sib is True
    blocked_out, _ = evaluate_active_subagent_write_scope("docs/foo.md", tmp_path, task_id="sub-1")
    assert blocked_out is True
    allowed_own, _ = evaluate_active_subagent_write_scope("agents/foo.py", tmp_path, task_id="sub-1")
    assert allowed_own is False

    # Hook enforcement: contractless self on inherit denied; self on branch allowed; teamwork syncs request atomically
    deny_self = _run_hook(
        handle_pre_subagent_delegation,
        {"TypeName": "self", "Workspace": "inherit", "Prompt": "Edit something"},
        tmp_path,
    )
    assert deny_self["decision"] == "deny" and "DELEGATION_VIOLATION_MISSING_CONTRACT" in deny_self["reason"]

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

    # File write hook enforces stage write scope and active subagent scope
    monkeypatch.setenv("AGY_SIDECAR_AGENT_ID", "agents-storage-worktree-hygiene")
    deny_write_stage = _run_hook(handle_pre_file_write, {"Path": "agents/foo.py"}, tmp_path)
    assert deny_write_stage["decision"] == "deny" and "PROMPT_STAGE_SCOPE_VIOLATION" in deny_write_stage["reason"]
    monkeypatch.delenv("AGY_SIDECAR_AGENT_ID", raising=False)
    deny_write_sub = _run_hook(handle_pre_file_write, {"Path": "agents/foo.py"}, tmp_path)
    assert deny_write_sub["decision"] == "deny" and "SUBAGENT_SCOPE_CONFLICT" in deny_write_sub["reason"]
    assert release_subagent_scope(tmp_path, "sub-1") is True
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
