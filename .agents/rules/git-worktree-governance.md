---
trigger: model_decision
description: Isolated git worktree lifecycle, root checkout ban, linear rebase discipline, and post-merge cleanup
---

# Git Worktree & Branch Isolation Rules (`agents` Overrides)

Inherits root-main checkout/write bans, explicit `-C` routing, linear rebase discipline, and post-merge teardown (`INV-POST-MERGE-WORKTREE-TEARDOWN`) from `~/.gemini/config/plugins/core-governance/rules/git-worktree-governance.md`.

## Repository Worktree Mechanics

- **Worktree Creation & Cap**: Create isolated worktrees via `git -C /Users/amitayer/Git/agents worktree add -b <branch> .worktrees/<slug> HEAD` (`<= 50` active feature worktrees).
- **Pre-Commit & Queue Locks**: `.githooks/pre-commit` blocks direct commits to `main` outside governed merges (`GOVERNED_PR_MERGE=1`). `tools/pr_governance.py` serializes promotion under `.git/governed_merge_queue.lock`, verifies post-merge tree integrity via `tools/verify_post_merge.py`, and prunes merged worktrees (`tools/storage_worktree_hygiene.py`).
