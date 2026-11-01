# Testing Gaps & Post-Merge Worktree Cleanup Assurance Plan

## Executive Overview
Deliver end-to-end testing assurance across `apps_research`, `outreach_engine`, `resume_engine`, and `tools/prune_merged_chat_worktrees.py` inside the isolated worktree branch `test/post-merge-worktree-cleanup-assurance`. Verify cross-subsystem handoff contracts, prompt-injection airlock boundaries, strict skip hygiene, and post-merge worktree/branch deletion.

| Wave # | Description / Scope | Status |
| :--- | :--- | :--- |
| **Wave 1** | Cross-Subsystem Handoff Contracts & Airlock Edge-Case Regression Suite | `COMPLETE` |
| **Wave 2** | Post-Merge Worktree & Branch Deletion Regression Verification | `COMPLETE` |

---

## Wave 1: Cross-Subsystem Handoff Contracts & Airlock Edge-Case Regression Suite

### Objective & Scope
- **In Scope**: Validate `CrossAppEnvelope` / `ResearchBriefEnvelope` serialization roundtrip, schema/version mismatch, SHA-256 tamper detection, TTL expiration, standalone outreach v2 research bundle persistence, bounded live research retry/timeout policy, inbound/outbound prompt-injection airlocks, spam-trigger phrase lookups, and resume CLI inspectors (`0` runtime skips).
- **Out of Scope**: Live external LLM network calls.

### Milestones & Deliverables
- `[MODIFY]` `tests/unit/test_cross_subsystem_handoff_contracts.py`: 8 contract and negative boundary tests for `apps_research` -> `resume_graph_engine` and `apps_research` -> `outreach_engine`.
- `[MODIFY]` `tests/unit/test_testing_gaps_edge_cases.py`: 5 edge-case boundary tests for `validate_research_query`, `sanitize_briefing_content`, `spam_trigger_phrases`, and `resume_engine/cli_inspectors.py`.
- `[MODIFY]` `tests/unit/test_resume_engine_unified_cli.py`: Deterministic CLI console-script entrypoint verification with zero `pytest.skip` calls.

### Acceptance Criteria
- All 26 tests across `test_cross_subsystem_handoff_contracts.py`, `test_testing_gaps_edge_cases.py`, and `test_resume_engine_unified_cli.py` pass with `0` skips.
- `E2E-EXEMPT`: Scoped unit and contract regression suite.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest tests/unit/test_cross_subsystem_handoff_contracts.py tests/unit/test_testing_gaps_edge_cases.py tests/unit/test_resume_engine_unified_cli.py -v --timeout=60`
- Input: Synthetic envelopes, temporary v2 bundle directories, adversarial prompt-injection strings, and CLI arguments.
- Expected: `26 passed` in `< 5s` with `0 skipped`.
- Verify independently: Inspect AST test and assertion counts across the 3 test modules.
- Fail if: Any test fails, times out, or skips execution.
- Record: `artifacts/sidecar_runs/agents_testing_gaps_assurance/20261101T123549Z/wave_receipts.md`

---

## Wave 2: Post-Merge Worktree & Branch Deletion Regression Verification

### Objective & Scope
- **In Scope**: Add a dedicated regression test in `tests/test_post_merge_cleanup.py` verifying that `prune_merged_worktrees` and `_teardown_merged_worktree` delete both `.worktrees/<slug>` worktrees and external chat-session worktrees (plus their local feature branches) once merged into `main`, when invoked from `main_root`.
- **Out of Scope**: Mutating unmerged feature worktrees.

### Milestones & Deliverables
- `[MODIFY]` `tests/test_post_merge_cleanup.py`: Add `test_teardown_and_prune_removes_both_repo_and_external_worktrees_on_merge` proving that both `.worktrees/<slug>` and external worktree directories and their branches are deleted after merging to `main`.
- `[MODIFY]` `implementation_plan.md`: Record wave completion status table for pre-commit and pre-merge validation.

### Acceptance Criteria
- `tests/test_post_merge_cleanup.py` passes all 5 test cases (`100%` pass rate).
- Merging `test/post-merge-worktree-cleanup-assurance` into `main` automatically deletes `.worktrees/test_post_merge_worktree_cleanup_assurance` and the `test/post-merge-worktree-cleanup-assurance` branch.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest tests/test_post_merge_cleanup.py -v --timeout=60`
- Input: Temporary git repositories with `.worktrees/<slug>` and external worktree paths merged into `main`.
- Expected: `5 passed` in `< 5s` with both worktree directories and branches verified deleted.
- Verify independently: Run `git worktree list` and `git branch -a` after `pr_governance.py merge` to prove zero remaining worktree or branch references.
- Fail if: Merged worktree directory or local branch remains after merge teardown.
- Record: `artifacts/sidecar_runs/agents_testing_gaps_assurance/20261101T123549Z/wave_receipts.md`
