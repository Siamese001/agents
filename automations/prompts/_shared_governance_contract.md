# Agents Repository — Consolidated On-Demand Assurance Shared Governance Contract (`C01–C13`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:3.0.0 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP | INV-PARALLEL-AGENT-MECE-ISOLATION -->

## 1. Repository Isolation & On-Demand Execution Invariant (`INV-REPO-SEPARATION-AGENTS-ONLY`)

1. **Workspace Containment**: All 4 `agents-*` on-demand assurance workflows are bound exclusively to `/Users/amitayer/Git/agents` and its isolated remediation worktrees under `/Users/amitayer/Git/agents/.worktrees/*`.
2. **Zero Cross-Repository Mutation**: Assurance agents in this repository are strictly forbidden from reading, modifying, locking, or writing to any file, database, worktree, or sidecar configuration belonging to external repositories.
3. **Preflight-First Artifact Isolation**: Phase 1 & Phase 1.5 read-only behavioral preflight checks execute without mutating tracked repository files. Whenever actionable findings exist (`B_total > 0`), all remediation runtime artifacts, manifests, plans, and receipts must be written exclusively inside `<WORKTREE_DIR>/artifacts/sidecar_runs/<agent_slug>/<run_id>/` and `<WORKTREE_DIR>/plans/<branch-slug>-<6hex>.md`.
4. **Zero Daily Background Schedules (`CATALOG_DISABLED_BY_DEFAULT`)**: Unattended daily `agents-*` background schedules are disabled (`"enabled": false`, `agents_scheduled_count == 0`). All 4 consolidated `agents-*` workflows are mirrored in `/Users/amitayer/.gemini/config/sidecars/` and `/Users/amitayer/.gemini/config/config.json` as disabled manual launchers (`"enabled": false`, `projectId: "f3cfd8ed-5fb8-40c7-b562-dbdf15522309"`) with thin SSOT pointer prompts targeting `file:///Users/amitayer/Git/agents/automations/prompts/agents_*_agent.md`. Static hygiene and test/mock checks execute automatically via `.githooks/{pre-commit,post-merge}`, `tools/verify_commit.py`, and `tools/verify_main_readiness.py` Stage 10.

---

## 2. Master 4-Agent Causal Execution Sequence & Automated Gate Split

| Order | Stage | Workflow ID | Consolidated Skill | Deterministic Auditor(s) | Canonical Thin Prompt |
| :---: | :---: | :--- | :--- | :--- | :--- |
| **1/4** | **Stage I (Architecture & Cost)** | `agents-architecture-cost-governance` | `agents-governance-hygiene` / `scope-containment` | `tools/ssot_boundary_auditor.py` + `tools/cost_token_budget_auditor.py` | `automations/prompts/agents_architecture_cost_agent.md` |
| **2/4** | **Stage II (Core Runtime)** | `agents-core-runtime-orchestration` | `agent-runtime-engineering` / `agent-subagent-orchestration` | `tools/agent_runtime_auditor.py` | `automations/prompts/agents_core_runtime_orchestration_agent.md` |
| **3/4** | **Stage III (Domain & Retrieval)** | `agents-domain-pipelines-retrieval` | `agents-domain-assurance` | `tools/e2e_functionality_auditor.py` + `tools/retrieval_surface_auditor.py` | `automations/prompts/agents_domain_pipelines_retrieval_agent.md` |
| **4/4** | **Stage IV (Evals & Flywheel)** | `agents-evals-flywheel-assurance` | `receipt-auditor` / `agents-domain-assurance` | `tools/validate_eval_rubrics.py` + `tools/run_eval_flywheel_cycle.py` | `automations/prompts/agents_evals_flywheel_assurance_agent.md` |

- **Retired to Automated Git & Readiness Gates**:
  - *Storage & Worktree Hygiene*: `.githooks/post-merge` + `tools/storage_worktree_hygiene.py --post-merge-quick` (manual full sweep via `agents-governance-hygiene` skill).
  - *Testing Gaps & Mock Reachability*: Tier 1 `tools/verify_commit.py` (staged AST mock reachability, skip/xfail, zero-assertion tests) + Tier 2 `tools/verify_main_readiness.py` Stage 10 (`tools/testing_gaps_auditor.py`).

---

## 3. Common Control Matrix & Shared Phase Templates (`C01–C13`)

- **`C01` — Trusted Launch & Multi-Extension Search (`INV-FULL-EXTENSION-SSOT-SEARCH`)**: Search `.md`, `.mdc`, `.txt`, `.jinja`, `.j2`, `.csv`, `.jsonl`, `.toml`, `.ini`, `.cfg`, `.sql`, `.yaml`, `.yml`, `.json`, `.py`, `.sh`, and `.ps1` across the repository.
- **`C02` — Preflight-First Ordering & Conditional Phase 0 Single-Worktree Provisioning (`Step 0.1`)**:
  Execute Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}` (`PYTHONDONTWRITEBYTECODE=1`, pytest `-p no:cacheprovider`). Only when `B_total > 0` (`is_clean == false`), provision an isolated worktree via `--consolidate-sidecar` and `--write-manifest` and `cd "${WORKTREE_DIR}"`:
  ```bash
  export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
  export PYTHONDONTWRITEBYTECODE=1
  export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
  export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
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
- **`C03` — Zero-Churn Fast-Exit (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`)**: When Phase 1.5 reports `B_total == 0` (`is_clean == true`), exit `COMPLETE` immediately without creating a worktree or synthetic plan.
- **`C04` — Unconditional Wave Plan & Quota (`UNCONDITIONAL_WAVE_PLAN_MANDATE`, `INV-REMEDIATION-QUOTA-FLOOR`, `INV-DEFECT-ACCOUNTING-TABLE-GATE`)**: On active defects, author `${WORKTREE_DIR}/${PLAN_REL}` validated via `validate_implementation_plan.py`, remediate `>= Q_min = min(B_total, max(3, ceil(0.02 * B_domain)))` defects, and render the 7-column Before/After Defect Accounting Table.
- **`C05` — Pre-HITL Dimension Findings Table & Compact `<= 115` Char HITL Gate**: Render the **Dimension Findings Table**, score options via `tools/hitl_governance.py` (`HITLDecisionStore`), and surface one atomic `ask_question` (`<= 115` chars per option with front-loaded confidence `(Recommended) HIGH 85%: ...`) when $\Delta \le 0.20$.
- **`C06`–`C12` — 5-Point Counterfactual Proof (`INV-RUNTIME-PROOF-5POINT`), Persistent Learning (`INV-AUTOMATION-PERSISTENT-LEARNING-LOOP`), Constitutional Floor, Turn/Commit Gates & Governed Promotion**: Capture `PRE_MUTATION_RUN` -> bounded fix -> `POST_MUTATION_RUN` -> scoped pytest (`--timeout=60`) -> independent check, record outcome in `HITLDecisionStore`, pass `validate_sidecar_separation.py`, `validate_turn_gates.py --mode all`, and `verify_commit.py`, and either stage via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` or obtain `PR_MERGE_AUTHORIZATION` and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(agents): <summary>"`.
- **`C13` — Parallel MECE Lease Isolation (`INV-PARALLEL-AGENT-MECE-ISOLATION`)**: All 4 workflows own strictly pairwise-disjoint write paths (`0 / 6` overlapping pairs in `PROMPT_STAGE_ALLOWED_WRITE_PATHS`). Never run unlocked `git worktree prune`; `evaluate_prompt_stage_write_scope` blocks concurrent peer collisions while allowing full-repo root-cause fixes during solo runs.
