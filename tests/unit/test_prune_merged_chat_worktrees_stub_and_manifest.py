"""Unit tests for Wave 1: Antigravity .agents/tools stub preservation, unlinked CWD fallback, and manifest helper."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from tools.prune_merged_chat_worktrees import (
    _preserve_cwd_stub_if_needed,
    main,
    prune_merged_worktrees,
    write_sidecar_manifest,
)


def _init_git_repo(repo_dir: Path) -> str:
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "tools").mkdir(exist_ok=True)
    (repo_dir / "tools" / "hook_dispatch.py").write_text("# stub\n", encoding="utf-8")
    (repo_dir / "scripts").mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(repo_dir)], check=True, capture_output=True, timeout=30)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "test@example.com"], check=True, timeout=15)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test User"], check=True, timeout=15)
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True, timeout=15)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "chore: init"], check=True, capture_output=True, timeout=15)
    rev = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=15)
    return rev.stdout.strip()


def test_preserve_cwd_stub_links_agents_tools_for_antigravity_hooks(tmp_path: Path) -> None:
    repo = tmp_path / "agents"
    _init_git_repo(repo)
    chat_wt = tmp_path / "antigravity" / "worktrees" / "agents" / "session_slug"

    created = _preserve_cwd_stub_if_needed(chat_wt, repo, force_stub_for_antigravity=True)
    assert created is True
    tools_link = chat_wt / ".agents" / "tools"
    assert tools_link.is_symlink()
    assert tools_link.resolve() == (repo / "tools").resolve()
    assert (tools_link / "hook_dispatch.py").is_file()


def test_prune_merged_worktrees_survives_unlinked_cwd_inode(tmp_path: Path) -> None:
    repo = tmp_path / "agents"
    _init_git_repo(repo)

    with patch("tools.prune_merged_chat_worktrees.Path.cwd", side_effect=FileNotFoundError(2, "No such file or directory")):
        result = prune_merged_worktrees(repo_root=repo, delete_merged=False)
        assert result["removed_worktrees"] == []
        rc = main(["--repo-root", str(repo), "--dry-run"])
        assert rc == 0


def test_write_sidecar_manifest_emits_canonical_six_fields(tmp_path: Path) -> None:
    repo = tmp_path / "agents"
    head_sha = _init_git_repo(repo)
    manifest_path = tmp_path / "run_dir" / "manifest.json"

    rc = main(
        [
            "--repo-root",
            str(repo),
            "--worktree-dir",
            str(repo),
            "--write-manifest",
            str(manifest_path),
            "--agent-id",
            "agents-storage-worktree-hygiene",
            "--run-id",
            "20261103T170000Z",
            "--mode",
            "interactive",
            "--plan-path",
            "plans/storage-abc123.md",
        ]
    )
    assert rc == 0
    assert manifest_path.is_file()
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(doc.keys()) == {"agent_id", "run_id", "mode", "pre_state_sha256", "worktree_dir", "plan_path"}
    assert doc["agent_id"] == "agents-storage-worktree-hygiene"
    assert doc["run_id"] == "20261103T170000Z"
    assert doc["mode"] == "interactive"
    assert doc["pre_state_sha256"] == head_sha
    assert doc["worktree_dir"] == str(repo.resolve())
    assert doc["plan_path"] == "plans/storage-abc123.md"

    direct = write_sidecar_manifest(
        tmp_path / "direct_manifest.json",
        worktree_dir=repo,
        agent_id="agents-evals-judge-assurance",
        run_id="20261103T170500Z",
    )
    assert direct["pre_state_sha256"] == head_sha
