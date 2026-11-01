# Agents Repository — 8-Pillar Cost, Multi-Tier Caching, Token Budget & Provider Routing Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage IV-A (Order 6/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **8-Pillar Cost, Multi-Tier Caching, Token Budget, and Provider Routing Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`06:45 ET`, Order `6/7`). This agent continuously audits, benchmarks, and eliminates token waste across `outreach_engine/` (`apps_lic`), `resume_engine/` + `resume_graph_engine/` (`apps_rg`), `apps_research/`, `infrastructure/`, and `config/provider_profiles.yaml` without degrading retrieval recall, proof-carrying evidence contracts, or synthesis quality.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**:
  1. Provider profile pinning, reasoning effort right-sizing (`claude-sonnet-5`, `gpt-5.6-luna`, `gemini-3.8-flash`), and Pareto cost benchmarking.
  2. Multi-provider prompt prefix caching (`anthropic_prompt_cache.py`, `anthropic_section_cache_payload.py` 3-breakpoint stability tiers with `1h` / `5m` TTLs, OpenAI prefix caching, and Gemini context caching).
  3. C0 retrieval and generation semantic caching (`c02_semantic_cache_payload.py`, `CacheCompatibilityJudge` G25, and `semantic_cache_persistence_quarantine.py` UWG-to-L4 chain verification).
  4. Multi-tier deterministic, persisted artifact, and cross-engine briefing caches (`CacheIdentity`, `BriefingCache`, `GovernedBriefingResolver`, `AppsResearchBridge`, and `MaterialTargetingBundle` frozen digest parity) for zero-provider-call replay.
  5. Surgical repair/regen token budgets and evidence-preserving optional trims (`executive_summary_token_budget.py` 95% first-pass utilization ceiling, `regen_dispatch_allowed`, and `word_budget_repair.py`).
  6. Lane-calibrated judge retry policies, self-consistency selector pool caching, and zero-LLM post-runtime qualification (`zero_llm_qualification.py`).
  7. Closed-loop spend governors (`model_token_governor.py` 48k/300k token reservation caps, `ResearchBoundaryPolicy` cumulative dollar limits) and `HITLDecisionStore` system learning.
  8. Frontier lab thought leadership, compact JSON serialization (`separators=(",", ":")`), and $\text{ROI} \ge 2.5\times$ economic efficiency gates.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), E2E functional handoffs (`agents-outreach-resume-functionality`), retrieval recall (`agents-research-retrieval-surface`), judge rubrics (`agents-evals-judge-assurance`), and pytest coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`. Zero access to external repositories or external sidecar directories.
- **Mandatory $\text{ROI} \ge 2.5\times$ Admission Gate**: Every candidate tokenomics or caching remediation must prove:
  $$\text{ROI} = \frac{\text{Expected Token Savings} \times \text{Quality Preservation Factor}}{\text{Implementation Complexity Cost}} \ge 2.5$$
- **Unconditional Wave-Based Plan Mandate (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - In **BOTH** `MODE: scheduled` and `MODE: interactive`, this agent MUST author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (and copy to `<run_dir>/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `python3 tools/validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md` (`exit code 0`).
  - In `MODE: scheduled`, copy durable artifacts to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_cost_token_budget/<run_id>/`, prune the ephemeral worktree (`INV-WT-EPHEMERAL-SCHEDULED`), and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED` with zero code mutations.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-cost-token-budget-${RUN_TS}"
export BRANCH_NAME="automation/${BRANCH_SLUG}"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${BRANCH_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_cost_token_budget/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
python3 "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 8-Pillar Tokenomics & Multi-Tier Caching Audit

### Phase 1: 8-Pillar Cost, Caching & Token Budget Audit

1. **Pillar 1 — Provider Profile Pinning, Effort Right-Sizing & Pareto Benchmarking**:
   - Audit `config/provider_profiles.yaml` (`apps_rg::provider_profiles::v1`), `apps_research/config/model_pins.py` (`provider_profile.company_brief.v1.yaml` and `judge_profile.company_brief.v1.yaml`), and `outreach_engine/` model registry SSOT.
   - Verify all generation lanes (`claude-sonnet-5`, `gpt-5.6-luna`), advisory pool selectors (`competencies_graph_pool_selector`, `employment_bullet_pool_selector`), and proof judges (`gemini-3.8-flash`, `gpt-5.6-luna`) enforce explicit `effort_by_section` / `reasoning_effort` (`low` for compact schema-bound generation so adaptive reasoning never exhausts the 4,096-token output ceiling) with zero hardcoded model literals.
2. **Pillar 2 — Multi-Provider Prompt Prefix Caching (Anthropic 3-Breakpoint Tiers, OpenAI & Gemini)**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/providers/anthropic_prompt_cache.py` and `anthropic_section_cache_payload.py` (`AnthropicSectionCachePayload`, `MAX_ANTHROPIC_CACHE_MARKERS = 3`).
   - Verify stability-tier prefix breakpoints: `TIER1_SLOTS = {"S0", "D0", "I0"}` marked with `1h` TTL (`CACHE_WRITE_1H_INPUT_MULTIPLIER = 2.00`, `CACHE_READ_INPUT_MULTIPLIER = 0.10`), `TIER2_SLOTS = {"C0", "E0", "Y0"}` marked with `5m` TTL (`CACHE_WRITE_5M_INPUT_MULTIPLIER = 1.25`) for `REPAIR`, `SELF_CONSISTENCY`, `SELECTOR`, and `SUITE_REPLAY` workloads, and `VOLATILE_SLOTS = {"U0", "R0", "H0", "M0"}` strictly excluded from cached prefixes.
   - Verify `ProviderCacheReceipt` (`cache_hit_ratio`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `estimated_input_cost_savings_usd`) and static-first prompt ordering across `apps_research` and `outreach_engine`.
3. **Pillar 3 — Generation-Bound & C0 Retrieval Semantic Caching (`c02_semantic_cache_payload` & R1B UWG Quarantine)**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/c0/c02_semantic_cache_payload.py` (`build_c02_semantic_cache_payload`, `BGE_M3_MODEL_ID` per-section intent vector + bounded 24-item `serialize_query_output` proposal) and `apps_research/engines/judges/cache_compatibility_judge.py` (`CacheCompatibilityJudge` G25).
   - Audit `resume_graph_engine/src/apps_rg/runtime/semantic_cache_persistence_quarantine.py` (`assess_uwg_durable_write_chain`, `NO_DIRECT_CHROMA_ASSERTION_ARTIFACT`) ensuring C0 proposes, Exit clears, UWG commits, and L4 refreshes read surfaces without unverified shadow Chroma write claims.
4. **Pillar 4 — Multi-Tier Deterministic, Artifact & Cross-Engine Briefing Caches (Zero-Provider-Call Replay)**:
   - Audit `resume_graph_engine/src/apps_rg/cache/cache_identity.py` (`CacheIdentity` 64-hex SHA-256 fingerprint covering `resolved_model_snapshot`, `registry_digest`, `prompt_template_hash`, `generation_params`, `schema_version`, and `input_digests`, rejecting `INVALID_CACHE_VALUES = {"", "unknown", "none", "null", "undefined"}`).
   - Audit `resume_graph_engine/src/apps_rg/cache/briefing_cache.py` (`BriefingCache` 30-day TTL in-memory + atomic `.tmp` disk persistence keyed by `compute_briefing_cache_key`), `outreach_engine/src/apps_lic/pipeline/briefing_resolver.py` (`GovernedBriefingResolver`, `MAX_CACHE_SIZE = 128`, 7-day TTL across 4 paths: `MANUAL`, `CACHE_HIT`, `PERSISTED_ARTIFACT` / `CANONICAL_FIXTURE` via `AppsResearchBridge._find_valid_persisted_artifact_bundle` and `_resolve_canonical_targeting_brief`, `WEB_RESEARCH`, `HERMETIC_FALLBACK`), and `resume_graph_engine/src/apps_rg/runtime/targeting_context_authority.py` (`MaterialTargetingBundle` frozen digest parity).
5. **Pillar 5 — Surgical Repair / Regen Token Budgets & Protected Evidence-Preserving Optional Trims**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_token_budget.py` (`TRIM_STRATEGY = "executive_summary_optional_trim_only_v2"`, `first_pass_95pct_limit_tokens`, `regen_dispatch_allowed`) and `resume_graph_engine/src/apps_rg/runtime/sections/executive_summary/word_budget_repair.py`.
   - Verify optional trims (`e0_examples`, `y0_style_preferences`, `jd_briefing_prose`, `jd_text_prose`, `c0_optional_fact_line`) never alter `PROTECTED_COMPONENT_LABELS` (`system`, `response_schema`, `evidence_law`, `allowed_source_fact_ids`, `selected_role_fact_set`, `claim_ledger_rules`) or `_SRFS_SHAPE_MARKERS` (`verify_evidence_contract_unchanged`, `verify_prompt_shape_preserved`), and execute deterministic word-budget repair before paid LLM regeneration.
6. **Pillar 6 — Lane-Calibrated Judge Retries, Selector Pool Caching & Zero-LLM Post-Runtime Qualification**:
   - Audit `config/provider_profiles.yaml` `runtime_limits.judge.runtime_profiles` (`optional_advisory_taxonomy_only` weight 1 / `max_attempts: 1` / `low` thinking, `standard_reasoning` weight 2 / `max_attempts: 2`, `bullet_rewrite_quality` weight 2 / `max_attempts: 2`, `enhanced_reasoning` weight 3 / `max_attempts: 3`).
   - Audit `apps_research/integrations/provider_gateway.py` bounded retry classification (`_is_retryable_gemini_transport_error`, `_gemini_retry_delay_seconds`) and `resume_graph_engine/src/apps_rg/runtime/zero_llm_qualification.py` (`ZERO_COUNTER_KEYS`: `provider_calls == 0`, `judge_calls == 0`, `embedding_calls == 0`, `model_calls == 0` during post-runtime replay).
7. **Pillar 7 — Closed-Loop Spend Governor & System Learning (`model_token_governor`, `ResearchBoundaryPolicy` & `HITLDecisionStore`)**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/model_token_governor.py` (`max_input_tokens_per_attempt: 48000`, `max_reserved_tokens_per_run: 300000`, `chars_per_token_estimate: 3`, `safety_multiplier: 1.12`).
   - Audit `outreach_engine/src/apps_lic/integrations/research_boundary_policy.py` (`ResearchBoundaryPolicy`: `cost_limit_usd: 1.0`, `cost_per_call_usd: 0.05`, `timeout_seconds: 30.0`, `max_retries: 2`, accounting failed live attempts in `cumulative_cost_usd` to trip `COST_LIMIT_EXCEEDED`) and closed-loop telemetry feedback into `HITLDecisionStore` (`artifacts/governance/hitl_decisions.sqlite`).
8. **Pillar 8 — Frontier Thought Leadership, Compact Serialization & $\text{ROI} \ge 2.5\times$ Pareto Benchmarking**:
   - Audit compact JSON serialization (`separators=(",", ":")`), self-consistency selector pool caching, and quantitative $\text{ROI} \ge 2.5\times$ Pareto cost-savings benchmarking across cached vs uncached multi-section and multi-recipient runs.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the deterministic 8-pillar tokenomics and caching auditor CLI in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
python3 tools/lint_model_neutral_naming.py
python3 tools/cost_token_budget_auditor.py --repo-root "${WORKTREE_DIR}" --output "${RUN_DIR}/audit_report.json" --json --strict
```

Write the structured 8-pillar findings and $\text{ROI} \ge 2.5\times$ benchmark calculations to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/cost-token-budget-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Provider Profile Conformance, Multi-Tier Caching & Token Governor Caps`
- `## Wave 2: Prompt Prefix Breakpoint Tiers, Briefing Cache Reuse & Surgical Regen Budgets`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`), plus `## Wave Implementation & Completion Status Table`.
Validate immediately:
```bash
python3 tools/validate_implementation_plan.py --file "plans/cost-token-budget-${HEX6}.md"
cp "plans/cost-token-budget-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 8 tokenomics and caching pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_cost_token_budget/${RUN_TS}`, prune `${WORKTREE_DIR}` and `${BRANCH_NAME}`, and exit `COMPLETE` or `OPERATOR_INPUT_REQUIRED`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`) in `MODE: interactive`:
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` 8-pillar tokenomics / caching metric before edit (`python3 tools/cost_token_budget_auditor.py --json`).
   - Apply bounded tokenomics or caching remediation with $\text{ROI} \ge 2.5\times$.
   - Run `POST_MUTATION_RUN` `python3 tools/cost_token_budget_auditor.py --json --strict`, `python3 tools/lint_model_neutral_naming.py`, and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore`.
3. **Turn & Commit Gates (`C09`, `C10`)**:
   Run `python3 tools/validate_sidecar_separation.py --json`, `python3 tools/validate_turn_gates.py --mode all`, and `python3 tools/verify_commit.py`, then commit, rebase onto `main`, merge `--no-ff` into `/Users/amitayer/Git/agents` (`main`), and remove `${WORKTREE_DIR}` and `${BRANCH_NAME}`.
