# Agents Repository Shared Scheduled Automation Governance Contract (`_shared_governance_contract.md`)

<!-- GOVERNED COMMON CONTRACT: urn:agents:scheduled-task-common-control-matrix:1.0.0 -->
<!-- INVARIANT: INV-REPO-SEPARATION-AGENTS-ONLY -->
<!-- INVARIANT: INV-DEOVERLAP-SHARED-CONTRACT -->
<!-- C01: Trusted Launch & Scope: Read-only discovery in MODE: scheduled; mutations only in MODE: interactive after HITL approval -->
<!-- C02: Bounded Authority: Execution confined strictly to /Users/amitayer/Git/agents and its isolated worktrees -->
<!-- C03: Change Accounting: Every candidate tracked with disposition (applied, skipped, deferred, blocked) -->
<!-- C04: Evidence Action Outcome: RunManifest emitted to artifacts/sidecar_runs/<agent_slug>/<run_id>/manifest.json -->
<!-- C05: Durable Identity & Closure: Durable findings ledger tracks stable finding_id across runs -->
<!-- C06: Reproducible Reconciliation: Pre/post state hashes recorded in RunManifest -->
<!-- C07: Honest Coverage: Checked vs unchecked scopes explicitly enumerated -->
<!-- C08: Sealed Evidence: SHA-256 digests verified prior to completion claim -->
<!-- C09: Failure Lifecycle: Failures record terminal_outcome=FAILED with diagnostic_artifact_paths -->
<!-- C10: Bounded Repeat Execution: Idempotent re-execution with single-instance lock -->
<!-- C11: Tested Executable Binding: Bound to tools/validate_sidecar_separation.py and tools/verify_commit.py -->
<!-- C12: Preserve Guardrails: Zero weakening of existing gates, tests, or safety invariants -->

This document is the canonical shared governance contract (`urn:agents:scheduled-task-common-control-matrix:1.0.0`) inherited by all 7 scheduled and interactive automation agent prompts in `/Users/amitayer/Git/agents/automations/prompts/agents_*_agent.md` and synchronized across `/Users/amitayer/.gemini/config/sidecars/agents-*/sidecar.json`.

---

## 1. Strict Cross-Repository Isolation Firewall (`INV-REPO-SEPARATION-AGENTS-ONLY`)

1. **Exclusive Workspace Containment**:
   - Every `agents-*` sidecar executes strictly within `/Users/amitayer/Git/agents` (and its isolated git worktrees under `/Users/amitayer/Git/agents/.worktrees/` or `/Users/amitayer/.gemini/antigravity/worktrees/agents/`).
   - **Hard Prohibition on Decision Intelligence Engine Access**: Reading, writing, executing commands, or mutating any file, worktree, SQLite database (`CANONICAL_GRAPH.db`, `graph.sqlite`), or sidecar configuration belonging to `/Users/amitayer/Git/decision-intelligence-engine` is strictly prohibited and triggers immediate fail-closed termination (`CROSS_REPO_BOUNDARY_VIOLATION`).
2. **Namespace & Display Prefix Isolation**:
   - All global sidecar folders for this repository in `/Users/amitayer/.gemini/config/sidecars/` MUST use the `agents-` directory prefix (`agents-storage-worktree-hygiene`, `agents-ssot-boundary-governance`, `agents-outreach-resume-functionality`, `agents-research-retrieval-surface`, `agents-evals-judge-assurance`, `agents-cost-token-budget`, `agents-testing-gaps-assurance`).
   - All `display_name` values MUST begin with `"Agents Repo: "` so they never collide with the 17 Decision Intelligence Engine sidecars.
3. **Disjoint Schedule Window (05:30–07:00 America/New_York)**:
   - To eliminate CPU, memory, and provider rate-limit contention with the Decision Intelligence Engine overnight sequence (02:00–05:00 ET), all 7 `agents-*` sidecars execute sequentially between `05:30 ET` and `07:00 ET` spaced 15 minutes apart.

---

## 2. Master 7-Agent Causal Execution Sequence

1. **Order 1/7 (`05:30 ET`) — Agents Repo: Storage & Worktree Hygiene** (`agents-storage-worktree-hygiene` -> `automations/prompts/agents_storage_worktree_hygiene_agent.md`): Prunes stale runtime proof directories (`artifacts/apps_rg/runtime_proofs`), superseded evaluation packages (`superseded_apps_eval_packages`), stale research run bundles, and merged git worktrees.
2. **Order 2/7 (`05:45 ET`) — Agents Repo: SSOT & Boundary Governance** (`agents-ssot-boundary-governance` -> `automations/prompts/agents_ssot_boundary_agent.md`): Enforces model pin alignment (`config/provider_profiles.yaml`, `resume_graph_engine/config/models/registry.yaml`), 600-line file budgets (`tools/lint_architecture_boundaries.py`), layer import isolation (`tools/lint_layer_imports.py`), `sys.path` purity, and model-neutral naming (`tools/lint_model_neutral_naming.py`).
3. **Order 3/7 (`06:05 ET`) — Agents Repo: Outreach & Resume Functionality** (`agents-outreach-resume-functionality` -> `automations/prompts/agents_e2e_functionality_assurance_agent.md`): Audits live execution across `resume_engine` (`run`, `eval`, `show`, `bootstrap`, `patch-run`, `preflight`, `doctor`), `OutreachOrchestrator` (`generate_single_draft`, `generate_full_campaign`, `resume_or_patch_run`), and `AppsResearchBridge` (`apps_research.v1`/`v2` handoff envelopes).
4. **Order 4/7 (`06:15 ET`) — Agents Repo: Research & Retrieval Surface** (`agents-research-retrieval-surface` -> `automations/prompts/agents_research_retrieval_surface_agent.md`): Audits `GovernedResearchRun` (`L1 -> L0 -> C0 -> L2 -> L5+L6`), `ResearchRetrievalEngine` (`ChromaResearchStore` vs `InMemoryResearchStore`), candidate fact vector indexing (`fact_vectors_bootstrap`), and persisted targeting brief bundle reuse (`_find_valid_persisted_artifact_bundle`).
5. **Order 5/7 (`06:30 ET`) — Agents Repo: Evals & Judge Validity** (`agents-evals-judge-assurance` -> `automations/prompts/agents_evals_judge_assurance_agent.md`): Audits construct validity and anti-tautology across the 9 Outreach hard gates (`SpamTriggerValidator`, `ChannelLengthValidator`, `QuestionEndingValidator`, `GroundingValidator`, `EmDashValidator`, `MarkdownLinkValidator`, `SubordinateToneValidator`, `ForbiddenClaimsValidator`, `UnsupportedPersonalizationValidator`), `RubricJudgeEvaluator`, Resume `X3D_ALLOW_FINISH` exit gates, and the `X2_RESEARCH_SEMANTIC_GATE` handoff judge.
6. **Order 6/7 (`06:45 ET`) — Agents Repo: Cost & Token Budget** (`agents-cost-token-budget` -> `automations/prompts/agents_cost_token_budget_agent.md`): Audits the 24,000-token `X2` research judge preflight cap (`_x2_prompt_budget_receipt`), `ResearchBoundaryPolicy` per-call and cumulative dollar limits (`cost_limit_usd`), and cross-engine briefing reuse between `resume_engine` and `outreach_engine`.
7. **Order 7/7 (`07:00 ET`) — Agents Repo: Testing Gaps Assurance** (`agents-testing-gaps-assurance` -> `automations/prompts/agents_testing_gaps_assurance_agent.md`): Audits negative-control and edge-case test coverage across blocked campaign touches, failed-lane `patch-run` recovery, unverified `HERMETIC_FALLBACK` rejection, and `pytest --timeout=60` compliance.

---

## 3. Dual-Mode Execution & Wave Governance

- **Scheduled Mode (`MODE: scheduled`)**: Strictly read-only discovery and sealed reporting under `artifacts/sidecar_runs/<agent_slug>/<run_id>/`. Never mutate tracked files or invoke `ask_question` in unattended cron runs; emit `OPERATOR_INPUT_REQUIRED` when remediation waves are proposed.
- **Interactive Mode (`MODE: interactive`)**: Create or verify an isolated feature worktree off `main`, author a sequential wave plan under `plans/<slug>-<6hex>.md`, validate via `python3 tools/validate_implementation_plan.py --file plans/<slug>-<6hex>.md`, present atomic HITL choices via `ask_question` when margin $\Delta \le 20\%$, verify changes with scoped `pytest <test_file> -v --timeout=60` and `python3 tools/verify_commit.py`, and clean up the feature worktree after merge.
