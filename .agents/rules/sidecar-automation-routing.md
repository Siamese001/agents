---
trigger: model_decision
description: On-demand assurance workflow routing, disabled background schedules, and cross-repository isolation.
---

# On-Demand Assurance Routing & Cross-Repository Firewall (`agents-*`)

Governs the 4 consolidated judgment-heavy on-demand assurance workflows and automated Git/Tier-2 gates for the `agents` repository across all 11 executable package roots (`agents/`, `apps_eval/`, `apps_model_telemetry/`, `apps_research/`, `infrastructure/`, `ops_scripts/`, `outreach_engine/`, `resume_engine/`, `resume_graph_engine/`, `scripts/`, and `tools/`), ensuring zero unattended daily background runs and strict isolation from all Decision Intelligence Engine sidecars.

## 1. Schedule Retirement & Cross-Repository Isolation (`INV-REPO-SEPARATION-AGENTS-ONLY`)

- **Zero Daily Background Schedules (`CATALOG_DISABLED_BY_DEFAULT`)**: All 4 `agents-*` sidecar launchers in `/Users/amitayer/.gemini/config/sidecars/` and `/Users/amitayer/.gemini/config/config.json` are registered with `"enabled": false` (`agents_scheduled_count == 0`, `agents_catalog_count == 4`). Continuous deterministic enforcement runs via `.githooks/pre-commit` (`tools/verify_commit.py` + `tools/validate_turn_gates.py`), `.githooks/post-merge` (`tools/storage_worktree_hygiene.py --post-merge-quick`), and Tier 2 `tools/verify_main_readiness.py` (10 risk-tiered stages), while judgment-heavy sweeps run on demand through the Antigravity Automations UI, `.agents/skills/`, and `automations/prompts/agents_*_agent.md`.
- **Preflight-First Exclusive Workspace Scope**: Interactive assurance triggers execute read-only behavioral preflight checks first (`PREFLIGHT_ZERO_DEFECT_FAST_EXIT` when `is_clean == true`) and provision an isolated `.worktrees/` branch only when actionable findings exist.
- **Zero Cross-Repository Mutation**: No `agents` workflow, skill, or checker may read, write, or execute commands against `/Users/amitayer/Git/decision-intelligence-engine` or its knowledge graph databases (`CANONICAL_GRAPH.db`, `graph.sqlite`).

## 2. Consolidated 4-Agent On-Demand Roster

| Order | Workflow ID | Consolidated Skill | Deterministic Auditor(s) | Canonical Thin Prompt | On-Demand Triggers |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1/4** | `agents-architecture-cost-governance` | `agents-governance-hygiene` / `scope-containment` | `tools/ssot_boundary_auditor.py`, `tools/cost_token_budget_auditor.py` | `automations/prompts/agents_architecture_cost_agent.md` | `"run agents architecture audit"`, `"run ssot remediation"`, `"run tokenomics"` |
| **2/4** | `agents-core-runtime-orchestration` | `agent-runtime-engineering` / `agent-subagent-orchestration` | `tools/agent_runtime_auditor.py` | `automations/prompts/agents_core_runtime_orchestration_agent.md` | `"run agents core runtime"`, `"run runtime orchestration"` |
| **3/4** | `agents-domain-pipelines-retrieval` | `agents-domain-assurance` | `tools/e2e_functionality_auditor.py`, `tools/retrieval_surface_auditor.py` | `automations/prompts/agents_domain_pipelines_retrieval_agent.md` | `"run agents domain pipeline"`, `"run retrieval surface"` |
| **4/4** | `agents-evals-flywheel-assurance` | `receipt-auditor` / `agents-domain-assurance` | `tools/validate_eval_rubrics.py`, `tools/run_eval_flywheel_cycle.py` | `automations/prompts/agents_evals_flywheel_assurance_agent.md` | `"run agents evals flywheel"`, `"run evals judge assurance"` |

## 3. Retired Manual Agents -> Automated Git & Readiness Gates

| Retired Manual Agent | Automated Gate / Skill Home | Enforcing Tool |
| :--- | :--- | :--- |
| `agents-storage-worktree-hygiene` | `.githooks/post-merge` + `agents-governance-hygiene` skill | `tools/storage_worktree_hygiene.py` (`--post-merge-quick` / `--remediate`) |
| `agents-testing-gaps-assurance` | Tier 1 `tools/verify_commit.py` + Tier 2 `tools/verify_main_readiness.py` Stage 10 + `testing-framework` skill | `tools/audit_mock_reachability.py`, `tools/testing_gaps_auditor.py` |

## 4. Mechanical Verification

Run `.venv/bin/python tools/validate_sidecar_separation.py --json` to verify zero background `agents-*` schedules, all 4 consolidated manual launchers, pairwise MECE stage isolation, and untouched preservation of all Decision Intelligence Engine sidecars.
