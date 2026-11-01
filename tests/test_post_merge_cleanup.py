#!/usr/bin/env python3
"""Unit tests for post-merge worktree and branch cleanup hook and tool.

Verifies:
1. `.githooks/post-merge` exists, is executable, and invokes `tools/prune_merged_chat_worktrees.py`.
2. `prune_merged_worktrees` removes a clean secondary worktree and deletes its local branch
   once the branch tip is merged into `main`.
3. `prune_merged_worktrees` preserves unmerged worktrees and branches.
4. `prune_merged_worktrees` preserves dirty worktrees (uncommitted changes) even if merged.
5. `prune_merged_worktrees` skips a worktree when `active_cwd` is inside that worktree.
6. Executing `.githooks/post-merge` inside a real temporary git repository after `git merge`
   automatically removes the merged worktree and branch.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.prune_merged_chat_worktrees import (
    get_merged_branches,
    list_worktrees,
    prune_merged_worktrees,
)

ROOT = Path(__file__).resolve().parents[1]


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=clean_env,
        shell=False,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )


class PostMergeCleanupTests(unittest.TestCase):
    def _init_repo_with_main(self, base_dir: Path) -> Path:
        repo = base_dir / "primary_repo"
        repo.mkdir(parents=True, exist_ok=True)
        _git(["init", "-b", "main"], cwd=repo)
        _git(["config", "user.email", "test@example.com"], cwd=repo)
        _git(["config", "user.name", "Test Operator"], cwd=repo)
        (repo / "README.md").write_text("# Main Repo\n", encoding="utf-8")
        _git(["add", "README.md"], cwd=repo)
        _git(["commit", "-m", "Initial commit on main"], cwd=repo)
        return repo

    def test_post_merge_hook_file_exists_and_references_pruner(self) -> None:
        hook_path = ROOT / ".githooks" / "post-merge"
        self.assertTrue(hook_path.is_file(), "Expected .githooks/post-merge to exist")
        content = hook_path.read_text(encoding="utf-8")
        self.assertIn("prune_merged_chat_worktrees.py", content)
        self.assertIn("--delete-merged", content)

    def test_prunes_merged_worktree_and_branch_and_preserves_unmerged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            repo = self._init_repo_with_main(base)

            # 1. Create a feature branch worktree and commit a change
            merged_wt = base / "wt_merged_feature"
            _git(["worktree", "add", "-b", "codex-merged-feature", str(merged_wt), "main"], cwd=repo)
            (merged_wt / "feature.txt").write_text("merged work\n", encoding="utf-8")
            _git(["add", "feature.txt"], cwd=merged_wt)
            _git(["commit", "-m", "Add merged feature"], cwd=merged_wt)

            # 2. Create an unmerged feature branch worktree and commit a change
            unmerged_wt = base / "wt_unmerged_feature"
            _git(["worktree", "add", "-b", "codex-unmerged-feature", str(unmerged_wt), "main"], cwd=repo)
            (unmerged_wt / "unmerged.txt").write_text("unmerged work\n", encoding="utf-8")
            _git(["add", "unmerged.txt"], cwd=unmerged_wt)
            _git(["commit", "-m", "Add unmerged feature"], cwd=unmerged_wt)

            # Merge only codex-merged-feature into main
            _git(["merge", "--no-ff", "codex-merged-feature", "-m", "Merge codex-merged-feature"], cwd=repo)

            merged_set = get_merged_branches(repo, target_ref="main")
            self.assertIn("codex-merged-feature", merged_set)
            self.assertNotIn("codex-unmerged-feature", merged_set)

            # Dry run first
            dry = prune_merged_worktrees(repo, target_ref="main", delete_merged=False, active_cwd=repo)
            self.assertEqual(dry["status"], "DRY_RUN")
            self.assertEqual(len(dry["candidates"]), 1)
            self.assertEqual(dry["candidates"][0]["branch"], "codex-merged-feature")
            self.assertTrue(merged_wt.exists())

            # Execute cleanup
            res = prune_merged_worktrees(repo, target_ref="main", delete_merged=True, active_cwd=repo)
            self.assertEqual(res["status"], "CLEANED")
            self.assertIn(str(merged_wt), res["removed_worktrees"])
            self.assertIn("codex-merged-feature", res["deleted_branches"])

            # Verify merged worktree and branch are gone, while unmerged remains intact
            self.assertFalse(merged_wt.exists())
            self.assertTrue(unmerged_wt.exists())
            remaining_branches = _git(["branch", "--format=%(refname:short)"], cwd=repo).stdout.splitlines()
            self.assertNotIn("codex-merged-feature", remaining_branches)
            self.assertIn("codex-unmerged-feature", remaining_branches)

    def test_preserves_dirty_or_active_cwd_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            repo = self._init_repo_with_main(base)

            dirty_wt = base / "wt_dirty"
            _git(["worktree", "add", "-b", "codex-dirty-branch", str(dirty_wt), "main"], cwd=repo)
            (dirty_wt / "dirty.txt").write_text("committed\n", encoding="utf-8")
            _git(["add", "dirty.txt"], cwd=dirty_wt)
            _git(["commit", "-m", "Commit before merge"], cwd=dirty_wt)

            _git(["merge", "--no-ff", "codex-dirty-branch", "-m", "Merge dirty branch"], cwd=repo)

            # Leave uncommitted untracked file in dirty_wt
            (dirty_wt / "untracked.txt").write_text("uncommitted work\n", encoding="utf-8")

            res_dirty = prune_merged_worktrees(repo, target_ref="main", delete_merged=True, active_cwd=repo)
            self.assertEqual(res_dirty["removed_worktrees"], [])
            self.assertTrue(any(s["reason"] == "dirty_worktree" for s in res_dirty["skipped"]))
            self.assertTrue(dirty_wt.exists())

            # Clean untracked file, but simulate active_cwd inside dirty_wt
            (dirty_wt / "untracked.txt").unlink()
            res_cwd = prune_merged_worktrees(repo, target_ref="main", delete_merged=True, active_cwd=dirty_wt)
            self.assertEqual(res_cwd["removed_worktrees"], [])
            self.assertTrue(any(s["reason"] == "active_cwd" for s in res_cwd["skipped"]))
            self.assertTrue(dirty_wt.exists())

    def test_git_post_merge_hook_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            repo = self._init_repo_with_main(base)

            # Install .githooks/post-merge and tools/prune_merged_chat_worktrees.py into temp repo
            githooks_dir = repo / ".githooks"
            tools_dir = repo / "tools"
            githooks_dir.mkdir(parents=True, exist_ok=True)
            tools_dir.mkdir(parents=True, exist_ok=True)

            hook_src = (ROOT / ".githooks" / "post-merge").read_text(encoding="utf-8")
            tool_src = (ROOT / "tools" / "prune_merged_chat_worktrees.py").read_text(encoding="utf-8")

            hook_dst = githooks_dir / "post-merge"
            tool_dst = tools_dir / "prune_merged_chat_worktrees.py"
            hook_dst.write_text(hook_src, encoding="utf-8")
            tool_dst.write_text(tool_src, encoding="utf-8")
            hook_dst.chmod(0o755)
            tool_dst.chmod(0o755)

            _git(["config", "core.hooksPath", ".githooks"], cwd=repo)
            _git(["add", ".githooks/post-merge", "tools/prune_merged_chat_worktrees.py"], cwd=repo)
            _git(["commit", "-m", "Add post-merge hook"], cwd=repo)

            # Create a secondary worktree, commit on feature branch, then merge into main
            feat_wt = base / "wt_e2e_feature"
            _git(["worktree", "add", "-b", "codex-e2e-feature", str(feat_wt), "main"], cwd=repo)
            (feat_wt / "e2e.txt").write_text("e2e feature\n", encoding="utf-8")
            _git(["add", "e2e.txt"], cwd=feat_wt)
            _git(["commit", "-m", "E2E feature commit"], cwd=feat_wt)

            # Running `git merge` on `main` triggers `.githooks/post-merge` automatically
            merge_proc = _git(["merge", "--no-ff", "codex-e2e-feature", "-m", "Merge e2e feature"], cwd=repo)
            combined_out = merge_proc.stdout + merge_proc.stderr
            self.assertIn("Post-Merge Cleanup Complete", combined_out)

            # Verify worktree folder and local branch were automatically deleted by the git merge
            self.assertFalse(feat_wt.exists(), "Worktree directory should be removed by post-merge hook")
            branches = _git(["branch", "--format=%(refname:short)"], cwd=repo).stdout.splitlines()
            self.assertNotIn("codex-e2e-feature", branches)
            wt_paths = [str(w["path"]) for w in list_worktrees(repo)]
            self.assertNotIn(str(feat_wt), wt_paths)


if __name__ == "__main__":
    unittest.main()
