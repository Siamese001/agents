# Agents Repository — Core Agent Runtime & Orchestration Assurance Agent (`2/4`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:3.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Order: 2/4 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective, Playbook & MECE Write Scope (`C01`, `C13`)
Execute a fail-closed **Core Agent Runtime, Supervisor State Machine, Context Budgeting, Event Persistence & Delegation Contract Audit & Remediation** exclusively within `/Users/amitayer/Git/agents`.
- **Canonical Skills**: Load `.agents/skills/agent-runtime-engineering/SKILL.md` and `.agents/skills/agent-subagent-orchestration/SKILL.md`.
- **MECE Single-Writer Scope (`AGY_SIDECAR_AGENT_ID="agents-core-runtime-orchestration"`)**: `agents/orchestration/`, `agents/persistence/`, `agents/observability/`, `agents/telemetry/`, `agents/gateway/`, `agents/context/budgeting.py`, `agents/cli.py`, `agents/_cli_helpers.py`, `agents/health.py`, `agents/e2e_artifacts.py`, `agents/e2e_output.py`, `agents/learning_cli.py`, `agents/live_preflight.py`, `tools/agent_runtime_auditor.py`, `tools/unified_agent_architecture.py`, `tools/hook_dispatch.py`, `tools/hitl_governance.py`, `tests/test_unified_agent_architecture.py`, `tests/test_hook_dispatch.py`, and `tests/test_hitl_governance_enforcement.py`.

## 2. Phase 1 & Phase 1.5: Read-Only Preflight Audit & Fast-Exit Gate (`C02`, `C03`)
Audit all 5 core runtime pillars (10-field delegation contracts, `WorkflowStateMachine` transitions, `TokenBudget` ceilings, `JsonlEventStore` tamper-evident persistence, and exception hygiene) in read-only mode first:
```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export PYTHONDONTWRITEBYTECODE=1
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/agent_runtime_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --json
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/test_unified_agent_architecture.py" "${PRIMARY_REPO_ROOT}/tests/test_hook_dispatch.py" "${PRIMARY_REPO_ROOT}/tests/test_hitl_governance_enforcement.py" -q -p no:cacheprovider --timeout=60
```
If all preflight gates exit `0` (`is_clean == true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

## 3. Phase 0, Phase 2 & Phase 3: Conditional Worktree, Wave Plan & 5-Point Promotion (`C02–C12`)
1. **Phase 0 (`Step 0.1`)**: On active findings (`is_clean == false`), export `AGY_SIDECAR_AGENT_ID="agents-core-runtime-orchestration"` and `AGENT_SLUG="core-runtime-orchestration"` (`RUN_DIR` appending `${RUN_TS}-${HEX6}`), invoke `prune_merged_chat_worktrees.py --consolidate-sidecar --write-manifest "${RUN_DIR}/manifest.json"`, and `cd "${WORKTREE_DIR}"` per `automations/prompts/_shared_governance_contract.md`.
2. **Phase 2**: Author `${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md`, validate via `validate_implementation_plan.py`, render the **Dimension Findings Table**, query `HITLDecisionStore`, and surface one atomic `<= 115` char `ask_question` if $\Delta \le 0.20$.
3. **Phase 3**: Execute sequential waves with 5-Point Counterfactual Runtime Proofs (`INV-RUNTIME-PROOF-5POINT`), record outcomes in `HITLDecisionStore`, pass `validate_sidecar_separation.py --json`, `validate_turn_gates.py --mode all`, and `verify_commit.py`, obtain `PR_MERGE_AUTHORIZATION`, and promote via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(agents): remediate core runtime orchestration contracts"`.
