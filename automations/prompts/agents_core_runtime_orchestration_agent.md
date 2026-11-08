# Agents Repository — Core Agent Runtime & Orchestration Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:2.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage III-A (Order 3/8) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Core Agent Runtime, Supervisor State Machine, Context Window Budgeting, Session Persistence & Delegation Contract Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (On-Demand, Order `3/8`). This agent verifies that the foundational agentic engine across `agents/` (`orchestration/`, `context/`, `persistence/`, `observability/`, `telemetry/`) executes with fail-closed state invariants, sliding token compaction, tamper-evident event streaming, and strict adherence to the mandatory 10-field delegation contract.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Core agent lifecycle states, `WorkflowStateMachine` transitions (`agents/orchestration/state_machine.py`), supervisor turn timeouts, `TokenBudget` limits and sliding window compaction (`agents/context/budgeting.py`), session persistence round-trip (`agents/persistence/jsonl/event_store.py`), mandatory 10-field delegation contract compliance (`tools/unified_agent_architecture.py`), and AST exception hygiene across `agents/`.
- **Delegated to peer agents**:
  - Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`),
  - Static layer imports & boundary encapsulation (`agents-ssot-boundary-governance`),
  - Domain business pipelines — outreach campaigns and resume graph tailoring (`agents-domain-applications-pipeline`),
  - Retrieval ranking & citation bindings (`agents-research-retrieval-surface`),
  - Judge rubrics & evaluation bounds (`agents-evals-judge-assurance`),
  - Token economics, caching & local model acceleration (`agents-cost-token-budget`),
  - Test entrypoint coverage & secret hygiene (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Preflight-First Fast-Exit & Wave-Based Plan Mandate (`C03`, `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - Execute Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}`. When `0` actionable findings exist (`is_clean: true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating an ephemeral worktree or authoring a synthetic plan.
  - Whenever `>= 1` findings exist (`is_clean: false`), execute Phase 0 isolated worktree provisioning, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md"` (`exit code 0`).

---

## 3. Phase 1 & Phase 1.5: 5-Pillar Read-Only Preflight Audit & Fast-Exit Gate

### Phase 1: 5-Pillar Core Runtime Audit
1. **Pillar 1 — Delegation Contracts**: Verify all subagent delegations construct the mandatory 10 fields (`task_id`, `parent_task_id`, `objective`, `scope_in`, `scope_out`, `allowed_tools`, `deliverable`, `definition_of_done`, `budget`, `escalation_rule`).
2. **Pillar 2 — State Machine Invariants**: Verify `WorkflowStateMachine` initial states, valid transitions, and illegal transition rejection.
3. **Pillar 3 — Context Budgeting**: Verify `TokenBudget` enforces maximum context token ceilings and raises `TokenBudgetExceededError` on overflow.
4. **Pillar 4 — Session Persistence**: Verify `JsonlEventStore` serializes and retrieves monotonic event streams without tamper.
5. **Pillar 5 — Exception Hygiene**: Verify zero unguarded silent exception swallows across all modules in `agents/`.

### Phase 1.5: Deterministic Auditor CLI Invocation
Execute the dedicated fail-closed checker against the primary checkout:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/agent_runtime_auditor.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --json
```
If `status == "PASS"` and `is_clean == true`, exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

---

## 4. Phase 0: Isolated Worktree Provisioning (`Step 0.1`)

When actionable defects exist, provision an isolated worktree:
```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(head -c 3 /dev/urandom | xxd -p)"
export BRANCH_SLUG="agents-core-runtime-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_core_runtime/${RUN_TS}"

"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --consolidate-sidecar \
  --worktree-dir "${WORKTREE_DIR}" \
  --branch "${BRANCH_NAME}" \
  --write-manifest "${RUN_DIR}/manifest.json" \
  --agent-id "agents-core-runtime-orchestration" \
  --run-id "${RUN_TS}" \
  --mode "on-demand"

cd "${WORKTREE_DIR}"
```

---

## 5. Phase 2: Remediation Wave Planning & Governance Approval

1. Author the wave plan at `${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md`.
2. Validate using `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md"`.
3. Copy plan: `cp "${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"`.
4. Surface the **Dimension Findings Table** and resolve atomic decisions with `HITLDecisionStore`.

---

## 6. Phase 3: Sequential Wave Execution & Governed Promotion

1. Execute bounded edits wave-by-wave with 5-Point Counterfactual Runtime Proofs.
2. Verify state with `agent_runtime_auditor.py`.
3. Commit on `${BRANCH_NAME}` and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "chore(agents): core runtime orchestration assurance"`.
