"""Tests for Companion Agents PR Governance, Overnight Staging, and 7-Agent Lifecycle Parity."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from tools.pr_governance import CONVENTIONAL_BRANCH_RE, build_parser
from tools.pr_governance_core.promotion import (
    cmd_submit,
    derive_branch_merge_title,
)


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )


def _init_temp_repo(base_dir: Path) -> Path:
    repo = base_dir / "companion_repo"
    repo.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    _git(["config", "user.name", "Companion Tester"], cwd=repo)
    (repo / "README.md").write_text("# Companion Repo\n", encoding="utf-8")
    _git(["add", "README.md"], cwd=repo)
    _git(["commit", "-m", "chore(init): seed companion repository"], cwd=repo)
    return repo


def test_submit_stage_only_rebases_behind_main_without_mutating_main(tmp_path: Path) -> None:
    """Verify --stage-only rebases a behind-main branch, writes review + morning manifest, and leaves main untouched."""
    repo = _init_temp_repo(tmp_path)
    wt_dir = repo / ".worktrees" / "fix_sample_bug"
    wt_dir.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", str(wt_dir), "-b", "fix/sample-bug", "main"], cwd=repo)

    (wt_dir / "feature_fix.py").write_text("VALUE = 42\n", encoding="utf-8")
    _git(["add", "feature_fix.py"], cwd=wt_dir)
    _git(["commit", "-m", "fix(outreach): harden empty payload handling"], cwd=wt_dir)

    # Advance main independently so fix/sample-bug is 1 commit behind main
    (repo / "main_advance.txt").write_text("main moved\n", encoding="utf-8")
    _git(["add", "main_advance.txt"], cwd=repo)
    _git(["commit", "-m", "chore(main): advance trunk"], cwd=repo)
    main_sha_before = _git(["rev-parse", "main"], cwd=repo).stdout.strip()

    args = argparse.Namespace(
        branch="fix/sample-bug",
        title=None,
        stage_only=True,
        delete_branch=True,
        skip_readiness_run=True,
        fail_fast=False,
        recheck_failed_only=False,
        full=False,
        worktree=str(wt_dir),
        repo_root=str(repo),
    )
    rc = cmd_submit(args)
    assert rc == 0

    main_sha_after = _git(["rev-parse", "main"], cwd=repo).stdout.strip()
    assert main_sha_after == main_sha_before, "--stage-only must never mutate main"

    manifest_file = repo / ".local" / "merge_queue" / "staged_morning_approvals" / "fix_sample_bug.json"
    assert manifest_file.is_file()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["status"] == "STAGED_FOR_MORNING_APPROVAL"
    assert manifest["branch"] == "fix/sample-bug"
    assert manifest["base_commit_sha"] == main_sha_before
    assert manifest["title"] == "fix(outreach): harden empty payload handling"


def test_submit_interactive_rebases_merges_and_tears_down_worktree(tmp_path: Path) -> None:
    """Verify interactive submit auto-derives title, rebases behind-main branch, merges --no-ff, and prunes worktree."""
    repo = _init_temp_repo(tmp_path)
    wt_dir = repo / ".worktrees" / "chore_agents_hygiene"
    wt_dir.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", str(wt_dir), "-b", "chore/agents-hygiene", "main"], cwd=repo)

    (wt_dir / "hygiene_note.txt").write_text("cleaned\n", encoding="utf-8")
    _git(["add", "hygiene_note.txt"], cwd=wt_dir)
    _git(["commit", "-m", "chore(hygiene): checkpoint sqlite journals"], cwd=wt_dir)

    (repo / "other.txt").write_text("other\n", encoding="utf-8")
    _git(["add", "other.txt"], cwd=repo)
    _git(["commit", "-m", "docs(readme): update notes"], cwd=repo)

    args = argparse.Namespace(
        branch="chore/agents-hygiene",
        title=None,
        stage_only=False,
        delete_branch=True,
        skip_readiness_run=True,
        fail_fast=False,
        recheck_failed_only=False,
        full=False,
        worktree=str(wt_dir),
        repo_root=str(repo),
    )
    rc = cmd_submit(args)
    assert rc == 0
    assert (repo / "hygiene_note.txt").is_file()
    assert not wt_dir.exists()
    log_subject = _git(["log", "-1", "--format=%s", "main"], cwd=repo).stdout.strip()
    assert "Merge branch 'chore/agents-hygiene' into main" in log_subject


def test_submit_zero_commit_clean_branch_auto_prunes_noop(tmp_path: Path) -> None:
    """Verify zero-commit clean worktrees auto-prune cleanly without creating empty merge commits."""
    repo = _init_temp_repo(tmp_path)
    main_before = _git(["rev-parse", "main"], cwd=repo).stdout.strip()
    wt_dir = repo / ".worktrees" / "chore_noop_run"
    wt_dir.parent.mkdir(parents=True, exist_ok=True)
    _git(["worktree", "add", str(wt_dir), "-b", "chore/noop-run", "main"], cwd=repo)

    args = argparse.Namespace(
        branch="chore/noop-run",
        title=None,
        stage_only=True,
        delete_branch=True,
        skip_readiness_run=True,
        fail_fast=False,
        recheck_failed_only=False,
        full=False,
        worktree=str(wt_dir),
        repo_root=str(repo),
    )
    rc = cmd_submit(args)
    assert rc == 0
    assert not wt_dir.exists()
    assert _git(["rev-parse", "main"], cwd=repo).stdout.strip() == main_before


def test_parser_supports_stateless_worktree_flag_and_optional_submit_title() -> None:
    """Verify CLI parser accepts -C before/after subcommand, consolidate-host, --stage-only, and optional --title."""
    parser = build_parser()
    ns1 = parser.parse_args(["-C", "/tmp/wt", "submit", "chore/agents-test", "--stage-only"])
    assert ns1.command == "submit"
    assert ns1.stage_only is True
    assert ns1.title is None
    assert CONVENTIONAL_BRANCH_RE.match("chore/agents-test")

    ns2 = parser.parse_args(["consolidate-host", "fix/sample"])
    assert ns2.command == "consolidate-host"
    assert ns2.branch == "fix/sample"


def test_derive_branch_merge_title_fallback(tmp_path: Path) -> None:
    repo = _init_temp_repo(tmp_path)
    _git(["checkout", "-b", "fix/nonconv"], cwd=repo)
    (repo / "a.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "a.txt"], cwd=repo)
    _git(["commit", "-m", "plain commit message"], cwd=repo)
    _git(["checkout", "main"], cwd=repo)

    derived = derive_branch_merge_title("fix/nonconv", repo)
    assert derived == "fix(companion): plain commit message"
