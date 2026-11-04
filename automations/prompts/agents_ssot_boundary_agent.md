# Agents Repository — SSOT & Subsystem Boundary Governance Automation Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:2.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage II (Order 2/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-REMEDIATION-QUOTA-FLOOR | INV-DEFECT-ACCOUNTING-TABLE-GATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **10-Dimension SSOT Centralization, Configuration Sprawl, Anti-Hardcoding & Subsystem Boundary Governance Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (On-Demand, Order `2/7`). This agent enforces unidirectional layer imports (`L0–L6`), strict subsystem encapsulation across all 11 executable repository roots (`agents/`, `apps_model_telemetry/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `infrastructure/`, `ops_scripts/`, `scripts/`, `tools/`), multi-folder configuration sprawl and shadow-copy elimination across root `config/`, `outreach_engine/config/`, `outreach_engine/data/`, `resume_graph_engine/config/`, `apps_research/config/`, `apps_eval/`, and all nested `pytest.ini` files (`config/governance/centralization_registry.yaml`, `tools/ssot_sprawl_scanner.py`), policy registry synchronization (`config/governance/policy_registry.yaml`), AST/prompt/eval anti-hardcoding and numeric parity (`tools/ssot_hardcoding_scanner.py`, `infrastructure/config/env_loader.py`, `resume_graph_engine/src/apps_rg/config/`), model-neutral naming and pin integrity, portable MCP/hook/boundary definitions (`.mcp.json`, `.agents/hooks.json`, `.antigravity/runtime-boundary.json`), and `AGENTS.md` / `.agents/rules/conformance-map.md` link synchronization.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Cross-subsystem import boundaries (`ssot_boundary_auditor.py`, `lint_architecture_boundaries.py`, `lint_layer_imports.py`), production purity (`lint_production_purity.py`), multi-folder config sprawl & cross-format bound parity (`ssot_sprawl_scanner.py`, `check_config_ssot_drift.py`, `lint_model_pins.py`, `lint_contract_schemas.py`, `lint_file_budgets.py`), AST/prompt/eval anti-hardcoding & centralization (`ssot_hardcoding_scanner.py`, `config/governance/centralization_registry.yaml`, `config/governance/policy_registry.yaml`), model-neutral naming (`lint_model_neutral_naming.py`), and `.mcp.json` / `.agents/` / `.antigravity/` synchronization.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), E2E runtime behavior (`agents-outreach-resume-functionality`), retrieval quality (`agents-research-retrieval-surface`), judge rubrics (`agents-evals-judge-assurance`), token cost (`agents-cost-token-budget`), and pytest coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Preflight-First Fast-Exit & Wave-Based Plan Mandate (`C03`, `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - Execute Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}`. When `0` actionable findings exist (`is_clean: true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating an ephemeral worktree or synthetic plan.
  - Whenever `>= 1` findings exist (`is_clean: false`), execute Phase 0 isolated worktree provisioning, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md"` (`exit code 0`).

---

## 3. Phase 1 & Phase 1.5: 10-Dimension Read-Only Preflight Audit & Fast-Exit Gate

### Phase 1: 10-Dimension SSOT, Centralization, Sprawl & Boundary Audit
1. **Dimension 1 — Cross-Subsystem Encapsulation**: Verify zero illegal direct imports across `agents/`, `apps_model_telemetry/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/src/`, `apps_research/`, `apps_eval/`, `infrastructure/`, and `ops_scripts/`.
2. **Dimension 2 — Unidirectional Layer Imports, File Budgets & Production Purity**: Run `lint_layer_imports.py`, `lint_architecture_boundaries.py`, `lint_production_purity.py`, and `lint_file_budgets.py`.
3. **Dimension 3 — Model-Neutral Naming, Pins & Dual-Engine Config/Data SSOT Drift (`outreach_engine` + `resume_graph_engine`)**: Run `lint_model_neutral_naming.py`, `lint_model_pins.py --strict`, `lint_contract_schemas.py`, and `check_config_ssot_drift.py --strict` across root `config/`/`data/`, `outreach_engine/config/`/`outreach_engine/data/`, and `resume_graph_engine/config/`/`resume_graph_engine/data/`.
4. **Dimension 4 — Constitutional AST Floor**: Scan all 9 packages plus `tools/` for `subprocess.*` calls missing `timeout=` and silent `except Exception: pass` without guardian comments.
5. **Dimension 5 — MCP, Hooks, Runtime Boundary & Conformance Link Sync**: Verify `.mcp.json` and `.agents/mcp_config.json` portability, `.antigravity/runtime-boundary.json` `allowedSubsystems`, `.agents/hooks.json`, and zero broken links in `AGENTS.md` / `.agents/rules/conformance-map.md`.
6. **Dimension 6 — Sidecar Separation Integrity**: Run `validate_sidecar_separation.py --repo-root "${PRIMARY_REPO_ROOT}" --json`.
7. **Dimension 7 — Multi-Folder Configuration Sprawl, Zero-Allowlist Drift & Intra-File Contradictions**: Run `ssot_sprawl_scanner.py --repo-root "${PRIMARY_REPO_ROOT}" --json` (`KNOWN_DRIFT_ALLOWLIST == frozenset()`) to detect nested shadow copies (`provider_profiles.yaml`, `pytest.ini`, `.mcp.json`), twin `.v1` profile sprawl, intra-file bound contradictions, and cross-format YAML/JSON bound drift against `config/governance/centralization_registry.yaml`.
8. **Dimension 8 — Governance Policy Registry Synchronization**: Verify every enforcer and rule referenced in `config/governance/policy_registry.yaml` dynamically resolves or enforces registered thresholds without hardcoded bypasses or unwired live hooks.
9. **Dimension 9 — Dynamic Registry Anti-Hardcoding, Guardian Rationales & Environment Centralization**: Run `ssot_hardcoding_scanner.py --repo-root "${PRIMARY_REPO_ROOT}" --json` across all 19 dynamic `domain_threshold_owners` in `config/governance/centralization_registry.yaml` to detect duplicate threshold constants, bare `# guardian:` comments missing `<category> -- <rationale>`, uncentralized `os.environ` reads, hardcoded machine paths, and unassigned `.split()` bugs.
10. **Dimension 10 — Prompt-to-Code Parity & Grandfathered Ratchet Backlog Visibility**: Verify word, sentence, and character limits embedded in prompt templates, repair builders, and judge rubrics match canonical runtime validator constants, and expose any remaining grandfathered entries in `env_lookup_ratchet.json`, `file_budgets_ratchet.json`, or physical duplicate config/data pairs via `--include-ratchet-backlog`.

### Phase 1.5: Mandatory Executable Read-Only Preflight Scanners
Execute the bounded 10-dimension boundary, sprawl, anti-hardcoding, and ratchet-backlog auditors plus scoped unit verification (`timeout <= 90s`):

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/ssot_boundary_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --include-ratchet-backlog --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/lint_contract_schemas.py" --all --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/lint_file_budgets.py" --all --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/unit/test_ssot_centralization_auditor.py" -q --timeout=60
```

If all preflight commands exit `0` (`"status": "PASS"`, `"is_clean": true`, zero ratchet backlog), fast-exit `COMPLETE` (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`). When `--include-ratchet-backlog` returns `BACKLOG_ACTION_REQUIRED` (`exit code 1`), proceed to Phase 0 and burn down at least `Q_min` grandfathered ratchet or duplicate items.

---

## 4. Phase 0: Conditional Isolated Worktree Provisioning on Findings (`Step 0.1` — `C02`)

When Phase 1.5 reports `>= 1` actionable findings (`is_clean == false`), provision a single isolated worktree, write `manifest.json` via `--write-manifest`, and switch into `${WORKTREE_DIR}`:

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-ssot-boundary-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_ssot_boundary/${RUN_TS}"
export PLAN_REL="plans/ssot-boundary-remediation-${HEX6}.md"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --consolidate-sidecar \
  --worktree-dir "${WORKTREE_DIR}" \
  --branch "${BRANCH_NAME}" \
  --write-manifest "${RUN_DIR}/manifest.json" \
  --agent-id "agents-ssot-boundary-governance" \
  --run-id "${RUN_TS}" \
  --mode "interactive" \
  --plan-path "${PLAN_REL}"
cd "${WORKTREE_DIR}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/ssot_boundary_auditor.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json || true
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential centralization-first waves:
- `## Wave 1: Configuration Sprawl Consolidation, Intra-File Schema Fixes & Centralization Registry Sync`
- `## Wave 2: Hardcoded Threshold Elimination, Prompt-to-Code Parity & Subsystem Boundary Remediation`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/ssot-boundary-remediation-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 10 dimensions.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` linter/AST violations.
   - Apply bounded boundary/SSOT centralization fixes.
   - Run `POST_MUTATION_RUN` linters and scoped single-file pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`):
     `"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${WORKTREE_DIR}/tests/test_model_neutral_naming.py" -v --timeout=60`
     `"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${WORKTREE_DIR}/tests/test_turn_gates.py" -v --timeout=60`
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record outcome in `HITLDecisionStore`.
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, and either stage overnight via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` or obtain interactive `ask_question` `PR_MERGE_AUTHORIZATION` and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(boundaries): remediate ssot and subsystem boundary drift"`.
