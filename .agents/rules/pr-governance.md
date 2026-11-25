---
trigger: glob
globs: "{tools/pr_governance*.py,tools/rebase_orchestrator.py,tools/verify_*merge*.py}"
---

# PR Governance & Local Main Promotion Rules (`agents` Overrides)

Inherits two-stage linear rebase, `--no-ff` governed promotion, and post-merge worktree teardown from `~/.gemini/config/plugins/core-governance/rules/pr-governance.md`.

## Repository Queue, Lock & Shard Train Mechanics

1. **Primary Root Isolation (`INV-WT-ISOLATION = 1`)**: Direct edits/commits on `main` are blocked; develop in `.worktrees/<slug>/` (`.agents/rules/git-worktree-governance.md`).
2. **FIFO Trunk Lock & Catch-Up Rebase (`tools/pr_governance.py`)**:
   - Stage A (`sync` / `rebase`) qualifies `reports/readiness/local_main_readiness_<slug>_receipt.json` via `tools/verify_main_readiness.py` (Lane 0: 4 stages, Lane 1: 9 stages, Lane 2: 10 stages; Tier 1 pre-check via `tools/verify_commit.py --staged` and `tools/change_lane_classifier.py`).
   - Stage B (`review` / `merge` / `promote`) acquires `.git/governed_merge_queue.lock` (`MAX_BYPASS_COUNT = 3`), auto-rebases onto advancing `main`, merges `--no-ff` with `GOVERNED_PR_MERGE=1`, certifies via `tools/verify_post_merge.py` (auto-rollback on failure), and tears down the merged worktree and branch.
3. **Multi-Agent Shard Train**: Sharded workers qualify via `tools/pr_governance.py shard-ready <shard_branch>` (`verify_commit.py --shard-fast`) and assemble via `tools/pr_governance.py train --wave <N> --shards <b1> ...` before `main` promotion.
