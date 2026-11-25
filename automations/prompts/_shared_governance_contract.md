# Agents Repository — Consolidated On-Demand Assurance Shared Governance Contract (`C01–C14`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:3.0.0 | v3.2.0 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-PARALLEL-AGENT-MECE-ISOLATION | INV-FULL-REPO-STAGE-COVERAGE -->

## 1. Repository Isolation & On-Demand Execution Invariant (`INV-REPO-SEPARATION-AGENTS-ONLY`)

1. **Workspace Containment**: All 7 `agents-*` on-demand assurance workflows are bound exclusively to `/Users/amitayer/Git/agents` and its isolated remediation worktrees under `/Users/amitayer/Git/agents/.worktrees/*`.
2. **Zero Cross-Repository Mutation**: Assurance agents in this repository are strictly forbidden from reading, modifying, locking, or writing to any file, database, worktree, or sidecar configuration belonging to external repositories.
3. **Preflight-First Artifact Isolation**: Phase 1 & Phase 1.5 read-only behavioral preflight checks execute without mutating tracked repository files. Whenever actionable findings exist (`B_total > 0`), all remediation runtime artifacts, manifests, plans, and receipts must be written exclusively inside `<WORKTREE_DIR>/artifacts/sidecar_runs/<agent_slug>/<run_id>/` and `<WORKTREE_DIR>/plans/<branch-slug>-<6hex>.md`.
4. **Zero Daily Background Schedules (`CATALOG_DISABLED_BY_DEFAULT`)**: Unattended daily `agents-*` background schedules are disabled by default (`"enabled": false`, `agents_scheduled_count == 0`). All 7 consolidated `agents-*` workflows are mirrored in `/Users/amitayer/.gemini/config/sidecars/` and `/Users/amitayer/.gemini/config/config.json` as on-demand manual launchers (`"enabled": false` on initial creation while preserving operator-toggled booleans, bound dynamically to the live `~/.gemini/config/projects/*.json` UUID for `/Users/amitayer/Git/agents` with `access_grants: ["command(.venv/bin/python)", "command(git)", "command(agy)"]`) and thin SSOT pointer prompts targeting `file:///Users/amitayer/Git/agents/automations/prompts/agents_*_agent.md`. Static hygiene and test/mock checks execute automatically via `.githooks/{pre-commit,post-merge}`, `tools/verify_commit.py`, and `tools/verify_main_readiness.py` Stage 10.

---

## 2. Master 7-Agent Causal Execution Sequence & Automated Gate Split

| Order | Stage | Workflow ID | Consolidated Skill | Deterministic Auditor(s) | Canonical Thin Prompt |
| :---: | :---: | :--- | :--- | :--- | :--- |
| **1/7** | **Stage I (Architecture, Storage & Cost)** | `agents-architecture-cost-governance` | `agents-governance-hygiene` / `scope-containment` | `tools/ssot_boundary_auditor.py`, `tools/cost_token_budget_auditor.py`, `tools/audit_governance_harmonization.py`, `tools/zero_bugfix_constraint_gate.py`, `tools/storage_worktree_hygiene.py` | `automations/prompts/agents_architecture_cost_agent.md` |
| **2/7** | **Stage II (Core Runtime & Transport)** | `agents-core-runtime-orchestration` | `agent-runtime-engineering` / `agent-subagent-orchestration` | `tools/agent_runtime_auditor.py` | `automations/prompts/agents_core_runtime_orchestration_agent.md` |
| **3/7** | **Stage III (Candidate Graph & QRELS)** | `agents-graph-retrieval-qrels-assurance` | `agents-domain-assurance` | `tools/retrieval_surface_auditor.py`, `tools/audit_graph_hygiene_and_consolidation.py`, `tools/audit_qrels_coverage.py`, `tools/audit_resume_fact_provenance.py`, `tools/verify_graph_integrity_and_embeddings.py` | `automations/prompts/agents_graph_retrieval_qrels_agent.md` |
| **4/7** | **Stage IV (Domain Synthesis Pipelines)** | `agents-domain-synthesis-pipelines` | `agents-domain-assurance` | `tools/e2e_functionality_auditor.py`, `tools/lint_prompt_validator_vocab_symmetry.py`, `tools/lint_apps_rg_domain_literals.py`, `tools/lint_no_jd_overfitting.py` | `automations/prompts/agents_domain_synthesis_pipelines_agent.md` |
| **5/7** | **Stage V (Evals, Judges & Flywheel)** | `agents-evals-flywheel-assurance` | `receipt-auditor` / `agents-domain-assurance` | `tools/validate_eval_rubrics.py`, `tools/run_eval_flywheel_cycle.py`, `tools/audit_eval_construct_validity.py`, `tools/verify_fix_eval_pinning.py`, `tools/testing_gaps_auditor.py` | `automations/prompts/agents_evals_flywheel_assurance_agent.md` |
| **6/7** | **Stage VI (Research Intelligence & Airlocks)** | `agents-research-intelligence-handoff` | `agents-domain-assurance` | `tools/apps_research_auditor.py` | `automations/prompts/agents_research_intelligence_handoff_agent.md` |
| **7/7** | **Stage VII (Live Canary, MCP & Release Gate)** | `agents-live-canary-release-certification` | `receipt-auditor` / `agents-domain-assurance` | `tools/live_canary_release_auditor.py`, `tools/verify_graph_explorer_gate.py`, `tools/verify_release_gate.py` | `automations/prompts/agents_live_canary_release_certification_agent.md` |

- **Retired to Automated Git & Readiness Gates**:
  - *Storage & Worktree Hygiene*: `.githooks/post-merge` + `tools/storage_worktree_hygiene.py --post-merge-quick` (full 6-pillar check enforced in Stage I preflight and `agents-governance-hygiene` skill).
  - *Testing Gaps & Mock Reachability*: Tier 1 `tools/verify_commit.py` (staged AST mock reachability, skip/xfail, zero-assertion tests) + Tier 2 `tools/verify_main_readiness.py` Stage 10 + Stage V `--include-uncovered-backlog` (`tools/testing_gaps_auditor.py`).

---

## 3. Common Control Matrix & Shared Phase Templates (`C01–C14`)

- **`C01` — Trusted Launch & Multi-Extension Search (`INV-FULL-EXTENSION-SSOT-SEARCH`)**: Search `.md`, `.mdc`, `.txt`, `.jinja`, `.j2`, `.csv`, `.jsonl`, `.toml`, `.ini`, `.cfg`, `.sql`, `.yaml`, `.yml`, `.json`, `.py`, `.sh`, and `.ps1` across the repository. Always invoke pytest via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" -m pytest` (never bare system `python3` or ungranted `.venv/bin/pytest`).
- **`C02` — Preflight-First Ordering & Conditional Phase 0 Single-Worktree Provisioning (`Step 0.1`)**:
  Execute Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}` (`PYTHONDONTWRITEBYTECODE=1`, pytest `-p no:cacheprovider`). Only when `B_total > 0` (`is_clean == false`), provision an isolated worktree via `--consolidate-sidecar` and `--write-manifest` and `cd "${WORKTREE_DIR}"`:
  ```bash
  export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
  export PYTHONDONTWRITEBYTECODE=1
  export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  export HEX6="$("${PRIMARY_REPO_ROOT}/.venv/bin/python" -c 'import secrets; print(secrets.token_hex(3))')"
  export BRANCH_NAME="chore/${AGENT_SLUG}-${RUN_TS}-${HEX6}"
  export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/$(echo "${BRANCH_NAME}" | tr '/-' '__')"
  export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/${AGENT_SLUG}/${RUN_TS}-${HEX6}"
  export PLAN_REL="plans/${AGENT_SLUG}-${HEX6}.md"
  "${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" \
    --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" \
    --branch "${BRANCH_NAME}" --write-manifest "${RUN_DIR}/manifest.json" \
    --agent-id "${AGY_SIDECAR_AGENT_ID}" --run-id "${RUN_TS}" --mode "interactive" --plan-path "${PLAN_REL}"
  cd "${WORKTREE_DIR}" && mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
  ```
- **`C03` — Zero-Churn Fast-Exit (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`)**: When Phase 1.5 reports `B_total == 0` (`is_clean == true`) with zero unsealed calibration states (`AWAITING_HUMAN_ADJUDICATION`), zero pending flywheel HITL items (`pending_hitl_count == 0`), and non-vacuous behavioral checks (`contracts_checked > 0` / verified routes), exit `COMPLETE` immediately without creating a worktree or synthetic plan.
- **`C04` — Unconditional Wave Plan & Full Root-Cause Closure (`UNCONDITIONAL_WAVE_PLAN_MANDATE`, `INV-REMEDIATION-QUOTA-FLOOR`, `INV-DEFECT-ACCOUNTING-TABLE-GATE`)**: On active defects, author `${WORKTREE_DIR}/${PLAN_REL}` validated via `validate_implementation_plan.py`, close **100% (`Q_min = B_total`)** of owned deterministic root-cause defects (never stopping at a partial `2%` cap; deferring only items blocked by explicit human HITL rejection/snooze or unsealed human labeling), and render the 7-column Before/After Defect Accounting Table.
- **`C05` — Pre-HITL Dimension Findings Table & Compact `<= 115` Char HITL Gate**: Render the **Dimension Findings Table**, score options via `tools/hitl_governance.py` (`HITLDecisionStore`), and surface one atomic `ask_question` (`<= 115` chars per option with front-loaded confidence `(Recommended) HIGH 85%: ...`) when $\Delta \le 0.20$.
- **`C06`–`C12` — 5-Point Counterfactual Proof (`INV-RUNTIME-PROOF-5POINT`), Persistent Learning (`INV-AUTOMATION-PERSISTENT-LEARNING-LOOP`), Constitutional Floor, Turn/Commit Gates, Post-Merge Teardown (`INV-POST-MERGE-WORKTREE-TEARDOWN`) & Top Closeout Table (`INV-WAVE-MERGE-WORKTREE-CLOSEOUT-TABLE`)**: Capture `PRE_MUTATION_RUN` -> root-cause fix -> `POST_MUTATION_RUN` -> scoped pytest (`--timeout=60`) -> independent check, record outcome in `HITLDecisionStore`, pass `validate_sidecar_separation.py`, `validate_turn_gates.py --mode all`, and `verify_commit.py`, and either stage via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` or obtain `PR_MERGE_AUTHORIZATION`, promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(agents): <summary>"`, immediately delete the merged worktree and branch (`prune_merged_chat_worktrees.py --delete-merged`), and render the top 3-column closeout table (`| **Merge to Main** | ✅ Complete | ... |` and `| **Worktree Deletion** | ✅ Complete | ... |`).
- **`C13` — Parallel MECE Lease Isolation (`INV-PARALLEL-AGENT-MECE-ISOLATION`)**: All 7 workflows own strictly pairwise-disjoint write paths (`0 / 21` overlapping pairs in `PROMPT_STAGE_ALLOWED_WRITE_PATHS`). Never run unlocked `git worktree prune`; `evaluate_prompt_stage_write_scope` blocks concurrent peer collisions while allowing full-repo root-cause fixes during solo runs.
- **`C14` — 100% Full-Repository Tracked-File Coverage (`INV-FULL-REPO-STAGE-COVERAGE`)**: `validate_stage_full_repo_coverage` in `tools/prompt_scope_isolation.py` verifies that 100% of `git ls-files` tracked paths map to `ALWAYS_ALLOWED_EPHEMERAL_PREFIXES` or an explicit stage owner in `PROMPT_STAGE_ALLOWED_WRITE_PATHS` (`0` unowned tracked files).
