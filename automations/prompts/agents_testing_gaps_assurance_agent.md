# Agents Repository — Testing Gaps & Regression Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:2.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage IV-B (Order 7/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Testing Gaps, Edge-Case Regression, Mock Reachability, Git Hook & Pytest Governance Assurance Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (On-Demand, Order `7/7`). This agent audits per-module and per-package public entrypoint coverage, separate cross-subsystem handoff contracts for both `outreach_engine` and `resume_graph_engine`, synchronous and async test assertions, skip/xfail hygiene, production mock reachability (`tools/audit_mock_reachability.py`), `pytest.ini` `--timeout=` and `--ignore=` quarantine limits, and `.githooks/` integrity across all 11 executable repository roots (`agents/`, `apps_eval/`, `apps_model_telemetry/`, `apps_research/`, `infrastructure/`, `ops_scripts/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `scripts/`, `tools/`) and all 6 test surfaces (`tests/`, `resume_graph_engine/tests/`, `outreach_engine/tests/`, `apps_eval/tests/`, `scripts/local_llm/`, `resume_graph_engine/src/apps_rg/evals/` — 945+ test files).

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Unit and integration test coverage gaps across all 6 test surfaces, per-module and per-package symbol/module coverage ratios across all 11 executable roots, synchronous and `async def test_*` strict assertion strength (rejecting bare re-raise and unasserted `validate*()` calls), `pytest.mark.skip(reason=...)` and `pytest.mark.xfail(strict=True)` hygiene, 11-root production mock reachability (`audit_mock_reachability.py`), multi-`pytest.ini` `--timeout=` & `--ignore=` quarantine enforcement, misplaced `src/` test detection, and `.githooks/` executable enforcement.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), production E2E code fixes (`agents-outreach-resume-functionality`), retrieval ranking logic (`agents-research-retrieval-surface`), judge rubrics (`agents-evals-judge-assurance`), and token budgets (`agents-cost-token-budget`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Pytest Run Protocol**:
  - Class A (Debug): Scoped to a single test file or test case with `--timeout=60` and synchronous `WaitMsBeforeAsync >= 15000`.
  - Class B (Receipt): Scoped to declared wave acceptance test files with `--timeout=60` and synchronous `WaitMsBeforeAsync >= 120000`.
  - Bare `pytest` or `pytest tests/` without scope is strictly forbidden.
- **Preflight-First Fast-Exit & Wave-Based Plan Mandate (`C03`, `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - Execute Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}`. When `0` actionable findings exist (`is_clean: true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating an ephemeral worktree or authoring a synthetic plan.
  - Whenever `>= 1` findings exist (`is_clean: false`), execute Phase 0 isolated worktree provisioning, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/testing-gaps-assurance-${HEX6}.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/testing-gaps-assurance-${HEX6}.md"` (`exit code 0`).

---

## 3. Phase 1 & Phase 1.5: 6-Pillar Read-Only Preflight Audit & Fast-Exit Gate

### Phase 1: 6-Pillar Testing Gaps Audit
1. **Pillar 1 — 11-Root Public Entrypoint & Module Coverage Floors (`>= 65%` Symbol, `>= 90%` Module)**: Audit public classes and functions across all 11 executable roots (`agents/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `apps_model_telemetry/`, `infrastructure/`, `ops_scripts/`, `scripts/`, and `tools/`) against all 6 test surfaces (`tests/`, `resume_graph_engine/tests/`, `outreach_engine/tests/`, `apps_eval/tests/`, `scripts/local_llm/`, `resume_graph_engine/src/apps_rg/evals/` — 959+ test files), enforcing `MIN_SYMBOL_COVERAGE_RATIO = 0.65` and `MIN_MODULE_COVERAGE_RATIO = 0.90`.
2. **Pillar 2 — Cross-Subsystem Contract Regression Tests**: Verify dedicated contract tests exist for `apps_research` -> `outreach_engine` and `apps_research` -> `resume_graph_engine` handoffs (including malformed, empty, and partial research packets).
3. **Pillar 3 — Constitutional Skip / Xfail Hygiene**: Detect any `@pytest.mark.skip` missing an explicit `reason=...` or any `@pytest.mark.xfail` missing `strict=True`.
4. **Pillar 4 — Sync & Async Weak Assertion Detection Across All 6 Test Surfaces**: Flag synchronous (`ast.FunctionDef`) and async (`ast.AsyncFunctionDef`) `test_*` functions across all 6 test surfaces that contain zero `assert` / `pytest.raises` / `mock.assert_*` statements.
5. **Pillar 5 — 11-Root Production Mock Reachability & Determinism (`audit_mock_reachability.py`)**: Verify zero unguarded mock branches exist across all 11 production roots and unit tests isolate external network calls cleanly.
6. **Pillar 6 — Quarantine Ceiling (`MAX_QUARANTINED_IGNORES = 2`), Sidecar Separation & Git Hook Enforcement (`.githooks/`)**: Verify multi-`pytest.ini` `--timeout=` and `--ignore=` quarantine limits (`<= 2`, restricted to `lib`/`lib64`), misplaced `src/` test exclusion, live scoped pytest smoke, and executable permissions on `.githooks/{pre-commit,pre-merge-commit,pre-push,post-merge}` pass 100%.

### Mandatory 6-Field Testing Gap Admission Proof
Every candidate test gap MUST declare:
1. `target_module_and_symbol` (`path/to/module.py:symbol_name`)
2. `subsystem_domain` (`agents` | `outreach_engine` | `resume_engine` | `resume_graph_engine` | `apps_research` | `apps_eval` | `apps_model_telemetry` | `infrastructure` | `governance`)
3. `untested_failure_mode` (specific boundary, exception, or state transition currently unverified)
4. `proposed_test_file` (`tests/unit/test_<name>.py`)
5. `assertion_contract` (exact behavioral assertions to enforce)
6. `priority_tier` (`P0_CRITICAL` | `P1_HIGH` | `P2_MEDIUM`)

### Phase 1.5: Mandatory Executable Read-Only Preflight Scanners
Execute the fail-closed 6-pillar behavioral testing gaps auditor (`tools/testing_gaps_auditor.py`), AST mock-reachability verifier (`tools/audit_mock_reachability.py`), and sidecar separation unit test check (`timeout <= 90s`):

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/testing_gaps_auditor.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --include-uncovered-backlog \
  --execute-pytest-smoke \
  --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/audit_mock_reachability.py" --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/unit/test_testing_gaps_full_parity.py" "${PRIMARY_REPO_ROOT}/tests/unit/test_all_seven_agents_coverage_elevation.py" "${PRIMARY_REPO_ROOT}/tests/unit/test_resume_graph_and_core_coverage_elevation.py" "${PRIMARY_REPO_ROOT}/outreach_engine/tests" -q --timeout=60
```

Verify `testing_gaps_auditor.py` exits `0` (`zero_assertion_tests == []`, `unreasoned_skips == []`, `non_strict_xfails == []`, `mock_reachability_violations == []`, zero uncovered module backlog) across all 6 test surfaces (`tests`, `resume_graph_engine/tests`, `outreach_engine/tests`, `apps_eval/tests`, `scripts/local_llm`, `resume_graph_engine/src/apps_rg/evals`); if `BACKLOG_ACTION_REQUIRED` (`exit code 1`), proceed to Phase 0 and author behavioral unit tests for uncovered modules.

---

## 4. Phase 0: Conditional Isolated Worktree Provisioning on Findings (`Step 0.1` — `C02`)

When Phase 1.5 reports `>= 1` actionable findings (`is_clean == false`), provision an isolated worktree, write `manifest.json` via `--write-manifest`, and switch into `${WORKTREE_DIR}`:

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-testing-gaps-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_testing_gaps_assurance/${RUN_TS}"
export PLAN_REL="plans/testing-gaps-assurance-${HEX6}.md"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --consolidate-sidecar \
  --worktree-dir "${WORKTREE_DIR}" \
  --branch "${BRANCH_NAME}" \
  --write-manifest "${RUN_DIR}/manifest.json" \
  --agent-id "agents-testing-gaps-assurance" \
  --run-id "${RUN_TS}" \
  --mode "interactive" \
  --plan-path "${PLAN_REL}"
cd "${WORKTREE_DIR}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/testing_gaps_auditor.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json || true
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/testing-gaps-assurance-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Outreach, Resume & Research Handoff Contract Unit Tests`
- `## Wave 2: Edge-Case Boundary Assertions & Strict Xfail/Skip Hygiene`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/testing-gaps-assurance-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/testing-gaps-assurance-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 6 testing pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` test count / coverage gap before edit.
   - Author bounded unit/integration tests under the target test root.
   - Run `POST_MUTATION_RUN` Class B receipt pytest (`--timeout=60`, `WaitMsBeforeAsync >= 120000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore`.
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, and either stage overnight via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` or obtain interactive `ask_question` `PR_MERGE_AUTHORIZATION` and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "test(coverage): remediate testing gaps and skip hygiene"`.
