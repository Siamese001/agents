# On-Demand Assurance Routing & Cross-Repository Firewall (`agents-*`)

Governs the 8 on-demand assurance workflows and consolidated skills for the `agents` repository across all 11 executable package roots (`agents/`, `apps_eval/`, `apps_model_telemetry/`, `apps_research/`, `infrastructure/`, `ops_scripts/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `scripts/`, and `tools/`), ensuring zero unattended daily background runs and strict isolation from all Decision Intelligence Engine sidecars.

## 1. Schedule Retirement & Cross-Repository Isolation (`INV-REPO-SEPARATION-AGENTS-ONLY`)

- **Zero Daily Background Schedules**: Background daily schedules for `agents-*` in `/Users/amitayer/.gemini/config/sidecars/` and `/Users/amitayer/.gemini/config/config.json` are retired (`agents_scheduled_count == 0`). Continuous enforcement runs locally via `.githooks/pre-commit` (`tools/verify_commit.py` + `tools/validate_turn_gates.py`), and deep domain sweeps run on demand through `.agents/skills/` and `automations/prompts/agents_*_agent.md`.
- **Preflight-First Exclusive Workspace Scope**: When operating in `/Users/amitayer/Git/agents`, interactive assurance triggers execute read-only behavioral preflight checks first (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT` when `is_clean == true`) and provision an isolated `.worktrees/` branch only when actionable findings exist.
- **Zero Cross-Repository Mutation**: No `agents` workflow, skill, or checker may read, write, or execute commands against `/Users/amitayer/Git/decision-intelligence-engine` or its knowledge graph databases (`CANONICAL_GRAPH.db`, `graph.sqlite`).

## 2. On-Demand Assurance & Skill Roster

| Order | Workflow ID | Consolidated Skill | Deterministic Checker | Canonical Prompt Specification | On-Demand Triggers (in `agents` workspace) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1/8** | `agents-storage-worktree-hygiene` | `agents-governance-hygiene` | `tools/storage_worktree_hygiene.py` | `automations/prompts/agents_storage_worktree_hygiene_agent.md` | `"run agents storage hygiene"`, `"run storage hygiene"`, `"run worktree hygiene"` |
| **2/8** | `agents-ssot-boundary-governance` | `scope-containment` / `agents-governance-hygiene` | `tools/ssot_boundary_auditor.py` | `automations/prompts/agents_ssot_boundary_agent.md` | `"run agents ssot agent"`, `"run ssot remediation"`, `"run boundary governance"` |
| **3/8** | `agents-core-runtime-orchestration` | `agent-runtime-engineering` | `tools/agent_runtime_auditor.py` | `automations/prompts/agents_core_runtime_orchestration_agent.md` | `"run agents core runtime"`, `"run runtime orchestration"`, `"run core agent audit"` |
| **4/8** | `agents-domain-applications-pipeline` | `agents-domain-assurance` | `tools/e2e_functionality_auditor.py` | `automations/prompts/agents_domain_applications_pipeline_agent.md` | `"run agents domain pipeline"`, `"run domain applications"`, `"run outreach resume e2e"` |
| **5/8** | `agents-research-retrieval-surface` | `agents-domain-assurance` | `tools/retrieval_surface_auditor.py` | `automations/prompts/agents_research_retrieval_surface_agent.md` | `"run agents retrieval agent"`, `"run research retrieval surface"`, `"run retrieval surface"` |
| **6/8** | `agents-evals-judge-assurance` | `receipt-auditor` / `agents-domain-assurance` | `tools/validate_eval_rubrics.py` | `automations/prompts/agents_evals_judge_assurance_agent.md` | `"run agents evals agent"`, `"run evals judge assurance"`, `"run evals surface"` |
| **7/8** | `agents-cost-token-budget` | `operational-gates` / `agents-governance-hygiene` | `tools/cost_token_budget_auditor.py` | `automations/prompts/agents_cost_token_budget_agent.md` | `"run agents cost agent"`, `"run cost token budget"`, `"run tokenomics"` |
| **8/8** | `agents-testing-gaps-assurance` | `testing-framework` | `tools/testing_gaps_auditor.py` | `automations/prompts/agents_testing_gaps_assurance_agent.md` | `"run agents testing gaps"`, `"run testing gaps"`, `"run security assurance"` |

## 3. Mechanical Verification

Run `.venv/bin/python tools/validate_sidecar_separation.py --json` to verify zero background `agents-*` schedules, complete on-demand prompt/skill/routing bindings, and untouched preservation of all active Decision Intelligence Engine sidecars.
