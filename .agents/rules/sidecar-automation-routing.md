# Sidecar Automation Routing & Cross-Repository Firewall (`agents-*`)

Governs the 7 scheduled and interactive sidecar automation agents for the `agents` repository (`agents/`, `apps_model_telemetry/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `apps_research/`, `apps_eval/`, and `infrastructure/`), ensuring strict isolation from all Decision Intelligence Engine sidecars.

## 1. Cross-Repository Isolation Invariant (`INV-REPO-SEPARATION-AGENTS-ONLY`)

- **Exclusive Workspace Scope**: When operating in `/Users/amitayer/Git/agents` (or any of its worktrees under `.worktrees/` or `.gemini/antigravity/worktrees/agents/`), interactive sidecar triggers resolve **exclusively** to the 7 `agents-*` sidecars in `/Users/amitayer/.gemini/config/sidecars/agents-*/sidecar.json` and their prompt specifications in `automations/prompts/agents_*_agent.md`.
- **Zero Cross-Repository Mutation**: No `agents-*` sidecar may read, write, or execute commands against `/Users/amitayer/Git/decision-intelligence-engine` or its knowledge graph databases (`CANONICAL_GRAPH.db`, `graph.sqlite`).
- **Disjoint Schedule Window (`05:00`–`07:30 America/New_York`, 25-Minute Spacing)**: All 7 `agents-*` sidecars execute at 25-minute collision-safe intervals (`05:00`, `05:25`, `05:50`, `06:15`, `06:40`, `07:05`, `07:30 ET`), avoiding `05:20 ET` (`energy-utilities-best-practices`) and `06:00 ET` (`corner-foresight-blindspot-scout`).

## 2. Registered `agents-*` Sidecar Roster

| Order | Sidecar Directory (`~/.gemini/config/sidecars/`) | Display Name | Schedule (`America/New_York`) | Canonical Prompt Specification | Interactive Triggers (in `agents` workspace) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1/7** | `agents-storage-worktree-hygiene` | `Agents Repo: Storage & Worktree Hygiene` | `0 5 * * *` (`05:00 ET`) | `automations/prompts/agents_storage_worktree_hygiene_agent.md` | `"run agents storage hygiene"`, `"run storage hygiene"`, `"run worktree hygiene"` |
| **2/7** | `agents-ssot-boundary-governance` | `Agents Repo: SSOT & Boundary Governance` | `25 5 * * *` (`05:25 ET`) | `automations/prompts/agents_ssot_boundary_agent.md` | `"run agents ssot agent"`, `"run ssot remediation"`, `"run boundary governance"` |
| **3/7** | `agents-outreach-resume-functionality` | `Agents Repo: Outreach & Resume Functionality` | `50 5 * * *` (`05:50 ET`) | `automations/prompts/agents_e2e_functionality_assurance_agent.md` | `"run agents functionality agent"`, `"run functionality assurance"`, `"run outreach resume e2e"` |
| **4/7** | `agents-research-retrieval-surface` | `Agents Repo: Research & Retrieval Surface` | `15 6 * * *` (`06:15 ET`) | `automations/prompts/agents_research_retrieval_surface_agent.md` | `"run agents retrieval agent"`, `"run research retrieval surface"`, `"run retrieval surface"` |
| **5/7** | `agents-evals-judge-assurance` | `Agents Repo: Evals & Judge Validity` | `40 6 * * *` (`06:40 ET`) | `automations/prompts/agents_evals_judge_assurance_agent.md` | `"run agents evals agent"`, `"run evals judge assurance"`, `"run evals surface"` |
| **6/7** | `agents-cost-token-budget` | `Agents Repo: Cost & Token Budget` | `5 7 * * *` (`07:05 ET`) | `automations/prompts/agents_cost_token_budget_agent.md` | `"run agents cost agent"`, `"run cost token budget"`, `"run tokenomics"` |
| **7/7** | `agents-testing-gaps-assurance` | `Agents Repo: Testing Gaps Assurance` | `30 7 * * *` (`07:30 ET`) | `automations/prompts/agents_testing_gaps_assurance_agent.md` | `"run agents testing gaps"`, `"run testing gaps"` |

## 3. Mechanical Verification

Run `python3 tools/validate_sidecar_separation.py --json` to verify namespace prefixes, prompt dereferencing, workspace permission containment, 25-minute schedule spacing, and untouched preservation of all active Decision Intelligence Engine sidecars.
