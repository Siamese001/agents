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

### Phase 1.5: Mandatory Executable Read-Only Preflight Scanners
Execute the dedicated fail-closed checker and scoped unit suite against the primary checkout (`timeout <= 90s`):
```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/agent_runtime_auditor.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --json
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/unit/test_sidecar_separation_governance.py" -q --timeout=60
```
If `status == "PASS"` and `is_clean == true`, exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

---

## 4. Phase 0: Conditional Isolated Worktree Provisioning on Findings (`Step 0.1` — `C02`)

When Phase 1.5 reports `>= 1` actionable findings (`is_clean == false`), provision an isolated worktree, write `manifest.json` via `--write-manifest`, and switch into `${WORKTREE_DIR}`:
```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-core-runtime-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_core_runtime/${RUN_TS}"
export PLAN_REL="plans/core-runtime-orchestration-${HEX6}.md"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --consolidate-sidecar \
  --worktree-dir "${WORKTREE_DIR}" \
  --branch "${BRANCH_NAME}" \
  --write-manifest "${RUN_DIR}/manifest.json" \
  --agent-id "agents-core-runtime-orchestration" \
  --run-id "${RUN_TS}" \
  --mode "interactive" \
  --plan-path "${PLAN_REL}"
cd "${WORKTREE_DIR}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/agent_runtime_auditor.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json || true
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Delegation Contract, Supervisor State Machine & Context Budget Remediation`
- `## Wave 2: Event Store Persistence & Exception Hygiene Enforcement`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/core-runtime-orchestration-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 5 runtime pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` runtime metric before edit (`"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/agent_runtime_auditor.py" --repo-root "${WORKTREE_DIR}" --json`).
   - Apply bounded fixes in `agents/` (`orchestration/`, `context/`, `persistence/`, `observability/`).
   - Run `POST_MUTATION_RUN` `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/agent_runtime_auditor.py" --repo-root "${WORKTREE_DIR}" --json` and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore`.
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, and either stage overnight via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` or obtain interactive `ask_question` `PR_MERGE_AUTHORIZATION` and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "chore(agents): core runtime orchestration assurance"`.
