---
name: agents-governance-hygiene
description: Consolidated 6-pillar storage, worktree, SQLite WAL hygiene, and SSOT architectural boundary governance for the Agents repository.
---

# Agents Governance, Storage & Cost Hygiene (On-Demand)

Consolidates `agents-storage-worktree-hygiene`, `agents-ssot-boundary-governance`, `agents-cost-token-budget`, and `agents-testing-gaps-assurance` into preflight-first, fail-closed on-demand CLI execution alongside `.githooks/pre-commit` (zero daily background schedules).

## Execution Protocol

1. **Preflight Read-Only Behavioral Audits (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`)**:
   Always execute read-only behavioral auditors first before provisioning any branch or mutating repository state:
   ```bash
   .venv/bin/python tools/storage_worktree_hygiene.py --json
   .venv/bin/python tools/ssot_boundary_auditor.py --include-ratchet-backlog --json
   .venv/bin/python tools/cost_token_budget_auditor.py --json --strict
   .venv/bin/python tools/lint_secrets.py --all
   .venv/bin/python tools/testing_gaps_auditor.py --include-uncovered-backlog --execute-pytest-smoke --json
   .venv/bin/python tools/validate_sidecar_separation.py --json
   .venv/bin/pytest outreach_engine/tests tests/unit/test_all_seven_agents_coverage_elevation.py tests/unit/test_resume_graph_and_core_coverage_elevation.py -q --timeout=60
   ```
   If all behavioral gates exit `0` (`is_clean == true`), fast-exit cleanly without creating empty worktrees or synthetic wave plans.

2. **Governed Remediation on Active Findings (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
   Whenever `>= 1` actionable findings exist (`is_clean == false`), provision an isolated `.worktrees/` branch via `prune_merged_chat_worktrees.py --consolidate-sidecar --write-manifest` (or `pr_governance.py start`), author and validate a wave plan in `plans/<slug>-<6hex>.md`, execute bounded remediation (such as `tools/storage_worktree_hygiene.py --remediate --json`), verify 5-point proofs, and obtain `PR_MERGE_AUTHORIZATION` before promoting to `main`.
