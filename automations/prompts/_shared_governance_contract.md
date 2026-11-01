# Agents Repository — Scheduled Automation Agents Shared Governance Contract (`C01–C12`)
<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY | UNCONDITIONAL_WAVE_PLAN_MANDATE | INV-RUNTIME-PROOF-5POINT | INV-AUTOMATION-PERSISTENT-LEARNING-LOOP -->

## 1. Repository Isolation & Namespace Invariant (`INV-REPO-SEPARATION-AGENTS-ONLY`)

1. **Workspace Containment**: All `agents-*` sidecar automation agents are bound exclusively to `/Users/amitayer/Git/agents` and its ephemeral worktrees under `/Users/amitayer/Git/agents/.worktrees/agents-*`.
2. **Zero Cross-Repository Mutation**: Sidecar agents in this repository are strictly forbidden from reading, modifying, locking, or writing to any file, database, worktree, or sidecar configuration belonging to external repositories.
3. **Artifact Isolation**: All automation runtime artifacts, manifests, plans, and receipts must be written exclusively inside `<WORKTREE_DIR>/artifacts/sidecar_runs/<agent_slug>/<run_id>/` and `<WORKTREE_DIR>/plans/<branch-slug>-<6hex>.md`.
4. **Sidecar Identifier Prefix**: Every global sidecar directory under `/Users/amitayer/.gemini/config/sidecars/` for this repository must start with `agents-`, use title prefix `"Agents Repo: ..."`, and stagger its cron schedule across `05:30–07:00 America/New_York` (`30 5`, `45 5`, `5 6`, `15 6`, `30 6`, `45 6`, `0 7`).

---

## 2. Master Causal Execution Sequence (`05:30–07:00 ET`)

| Order | Stage | Sidecar ID | Cron (`America/New_York`) | Canonical Prompt Specification | Target Surface |
| :---: | :---: | :--- | :---: | :--- | :--- |
| **1/7** | **Stage I (Foundation)** | `agents-storage-worktree-hygiene` | `30 5 * * *` (`05:30 ET`) | `automations/prompts/agents_storage_worktree_hygiene_agent.md` | `.worktrees/`, `artifacts/`, SQLite/WAL health, git branch pruning |
| **2/7** | **Stage II (Governance)** | `agents-ssot-boundary-governance` | `45 5 * * *` (`05:45 ET`) | `automations/prompts/agents_ssot_boundary_agent.md` | `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `infrastructure/` boundaries |
| **3/7** | **Stage III-A (Core E2E)** | `agents-outreach-resume-functionality` | `5 6 * * *` (`06:05 ET`) | `automations/prompts/agents_e2e_functionality_assurance_agent.md` | Outreach (`apps_lic`), Resume (`apps_rg`), and Research (`apps_research`) E2E pipelines |
| **4/7** | **Stage III-B (Retrieval)** | `agents-research-retrieval-surface` | `15 6 * * *` (`06:15 ET`) | `automations/prompts/agents_research_retrieval_surface_agent.md` | `apps_research/` & `resume_graph_engine/` hybrid retrieval, chunking, provenance, cache parity |
| **5/7** | **Stage III-C (Evaluation)** | `agents-evals-judge-assurance` | `30 6 * * *` (`06:30 ET`) | `automations/prompts/agents_evals_judge_assurance_agent.md` | `apps_eval/`, `tools/eval/`, `tools/lint_production_purity.py`, judge rubrics & golden datasets |
| **6/7** | **Stage IV-A (Economics)** | `agents-cost-token-budget` | `45 6 * * *` (`06:45 ET`) | `automations/prompts/agents_cost_token_budget_agent.md` | `config/provider_profiles.yaml`, prompt caching, token budgets, $\text{ROI} \ge 2.5\times$ |
| **7/7** | **Stage IV-B (Verification)** | `agents-testing-gaps-assurance` | `0 7 * * *` (`07:00 ET`) | `automations/prompts/agents_testing_gaps_assurance_agent.md` | `tests/`, critical path coverage gaps, Class A/B `--timeout=60` test assurance |

---

## 3. Common Control Matrix (`C01–C12`)

Every `agents_*_agent.md` specification inherits and enforces the 12 mandatory controls below:

- **`C01` — Trusted Launch & Scope Boundary**:
  - `trust_level: workspace_trusted`, `sandbox_mode: workspace-write`, `network_access: disabled`.
  - Allowed write paths: `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, `infrastructure/`, `tools/`, `tests/`, `config/`, `plans/`, `artifacts/sidecar_runs/`.
- **`C02` — Mandatory Phase 0 Isolated Worktree Provisioning (`Step 0.1`)**:
  - Every run must create a fresh worktree off local `main` before any inspection or file write:
    `git worktree add .worktrees/<branch_slug> -b <branch_name> main`
  - Record `PRE_STATE_SHA256` (`git rev-parse HEAD`) in `manifest.json`.
- **`C03` — Dual-Mode Execution & Ephemeral Scheduled Worktrees (`INV-WT-EPHEMERAL-SCHEDULED`)**:
  - **`MODE: scheduled`** (`--non-interactive` or `CI=true`): Execute Phase 0, Phase 1/1.5 read-only audits, and **Phase 2 mandatory wave-based remediation plan generation** (`plans/<branch-slug>-<6hex>.md` + `<run_dir>/implementation_plan.md`), validate the plan via `python3 tools/validate_implementation_plan.py --file plans/<branch-slug>-<6hex>.md`, copy durable artifacts (`manifest.json`, `audit_report.json`, `implementation_plan.md`) to `<PRIMARY_REPO_ROOT>/artifacts/sidecar_runs/<agent_slug>/<run_id>/`, prune the ephemeral worktree and branch (`git worktree remove --force`, `git branch -D`), and exit `COMPLETE` (0 findings) or `OPERATOR_INPUT_REQUIRED` ($\ge 1$ finding). **Zero code mutations in scheduled mode.**
  - **`MODE: interactive`** (active operator session): Execute Phases 0–2, present the mandatory **Dimension Findings Table** and atomic `ask_question` HITL decision when calibrated margin $\Delta \le 0.20$, execute Phase 3 wave-by-wave remediation, verify 5-Point Counterfactual Runtime Proof, commit, rebase onto `main`, merge `--no-ff` to local `main`, and prune the worktree and branch.
- **`C04` — Unconditional Wave-Based Plan Mandate (`UNCONDITIONAL_WAVE_PLAN_MANDATE`)**:
  - Every sidecar agent run (**both `MODE: scheduled` and `MODE: interactive`**) MUST author a wave-based remediation plan at `plans/<branch-slug>-<6hex>.md` (500–800 words, hard ceiling 1,000 words) decomposed into sequential numbered waves (`## Wave 1: ...`, `## Wave 2: ...`), each containing:
    - `### Objective & Scope`
    - `### Milestones & Deliverables` (`[NEW]`, `[MODIFY]`, `[DELETE]`)
    - `### Acceptance Criteria`
    - `### Runtime Receipt & Completion Gate` (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`)
    - `## Wave Implementation & Completion Status Table` (`| Wave | Description / Scope | Status |`)
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
  - Every wave commit must pass `python3 tools/validate_turn_gates.py --mode all`, `python3 tools/verify_commit.py`, and `python3 tools/validate_sidecar_separation.py --json`.
- **`C10` — Three-Step Commit, Rebase, Local Main Merge & Worktree Pruning**:
  - Commit wave changes on `<branch_name>`, rebase onto local `main` (`git rebase main`), fast-forward/merge into `/Users/amitayer/Git/agents` (`git merge --no-ff <branch_name>`), and immediately remove the worktree and branch (`git worktree remove --force <WORKTREE_DIR>`, `git branch -d <branch_name>`).
- **`C11` — Tested Python Runner Binding**:
  - Bind `PYTHON_BIN="/Users/amitayer/Git/agents/.venv/bin/python"` and `PYTEST_BIN="/Users/amitayer/Git/agents/.venv/bin/pytest"` (falling back to `python3` / `python3 -m pytest` only if `.venv` is absent).
- **`C12` — Output Brevity & Plain-Language Reporting**:
  - User-facing summaries must use plain layman English with zero technical jargon, zero `snake_case` identifiers, zero raw filenames in prose, zero em-dashes, and 120–300 words maximum.
