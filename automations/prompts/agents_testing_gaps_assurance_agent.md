# Agents Repository — Testing Gaps & Regression Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage IV-B (Order 7/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Testing Gaps, Edge-Case Regression, Mock Reachability, Git Hook & Pytest Governance Assurance Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`07:30 ET`, Order `7/7`). This agent audits untested public functions, cross-subsystem handoff edge cases, synchronous and async test assertions, skip/xfail hygiene, production mock reachability (`tools/audit_mock_reachability.py`), and `.githooks/` integrity across all 9 production packages (`agents/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/src/`, `apps_research/`, `apps_eval/`, `apps_model_telemetry/`, `infrastructure/`, `ops_scripts/`) and all 4 test roots (`tests/`, `resume_graph_engine/tests/`, `outreach_engine/tests/`, `apps_eval/tests/` — 932+ test files).

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Unit and integration test coverage gaps across all 4 test roots (`tests/`, `resume_graph_engine/tests/`, `outreach_engine/tests/`, `apps_eval/tests/`), synchronous and `async def test_*` assertion strength, `pytest.mark.skip(reason=...)` and `pytest.mark.xfail(strict=True)` hygiene, production mock reachability (`audit_mock_reachability.py`), `.githooks/` executable enforcement, and Class A/B `--timeout=60` test execution compliance.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), production E2E code fixes (`agents-outreach-resume-functionality`), retrieval ranking logic (`agents-research-retrieval-surface`), judge rubrics (`agents-evals-judge-assurance`), and token budgets (`agents-cost-token-budget`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Pytest Run Protocol**:
  - Class A (Debug): Scoped to a single test file or test case with `--timeout=60` and synchronous `WaitMsBeforeAsync >= 15000`.
  - Class B (Receipt): Scoped to declared wave acceptance test files with `--timeout=60` and synchronous `WaitMsBeforeAsync >= 120000`.
  - Bare `pytest` or `pytest tests/` without scope is strictly forbidden.
- **Zero-Defect Fast-Exit & Wave-Based Plan Mandate (`C03`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - When Phase 1.5 reports `0` actionable findings (`is_clean: true`), fast-exit cleanly per `C03`: copy `${RUN_DIR}` to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_testing_gaps_assurance/${RUN_TS}`, tear down the ephemeral worktree via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only`, and exit `COMPLETE` without authoring a synthetic plan.
  - Whenever `>= 1` findings exist in **EITHER** `MODE: scheduled` or `MODE: interactive`, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md"` (`exit code 0`).
  - In `MODE: scheduled`, stage validated fixes on `${BRANCH_NAME}` via `pr_governance.py submit "${BRANCH_NAME}" --stage-only` without mutating `local main` directly.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-testing-gaps-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_testing_gaps_assurance/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 6-Pillar Testing Gaps Audit, 6-Field Proof & Executable Scanners

### Phase 1: 6-Pillar Testing Gaps Audit
1. **Pillar 1 — Untested Critical Public Entrypoints**: Identify public classes and functions across `agents/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/src/`, `apps_research/`, `apps_eval/`, `apps_model_telemetry/`, and `infrastructure/` with zero corresponding test references across the 4 test roots (`tests/`, `resume_graph_engine/tests/`, `outreach_engine/tests/`, `apps_eval/tests/`).
2. **Pillar 2 — Cross-Subsystem Contract Regression Tests**: Verify dedicated contract tests exist for `apps_research` -> `outreach_engine` and `apps_research` -> `resume_graph_engine` handoffs (including malformed, empty, and partial research packets).
3. **Pillar 3 — Constitutional Skip / Xfail Hygiene**: Detect any `@pytest.mark.skip` missing an explicit `reason=...` or any `@pytest.mark.xfail` missing `strict=True`.
4. **Pillar 4 — Sync & Async Weak Assertion Detection**: Flag synchronous (`ast.FunctionDef`) and async (`ast.AsyncFunctionDef`) `test_*` functions across all 4 test roots that contain zero `assert` / `pytest.raises` / `mock.assert_*` statements.
5. **Pillar 5 — Production Mock Reachability & Determinism (`audit_mock_reachability.py`)**: Verify zero unguarded mock branches exist in production roots and unit tests isolate external network calls cleanly.
6. **Pillar 6 — Governance, Sidecar Separation & Git Hook Enforcement (`.githooks/`)**: Verify `tests/unit/test_sidecar_separation_governance.py`, `tests/test_turn_gates.py`, and executable permissions on `.githooks/{pre-commit,pre-merge-commit,pre-push,post-merge}` pass 100%.

### Mandatory 6-Field Testing Gap Admission Proof
Every candidate test gap MUST declare:
1. `target_module_and_symbol` (`path/to/module.py:symbol_name`)
2. `subsystem_domain` (`agents` | `outreach_engine` | `resume_engine` | `resume_graph_engine` | `apps_research` | `apps_eval` | `apps_model_telemetry` | `infrastructure` | `governance`)
3. `untested_failure_mode` (specific boundary, exception, or state transition currently unverified)
4. `proposed_test_file` (`tests/unit/test_<name>.py`)
5. `assertion_contract` (exact behavioral assertions to enforce)
6. `priority_tier` (`P0_CRITICAL` | `P1_HIGH` | `P2_MEDIUM`)

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the fail-closed 6-pillar behavioral testing gaps auditor (`tools/testing_gaps_auditor.py`), AST mock-reachability verifier (`tools/audit_mock_reachability.py`), and sidecar separation unit test check in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/testing_gaps_auditor.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/audit_mock_reachability.py" --repo-root "${WORKTREE_DIR}"
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${WORKTREE_DIR}/tests/unit/test_sidecar_separation_governance.py" -v --timeout=60
```

Verify `testing_gaps_auditor.py` exits `0` (`zero_assertion_tests == []`, `unreasoned_skips == []`, `non_strict_xfails == []`, `mock_reachability_violations == []`) across all 4 test roots (`tests`, `resume_graph_engine/tests`, `outreach_engine/tests`, `apps_eval/tests`, covering both `FunctionDef` and `AsyncFunctionDef`) before any `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`. Write the structured findings and 6-field admission proofs to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
When findings exist, author `${WORKTREE_DIR}/plans/testing-gaps-assurance-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
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
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_testing_gaps_assurance/${RUN_TS}`, then stage verified fixes (or prune 0-commit runs) via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` without mutating `main`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

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
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, then stage via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` in scheduled mode or promote after interactive `ask_question` `PR_MERGE_AUTHORIZATION` via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "test(coverage): remediate testing gaps and skip hygiene"`.
