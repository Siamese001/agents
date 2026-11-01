# Sidecar Automation Routing & Cross-Repository Firewall (`agents-*`)

Governs the 7 scheduled and interactive sidecar automation agents for the `agents` repository (`outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, and `apps_research/`), ensuring strict isolation from the 17 Decision Intelligence Engine sidecars.

## 1. Cross-Repository Isolation Invariant (`INV-REPO-SEPARATION-AGENTS-ONLY`)

- **Exclusive Workspace Scope**: When operating in `/Users/amitayer/Git/agents` (or any of its worktrees under `.worktrees/` or `.gemini/antigravity/worktrees/agents/`), interactive sidecar triggers resolve **exclusively** to the 7 `agents-*` sidecars in `/Users/amitayer/.gemini/config/sidecars/agents-*/sidecar.json` and their prompt specifications in `automations/prompts/agents_*_agent.md`.
- **Zero Cross-Repository Mutation**: No `agents-*` sidecar may read, write, or execute commands against `/Users/amitayer/Git/decision-intelligence-engine` or its knowledge graph databases (`CANONICAL_GRAPH.db`, `graph.sqlite`).
- **Disjoint Schedule Window (`05:30`–`07:00 America/New_York`)**: All 7 `agents-*` sidecars execute after the Decision Intelligence Engine overnight sequence (`01:00`–`05:00 ET`), avoiding `06:00 ET` (`corner-foresight-blindspot-scout`).

## 2. Registered `agents-*` Sidecar Roster

| Order | Sidecar Directory (`~/.gemini/config/sidecars/`) | Display Name | Schedule (`America/New_York`) | Canonical Prompt Specification | Interactive Triggers (in `agents` workspace) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1/7** | `agents-storage-worktree-hygiene` | `Agents Repo: Storage & Worktree Hygiene` | `30 5 * * *` (`05:30 ET`) | `automations/prompts/agents_storage_worktree_hygiene_agent.md` | `"run agents storage hygiene"`, `"run storage hygiene"`, `"run worktree hygiene"` |
| **2/7** | `agents-ssot-boundary-governance` | `Agents Repo: SSOT & Boundary Governance` | `45 5 * * *` (`05:45 ET`) | `automations/prompts/agents_ssot_boundary_agent.md` | `"run agents ssot agent"`, `"run ssot remediation"`, `"run boundary governance"` |
| **3/7** | `agents-outreach-resume-functionality` | `Agents Repo: Outreach & Resume Functionality` | `5 6 * * *` (`06:05 ET`) | `automations/prompts/agents_e2e_functionality_assurance_agent.md` | `"run agents functionality agent"`, `"run functionality assurance"`, `"run outreach resume e2e"` |
| **4/7** | `agents-research-retrieval-surface` | `Agents Repo: Research & Retrieval Surface` | `15 6 * * *` (`06:15 ET`) | `automations/prompts/agents_research_retrieval_surface_agent.md` | `"run agents retrieval agent"`, `"run research retrieval surface"`, `"run retrieval surface"` |
| **5/7** | `agents-evals-judge-assurance` | `Agents Repo: Evals & Judge Validity` | `30 6 * * *` (`06:30 ET`) | `automations/prompts/agents_evals_judge_assurance_agent.md` | `"run agents evals agent"`, `"run evals judge assurance"`, `"run evals surface"` |
| **6/7** | `agents-cost-token-budget` | `Agents Repo: Cost & Token Budget` | `45 6 * * *` (`06:45 ET`) | `automations/prompts/agents_cost_token_budget_agent.md` | `"run agents cost agent"`, `"run cost token budget"`, `"run tokenomics"` |
| **7/7** | `agents-testing-gaps-assurance` | `Agents Repo: Testing Gaps Assurance` | `0 7 * * *` (`07:00 ET`) | `automations/prompts/agents_testing_gaps_assurance_agent.md` | `"run agents testing gaps"`, `"run testing gaps"` |

## 3. Mechanical Verification

Run `python3 tools/validate_sidecar_separation.py --json` to verify namespace prefixes, prompt dereferencing, workspace permission containment, schedule non-overlap, and untouched preservation of all 17 Decision Intelligence Engine sidecars.
