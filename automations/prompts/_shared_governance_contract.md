# Agents Repository — On-Demand Assurance Agents Shared Governance Contract (`C01–C12`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:on-demand-assurance-control-matrix:2.0.0 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | PREFLIGHT_ZERO_DEFECT_FAST_EXIT | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Repository Isolation & On-Demand Execution Invariant (`INV-REPO-SEPARATION-AGENTS-ONLY`)

1. **Workspace Containment**: All `agents-*` on-demand assurance workflows are bound exclusively to `/Users/amitayer/Git/agents` and its isolated remediation worktrees under `/Users/amitayer/Git/agents/.worktrees/*` (e.g. `chore__agents__*` or `feat_*`).
2. **Zero Cross-Repository Mutation**: Assurance agents in this repository are strictly forbidden from reading, modifying, locking, or writing to any file, database, worktree, or sidecar configuration belonging to external repositories.
3. **Preflight-First Artifact Isolation**: Phase 1 / Phase 1.5 read-only behavioral preflight checks execute without mutating tracked repository files. Whenever actionable findings exist (`B_total > 0`), all remediation runtime artifacts, manifests, plans, and receipts must be written exclusively inside `<WORKTREE_DIR>/artifacts/sidecar_runs/<agent_slug>/<run_id>/` and `<WORKTREE_DIR>/plans/<branch-slug>-<6hex>.md`.
4. **Zero Daily Background Schedules**: Unattended daily `agents-*` schedules in `/Users/amitayer/.gemini/config/sidecars/` and `/Users/amitayer/.gemini/config/config.json` are permanently retired (`agents_scheduled_count == 0`); continuous structural gates run via `.githooks/pre-commit` (`tools/verify_commit.py`) and deep sweeps run on demand through `.agents/skills/` and `automations/prompts/agents_*_agent.md`.

---

## 2. Master Causal Execution Sequence (On-Demand & Pre-Save Gates)

| Order | Stage | Workflow ID | Execution Mode | Deterministic Checker | Canonical Prompt Specification |
| :---: | :---: | :--- | :---: | :--- | :--- |
| **1/7** | **Stage I (Foundation)** | `agents-storage-worktree-hygiene` | On-Demand CLI / Skill | `tools/storage_worktree_hygiene.py` | `automations/prompts/agents_storage_worktree_hygiene_agent.md` |
| **2/7** | **Stage II (Governance)** | `agents-ssot-boundary-governance` | Pre-Save Gate + Skill | `tools/ssot_boundary_auditor.py` | `automations/prompts/agents_ssot_boundary_agent.md` |
| **3/7** | **Stage III-A (Core E2E)** | `agents-outreach-resume-functionality` | On-Demand Skill | `tools/e2e_functionality_auditor.py` | `automations/prompts/agents_e2e_functionality_assurance_agent.md` |
| **4/7** | **Stage III-B (Retrieval)** | `agents-research-retrieval-surface` | On-Demand Skill | `tools/retrieval_surface_auditor.py` | `automations/prompts/agents_research_retrieval_surface_agent.md` |
| **5/7** | **Stage III-C (Evaluation)** | `agents-evals-judge-assurance` | Pre-Save + On-Demand | `tools/validate_eval_rubrics.py` | `automations/prompts/agents_evals_judge_assurance_agent.md` |
| **6/7** | **Stage IV-A (Economics)** | `agents-cost-token-budget` | Pre-Save + On-Demand | `tools/cost_token_budget_auditor.py` | `automations/prompts/agents_cost_token_budget_agent.md` |
| **7/7** | **Stage IV-B (Verification)** | `agents-testing-gaps-assurance` | Pre-Save Hook + Skill | `tools/testing_gaps_auditor.py` | `automations/prompts/agents_testing_gaps_assurance_agent.md` |

---

## 3. Common Control Matrix (`C01–C12`)

Every `agents_*_agent.md` specification inherits and enforces the 12 mandatory controls below:

- **`C01` — Trusted Launch & Full-Repository Scope Boundary**:
  - `trust_level: workspace_trusted`, `sandbox_mode: workspace-write`, `network_access: disabled`.
  - Allowed write paths (inside isolated worktree on findings): `agents/`, `apps_model_telemetry/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `infrastructure/`, `data/`, `ops_scripts/`, `scripts/`, `tools/`, `tests/`, `config/`, `plans/`, `reports/`, `docs/`, `scratch/`, `automations/`, `.agents/`, `.antigravity/`, `.githooks/`, `AGENTS.md`, `pyproject.toml`, `.mcp.json`, `artifacts/`.
- **`C02` — Preflight-First Ordering & Conditional Phase 0 Single-Worktree Provisioning (`Step 0.1`)**:
  - Every run executes Phase 1 & Phase 1.5 read-only behavioral preflight **first** against `${PRIMARY_REPO_ROOT}` so zero-defect runs never churn branches or unlink active session directories.
  - When `B_total > 0` (`is_clean == false`), Phase 0 (`Step 0.1`) deduplicates clean merged chat worktrees (preserving `.agents/tools` hook symlinks), provisions a single isolated worktree off local `main`, writes `${RUN_DIR}/manifest.json` deterministically via `--write-manifest`, and switches into `${WORKTREE_DIR}` (`cd "${WORKTREE_DIR}"`):
    `"/Users/amitayer/Git/agents/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}" --write-manifest "${RUN_DIR}/manifest.json"`
- **`C03` — On-Demand Interactive Execution & Zero-Churn Fast-Exit (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`)**:
  - Execute Phase 1 & Phase 1.5 read-only behavioral auditors first. When `0` actionable findings exist (`B_total == 0` and `is_clean == true`), exit `COMPLETE` immediately (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) without provisioning a temporary worktree or authoring synthetic no-op plans.
  - When actionable findings exist (`B_total > 0`), execute Phase 0 isolated worktree provisioning, author and validate the Phase 2 wave plan, surface the **Dimension Findings Table** and atomic `ask_question` HITL decision when calibrated margin $\Delta \le 0.20$, execute Phase 3 wave-by-wave remediation with 5-Point Counterfactual Runtime Proofs, commit on `"${BRANCH_NAME}"`, obtain explicit operator `PR_MERGE_AUTHORIZATION` via `ask_question`, and promote into local `main` via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(agents): <summary>"`.
- **`C04` — Unconditional Wave-Based Plan Mandate on Active Defects (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - Every workflow's Phase 1.5 preflight MUST execute its dedicated fail-closed behavioral auditor (`storage_worktree_hygiene.py`, `ssot_boundary_auditor.py`, `e2e_functionality_auditor.py`, `retrieval_surface_auditor.py`, `validate_eval_rubrics.py`, `cost_token_budget_auditor.py`, `testing_gaps_auditor.py`). Generic commit-gate checks (`verify_commit.py`) or inline heredoc scripts NEVER qualify for `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`.
  - Whenever actionable findings exist (`B_total > 0`), author a wave-based remediation plan at `${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md` (500–800 words, hard ceiling 1,000 words) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), each containing `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`), validated via `validate_implementation_plan.py` (`exit code 0`).
  - Remediate at least `Q_min = min(B_total, max(3, ceil(0.02 * B_domain)))` defects (`INV-REMEDIATION-QUOTA-FLOOR`) and emit the 7-column Before/After Defect Accounting Table (`INV-DEFECT-ACCOUNTING-TABLE-GATE`).
- **`C05` — Pre-HITL Dimension Findings Table & Atomic 20% Margin HITL Gate**:
  - Render the markdown **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`), compute calibrated confidence via `tools/hitl_governance.py` (`HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`), surface one atomic `ask_question` decision when $\Delta \le 0.20$, and proceed autonomously under a sealed receipt when $\Delta > 0.20$.
- **`C06` — Sequential Wave Execution & 5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
  - Never advance to Wave $N+1$ until Wave $N$ captures `PRE_MUTATION_RUN` -> bounded edit -> `POST_MUTATION_RUN` real CLI entrypoint -> scoped pytest (`--timeout=60`, `WaitMsBeforeAsync >= 15000`) -> independent state inspection -> durable 5-column proof table.
- **`C07` — Persistent Closed-Loop System Learning (`INV-AUTOMATION-PERSISTENT-LEARNING-LOOP`)**:
  - Query prior decisions from `HITLDecisionStore` (`artifacts/governance/hitl_decisions.sqlite`) in Phase 2 and record wave execution outcomes (`record_execution_outcome`) in Phase 3.
- **`C08` — Constitutional Floor & Production Purity**:
  - Explicit `timeout=` on all `subprocess.*` calls; no `pytest.mark.skip` without `reason=`; `pytest.mark.xfail(strict=True)`; no bare `except Exception: pass` without `# guardian:`; zero golden fixtures imported in production (`tools/lint_production_purity.py`); approved model pins in `config/provider_profiles.yaml`.
- **`C09` — Turn Gate & Tier-1 Commit Gate Compliance**:
  - Every wave commit must pass `validate_turn_gates.py --mode all`, `verify_commit.py`, and `validate_sidecar_separation.py --json` against `"${WORKTREE_DIR}"`.
- **`C10` — Governed Commit, Review, Promotion & Worktree Teardown**:
  - Commit wave changes via `git -C "${WORKTREE_DIR}" commit`, obtain explicit interactive `PR_MERGE_AUTHORIZATION` via `ask_question`, and promote via `pr_governance.py -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "<conventional title>"`.
- **`C11` — Tested Python Runner Binding**:
  - Bind `PYTHON_BIN="/Users/amitayer/Git/agents/.venv/bin/python"` and `PYTEST_BIN="/Users/amitayer/Git/agents/.venv/bin/pytest"`.
- **`C12` — Output Brevity & Plain-Language Reporting**:
  - User-facing summaries must use plain layman English with zero technical jargon, zero `snake_case` identifiers, zero raw filenames in prose, zero em-dashes, `MM/DD/YYYY` dates, and `<= 300` words.
