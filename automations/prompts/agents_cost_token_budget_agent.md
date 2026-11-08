# Agents Repository — 8-Pillar Cost, Multi-Tier Caching, Token Budget & Provider Routing Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:2.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage IV-A (Order 7/8) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **8-Pillar Cost, Multi-Tier Caching, Token Budget, Provider Routing & Local Hardware Economics Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (On-Demand, Order `7/8`). This agent audits, benchmarks, and eliminates token waste, redundant external API spend, and optimizes local offline execution across `outreach_engine/` (`apps_lic`), `resume_engine/` + `resume_graph_engine/` (`apps_rg`), `apps_research/`, `apps_model_telemetry/`, `agents/`, `infrastructure/`, `scripts/local_llm/`, `pyproject.toml`, and `config/provider_profiles.yaml` without degrading retrieval recall, proof-carrying evidence contracts, or synthesis quality.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Provider profile pinning, reasoning effort right-sizing, multi-provider prompt prefix caching, semantic caching, exact response reuse, surgical repair budgets, closed-loop spend governors, local model serving (`scripts/local_llm/serve_qwen_m5.py`), Apple Silicon hardware acceleration benchmarks (`tools/benchmark_macbook_runtime.py`), and dynamic Pareto cost optimization.
- **Delegated to peer agents**:
  - Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`),
  - Static layer imports & boundary encapsulation (`agents-ssot-boundary-governance`),
  - Core agent runtime mechanics & delegation contracts (`agents-core-runtime-orchestration`),
  - Domain business pipelines (`agents-domain-applications-pipeline`),
  - Retrieval recall & citation provenance (`agents-research-retrieval-surface`),
  - Judge rubrics & evaluation bounds (`agents-evals-judge-assurance`),
  - Test coverage floors & credential/secret hygiene (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`. Zero access to external repositories or external sidecar directories.
- **Mandatory $\text{ROI} \ge 2.5\times$ Admission Gate**: Every candidate tokenomics or caching remediation must prove:
  $$\text{ROI} = \frac{\text{Expected Token Savings} \times \text{Quality Preservation Factor}}{\text{Implementation Complexity Cost}} \ge 2.5$$
- **Preflight-First Fast-Exit & Wave-Based Plan Mandate (`C03`, `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - Execute Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}`. When zero defects exist (`is_clean: true` and `lint_secrets.py` exits `0`), exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating an ephemeral worktree or authoring a synthetic plan.
  - Whenever defects exist (`is_clean: false`), execute Phase 0 isolated worktree provisioning, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/cost-token-budget-${HEX6}.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/cost-token-budget-${HEX6}.md"` (`exit code 0`).

---

## 3. Phase 1 & Phase 1.5: 8-Pillar Read-Only Preflight Audit & Fast-Exit Gate

### Phase 1: 8-Pillar Cost, Caching & Token Budget Audit

1. **Pillar 1 — Pinned Model Reassessment Matrix, Effort Right-Sizing & Frontier Retention Defense**:
   - Audit `config/provider_profiles.yaml` (`apps_rg::provider_profiles::v1`), `resume_graph_engine/config/models/registry.yaml`, `outreach_engine/config/provider_profiles.yaml`, `apps_research/config/model_pins.py` (`provider_profile.company_brief.v1.yaml` and `judge_profile.company_brief.v1.yaml`), and `scripts/local_llm/serve_qwen_m5.py` (`config/model_catalog.json` resolution).
   - Retire legacy/unpriced pins (`claude-3-5-sonnet-20241022`), right-size non-proof selectors and mechanical repair lanes to `claude-haiku-4-5-20251001` or `gemini-3.8-flash`, right-size standard-tier judge effort to `low`/`medium` (reserving `high` for `proof_judge.enhanced`), and defend `claude-sonnet-5` / `gpt-5.6-luna` (`low` effort) on primary proof-bearing generation where citation and 6-sentence constraints prevent `3x–4x` retry cascades.
2. **Pillar 2 — Multi-Provider Prompt Prefix Caching (Anthropic 3-Breakpoint Tiers, Pre-Warming, OpenAI & Gemini)**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/providers/anthropic_prompt_cache.py`, `anthropic_section_cache_payload.py` (`MAX_ANTHROPIC_CACHE_MARKERS = 3`), and `agents/observability/prompt_cache.py`.
   - Verify `TIER1_SLOTS = {"S0", "D0", "I0"}` (`1h` TTL), `TIER2_SLOTS = {"C0", "E0", "Y0"}` (`5m` TTL), `VOLATILE_SLOTS = {"U0", "R0", "H0", "M0"}` exclusion, single-section prefix pre-warming before parallel fan-out, and `ProviderCacheReceipt` telemetry.
3. **Pillar 3 — Generation-Bound & C0 Retrieval Semantic Caching (`c02_semantic_cache_payload` & R1B UWG Quarantine)**:
   - Audit `c02_semantic_cache_payload.py` (`BAAI/bge-m3` cosine similarity `>= 0.985` + identical `CacheIdentity` fact-set digests), `CacheCompatibilityJudge` G25, and `semantic_cache_persistence_quarantine.py` (`assess_uwg_durable_write_chain`).
4. **Pillar 4 — Multi-Tier Deterministic, Artifact & Cross-Engine Briefing Caches (Zero-Provider-Call Replay)**:
   - Audit `cache_identity.py` (`INVALID_CACHE_VALUES` rejection), `exact_response_reuse.py`, `briefing_cache.py` (30-day TTL + atomic `.tmp` persistence), `briefing_resolver.py` (`GovernedBriefingResolver`), and `MaterialTargetingBundle` frozen digest parity.
5. **Pillar 5 — Surgical Repair / Regen Token Budgets & Protected Evidence-Preserving Optional Trims**:
   - Audit `executive_summary_token_budget.py` (`first_pass_95pct_limit_tokens`, `regen_dispatch_allowed`) and `word_budget_repair.py`, ensuring optional trims never mutate `PROTECTED_COMPONENT_LABELS` or `_SRFS_SHAPE_MARKERS`.
6. **Pillar 6 — Lane-Calibrated Judge Retries, Selector Pool Caching & Zero-LLM Post-Runtime Qualification**:
   - Audit `config/provider_profiles.yaml` `runtime_limits.judge.runtime_profiles` (`enhanced_reasoning.max_attempts: 3`), `provider_gateway.py` bounded retry classification, and `zero_llm_qualification.py` (`ZERO_COUNTER_KEYS`).
7. **Pillar 7 — Closed-Loop Spend Governor, Telemetry/Manifest/Reuse Live Probes, Secret Hygiene & System Learning**:
   - Audit `model_token_governor.py` (`48000` / `300000` caps), live behavioral execution of `apps_model_telemetry/telemetry_facade.py`, `run_manifest.py`, and `exact_response_reuse.py` (`tools/cost_token_budget_governor_probes.py`), `ResearchBoundaryPolicy` (`cost_limit_usd: 1.0`), `tools/lint_secrets.py`, and `HITLDecisionStore` (`record_execution_outcome`).
8. **Pillar 8 — Internal Antigravity Argon 4 (Medium & High Reasoning) vs. External LLM API Value-Add Gate, Compact Serialization & $\text{ROI} \ge 2.5\times$ Pareto Benchmarking**:
   - Verify interactive sessions route primary generation to **Argon 4 High** (`$0.00` marginal API cost, full thinking separation without JSON truncation) and advisory selectors/repairs to **Argon 4 Medium**, retaining paid external APIs strictly for headless batch runs and cross-family adversarial dual-provider proof judging (`X1D`), alongside compact JSON serialization (`separators=(",", ":")`) and $\text{ROI} \ge 2.5\times$ Pareto benchmarking.

### Phase 1.5: Mandatory Executable Read-Only Preflight Scanners
Execute the deterministic 8-pillar tokenomics, model-neutrality, and secrets auditor CLIs (`timeout <= 90s`):

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/lint_model_neutral_naming.py" --all --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/lint_secrets.py" --all --repo-root "${PRIMARY_REPO_ROOT}"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/cost_token_budget_auditor.py" --repo-root "${PRIMARY_REPO_ROOT}" --json --strict
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/unit/test_evals_and_budget_full_parity.py" "${PRIMARY_REPO_ROOT}/outreach_engine/tests/test_research_cost_optimization.py" -q --timeout=60
```

If all preflight commands exit `0` (`"status": "PASS"`, `"is_clean": true`), fast-exit `COMPLETE` (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

---

## 4. Phase 0: Conditional Isolated Worktree Provisioning on Findings (`Step 0.1` — `C02`)

When Phase 1.5 reports `>= 1` actionable findings (`is_clean == false`), provision an isolated worktree, write `manifest.json` via `--write-manifest`, and switch into `${WORKTREE_DIR}`:

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-cost-token-budget-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_cost_token_budget/${RUN_TS}"
export PLAN_REL="plans/cost-token-budget-${HEX6}.md"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --consolidate-sidecar \
  --worktree-dir "${WORKTREE_DIR}" \
  --branch "${BRANCH_NAME}" \
  --write-manifest "${RUN_DIR}/manifest.json" \
  --agent-id "agents-cost-token-budget" \
  --run-id "${RUN_TS}" \
  --mode "interactive" \
  --plan-path "${PLAN_REL}"
cd "${WORKTREE_DIR}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/cost_token_budget_auditor.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json --strict || true
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/cost-token-budget-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Provider Profile Conformance, Pinned Model Right-Sizing & Internal Argon 4 Routing`
- `## Wave 2: Prompt Prefix Pre-Warming, Semantic Fact-Digest Caching & Unified 30-Day Briefing Persistence`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/cost-token-budget-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/cost-token-budget-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 8 tokenomics and caching pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` 8-pillar tokenomics / caching metric before edit (`"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/cost_token_budget_auditor.py" --repo-root "${WORKTREE_DIR}" --json`).
   - Apply bounded tokenomics or caching remediation with $\text{ROI} \ge 2.5\times$.
   - Run `POST_MUTATION_RUN` `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/cost_token_budget_auditor.py" --repo-root "${WORKTREE_DIR}" --json --strict`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/lint_model_neutral_naming.py" --all --repo-root "${WORKTREE_DIR}"`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/lint_secrets.py" --all --repo-root "${WORKTREE_DIR}"`, and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome via `HITLDecisionStore.record_execution_outcome`.
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, and either stage overnight via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` or obtain interactive `ask_question` `PR_MERGE_AUTHORIZATION` and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "perf(tokenomics): optimize caching and token budget caps"`.
