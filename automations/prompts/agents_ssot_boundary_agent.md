# Agents Repository — SSOT & Subsystem Boundary Governance Automation Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage II (Order 2/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **SSOT Conformance & Subsystem Boundary Governance Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`05:25 ET`, Order `2/7`). This agent enforces unidirectional layer imports (`L0–L6`), strict subsystem encapsulation across all 9 repository packages (`agents/`, `apps_model_telemetry/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/src/`, `apps_research/`, `apps_eval/`, `infrastructure/`, `ops_scripts/`), config/data SSOT drift (`config/` vs `resume_graph_engine/config/`), model-neutral naming and pin integrity, portable MCP/hook/boundary definitions (`.mcp.json`, `.agents/hooks.json`, `.antigravity/runtime-boundary.json`), and `AGENTS.md` / `.agents/rules/conformance-map.md` link synchronization.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Cross-subsystem import boundaries (`ssot_boundary_auditor.py`, `lint_architecture_boundaries.py`, `lint_layer_imports.py`), production purity (`lint_production_purity.py`), config/schema/pin SSOT (`check_config_ssot_drift.py`, `lint_model_pins.py`, `lint_contract_schemas.py`, `lint_file_budgets.py`), model-neutral naming (`lint_model_neutral_naming.py`), and `.mcp.json` / `.agents/` / `.antigravity/` synchronization.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), E2E runtime behavior (`agents-outreach-resume-functionality`), retrieval quality (`agents-research-retrieval-surface`), judge rubrics (`agents-evals-judge-assurance`), token cost (`agents-cost-token-budget`), and pytest coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Zero-Defect Fast-Exit & Wave-Based Plan Mandate (`C03`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - When Phase 1.5 reports `0` actionable findings (`is_clean: true`), fast-exit cleanly per `C03`: copy `${RUN_DIR}` to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_ssot_boundary/${RUN_TS}`, tear down the ephemeral worktree via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only`, and exit `COMPLETE` without authoring a synthetic plan.
  - Whenever `>= 1` findings exist in **EITHER** `MODE: scheduled` or `MODE: interactive`, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md"` (`exit code 0`).
  - In `MODE: scheduled`, stage validated fixes on `${BRANCH_NAME}` via `pr_governance.py submit "${BRANCH_NAME}" --stage-only` without mutating `local main` directly.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-ssot-boundary-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_ssot_boundary/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 6-Dimension Read-Only Audit & Executable Forensic Scanners

### Phase 1: 6-Dimension SSOT & Boundary Audit
1. **Dimension 1 — Cross-Subsystem Encapsulation**: Verify zero illegal direct imports across `agents/`, `apps_model_telemetry/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/src/`, `apps_research/`, `apps_eval/`, `infrastructure/`, and `ops_scripts/`.
2. **Dimension 2 — Unidirectional Layer Imports, File Budgets & Production Purity**: Run `lint_layer_imports.py`, `lint_architecture_boundaries.py`, `lint_production_purity.py`, and `lint_file_budgets.py`.
3. **Dimension 3 — Model-Neutral Naming, Pins & Config SSOT Drift**: Run `lint_model_neutral_naming.py`, `lint_model_pins.py --strict`, `lint_contract_schemas.py`, and `check_config_ssot_drift.py --strict` across all config and data surfaces.
4. **Dimension 4 — Constitutional AST Floor**: Scan all 9 packages plus `tools/` for `subprocess.*` calls missing `timeout=` and silent `except Exception: pass` without guardian comments.
5. **Dimension 5 — MCP, Hooks, Runtime Boundary & Conformance Link Sync**: Verify `.mcp.json` and `.agents/mcp_config.json` portability, `.antigravity/runtime-boundary.json` `allowedSubsystems`, `.agents/hooks.json`, and zero broken links in `AGENTS.md` / `.agents/rules/conformance-map.md`.
6. **Dimension 6 — Sidecar Separation Integrity**: Run `validate_sidecar_separation.py --repo-root "${WORKTREE_DIR}" --json`.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the bounded 6-dimension boundary and SSOT auditor in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/ssot_boundary_auditor.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/lint_contract_schemas.py" --all --repo-root "${WORKTREE_DIR}"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/lint_file_budgets.py" --all --repo-root "${WORKTREE_DIR}"
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
When findings exist (`is_clean == false`), author `${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Subsystem Boundary, Layer Import & Timeout Remediation`
- `## Wave 2: Model Registry, Config Drift & Conformance Map Sync`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 6 dimensions.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_ssot_boundary/${RUN_TS}`, then stage verified fixes (or prune 0-commit runs) via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` without mutating `main`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` linter/AST violations.
   - Apply bounded boundary/SSOT fixes.
   - Run `POST_MUTATION_RUN` linters and scoped single-file pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`):
     `"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${WORKTREE_DIR}/tests/test_model_neutral_naming.py" -v --timeout=60`
     `"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${WORKTREE_DIR}/tests/test_turn_gates.py" -v --timeout=60`
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record outcome in `HITLDecisionStore`.
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, then stage via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` in scheduled mode or promote after interactive `ask_question` `PR_MERGE_AUTHORIZATION` via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(boundaries): remediate ssot and subsystem boundary drift"`.
