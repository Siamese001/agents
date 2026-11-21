# Agent Guidance — Agentic-Workflow

## Plan First. Execute Second.

Root `AGENTS.md` is the primary agent execution adapter. Repo governance, rules, and skills live under `.agents/` and `.antigravity/`.

**Bug Fixes, `/boost`, & `/swarm` (Zero Blast-Radius Ceiling, `INV-REFACTOR-EXTENT-UNBOUNDED`, `INV-ZERO-BUGFIX-BLAST-RADIUS-CAP`)**: Whenever a bug is found or `/boost` / `/swarm` is invoked, trace the defect to its root cause and fix all impacted upstream producers, shared domain contracts, consumers, validators, and tests across the repository immediately with zero file-count, file-size, line-count, wave-count, or blast-radius limits (preserving directional inter-subsystem and storage import boundaries).

**Planned Architecture & Refactors**: For open-ended design or multi-wave architectural work, inspect connected upstream/downstream dependencies (`.agents/rules/scope-containment.md`) and align coupled contracts cohesively. See `.agents/rules/plan-first-enforcement.md`.

## Wave Refactoring Protocol

Before performing refactoring work, read and follow `docs/refactoring-wave-protocol.md`:

- Align all coupled upstream/downstream spine dependencies (`INV-REFACTOR-EXTENT-UNBOUNDED`) across as many files, lines, subsystems, or waves as needed; cohesive submodule decomposition behind a facade and shared domain contracts are authorized with zero file-size or line-ratchet caps (`INV-BUDGET-FILE-LINES = 0`).
- Fix newly discovered root-cause bugs immediately across all impacted components rather than deferring them to a backlog.
- Preserve behavior not explicitly targeted and avoid unrelated drift in uncoupled code.
- Parallel `/boost` and `/swarm` workers may execute concurrently without artificial wave-count, file-count, or disjoint-file freezes, provided directional inter-subsystem and storage import boundaries hold.
- Validate each wave or shard with concrete runtime and test evidence before claiming completion.

## MCP Quick Reference

Stable server IDs are defined in root `.mcp.json` (the sole MCP SSOT). Optional transports (`adg_sqlite`, `memory`, `vector_db`, `playwright`, `notion`, `deepwiki`, `context7`, `GitKraken`, `filesystem`) never block work when offline; fall back directly to local AST/grep inspection and native tools.

## Constitutional floor

- Subprocess timeout required: `subprocess.run(argv, shell=False, timeout=30)`.
- No `pytest.mark.xfail` without `strict=True` and no `pytest.mark.skip` without explicit `reason=`.
- No bare `except:` or `except Exception` without `# guardian: allow-<type> -- <specific justification>`.
- Honor explicit `PLAN ONLY` / `NO IMPLEMENT` prompts; otherwise execute root-cause bug fixes, `/boost`, and `/swarm` end-to-end.
- Use ADG (`adg_sqlite`), AST inspection, and `grep_search` freely together; never self-block when `adg_sqlite` is offline.
- Output Brevity & Word Budget Invariant: target ~150-250 words, ceiling 450 words (5,000 visible prose characters, excluding `### Evidence & Graph Lineage` footers and link URLs).
- Full rules: `.agents/rules/constitutional.md` and `.agents/rules/conformance-map.md`.

## Production Derivation Integrity

> Every domain-bearing production artifact must be derived from runtime source inputs plus approved configuration through the declared execution path. Golden outputs, expected answers, reference graphs, pinned evaluations, benchmark fixtures, and precomputed domain conclusions may be used for testing/evaluation but must not substitute for production generation, reasoning, evaluation, or publication.

No production-executable directory may evade applicable architecture governance merely because of directory placement.

## Plans

Plans are disk-only under `plans/<name>-<6hex>.md` (Notion plan/wave/status enforcement is retired). Validate wave plans via `tools/validate_implementation_plan.py`.

## Pytest

Pytest runs with plugin **autoload ON** (CI default); `addopts` carries `--timeout=180` in `pytest.ini`. Do **not** set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Debug and verification runs permit single files, named cases, coupled multi-file slices, or full subsystem/repository test suites (`--timeout=60` or `--timeout=180`) without batch-size restrictions.

## Subsystems vs Infrastructure (summary)

Production code is partitioned across 11 executable package roots with zero unowned modules:
- **Autonomous Subsystems (7)**: `agents/`, `apps_eval/`, `apps_model_telemetry/`, `apps_research/`, `outreach_engine/`, `resume_engine/`, and `resume_graph_engine/`.
- **Shared Infrastructure & Operations (4)**: `infrastructure/`, `ops_scripts/`, `scripts/`, and `tools/`.

Cross-subsystem direct imports are blocked by `tools/ssot_boundary_auditor.py` and `tools/lint_architecture_boundaries.py`.

## Antigravity Execution Adapter

Repo-owned governance assets live under `.agents/`, `.antigravity/`, `.githooks/`, `config/governance/`, and `tools/`:

- **Rules & Skills**: `.agents/rules/*.md` and `.agents/skills/*/SKILL.md`.
- **Lifecycle Hooks**: `.agents/hooks.json` dispatched via `tools/hook_dispatch.py`.
- **Turn & Commit Gates**: `tools/validate_turn_gates.py`, Tier 1 `tools/verify_commit.py`, and Tier 2 `tools/verify_main_readiness.py` (10 risk-tiered stages including `tools/audit_governance_harmonization.py` and `tools/testing_gaps_auditor.py`).
- **MCP & Runtime Boundary**: Root `.mcp.json` and `.antigravity/runtime-boundary.json`.
- **On-Demand Assurance Workflows (`INV-REPO-SEPARATION-AGENTS-ONLY`)**: Unattended daily background schedules are disabled (`enabled: false`, `0` active schedules). 4 consolidated manual launchers live in `automations/prompts/agents_*_agent.md` (`_shared_governance_contract.md`, `.agents/rules/sidecar-automation-routing.md`, validated by `tools/validate_sidecar_separation.py`).
- **Governed PR Queue & Worktree Hygiene**: Feature branches merge into local `main` via `tools/pr_governance.py` under `.git/governed_merge_queue.lock` (`.agents/rules/pr-governance.md`). Direct commits to `main` are blocked by `.githooks/pre-commit`. Prune merged worktrees and branches cleanly after merge.
