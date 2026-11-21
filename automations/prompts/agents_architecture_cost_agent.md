# Agents Repository — Architecture, SSOT Boundaries, Caching & Tokenomics Agent (`1/4`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:3.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Order: 1/4 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective, Playbook & MECE Write Scope (`C01`, `C13`)
Execute a fail-closed **Architecture Boundaries, SSOT Centralization, Multi-Tier Caching, Model Pinning & Token Budget Audit & Remediation** exclusively within `/Users/amitayer/Git/agents`.
- **Canonical Skills**: Load `.agents/skills/agents-governance-hygiene/SKILL.md` and `.agents/skills/scope-containment/SKILL.md` for pillar checklists.
- **MECE Single-Writer Scope (`AGY_SIDECAR_AGENT_ID="agents-architecture-cost-governance"`)**: `config/governance/`, `config/schemas/`, `config/structure_blueprint/`, `config/provider_profiles.yaml`, `config/model_catalog.json`, `config/token_budget.yaml`, `config/runtime_budget_policy.yaml`, `outreach_engine/config/provider_profiles.yaml`, `resume_graph_engine/config/models/`, `resume_graph_engine/src/apps_rg/cache/`, `apps_model_telemetry/`, `infrastructure/`, `scripts/local_llm/`, `.mcp.json`, `pyproject.toml`, `AGENTS.md`, `.agents/`, `.antigravity/`, `.githooks/`, `pytest.ini`, `outreach_engine/pytest.ini`, `resume_graph_engine/pytest.ini`, `tools/ssot_boundary_auditor.py`, `tools/ssot_sprawl_scanner.py`, `tools/ssot_hardcoding_scanner.py`, `tools/cost_token_budget_auditor.py`, `tools/cost_token_budget_governor_probes.py`, `tools/lint_model_pins.py`, `tools/lint_model_neutral_naming.py`, `tools/lint_architecture_boundaries.py`, `tools/lint_layer_imports.py`, `tools/lint_contract_schemas.py`, `tools/validate_sidecar_separation.py`, `tools/prompt_scope_isolation.py`, and `automations/prompts/_shared_governance_contract.md`.

## 2. Phase 1 & Phase 1.5: Read-Only Preflight Audit & Fast-Exit Gate (`C02`, `C03`)
Audit all 10-Dimension SSOT/boundary invariants (`centralization_registry.yaml`, `ssot_sprawl_scanner.py`, `ssot_hardcoding_scanner.py`) and all 8 caching/tokenomics pillars ($\text{ROI} \ge 2.5\times$ gate) in read-only mode first:
```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export PYTHONDONTWRITEBYTECODE=1
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/ssot_boundary_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --include-ratchet-backlog --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/cost_token_budget_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --json --strict
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/lint_contract_schemas.py" --all --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/lint_secrets.py" --all --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/unit/test_ssot_centralization_auditor.py" "${PRIMARY_REPO_ROOT}/tests/unit/test_evals_and_budget_full_parity.py" -q -p no:cacheprovider --timeout=60
```
If all preflight gates exit `0` (`is_clean == true`), fast-exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

## 3. Phase 0, Phase 2 & Phase 3: Conditional Worktree, Wave Plan & 5-Point Promotion (`C02–C12`)
1. **Phase 0 (`Step 0.1`)**: On active findings (`is_clean == false`), export `AGY_SIDECAR_AGENT_ID="agents-architecture-cost-governance"` and `AGENT_SLUG="architecture-cost"` (`RUN_DIR` appending `${RUN_TS}-${HEX6}`), invoke `prune_merged_chat_worktrees.py --consolidate-sidecar --write-manifest "${RUN_DIR}/manifest.json"`, and `cd "${WORKTREE_DIR}"` per `automations/prompts/_shared_governance_contract.md`.
2. **Phase 2**: Author `${WORKTREE_DIR}/plans/architecture-cost-${HEX6}.md`, validate via `validate_implementation_plan.py`, render the **Dimension Findings Table**, query `HITLDecisionStore`, and surface one atomic `<= 115` char `ask_question` if $\Delta \le 0.20$.
3. **Phase 3**: Execute sequential waves with 5-Point Counterfactual Runtime Proofs (`INV-RUNTIME-PROOF-5POINT`), record outcomes in `HITLDecisionStore`, pass `validate_sidecar_separation.py --json`, `validate_turn_gates.py --mode all`, and `verify_commit.py`, obtain `PR_MERGE_AUTHORIZATION`, and promote via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(governance): remediate architecture boundaries and token budgets"`.
