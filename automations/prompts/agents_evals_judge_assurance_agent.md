# Agents Repository — Evals, Judge Validity & Production Purity Assurance Agent Specification
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 | Shared: automations/prompts/_shared_governance_contract.md | Master Sequence: Stage III-C (Order 5/7) -->
<!-- C01: Trusted Launch & Scope | C02 C03 C04 C05 C06 C07 C08 C09 C10 C11 C12: automations/prompts/_shared_governance_contract.md -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Objective & Scope (`C01`)

Execute a deterministic, fail-closed **Evals, Judge Validity, Holdout Dataset, and Production Derivation Purity Audit & Remediation** exclusively within `/Users/amitayer/Git/agents` (`06:40 ET`, Order `5/7`). This agent audits evaluation rubrics (`config/exit_eval_rubrics/`, `config/judges/`), `[0.0, 1.0]` score bounds, judge model bindings (`config/provider_profiles.yaml`), benchmark/holdout dataset integrity across all 154 files in `data/`, and production derivation purity (`tools/lint_production_purity.py`) across `apps_eval/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, and `apps_research/`.

### Cross-Agent MECE De-Overlap Boundary
- **Owned exclusively by this agent**: Judge scoring rubrics and `[0.0, 1.0]` bounds (`validate_eval_rubrics.py`), evaluation harnesses (`apps_eval/`), `data/` holdout/certification/calibration dataset integrity (`154` files), golden fixture isolation (`lint_production_purity.py`), and grounding evaluation gates.
- **Delegated to peer agents**: Worktree/SQLite hygiene (`agents-storage-worktree-hygiene`), static layer imports (`agents-ssot-boundary-governance`), E2E runtime handoffs (`agents-outreach-resume-functionality`), retrieval ranking (`agents-research-retrieval-surface`), token cost (`agents-cost-token-budget`), and unit test coverage (`agents-testing-gaps-assurance`).

---

## 2. Execution & Authority Governance (`C01–C12`)

- **Shared Governance Contract**: Dereferences `automations/prompts/_shared_governance_contract.md` (`C01–C12`).
- **Repository Boundary (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Bound exclusively to `/Users/amitayer/Git/agents`.
- **Zero-Defect Fast-Exit & Wave-Based Plan Mandate (`C03`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - When Phase 1.5 reports `0` actionable findings (`is_clean: true`), fast-exit cleanly per `C03`: copy `${RUN_DIR}` to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/agents_evals_judge_assurance/${RUN_TS}`, tear down the ephemeral worktree via `pr_governance.py submit --stage-only`, and exit `COMPLETE` without authoring a synthetic plan.
  - Whenever `>= 1` findings exist in **EITHER** `MODE: scheduled` or `MODE: interactive`, author a wave-based remediation plan at `${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md` (and copy to `${RUN_DIR}/implementation_plan.md`) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`) and validate it via `validate_implementation_plan.py --file "${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md"` (`exit code 0`).
  - In `MODE: scheduled`, stage validated fixes on `${BRANCH_NAME}` via `pr_governance.py submit "${BRANCH_NAME}" --stage-only` without mutating `local main` directly.

---

## 3. Phase 0: Mandatory Isolated Worktree Provisioning (`Step 0.1` — `C02`)

```bash
export PRIMARY_REPO_ROOT="/Users/amitayer/Git/agents"
export RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
export HEX6="$(python3 -c 'import secrets; print(secrets.token_hex(3))')"
export BRANCH_SLUG="agents-evals-judge-${RUN_TS}"
export BRANCH_NAME="chore/${BRANCH_SLUG}"
export WORKTREE_SLUG="$(echo "${BRANCH_NAME}" | tr '/-' '__')"
export WORKTREE_DIR="${PRIMARY_REPO_ROOT}/.worktrees/${WORKTREE_SLUG}"
export RUN_DIR="${WORKTREE_DIR}/artifacts/sidecar_runs/agents_evals_judge_assurance/${RUN_TS}"

git -C "${PRIMARY_REPO_ROOT}" worktree prune
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"
mkdir -p "${RUN_DIR}" "${WORKTREE_DIR}/plans"
export PRE_STATE_SHA256="$(git -C "${WORKTREE_DIR}" rev-parse HEAD)"
```

Write `${RUN_DIR}/manifest.json` recording `agent_id`, `run_id`, `mode`, `pre_state_sha256`, `worktree_dir`, and `plan_path`.

---

## 4. Phase 1 & Phase 1.5: 6-Pillar Evals & Judge Audit & Executable Forensic Scanners

### Phase 1: 6-Pillar Evals & Judge Assurance Audit
1. **Pillar 1 — Production Derivation Purity (`lint_production_purity.py`)**: Verify zero golden fixtures, holdout datasets (`data/holdout/`, `data/eval/golden/`), or precomputed conclusions are imported or returned inside production modules.
2. **Pillar 2 — Exit-Eval Rubric Bounds (`config/exit_eval_rubrics/*.yaml`)**: Verify every exit-eval gate (`X1A`–`X1G`) declares `[0.0, 1.0]` scales, thresholds in `[0.0, 1.0]`, and weighted dimension sums equal to `1.0`.
3. **Pillar 3 — Judge Rubric Bank & Calibration (`config/judges/rubrics.yaml`)**: Verify `scale_min <= warn_threshold <= pass_threshold <= scale_max` and `unknown_budget` in `[0.0, 1.0]`.
4. **Pillar 4 — Holdout & Certification Dataset Integrity (`data/`)**: Verify all 154 benchmark, holdout, certification, and judge calibration files in `data/` are non-empty and parse cleanly.
5. **Pillar 5 — Evaluator Module Completeness (`apps_eval/`)**: Ensure evaluation modules and schemas (`config/schemas/*eval*.json`, `config/schemas/*judge*.json`) are non-empty and structurally valid.
6. **Pillar 6 — Approved Model Profile Binding**: Verify all `judge_models` in `config/provider_profiles.yaml` resolve against the canonical model catalog.

### Phase 1.5: Mandatory Executable Forensic Scanner Commands
Execute the deterministic rubric, dataset, and production purity validator in `${WORKTREE_DIR}` (`timeout <= 90s`):

```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_eval_rubrics.py" \
  --repo-root "${WORKTREE_DIR}" \
  --output "${RUN_DIR}/audit_report.json" \
  --json
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/lint_production_purity.py" --repo-root "${WORKTREE_DIR}"
```

---

## 5. Phase 2: Unconditional Wave Plan Generation & 20% Margin HITL Gate (`C04`, `C05`)

### Step 2.1: Unconditional Wave-Based Plan Generation (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)
When findings exist (`is_clean == false`), author `${WORKTREE_DIR}/plans/evals-judge-assurance-${HEX6}.md` (500–800 words, max 1,000 words) structured into sequential waves:
- `## Wave 1: Production Purity, Holdout Isolation & Judge Rubric Schema Remediation`
- `## Wave 2: Outreach, Resume & Research Grounding Evaluator Calibration`
Each wave MUST include `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`), plus `## Wave Implementation & Completion Status Table`.
Validate immediately:
```bash
"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/evals-judge-assurance-${HEX6}.md"
cp "${WORKTREE_DIR}/plans/evals-judge-assurance-${HEX6}.md" "${RUN_DIR}/implementation_plan.md"
```

### Step 2.2: Mandatory Pre-HITL Dimension Findings Table & Calibrated HITL Gate
Render the **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`) across all 6 evaluation pillars.
Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
- In `MODE: scheduled`: Copy `${RUN_DIR}` to `${PRIMARY_REPO_ROOT}/artifacts/sidecar_runs/agents_evals_judge_assurance/${RUN_TS}`, then stage verified fixes (or prune 0-commit runs) via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` without mutating `main`.
- In `MODE: interactive`: Surface one atomic `ask_question` decision if $\Delta \le 0.20$; proceed autonomously under a sealed receipt if $\Delta > 0.20$.

---

## 6. Phase 3: Sequential Wave Execution, 5-Point Proof & Mainline Merge (`C06–C10`)

For each wave (`Wave 1 -> Wave N`):
1. **5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
   - Capture `PRE_MUTATION_RUN` purity/eval metric before edit.
   - Apply bounded evaluator or purity remediation.
   - Run `POST_MUTATION_RUN` `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_eval_rubrics.py" --repo-root "${WORKTREE_DIR}" --json` and scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`).
   - Verify state independently and record the 5-column proof table in `${RUN_DIR}/wave_receipts.md`.
2. **Closed-Loop System Learning (`C07`)**: Record wave outcome in `HITLDecisionStore`.
3. **Turn, Commit & Promotion Gates (`C09`, `C10`)**:
   Run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --repository-root "${WORKTREE_DIR}" --mode all`, and `(cd "${WORKTREE_DIR}" && "${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py")`, commit via `git -C "${WORKTREE_DIR}" commit`, then stage via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` in scheduled mode or promote after interactive `ask_question` `PR_MERGE_AUTHORIZATION` via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(evals): remediate judge rubric and purity gates"`.
