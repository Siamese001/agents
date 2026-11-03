# Agents Repository — Storage & Worktree Hygiene Automation Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage I (Order 1/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Storage, Worktree, Scratch, and SQLite Hygiene Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`05:00 ET`, Order `1/7`). This agent prepares a clean foundation before Stages II–IV run by auditing and remediating orphaned git worktrees, merged local feature branches, SQLite/WAL health across all repository databases (discovering SQLite/Chroma/vector databases across `artifacts/`, `.codex/`, `data/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `apps_model_telemetry/`, `infrastructure/`, `agents/`, `ops_scripts/`, `scripts/`, and `tools/`), stale locks (`resume_graph_engine/artifacts/`, `.worktrees/.provisioning.lock`, and expired `.sidecar_active_run.lock` leases), cross-repo `scratch/` leaks, and the full-repository storage inventory (`artifacts/models/`, `artifacts/career_calls/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `apps_model_telemetry/`, `data/`, `.worktrees/`, `plans/`, `reports/`, `scratch/`), enforcing `INV-REMEDIATION-QUOTA-FLOOR` (`C04`).

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Git worktree pruning, merged local branch cleanup, SQLite `PRAGMA integrity_check` / `PRAGMA wal_checkpoint(TRUNCATE)` across all 6 databases, `scratch/` hygiene, stale `.provisioning.lock` cleanup, and `artifacts/sidecar_runs/` + `28 GB` storage inventory auditing.
- **Delegated to peer agents**: Subsystem boundary & SSOT drift (`agents-ssot-boundary-governance`), E2E pipeline execution (`agents-outreach-resume-functionality`), retrieval quality (`agents-research-retrieval-surface`), judge validity (`agents-evals-judge-assurance`), token budgets (`agents-cost-token-budget`), and test coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Strictly bound to `/Users/amitayer/Git/agents`. Zero access to external repositories or external sidecar directories.
- **Zero-Defect Fast-Exit & Wave-Based Plan Mandate (`C03`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - When Phase 1.5 reports `0` actionable findings (`is_clean: true`), fast-exit cleanly per `C03`: copy `${RUN_DIR}` to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_storage_worktree_hygiene/${RUN_TS}`, tear down the ephemeral worktree via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only`, and exit `COMPLETE` without authoring a synthetic plan.
  - Whenever `>= 1` findings exist in **EITHER** `MODE: scheduled` or `MODE: interactive`, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md` (and copy it to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md"` (`exit code 0`).
  - In `MODE: scheduled`, stage validated fixes on `${BRANCH_NAME}` via `pr_governance.py submit "${BRANCH_NAME}" --stage-only` without mutating `local main` directly.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

Before executing any inspection or writing any file, provision an isolated worktree off local `main`:

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-storage-hygiene-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_storage_worktree_hygiene/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 6-Pillar Read-Only Audit & Executable Forensic Scanners

### Phase 1: 6-Pillar Hygiene Audit
1. **Pillar 1 — Worktree & Branch Drift**: Detect stale worktrees in `git worktree list --porcelain` and non-active local branches already merged into `main` (`git branch --merged main`), respecting `.sidecar_active_run.lock` leases and dirty worktrees.
2. **Pillar 2 — SQLite Integrity & Journal Mode**: Verify `PRAGMA integrity_check` and `PRAGMA journal_mode=WAL` across all 6 SQLite/Chroma/vector databases (`artifacts/governance/hitl_decisions.sqlite`, `artifacts/learning/feedback_learning.sqlite`, `resume_graph_engine/artifacts/apps_rg/fact_inventory/augmented_skills_graph.sqlite`, `resume_graph_engine/data/cache/chromadb/**/chroma.sqlite3`, `resume_graph_engine/data/cache/sparse/fact_vectors.db`).
3. **Pillar 3 — WAL / SHM Bloat Detection**: Flag `-wal` or `-shm` sidecar files exceeding `32 MB` that require `PRAGMA wal_checkpoint(TRUNCATE)`.
4. **Pillar 4 — Ephemeral Artifact Sprawl, Duplicate Models, Runtime Proof Retention & Storage Inventory**: Measure ephemeral sprawl (`artifacts/sidecar_runs/`, `artifacts/mcp/playwright/`, `.pytest_cache/`, duplicate `resume_graph_engine/artifacts/models/`, unretained `resume_graph_engine/artifacts/apps_rg/runtime_proofs/full_resume_*` runs beyond the newest active run and pointer-protected runs, unretained `resume_graph_engine/.runtime/tests/` runs, and repository-wide `__pycache__` trees > `500 MB`) alongside the full storage inventory (`artifacts/models/`, `artifacts/career_calls/`, `resume_graph_engine/artifacts/`, `resume_graph_engine/.runtime/`, `plans/`, `reports/`, `scratch/`).
5. **Pillar 5 — Stale Lock, Provisioning Lock & Scratch Sweep**: Identify orphaned `.lock`/`.tmp` files and `.worktrees/.provisioning.lock` older than 24 hours plus any cross-repo/credential leaks inside `scratch/`.
6. **Pillar 6 — Cross-Repository Isolation Verification**: Run `tools/validate_sidecar_separation.py --repo-root "${WORKTREE_DIR}" --json` to confirm zero namespace, cron, or path drift.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the bounded 6-pillar scanner CLI in `${WORKTREE_DIR}` (`timeout <= 60s`):

```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/storage_worktree_hygiene.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
When findings exist (`is_clean == false`), author `${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md` (500–800 words, max 1,000 words) structured as sequential waves:
- `## Wave 1: Worktree, Merged Branch, Scratch & Lock Hygiene`
- `## Wave 2: SQLite WAL Checkpoint & Artifact Retention`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/storage-hygiene-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) covering all 6 pillars.
Compute multi-factor calibrated confidence using `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_storage_worktree_hygiene/${RUN_TS}`. When 0 findings exist, prune `${WORKTREE_DIR}` and `${BRANCH_NAME}` via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` and exit `COMPLETE`; when remediable findings pass all 5 proof points with $\Delta > 0.20$, commit on `${BRANCH_NAME}` and stage via `--stage-only` without mutating `main`.
- In `MODE: interactive`: If $\Delta \le 0.20$, invoke `ask_question` with one atomic decision (`Candidate ID`, calibrated confidence scores, `(Recommended)` option). If $\Delta > 0.20$, record the autonomous decision receipt in `HITLDecisionStore` and proceed to Phase 3.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` metrics (worktree count, merged branch count, 6-DB WAL state, scratch violations).
   - Execute bounded remediation (`storage_worktree_hygiene.py --repo-root "${WORKTREE_DIR}" --remediate --json`).
   - Run `POST_MUTATION_RUN` verification and scoped pytest:
     `"${PRIMARY_REPO_ROOT}/.venv/bin/pytest" "${WORKTREE_DIR}/tests/unit/test_sidecar_separation_governance.py" -v --timeout=60`
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore` (`artifacts/governance/hitl_decisions.sqlite`).
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   ```bash
   "${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json
   "${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all
   "${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"
   ```
   Commit via `git -C "${WORKTREE_DIR}" commit`, then stage via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` in scheduled mode, or obtain interactive `ask_question` `PR_MERGE_AUTHORIZATION` and promote via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "chore(hygiene): remediate storage and worktree drift"`.
