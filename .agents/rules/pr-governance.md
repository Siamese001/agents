---
trigger: glob
globs: "{tools/pr_governance*.py,tools/rebase_orchestrator.py,tools/verify_*merge*.py}"
---

# PR Governance & Local Main Promotion Rules

Governs feature branch alignment, review, FIFO queue serialization, and promotion into local `main`.

1. **Governed Two-Stage PR Lifecycle**: Direct fast-forwards, unstructured squashes, or direct commits into `main` are prohibited.
   - **Stage A: Branch Alignment & Post-Rebase Readiness** (`python tools/pr_governance.py sync <branch>` or `rebase <branch>`): Rebase onto `main`, establish linear history, and verify post-rebase readiness (`tools/verify_main_readiness.py`).
   - **Stage B: Governed PR Review & Merge** (`python tools/pr_governance.py review <branch>` and `merge <branch> --title "<Title>"`): Pre-merge qualification outside the trunk lock, followed by serialized FIFO queue acquisition (`GovernedMergeQueueLock` at `.git/governed_merge_queue.lock`), automatic catch-up rebase onto `main` when `main` advances while queued, disjoint rebase receipt rebinding, and governed `--no-ff` merge commit with `GOVERNED_PR_MERGE=1`.
2. **Trunk Reservation Lock & Moving-Target Prevention**:
   - All worktrees share the trunk lock (`.git/governed_merge_queue.lock`) and FIFO waiter registry (`.git/governed_merge_queue_waiters.json`) in the git common directory.
   - Starvation-bounded disjoint bypass allows non-overlapping verified waiters to bypass an unverified queue head up to 3 times (`MAX_BYPASS_COUNT = 3`).
   - When a paused branch wakes from the queue after `main` has advanced, `_catch_up_queued_branch_under_lock` automatically rebases the branch onto the new `main` tip while holding the lock. If mainline changes are disjoint, the review receipt is automatically rebound; if overlapping, the lock is released and readiness is re-verified.
3. **Out-of-Tree Receipt Hygiene**: Readiness receipts (`reports/readiness/local_main_readiness_<slug>_receipt.json`) and PR review/merge receipts (`reports/pr_review_<slug>_receipt.json`, `reports/pr_merge_<slug>_receipt.json`) are git-ignored on feature branches.
4. **Governed Merge Commit Standard**: Use `--no-ff` with format: `Merge branch '<branch>' into main (<Summary>)` and commit trailers (`PR-Merge-Target`, `PR-Branch-Head`, `PR-Main-Base`, `PR-Terminal-Outcome`).
5. **Post-Merge Certification & Auto-Rollback**: Every merge into `main` is certified by `tools/verify_post_merge.py`. If certification fails, `atomic_rollback_main_to_sha` immediately restores `main` to its pre-merge SHA.
6. **Worktree & Branch Teardown**: Upon a certified merge into `main`, the feature worktree and branch are automatically torn down (`_teardown_merged_worktree` / `cmd_finish`).
7. **Same-Turn Promotion & Ratchet Ceiling Verification**: Before committing on any feature branch, run `.venv/bin/python tools/verify_commit.py --staged` to confirm ratcheted legacy files have not exceeded their line-count ceiling, keep command execution synchronous (`WaitMsBeforeAsync: 10000`), and complete `pr_governance.py promote <branch>` in the same turn whenever repository files are modified under an `implement` or `/learn` directive.
