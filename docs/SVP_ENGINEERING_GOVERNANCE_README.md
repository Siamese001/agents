# Repository Governance Architecture

This repository is engineered and governed as a production control plane, not merely an application codebase with unit tests.

The active governance model enforces four mechanical layers:

1. **Pre-Turn & Lifecycle Hook Discipline**: Repo-owned rules, skills, lifecycle hooks, and delegation contracts under `.agents/` and `.antigravity/`.
2. **Commit-Time Structural Verification**: Deterministic Git hooks (`.githooks/`) and Tier 1 static verifiers (`tools/verify_commit.py`).
3. **Compile-Time Architecture & Boundary Auditing**: AST-based layer import enforcement (`L0`–`L6`), domain storage isolation, production purity, and tokenomics ROI gates.
4. **Runtime & Cross-Subsystem Proof**: End-to-end authoritative smoke verification, cryptographic cross-app handoff envelopes, and isolated sidecar automation.

In this architecture, unit tests prove runtime behavior, while deterministic AST and turn-gate validators prove that the codebase remains **structurally governable** as engineering headcount and AI-assisted velocity scale.

---

## Executive Summary

Most engineering organizations rely on code review and unit tests as their sole quality layer. Under high-velocity AI-assisted development, prose conventions rapidly erode into cross-layer coupling, direct database bypasses, hardcoded provider tokens, and unbounded retry loops.

This repository enforces a four-tier mechanical control loop:

```text
Lifecycle Hook Discipline  -> .agents/rules/, .agents/hooks.json, tools/hook_dispatch.py
Turn & Plan Gatekeeping    -> tools/validate_turn_gates.py, tools/validate_implementation_plan.py
Tier 1 Commit Verification -> tools/verify_commit.py, tools/lint_architecture_boundaries.py
Runtime & Economics Proof  -> tools/cost_token_budget_auditor.py, ops_scripts/run_e2e_authoritative_smoke.py
```

---

## Why This Matters to Senior Engineering Leadership

At organizational scale, engineering leadership must answer three operational questions:

1. **Can the platform scale across multiple squads without accumulating silent architectural drift?**
2. **Are unit economics, token budgets, and latency ceilings mechanically bounded before deployment?**
3. **Can autonomous and AI-assisted development run at high velocity without bypassing security, branch, or write controls?**

This repository answers all three by turning architectural invariants into fast (`< 5s`), machine-checkable gates that execute on every turn, commit, and merge.

---

## Layer 1: Lifecycle Hook & Turn-Gate Discipline

Repo-owned governance assets live under `.agents/`, `.antigravity/`, and `tools/`:

| Surface | Role | Canonical Path |
| :--- | :--- | :--- |
| **Root Operating Contract** | Memory-bounded (`<= 200` lines) primary execution contract | [`AGENTS.md`](../AGENTS.md) |
| **Conformance Map** | Maps every operating invariant to its enforcing tool and test | [`.agents/rules/conformance-map.md`](../.agents/rules/conformance-map.md) |
| **Governance Rules** | Wave progression, HITL ambiguity margin (`20%`), PR queue lock | [`.agents/rules/`](../.agents/rules/) |
| **Procedural Skills** | Reusable operational gates, scope containment, security hardening | [`.agents/skills/`](../.agents/skills/) |
| **Native Lifecycle Hooks** | Pre-tool and post-tool intercepts on edits, commands, and plans | [`.agents/hooks.json`](../.agents/hooks.json) & [`tools/hook_dispatch.py`](../tools/hook_dispatch.py) |
| **Runtime Boundary** | Workspace path containment and cross-repo isolation rules | [`.antigravity/runtime-boundary.json`](../.antigravity/runtime-boundary.json) |

Verify Layer 1 directly from the repository root:

```bash
python tools/validate_turn_gates.py --mode all
```

---

## Layer 2: Tier 1 Commit & Architectural Boundary Verification

Every commit and PR review executes [`tools/verify_commit.py`](../tools/verify_commit.py) and [`tools/lint_architecture_boundaries.py`](../tools/lint_architecture_boundaries.py), enforcing five non-bypassable categories:

1. **Standard Code Hygiene**: In-memory AST syntax and compilation verification across all Python modules.
2. **File Budgets & Layer Hierarchy**: Enforces the `<= 600` line ceiling per production module (`tools/lint_file_budgets.py`), unidirectional `L0`–`L6` layer imports (`tools/lint_layer_imports.py`), and model-neutral naming (`tools/lint_model_neutral_naming.py`).
3. **Domain Storage Isolation & `sys.path` Purity**: Verifies zero concrete persistence imports (`sqlite3`, filesystem stores) inside domain synthesis or pipeline services and zero `sys.path` mutations across production entrypoints.
4. **Production Derivation Purity**: AST scanner (`tools/lint_production_purity.py`) prohibiting test fixtures or predetermined golden outputs from being imported in production paths.
5. **Secrets & Schema Integrity**: Deterministic credential scanning (`tools/lint_secrets.py`) and declarative config validation (`tools/lint_contract_schemas.py`).

Run the complete Tier 1 structural audit:

```bash
python tools/verify_commit.py --all
python tools/lint_architecture_boundaries.py
```

---

## Layer 3: Tokenomics, Sidecar Isolation & Worktree Hygiene

Beyond code structure, the platform continuously audits operational economics and workspace state:

- **Tokenomics & Multi-Tier Caching ROI (`>= 2.5x` Pareto Floor)**: [`tools/cost_token_budget_auditor.py`](../tools/cost_token_budget_auditor.py) evaluates 8 pillars of token efficiency, prompt caching, and bounded retry ceilings.
- **Autonomous Sidecar Isolation (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: [`tools/validate_sidecar_separation.py`](../tools/validate_sidecar_separation.py) verifies namespace, prompt, and schedule separation across the 7 scheduled automation agents.
- **Storage & Worktree Hygiene**: [`tools/storage_worktree_hygiene.py`](../tools/storage_worktree_hygiene.py) audits SQLite WAL health, stale worktrees, and merged branch pruning.
- **Serialized FIFO PR Merge Queue**: [`tools/pr_governance.py`](../tools/pr_governance.py) enforces trunk reservation locking (`.git/governed_merge_queue.lock`), automatic branch catch-up, and two-parent `--no-ff` merges into `main`.

Run the operational governance auditors:

```bash
python tools/cost_token_budget_auditor.py
python tools/validate_sidecar_separation.py
python tools/storage_worktree_hygiene.py
```

---

## Layer 4: Reviewer Inspection Path

For a rapid, falsifiable technical audit of this repository:

1. Read [`README.md`](../README.md) for platform invariants and benchmark economics.
2. Read [`docs/EXECUTIVE_OVERVIEW.md`](EXECUTIVE_OVERVIEW.md) and [`docs/RECRUITER_GUIDE.md`](RECRUITER_GUIDE.md) for the operating model and reliability economics.
3. Read [`docs/RUNTIME_CONTROL_PLANE.md`](RUNTIME_CONTROL_PLANE.md) for the `U0 → L1 → L0 → C0 → L2 → Exit → UWG → L4/L6` execution model.
4. Execute the verification suite:

```bash
python tools/validate_turn_gates.py --mode all
python tools/verify_commit.py --all
python tools/lint_architecture_boundaries.py
python tools/cost_token_budget_auditor.py
python ops_scripts/run_e2e_authoritative_smoke.py
```
