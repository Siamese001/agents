---
trigger: model_decision
description: Isolated git worktree lifecycle, root checkout ban, linear rebase discipline, and post-merge cleanup
---
# Git Worktree & Branch Isolation Governance

Governs isolated feature development, worktree hygiene, and clean post-merge teardown across `/Users/amitayer/Git/agents`.

## 1. Non-Negotiable Worktree Invariants

1. **Root Workspace Checkout Ban**: Never run `git checkout <branch>` or `git switch <branch>` inside the primary repository root (`/Users/amitayer/Git/agents`). Primary root stays cleanly on `main`.
2. **Isolated Feature Worktrees**: All code edits, commits, rebases, and PR qualification execute inside `.worktrees/<slug>/` created via `git -C /Users/amitayer/Git/agents worktree add -b <branch> .worktrees/<slug> HEAD`.
3. **Explicit `-C` Git Routing**: Always pass `-C <worktree_or_repo_path>` on git commands so invocations never mutate the wrong working tree.
4. **Zero Dirty-Dump Commits**: Stage explicitly authored paths and verify `git -C <worktree> status --short` before committing. Never sweep unrelated untracked artifacts into a feature commit.
5. **Linear Rebase Only**: Feature branches synchronize onto `main` strictly via linear rebase (`git rebase main` or `tools/pr_governance.py sync <branch>`). Merging `main` backwards into a feature branch is prohibited.
6. **Worktree WIP Cap & Teardown**: Maintain `<= 50` active feature worktrees. Immediately after a certified merge via `tools/pr_governance.py promote`, remove the merged worktree directory and run `git -C /Users/amitayer/Git/agents worktree prune`.

## 2. Enforcement

- Pre-commit hook (`.githooks/pre-commit`): Blocks direct commits to `main` outside governed merges (`GOVERNED_PR_MERGE=1`).
- PR Governance (`tools/pr_governance.py`): Serializes merges under `.git/governed_merge_queue.lock` and verifies post-merge tree integrity via `tools/verify_post_merge.py`.
- Hygiene Auditor (`tools/storage_worktree_hygiene.py`): Audits worktree health and stale locks.
