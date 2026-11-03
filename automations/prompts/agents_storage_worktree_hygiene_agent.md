# Agents Repository — Storage & Worktree Hygiene Automation Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:2.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage I (Order 1/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Storage, Worktree, Scratch, and SQLite Hygiene Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (On-Demand, Order `1/7`). This agent prepares a clean foundation before Stages II–IV run by auditing and remediating orphaned git worktrees, merged local feature branches, SQLite/WAL health across all repository databases (discovering SQLite/Chroma/vector databases across `artifacts/`, `.codex/`, `data/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `apps_model_telemetry/`, `infrastructure/`, `agents/`, `ops_scripts/`, `scripts/`, and `tools/`), stale locks (`resume_graph_engine/artifacts/`, `.worktrees/.provisioning.lock`, and expired `.sidecar_active_run.lock` leases), cross-repo `scratch/` leaks, duplicate model weights, unretained runtime proof runs, and the full-repository storage inventory (`artifacts/models/`, `artifacts/career_calls/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `apps_model_telemetry/`, `data/`, `.worktrees/`, `plans/`, `reports/`, `scratch/`), enforcing `INV-REMEDIATION-QUOTA-FLOOR` (`C04`).

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Git worktree pruning, merged local branch cleanup, SQLite `PRAGMA integrity_check` / `PRAGMA wal_checkpoint(TRUNCATE)` across all repository databases, `scratch/` hygiene, stale `.provisioning.lock` cleanup, duplicate `artifacts/models/` deduplication, `runtime_proofs` / `.runtime/tests` retention pruning, and full-repository storage inventory auditing.
- **Delegated to peer agents**: Subsystem boundary & SSOT drift (`agents-ssot-boundary-governance`), E2E pipeline execution (`agents-outreach-resume-functionality`), retrieval quality (`agents-research-retrieval-surface`), judge validity (`agents-evals-judge-assurance`), token budgets (`agents-cost-token-budget`), and test coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Strictly bound to `/Users/amitayer/Git/agents`. Zero access to external repositories or external sidecar directories.
- **Preflight-First Fast-Exit & Wave-Based Plan Mandate (`C03`, `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - Execute Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}`. When `0` actionable findings exist (`is_clean: true`), exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without creating an ephemeral worktree or synthetic plan.
  - Whenever `>= 1` findings exist (`is_clean: false`), execute Phase 0 isolated worktree provisioning, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md` (copied to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md"` (`exit code 0`).

---

## 3. Phase 1 & Phase 1.5: 6-Pillar Read-Only Preflight Audit & Fast-Exit Gate

### Phase 1: 6-Pillar Hygiene Audit
1. **Pillar 1 — Worktree, Zombie Chat Shell & Branch Drift**: Detect stale worktrees in `git worktree list --porcelain`, orphaned external IDE chat worktree shells (`~/.gemini/antigravity/worktrees/agents/*` excluding active `PWD`/`OLDPWD`), and non-active local branches already merged into `main` (`git branch --merged main`), respecting `.sidecar_active_run.lock` leases and dirty worktrees.
2. **Pillar 2 — SQLite Integrity & Journal Mode**: Verify `PRAGMA integrity_check` and `PRAGMA journal_mode=WAL` across all repository SQLite/Chroma/vector databases (`artifacts/governance/hitl_decisions.sqlite`, `artifacts/learning/feedback_learning.sqlite`, `resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite`, `resume_graph_engine/data/cache/chromadb/**/chroma.sqlite3`, `resume_graph_engine/data/cache/sparse/fact_vectors.db`).
3. **Pillar 3 — WAL / SHM Bloat Detection**: Flag `-wal` or `-shm` sidecar files exceeding `32 MB` that require `PRAGMA wal_checkpoint(TRUNCATE)`.
4. **Pillar 4 — Ephemeral Artifact Sprawl, Duplicate Models, Runtime Proof Retention & Storage Inventory**: Flag ephemeral sprawl (`artifacts/sidecar_runs/`, `artifacts/mcp/playwright/`, `.pytest_cache/` > `50 MB`, duplicate `resume_graph_engine/artifacts/models/`, unretained `resume_graph_engine/artifacts/apps_rg/runtime_proofs/full_resume_*` runs beyond the newest active run and pointer-protected runs, unretained `resume_graph_engine/.runtime/tests/` runs, and any repository `__pycache__` directory count `> 0`) alongside the full storage inventory.
5. **Pillar 5 — Stale Lock, Provisioning Lock & Scratch Sweep**: Identify orphaned `.lock`/`.tmp` files and `.worktrees/.provisioning.lock` older than 24 hours plus any cross-repo/credential leaks inside `scratch/`.
6. **Pillar 6 — Cross-Repository Isolation Verification**: Run `tools/validate_sidecar_separation.py --repo-root "${PRIMARY_REPO_ROOT}" --json` to confirm zero namespace, schedule, or routing drift.

### Phase 1.5: Mandatory Executable Read-Only Preflight Scanner
Execute the bounded 6-pillar read-only scanner CLI and scoped unit verification (`timeout <= 60s`):

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/storage_worktree_hygiene.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --json
"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${PRIMARY_REPO_ROOT}/tests/unit/test_storage_hygiene_full_repo_remediation.py" -q --timeout=60
```

If `storage_worktree_hygiene.py` exits `0` (`"status": "PASS"`, `"is_clean": true`), fast-exit `COMPLETE` (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`).

---

## 4. Phase 0: Conditional Isolated Worktree Provisioning on Findings (`Step 0.1` — `C02`)

When Phase 1.5 reports `>= 1` actionable findings (`is_clean == false`), provision a single isolated worktree, emit `manifest.json` deterministically via `--write-manifest`, and switch into `${WORKTREE_DIR}`:

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-storage-hygiene-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_storage_worktree_hygiene/${RUN_TS}"
export PLAN_REL="plans/storage-hygiene-${HEX6}.md"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" \
  --repo-root "${PRIMARY_REPO_ROOT}" \
  --consolidate-sidecar \
  --worktree-dir "${WORKTREE_DIR}" \
  --branch "${BRANCH_NAME}" \
  --write-manifest "${RUN_DIR}/manifest.json" \
  --agent-id "agents-storage-worktree-hygiene" \
  --run-id "${RUN_TS}" \
  --mode "interactive" \
  --plan-path "${PLAN_REL}"
cd "${WORKTREE_DIR}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/storage_worktree_hygiene.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json || true
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
Author `${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md` (500–800 words, max 1,000 words) structured as sequential waves:
- `## Wave 1: Worktree, Merged Branch, Scratch & Lock Hygiene`
- `## Wave 2: SQLite WAL Checkpoint, Model Deduplication & Artifact Retention`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) covering all 6 pillars.
Compute multi-factor calibrated confidence using `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- If $\Delta \le 0.20$, invoke `ask_question` with one atomic decision (calibrated confidence scores, `(Recommended)` option).
- If $\Delta > 0.20$, record the autonomous decision receipt in `HITLDecisionStore` and proceed to Phase 3.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` metrics (worktree count, merged branch count, DB WAL state, Pillar 4 bloat MB, scratch violations).
   - Execute bounded remediation (`"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/storage_worktree_hygiene.py" --repo-root "${WORKTREE_DIR}" --remediate --json`).
   - Run `POST_MUTATION_RUN` verification and scoped pytest:
     `"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${WORKTREE_DIR}/tests/unit/test_storage_hygiene_full_repo_remediation.py" "${WORKTREE_DIR}/tests/unit/test_sidecar_separation_governance.py" -v --timeout=60`
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore` (`artifacts/governance/hitl_decisions.sqlite`).
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   ```bash
   "${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json
   "${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all
   "${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"
   ```
   Commit via `git -C "${WORKTREE_DIR}" commit`, obtain interactive `ask_question` `PR_MERGE_AUTHORIZATION`, and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "chore(hygiene): remediate storage and worktree drift"`.
