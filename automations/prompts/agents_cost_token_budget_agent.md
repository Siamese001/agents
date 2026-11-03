# Agents Repository — 8-Pillar Cost, Multi-Tier Caching, Token Budget & Provider Routing Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage IV-A (Order 6/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-REMEDIATION-QUOTA-FLOOR -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **8-Pillar Cost, Multi-Tier Caching, Token Budget, Provider Routing & Secret Hygiene Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`07:05 ET`, Order `6/7`). This agent continuously audits, benchmarks, and eliminates token waste, redundant external API spend, and credential exposure across `outreach_engine/` (`apps_lic`), `resume_engine/` + `resume_graph_engine/` (`apps_rg`), `apps_research/`, `apps_model_telemetry/`, `agents/`, `infrastructure/`, `scripts/local_llm/`, `pyproject.toml`, and `config/provider_profiles.yaml` without degrading retrieval recall, proof-carrying evidence contracts, or synthesis quality.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**:
  1. Provider profile pinning, pinned-model reassessment against latest lower-cost models (`claude-haiku-4-5-20251001`, `gemini-3.8-flash`) with explicit frontier-retention defense, reasoning effort right-sizing (via `profiles.*.model_by_section`, `judge_models`, and `selector_models` in `config/provider_profiles.yaml`, `outreach_engine/config/provider_profiles.yaml`, and `scripts/local_llm/serve_qwen_m5.py`), and dynamic Pareto cost benchmarking from `resume_graph_engine/config/models/registry.yaml`.
  2. Multi-provider prompt prefix caching (`anthropic_prompt_cache.py`, `anthropic_section_cache_payload.py` 3-breakpoint stability tiers with `1h` / `5m` TTLs, single-section prefix pre-warming before parallel fan-out, `agents/observability/prompt_cache.py` OpenAI prefix normalization, and Gemini context caching).
  3. C0 retrieval and generation semantic caching (`c02_semantic_cache_payload.py` `BGE_M3_MODEL_ID` cosine similarity `>= 0.985` + `CacheIdentity` fact-digest parity, `CacheCompatibilityJudge` G25, and `semantic_cache_persistence_quarantine.py` UWG-to-L4 chain verification).
  4. Multi-tier deterministic, persisted artifact, exact response reuse (`apps_model_telemetry/exact_response_reuse.py`), and unified 30-day cross-engine disk briefing caches (`cache_identity.py`, `briefing_cache.py`, `briefing_resolver.py`, `AppsResearchBridge`, and `MaterialTargetingBundle` frozen digest parity) for zero-provider-call replay.
  5. Surgical repair/regen token budgets and evidence-preserving optional trims (`executive_summary_token_budget.py` 95% first-pass utilization ceiling, `regen_dispatch_allowed`, `word_budget_repair.py`, `outreach_engine/config/prompt_templates/*.yaml`, and `outreach_engine/src/apps_lic/domain/repair.py` `DeterministicDraftRepairer` zero-token outreach formatting/length repair).
  6. Lane-calibrated judge retry policies, self-consistency selector pool caching, and zero-LLM post-runtime qualification (`zero_llm_qualification.py`).
  7. Closed-loop spend governors (`model_token_governor.py` 48k/300k token reservation caps, `infrastructure/live_governor.py` `LiveTokenGovernor` + `LiveTelemetryLock`, `apps_model_telemetry/pricing.py`, `apps_model_telemetry/token_budget_governor.py`, `apps_model_telemetry/token_counter.py`, `agents/context/budgeting.py`, `ResearchBoundaryPolicy` cumulative dollar limits), inline secret & model-neutral naming hygiene (`tools/lint_secrets.py`, `tools/lint_model_neutral_naming.py`), and `HITLDecisionStore` system learning (`record_execution_outcome`).
  8. Internal Antigravity IDE **Argon 4 (Medium & High reasoning)** vs. external LLM API value-add routing gate, quality non-deterioration defense, compact JSON serialization (`separators=(",", ":")`), and $\text{ROI} \ge 2.5\times$ economic efficiency gates.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), E2E functional handoffs (`agents-outreach-resume-functionality`), retrieval recall (`agents-research-retrieval-surface`), judge rubrics (`agents-evals-judge-assurance`), and pytest coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`. Zero access to external repositories or external sidecar directories.
- **Mandatory $\text{ROI} \ge 2.5\times$ Admission Gate**: Every candidate tokenomics or caching remediation must prove:
  $$\text{ROI} = \frac{\text{Expected Token Savings} \times \text{Quality Preservation Factor}}{\text{Implementation Complexity Cost}} \ge 2.5$$
- **Remediation Wave Plan & Zero-Defect Fast-Exit (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - When Phase 1.5 reports zero defects (`is_clean: true` and `lint_secrets.py` exits `0`), persist `${RUN_DIR}/audit_report.json` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_cost_token_budget/${RUN_TS}/`, run `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` to cleanly prune the 0-commit worktree (`INV-WT-EPHEMERAL-SCHEDULED`), and exit `COMPLETE`.
  - Whenever defects exist in **EITHER** `MODE: scheduled` or `MODE: interactive`, author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (and copy to `<run_dir>/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md` (`exit code 0`). In `MODE: scheduled`, stage verified fixes via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` without mutating `main`.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-cost-token-budget-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_cost_token_budget/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 8-Pillar Tokenomics & Multi-Tier Caching Audit

### Phase 1: 8-Pillar Cost, Caching & Token Budget Audit

1. **Pillar 1 — Pinned Model Reassessment Matrix, Effort Right-Sizing & Frontier Retention Defense**:
   - Audit `config/provider_profiles.yaml` (`apps_rg::provider_profiles::v1`), `resume_graph_engine/config/models/registry.yaml`, `outreach_engine/config/provider_profiles.yaml`, `apps_research/config/model_pins.py` (`provider_profile.company_brief.v1.yaml` and `judge_profile.company_brief.v1.yaml`), and `scripts/local_llm/serve_qwen_m5.py` (`config/model_catalog.json` resolution).
   - **Mandatory Pinned-Model Reassessment Rules**:
     - *Retire Legacy / Unpriced Pins*: Fail closed if any profile pins deprecated or unpriced identifiers (such as `claude-3-5-sonnet-20241022` in `outreach_engine/config/provider_profiles.yaml` `rubric_judge_panel`).
     - *Right-Size Non-Proof Selectors & Mechanical Repair*: Audit `selector_models` (`competencies_graph_pool_selector`, `employment_bullet_pool_selector`) and mechanical repair lanes (`repair.executive_voice`, `optional_advisory_taxonomy_only`). Reassign over-provisioned frontier pins (`claude-sonnet-5` at `$3.00/$15.00` per MTok) to `claude-haiku-4-5-20251001` (`$0.80/$4.00` per MTok, `73.3%` savings) or `gemini-3.8-flash` (`$0.15/$0.60` per MTok, `95.0%` savings) because candidate pool selection only emits bounded IDs from pre-validated graph nodes.
     - *Right-Size Standard-Tier Judge Effort*: Ensure `proof_judge.standard.openai_chatgpt` uses `low` or `medium` reasoning effort (or `gemini-3.8-flash`) rather than `high` effort on standard-tier checks, reserving `high` effort strictly for `proof_judge.enhanced` (`X1D`).
     - *Explicit Frontier Model Retention Defense*: Defend retaining `claude-sonnet-5` (`low` effort) and `gpt-5.6-luna` (`low` effort) on external proof-bearing primary generation (`executive_summary`, `headline`, `*_bullets`, `*_narrative`) where strict `ALLOWED_SOURCE_FACT_IDS` citation bindings and 6-sentence `SRFS_FIVE_PART_EXEC_ARCH_V1` constraints cause `3x–4x` regeneration retry cascades on smaller external models, erasing nominal per-token savings.
2. **Pillar 2 — Multi-Provider Prompt Prefix Caching (Anthropic 3-Breakpoint Tiers, Pre-Warming, OpenAI & Gemini)**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/providers/anthropic_prompt_cache.py`, `anthropic_section_cache_payload.py` (`AnthropicSectionCachePayload`, `MAX_ANTHROPIC_CACHE_MARKERS = 3`), and `agents/observability/prompt_cache.py` (`normalize_static_template`, `prefix_fingerprint`, `routing_key`, `chat_usage_metrics`).
   - Verify stability-tier prefix breakpoints: `TIER1_SLOTS = {"S0", "D0", "I0"}` marked with `1h` TTL (`CACHE_WRITE_1H_INPUT_MULTIPLIER = 2.00`, `CACHE_READ_INPUT_MULTIPLIER = 0.10`), `TIER2_SLOTS = {"C0", "E0", "Y0"}` marked with `5m` TTL (`CACHE_WRITE_5M_INPUT_MULTIPLIER = 1.25`) for `REPAIR`, `SELF_CONSISTENCY`, `SELECTOR`, and `SUITE_REPLAY` workloads, and `VOLATILE_SLOTS = {"U0", "R0", "H0", "M0"}` strictly excluded from cached prefixes.
   - Verify **single-section prefix pre-warming** before parallel section fan-out so concurrent requests hit `cache_read_input_tokens` (`0.10x` cost) rather than paying duplicate `cache_creation_input_tokens`, and verify `ProviderCacheReceipt` (`cache_hit_ratio`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `estimated_input_cost_savings_usd`) across `apps_rg`, `apps_research`, and `outreach_engine`.
3. **Pillar 3 — Generation-Bound & C0 Retrieval Semantic Caching (`c02_semantic_cache_payload` & R1B UWG Quarantine)**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/c0/c02_semantic_cache_payload.py` (`build_c02_semantic_cache_payload`, `BGE_M3_MODEL_ID` per-section intent vector + bounded 24-item `serialize_query_output` proposal) and `apps_research/engines/judges/cache_compatibility_judge.py` (`CacheCompatibilityJudge` G25).
   - Verify **dual-key semantic + fact-digest generation cache reuse** gating cross-run hits on `BAAI/bge-m3` cosine similarity `>= 0.985` AND identical `CacheIdentity` fact-set digests (`allowed_source_fact_ids`, `selected_role_fact_set`, `schema_version`) to guarantee zero hallucinated claims.
   - Audit `resume_graph_engine/src/apps_rg/runtime/semantic_cache_persistence_quarantine.py` (`assess_uwg_durable_write_chain`, `NO_DIRECT_CHROMA_ASSERTION_ARTIFACT`) ensuring C0 proposes, Exit clears, UWG commits, and L4 refreshes read surfaces without unverified shadow Chroma write claims.
4. **Pillar 4 — Multi-Tier Deterministic, Artifact & Cross-Engine Briefing Caches (Zero-Provider-Call Replay)**:
   - Audit `resume_graph_engine/src/apps_rg/cache/cache_identity.py` (`CacheIdentity` 64-hex SHA-256 fingerprint covering `resolved_model_snapshot`, `registry_digest`, `prompt_template_hash`, `generation_params`, `schema_version`, and `input_digests`, rejecting `INVALID_CACHE_VALUES = {"", "unknown", "none", "null", "undefined"}`) and `apps_model_telemetry/exact_response_reuse.py` (`ExactRequestIdentity`, `build_exact_request_identity`).
   - Audit `resume_graph_engine/src/apps_rg/cache/briefing_cache.py` (`BriefingCache` 30-day TTL in-memory + atomic `.tmp` disk persistence keyed by `compute_briefing_cache_key`), `outreach_engine/src/apps_lic/pipeline/briefing_resolver.py` (`GovernedBriefingResolver`, `MAX_CACHE_SIZE = 128`, unified 30-day atomic disk persistence shared across `apps_rg` and `outreach_engine` across `MANUAL`, `CACHE_HIT`, `PERSISTED_ARTIFACT` / `CANONICAL_FIXTURE` via `AppsResearchBridge._find_valid_persisted_artifact_bundle` and `_resolve_canonical_targeting_brief`, `WEB_RESEARCH`, `HERMETIC_FALLBACK`), and `resume_graph_engine/src/apps_rg/runtime/targeting_context_authority.py` (`MaterialTargetingBundle` frozen digest parity).
5. **Pillar 5 — Surgical Repair / Regen Token Budgets & Protected Evidence-Preserving Optional Trims**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_token_budget.py` (`TRIM_STRATEGY = "executive_summary_optional_trim_only_v2"`, `first_pass_95pct_limit_tokens`, `regen_dispatch_allowed`) and `resume_graph_engine/src/apps_rg/runtime/sections/executive_summary/word_budget_repair.py`.
   - Verify optional trims (`e0_examples`, `y0_style_preferences`, `jd_briefing_prose`, `jd_text_prose`, `c0_optional_fact_line`) never alter `PROTECTED_COMPONENT_LABELS` (`system`, `response_schema`, `evidence_law`, `allowed_source_fact_ids`, `selected_role_fact_set`, `claim_ledger_rules`) or `_SRFS_SHAPE_MARKERS` (`verify_evidence_contract_unchanged`, `verify_prompt_shape_preserved`), and execute deterministic zero-token word-budget repair before any paid LLM regeneration.
6. **Pillar 6 — Lane-Calibrated Judge Retries, Selector Pool Caching & Zero-LLM Post-Runtime Qualification**:
   - Audit `config/provider_profiles.yaml` `runtime_limits.judge.runtime_profiles` (`optional_advisory_taxonomy_only` weight 1 / `max_attempts: 1` / `low` thinking, `standard_reasoning` weight 2 / `max_attempts: 2`, `bullet_rewrite_quality` weight 2 / `max_attempts: 2`, `enhanced_reasoning` weight 3 / `max_attempts: 3`).
   - Audit `apps_research/integrations/provider_gateway.py` bounded retry classification (`_is_retryable_gemini_transport_error`, `_gemini_retry_delay_seconds`) and `resume_graph_engine/src/apps_rg/runtime/zero_llm_qualification.py` (`ZERO_COUNTER_KEYS`: `provider_calls == 0`, `judge_calls == 0`, `embedding_calls == 0`, `model_calls == 0` during post-runtime replay).
7. **Pillar 7 — Closed-Loop Spend Governor, Secret Hygiene & System Learning (`model_token_governor`, `apps_model_telemetry`, `lint_secrets` & `HITLDecisionStore`)**:
   - Audit `resume_graph_engine/src/apps_rg/runtime/model_token_governor.py` (`max_input_tokens_per_attempt: 48000`, `max_reserved_tokens_per_run: 300000`, `chars_per_token_estimate: 3`, `safety_multiplier: 1.12`), `apps_model_telemetry/pricing.py`, `apps_model_telemetry/token_budget_governor.py`, `apps_model_telemetry/token_counter.py`, and `agents/context/budgeting.py`.
   - Audit `outreach_engine/src/apps_lic/integrations/research_boundary_policy.py` (`ResearchBoundaryPolicy`: `cost_limit_usd: 1.0`, `cost_per_call_usd: 0.05`, `timeout_seconds: 30.0`, `max_retries: 2`, accounting failed live attempts in `cumulative_cost_usd` to trip `COST_LIMIT_EXCEEDED`), `tools/lint_secrets.py` + `pyproject.toml` dependency/security hygiene, and closed-loop telemetry feedback into `HITLDecisionStore` (`record_execution_outcome` in `artifacts/governance/hitl_decisions.sqlite`).
8. **Pillar 8 — Internal Antigravity Argon 4 (Medium & High Reasoning) vs. External LLM API Value-Add Gate, Compact Serialization & $\text{ROI} \ge 2.5\times$ Pareto Benchmarking**:
   - **Internal Antigravity Argon 4 Medium & High Routing Rationalization**:
     - *Elimination of Legacy External API Overhead*: External LLM API calls were originally introduced when IDEs lacked frontier reasoning and large context windows. Inside interactive Antigravity IDE sessions, **Argon 4 Medium and High reasoning** provide `>131,072`-token context windows at **`$0.00` marginal API token cost**.
     - *Non-Deterioration & Reasoning Superiority Defense*:
       1. External `claude-sonnet-5` had to be forced to `low` effort in `config/provider_profiles.yaml` because `medium`/`high` adaptive thinking consumes the `4,096`-token `max_tokens` ceiling and truncates structured JSON responses. Internal Antigravity Argon 4 Medium and High separate thinking deliberation from emitted response tokens, delivering full Medium/High reasoning depth with zero JSON truncation risk.
       2. Every Argon 4 Medium/High output is verified by the exact same fail-closed deterministic validators as external API calls: `ALLOWED_SOURCE_FACT_IDS` claim-ledger binding, `verify_evidence_contract_unchanged`, 6-sentence `SRFS_FIVE_PART_EXEC_ARCH_V1` structural validation, `sanitize_briefing_content` forbidden-term scrubbing, and the 154-file holdout rubric gates (`tools/validate_eval_rubrics.py`).
     - *Mandatory Value-Add Routing Matrix*:
       - **Route to Internal Antigravity Argon 4 High (`$0.00` marginal API cost)**: Interactive `apps_rg` primary section generation (`executive_summary`, `headline`, `*_bullets`, `*_narrative`), `apps_research` company brief synthesis, and `outreach_engine` multi-touch message generation.
       - **Route to Internal Antigravity Argon 4 Medium (`$0.00` marginal API cost)**: Advisory pool selectors (`competencies_graph_pool_selector`, `employment_bullet_pool_selector`), surgical word-budget/voice repair, and single-judge rubric evaluations.
       - **Retain Paid External LLM APIs ONLY Where Strictly Value-Added**: (a) Unattended headless CI/CLI batch pipelines executing outside an active Antigravity IDE session, and (b) Cross-family adversarial dual-provider proof judging (`X1D` requiring two independent model families to prevent self-preference bias).
   - Audit compact JSON serialization (`separators=(",", ":")`), self-consistency selector pool caching, and dynamic $\text{ROI} \ge 2.5\times$ Pareto cost-savings benchmarking derived from `resume_graph_engine/config/models/registry.yaml` pricing and `config/provider_profiles.yaml` capacities.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the deterministic 8-pillar tokenomics, model-neutrality, and secrets auditor CLIs in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/lint_model_neutral_naming.py" --all --repo-root "${WORKTREE_DIR}"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/lint_secrets.py" --all --repo-root "${WORKTREE_DIR}"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/cost_token_budget_auditor.py" --repo-root "${WORKTREE_DIR}" --output "${RUN_DIR}/audit_report.json" --json --strict
```

Write the structured 8-pillar findings and $\text{ROI} \ge 2.5\times$ benchmark calculations to `${RUN_DIR}/audit_report.json`.

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
When findings exist (`is_clean == false`), author `${WORKTREE_DIR}/plans/cost-token-budget-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
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
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_cost_token_budget/${RUN_TS}`, then stage verified fixes (or prune 0-commit runs) via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` without mutating `main`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

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
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, commit via `git -C "${WORKTREE_DIR}" commit`, then stage via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` in scheduled mode or promote after interactive `ask_question` `PR_MERGE_AUTHORIZATION` via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "perf(tokenomics): optimize caching and token budget caps"`.
