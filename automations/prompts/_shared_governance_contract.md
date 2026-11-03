# Agents Repository — On-Demand Assurance Agents Shared Governance Contract (`C01–C12`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Repository Isolation & On-Demand Execution Invariant (`INV-REPO-SEPARATION-AGENTS-ONLY`)

1. **Workspace Containment**: All `agents-*` on-demand assurance workflows are bound exclusively to `/Users/amitayer/Git/agents` and its isolated worktrees under `/Users/amitayer/Git/agents/.worktrees/chore_agents_*`.
2. **Zero Cross-Repository Mutation**: Assurance agents in this repository are strictly forbidden from reading, modifying, locking, or writing to any file, database, worktree, or sidecar configuration belonging to external repositories.
3. **Artifact Isolation**: All assurance runtime artifacts, manifests, plans, and receipts must be written exclusively inside `<WORKTREE_DIR>/artifacts/sidecar_runs/<agent_slug>/<run_id>/` and `<WORKTREE_DIR>/plans/<branch-slug>-<6hex>.md`.
4. **Zero Daily Background Schedules**: Unattended daily `agents-*` schedules in `/Users/amitayer/.gemini/config/sidecars/` and `/Users/amitayer/.gemini/config/config.json` are retired (`agents_scheduled_count == 0`); continuous structural gates run via `.githooks/pre-commit` (`tools/verify_commit.py`) and deep sweeps run on demand through `.agents/skills/` and `automations/prompts/agents_*_agent.md`.

---

## 2. Master Causal Execution Sequence (On-Demand & Pre-Save Gates)

| Order | Stage | Workflow ID | Execution Mode | Canonical Prompt Specification | Target Surface |
| :---: | :---: | :--- | :---: | :--- | :--- |
| **1/7** | **Stage I (Foundation)** | `agents-storage-worktree-hygiene` | On-Demand CLI / Skill | `automations/prompts/agents_storage_worktree_hygiene_agent.md` | `.worktrees/`, `artifacts/`, `resume_graph_engine/artifacts/`, `scratch/`, `plans/`, `reports/`, all SQLite/Chroma DBs, lock & branch pruning |
| **2/7** | **Stage II (Governance)** | `agents-ssot-boundary-governance` | Pre-Save Gate + Skill | `automations/prompts/agents_ssot_boundary_agent.md` | `agents/`, `apps_model_telemetry/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `infrastructure/`, `ops_scripts/`, `config/`, `.agents/`, `.antigravity/`, `.mcp.json`, `AGENTS.md` |
| **3/7** | **Stage III-A (Core E2E)** | `agents-outreach-resume-functionality` | On-Demand Skill | `automations/prompts/agents_e2e_functionality_assurance_agent.md` | `tools/e2e_functionality_auditor.py`, `agents/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `ops_scripts/` E2E smoke & release gates |
| **4/7** | **Stage III-B (Retrieval)** | `agents-research-retrieval-surface` | On-Demand Skill | `automations/prompts/agents_research_retrieval_surface_agent.md` | `tools/retrieval_surface_auditor.py`, `apps_research/` & `resume_graph_engine/` hybrid retrieval, BGE-M3 embedding norms, chunking, provenance, latency & cache parity |
| **5/7** | **Stage III-C (Evaluation)** | `agents-evals-judge-assurance` | Pre-Save + On-Demand | `automations/prompts/agents_evals_judge_assurance_agent.md` | `apps_eval/`, `tools/validate_eval_rubrics.py`, `tools/lint_production_purity.py`, `data/` holdout & certification datasets, judge rubrics |
| **6/7** | **Stage IV-A (Economics)** | `agents-cost-token-budget` | Pre-Save + On-Demand | `automations/prompts/agents_cost_token_budget_agent.md` | `tools/cost_token_budget_auditor.py`, `apps_model_telemetry/`, `agents/`, `scripts/`, `config/provider_profiles.yaml`, `pyproject.toml`, `tools/lint_secrets.py`, live prompt/semantic caching, dynamically derived $\text{ROI} \ge 2.5\times$ |
| **7/7** | **Stage IV-B (Verification)** | `agents-testing-gaps-assurance` | Pre-Save Hook + Skill | `automations/prompts/agents_testing_gaps_assurance_agent.md` | `tools/testing_gaps_auditor.py`, all 4 test roots (`tests/`, `resume_graph_engine/tests/`, `outreach_engine/tests/`, `apps_eval/tests/`), `.githooks/`, mock reachability, Class A/B `--timeout=60` test assurance |

---

## 3. Common Control Matrix (`C01–C12`)

Every `agents_*_agent.md` specification inherits and enforces the 12 mandatory controls below:

- **`C01` — Trusted Launch & Full-Repository Scope Boundary**:
  - `trust_level: workspace_trusted`, `sandbox_mode: workspace-write`, `network_access: disabled`.
  - Allowed write paths: `agents/`, `apps_model_telemetry/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `infrastructure/`, `data/`, `ops_scripts/`, `scripts/`, `tools/`, `tests/`, `config/`, `plans/`, `reports/`, `docs/`, `scratch/`, `automations/`, `.agents/`, `.antigravity/`, `.githooks/`, `AGENTS.md`, `pyproject.toml`, `.mcp.json`, `artifacts/`.
- **`C02` — Mandatory Phase 0 Single-Worktree Consolidation & Active Lease (`Step 0.1`)**:
  - Every run must deduplicate clean merged platform-spawned chat worktrees under lock, link `.venv`/`.agents`/`.antigravity`, register an active-run lease (`.sidecar_active_run.lock`), and provision a single canonical worktree off local `main` before any inspection or file write:
    `"/Users/amitayer/Git/agents/.venv/bin/python" "${PRIMARY_REPO_ROOT}/tools/prune_merged_chat_worktrees.py" --repo-root "${PRIMARY_REPO_ROOT}" --consolidate-sidecar --worktree-dir "${WORKTREE_DIR}" --branch "${BRANCH_NAME}"`
  - Record `PRE_STATE_SHA256` (`git -C "${WORKTREE_DIR}" rev-parse HEAD`) in `manifest.json`.
- **`C03` — Dual-Mode Execution & Overnight Staging (`INV-WT-EPHEMERAL-SCHEDULED`)**:
  - **`MODE: scheduled`** (`--non-interactive` or `CI=true`): Execute Phase 0 and Phase 1/1.5 read-only audits against `"${WORKTREE_DIR}"`. When `0` actionable findings exist (`B_total == 0`), skip Phase 2 plan creation (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`), copy `manifest.json` and `audit_report.json` to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/<agent_slug>/<run_id>/`, prune the clean zero-commit worktree via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only`, and exit `COMPLETE` without mutating `main`. When actionable findings exist (`B_total > 0`), execute Phase 2 wave-based remediation plan generation (`"${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md"` + `"${RUN_DIR}/implementation_plan.md"`), validate via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_implementation_plan.py" --file "${WORKTREE_DIR}/plans/<branch-slug>-<6hex>.md"`, copy durable artifacts to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/<agent_slug>/<run_id>/`, and when remediable findings pass all 5 proof points and `--timeout=60` pytest gates with decisive margin ($\Delta > 0.20$), commit on `"${BRANCH_NAME}"` and stage the verified branch for morning approval via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` without mutating `main`.
  - **`MODE: interactive`** (active operator session): Execute Phases 0–1.5; exit cleanly in preflight if `B_total == 0`, otherwise execute Phase 2 plan authoring, present the **Dimension Findings Table** and atomic `ask_question` HITL decision when calibrated margin $\Delta \le 0.20$, execute Phase 3 wave-by-wave remediation, verify 5-Point Counterfactual Runtime Proof with `--timeout=60` pytest gates, commit on `"${BRANCH_NAME}"`, obtain explicit operator `PR_MERGE_AUTHORIZATION` via `ask_question`, and promote into local `main` via `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(agents): <summary>"`.
- **`C04` — Unconditional Wave-Based Plan Mandate on Active Defects & Behavioral Preflight Fast-Exit (`UNCONDITIONAL_WAVE_PLAN_MANDATE` / `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`)**:
  - Every workflow's Phase 1.5 preflight MUST execute its dedicated fail-closed behavioral auditor (`storage_worktree_hygiene.py`, `ssot_boundary_auditor.py`, `e2e_functionality_auditor.py`, `retrieval_surface_auditor.py`, `validate_eval_rubrics.py`, `cost_token_budget_auditor.py`, `testing_gaps_auditor.py`). Generic commit-gate checks (`verify_commit.py`) or print-only inline scripts NEVER qualify for `PREFLIGHT_ZERO_DEFECT_FAST_EXIT`.
  - When the dedicated behavioral preflight auditor returns `0` actionable findings (`B_total == 0`), exit cleanly in preflight (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT`) and prune the zero-commit worktree without authoring synthetic no-op wave plans.
  - Whenever actionable findings exist (`B_total > 0`), every sidecar or skill healer run (**both `MODE: scheduled` and `MODE: interactive`**) MUST author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (500–800 words, hard ceiling 1,000 words) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), each containing:
    - `### Objective & Scope`
    - `### Milestones & Deliverables` (`[NEW]`, `[MODIFY]`, `[DELETE]`)
    - `### Acceptance Criteria`
    - `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`)
  - Every interactive remediation run with `B_total > 0` must remediate at least `Q_min = min(B_total, max(3, ceil(0.02 * B_domain)))` production defects (`INV-REMEDIATION-QUOTA-FLOOR`) and emit the 7-column Before/After Defect Accounting Table (`| Defect Category | Scanner Command | Unmasked Backlog (Before) | Remediated This Run | Remaining Backlog (After) | Net Delta | Exact Files Remediated |`, `INV-DEFECT-ACCOUNTING-TABLE-GATE`).
  - Every generated plan must pass `python3 tools/validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md` (`exit code 0`).
- **`C05` — Pre-HITL Dimension Findings Table & Atomic 20% Margin HITL Gate**:
  - Before invoking `ask_question`, output the markdown **Dimension Findings Table** (`| Dimension | Score / Status | Concrete Findings | Planned Action |`).
  - Compute multi-factor calibrated confidence via `tools/hitl_governance.py` (`calculate_calibrated_confidence`, `evaluate_hitl_surfacing_gate`, `HITLDecisionStore` at `artifacts/governance/hitl_decisions.sqlite`).
  - Surface one atomic `ask_question` decision at a time when $\Delta = c_{\text{top}} - c_{\text{second}} \le 0.20$; proceed autonomously under a sealed audit receipt when $\Delta > 0.20$ in interactive mode.
- **`C06` — Sequential Wave Execution & 5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`)**:
  - Never advance to Wave $N+1$ until Wave $N$ passes all 5 proof points:
    1. **Point 1 (Counterfactual Baseline & Delta)**: Capture `PRE_MUTATION_RUN` failure/metric before edit and `POST_MUTATION_RUN` pass/metric after edit (`PRE_SHA256 != POST_SHA256`).
    2. **Point 2 (Real Entrypoint Execution)**: Execute the real CLI/validator/pipeline entrypoint in a fresh subprocess (`timeout <= 120s`).
    3. **Point 3 (100% Diff Coverage & Pytest Protocol)**: Run scoped pytest (`/Users/amitayer/Git/agents/.venv/bin/pytest <test_file> -v --timeout=60`, `WaitMsBeforeAsync >= 15000`); never run bare `pytest`.
    4. **Point 4 (Independent State Verification)**: Verify filesystem/SQLite/AST state via an independent inspection command.
    5. **Point 5 (Durable 5-Column Proof Table)**: Record `| Wave / Rem ID | Pre-Mutation Failure / Metric | Post-Mutation Output / Metric | Entrypoint + Pytest Command | Receipt SHA-256 |`.
- **`C07` — Persistent Closed-Loop System Learning (`INV-AUTOMATION-PERSISTENT-LEARNING-LOOP`)**:
  - Query prior decisions from `HITLDecisionStore` (`artifacts/governance/hitl_decisions.sqlite`) during Phase 2 confidence scoring and write back terminal wave outcomes (`record_execution_outcome`) in Phase 3.
- **`C08` — Constitutional Floor & Production Purity**:
  - All `subprocess.run(..., shell=False, timeout=...)` calls require explicit timeouts; no `pytest.mark.skip` without `strict=True`; no bare `except Exception:` without guardian comment; zero golden fixtures imported in production paths (`python3 tools/lint_production_purity.py`); model identifiers must resolve against `config/provider_profiles.yaml`.
- **`C09` — Turn Gate & Tier-1 Commit Gate Compliance**:
  - Every wave commit must pass `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_turn_gates.py" --mode all --repository-root "${WORKTREE_DIR}"`, `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/verify_commit.py" --repo-root "${WORKTREE_DIR}"`, and `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/validate_sidecar_separation.py" --repo-root "${WORKTREE_DIR}" --json`.
- **`C10` — Governed Commit, Rebase, Review, Promotion & Worktree Teardown**:
  - Never rely on stateful `cd` across shell calls and never invoke raw unreviewed merge commands on `main`. Commit wave changes via `git -C "${WORKTREE_DIR}" commit`, then run `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --stage-only` in scheduled mode or `"${PRIMARY_REPO_ROOT}/.venv/bin/python" "${WORKTREE_DIR}/tools/pr_governance.py" -C "${WORKTREE_DIR}" submit "${BRANCH_NAME}" --title "fix(agents): <summary>"` after interactive `ask_question` `PR_MERGE_AUTHORIZATION`.
- **`C11` — Tested Python Runner Binding**:
  - Bind `PYTHON_BIN="/Users/amitayer/Git/agents/.venv/bin/python"` and `PYTEST_BIN="/Users/amitayer/Git/agents/.venv/bin/pytest"` (falling back to `python3` / `python3 -m pytest` only if `.venv` is absent).
- **`C12` — Output Brevity & Plain-Language Reporting**:
  - User-facing summaries must use plain layman English with zero technical jargon, zero `snake_case` identifiers, zero raw filenames in prose, zero em-dashes, and 120–300 words maximum.
