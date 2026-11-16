---
trigger: model_decision
---

# PR Publisher Dirty-Worktree Recovery Contract

ProceduralPattern:PRPublisherDirtyWorktreeRecovery

- Fixed recurring stop condition where the on-demand PR publisher treated dirty-worktree intake as a hard TOML/PR-flow audit failure before recovery could preserve and route the work.
- Use `.venv/bin/python tools/pr_governance.py status` for intake; dirty current worktrees are reported cleanly so recovery can preserve and route uncommitted work without hard TOML/PR-flow crashes.
- Use `.venv/bin/python tools/verify_merge_receipt.py` and `.venv/bin/python tools/pr_governance.py review <branch>` for automation-facing readiness verification.
- Use `--require-single-main-worktree` only for strict final closeout; dirty current worktree is a blocker there until the recovery/cleanup loop clears it.
- Guard tests: `tests/test_pr_merge_queue_governance.py`.
- Do not "fix" recurrence by weakening PR-flow TOML validation; invalid `publication_mode`, `allow_direct_main_push`, `require_github_ci_green`, or `allow_bypass_merge` remains a hard `pr_flow_contract_violation`.
- discovered: 2026-06-30, validated: 2026-06-30
