---
trigger: always_on
---

# Conformance Map: AGENTS.md → Enforceable Artifacts

Traces every `AGENTS.md` section to enforceable rules, skills, hooks, tools, and tests in `.agents/` and `tools/`.

## Control Mapping

### §"Plan First. Execute Second."
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/plan-first-enforcement.md` | T2/T3 plan-mode gating, decomposition, and review |
| Skill | `.agents/skills/scope-containment/SKILL.md` | Bounded scope decomposition and retrieval guidance in plan mode |
| Hook | `.agents/hooks.json` → `agents-implementation-plan-guard` | Mechanical wave plan validation before writing |
| Tool | `tools/validate_turn_gates.py` | Pre-turn contract integrity check |

### §"Wave Refactoring Protocol"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Policy | `docs/refactoring-wave-protocol.md` | 6-wave maximum, sequential scope, receipt validation |
| Hook | `.agents/hooks.json` → `agents-implementation-plan-guard` | Implementation status table and wave plan validation before writing |
| Hook | `.agents/hooks.json` → `agents-wave-completion-guard` | Stop hook wave completion summary table display |
| Dispatcher | `tools/hook_dispatch.py` | Antigravity native lifecycle hook dispatcher and wave table generator |
| Tool | `tools/validate_implementation_plan.py` | Mechanical status table, brain plan discovery, and markdown table validator |
| Test | `tests/test_implementation_plan_governance.py` | Plan governance and status table invariant tests |
| Test | `tests/test_hook_dispatch.py` | Antigravity hook dispatcher and wave summary tests |

### §"MCP Quick Reference"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Config | `.mcp.json` | Repository MCP Server-of-Record (SSOT) |
| Rule | `.agents/rules/mcp-config-ssot.md` | MCP configuration and portable transport governance |
| Skill | `.agents/skills/mcp-engineering/SKILL.md` | MCP server schema contracts, transport verification, and tool-call lifecycle checks |
| Skill | `.agents/skills/agents-governance-hygiene/SKILL.md` | Consolidated repository boundary and infrastructure hygiene |

### §"Notion Workspace Map"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/plan-location.md` | Disk-only plans and Notion workspace routing reference |
| Config | `AGENTS.md` | Data source IDs, database write targets, read/write patterns |

### §"Memory"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| State | `memory/MEMORY.md` | Native session start file memory |
| State | `memory/codex/memory_summary.md` | Run history and worktree workflow memory |
| Rule | `.agents/rules/memory-management.md` | Memory hygiene and persistence constraints |

### §"Constitutional floor"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/constitutional.md` | Subprocess timeouts, pytest skip rules, exception handling |
| Tool | `tools/verify_commit.py` | Tier 1 commit gate enforcement (Secrets, AST, File Budgets) |
| Hook | `.agents/hooks.json` → `agents-pytest-scope-guard` | Mandatory `--timeout=180` on pytest |

### §"Production Derivation Integrity"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `AGENTS.md` L94–L98 | Prohibition of predetermined golden fixtures substituting domain derivation |
| Tool | `tools/lint_production_purity.py` | AST scanner detecting golden fixtures imported in production paths |
| Tool | `tools/verify_commit.py` | Category 3 Production Purity verification |
| Invariant | `resume_graph_engine/src/apps_rg/runtime/final_resume_outputs.py` | Single Canonical Pipeline Invariant (`INV-SINGLE-CANONICAL-PIPELINE`): zero parallel runners or shadow flatteners |
| Invariant | `resume_graph_engine/src/apps_rg/runtime/aggregation/cross_section_x2.py` | Production Resume & Acronym Clarity Invariant (`INV-RESUME-NO-UNDEFINED-ACRONYMS`): zero undefined MGA/MGAs acronyms in assembled corpus |
| Invariant | `resume_graph_engine/src/apps_rg/runtime/c0/resume_graph_allocation.py` | Whole-Resume Bundle Coherence & Wave Timeout Invariant (`INV-RESUME-BUNDLE-COHERENCE-AND-WAVE-TIMEOUT`): exact raw-chunk fact resolution, wave `run_timeout` cap, mean-quorum parity, POSIX paths, and `0644` artifact permissions |
| Invariant | `resume_graph_engine/src/apps_rg/runtime/quad_graph_retriever.py` | DIE-Aligned 4-Channel Graph Hybrid Retrieval Invariant (`INV-QUAD-GRAPH-HYBRID-RETRIEVAL`): Stage-1 candidate union admission quota, generational dense/sparse/ColBERT caches, 1-hop graph signal injection, and C0.3 convergent path expansion |

### §"Plans"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/plan-location.md` | Disk-only plans under `plans/<name>-<6hex>.md` |
| Tool | `tools/validate_implementation_plan.py` | Wave numbering, milestones, criteria, receipts verification |

### §"Pytest"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Config | `pytest.ini` | Autoload ON, `--timeout=180`, default timeout options |
| Hook | `.agents/hooks.json` → `agents-pytest-scope-guard` | Blocks bare `pytest` sweeps; mandates scoped execution |
| Skill | `.agents/skills/testing-framework/SKILL.md` | Scoped pytest Class A/B run protocol and collection checks |

### §"Subsystems vs Infrastructure (summary)"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `AGENTS.md` | Subsystem encapsulation; autonomous domains, shared utilities in infrastructure |
| Tool | `tools/lint_layer_imports.py` | Unidirectional layer import linter (L0–L6) |
| Tool | `tools/lint_architecture_boundaries.py` | Cross-subsystem architectural boundary enforcement |
| Tool | `tools/ssot_boundary_auditor.py` | Full 11-root cross-subsystem, timeout, config drift, and link auditor |

### §"Rules & Skills SSOT"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Policy Registry | `config/governance/policy_registry.yaml` | Machine-readable SSOT for quantitative, structural, and lifecycle invariants |
| Rules | `.agents/rules/*.md` | Active governance rules |
| Skills | `.agents/skills/*/SKILL.md` | Reusable procedural adapters (audited by pre-turn skills context budget gate) |
| Hook | `.agents/hooks.json` | Native Antigravity lifecycle hook registry (9 active guards) |
| Tool | `tools/validate_turn_gates.py` | Mechanical pre-turn & post-turn turn gate validator |
| Tool | `tools/verify_commit.py` | Tier 1 structural pre-commit gate |

### §"HITL Decisions & Ambiguity Gating"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/hitl-decisions.md` | Atomic presentation, 20% calibrated margin rule, multi-factor confidence, synthetic firewall |
| Tool | `tools/hitl_governance.py` | Calibrated margin evaluator, multi-factor confidence model, SQLite persistent store |
| Hook | `.agents/hooks.json` → `agents-hitl-atomic-guard` | PreToolUse (`pre_ask_question`), PostToolUse (`post_ask_question`), PostInvocation (`post_invocation`) |
| Hook | `.agents/hooks.json` → `agents-main-worktree-write-guard` | PreToolUse (`pre_file_write`) enforcing primary main-worktree isolation and layman artifact guard |
| Hook | `.agents/hooks.json` → `agents-model-registry-conformance-guard` | Pre-tool check verifying model tokens resolve to config/provider_profiles.yaml |
| Test | `tests/test_hitl_governance_enforcement.py` | Unit tests for margin calculation, persistent store, and origin validation |

### §"Model-Neutral Artifact Naming"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Tool | `tools/lint_model_neutral_naming.py` | File path and AST model token scanner |
| Hook | `.agents/hooks.json` → `agents-model-neutral-artifact-guard` | Pre-tool check on file writes and moves |
| Test | `tests/test_model_neutral_naming.py` | Unit tests for path and code neutrality |

### §"Antigravity Execution Adapter"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Boundary | `.antigravity/runtime-boundary.json` | Workspace runtime boundary and path containment |
| Hook | `.agents/hooks.json` | Native Antigravity IDE lifecycle intercepts |
| Validator | `tools/validate_turn_gates.py` | Automated turn validator CLI (`--mode all`) |
| Test | `tests/test_turn_gates.py` | Turn-gate regression test suite |
| Rule | `.agents/rules/sidecar-automation-routing.md` | On-demand assurance routing, zero daily schedules, and cross-repo firewall (`INV-REPO-SEPARATION-AGENTS-ONLY`) |
| Contract | `automations/prompts/_shared_governance_contract.md` | Shared 7-workflow on-demand/pre-save contract and prompt specifications (`automations/prompts/agents_*_agent.md`) |
| Validator | `tools/validate_sidecar_separation.py` | Mechanical validator enforcing zero `agents-*` background schedules, prompt/skill parity, and NEE sidecar isolation |
| Engine | `tools/storage_worktree_hygiene.py` | Deterministic 6-pillar storage, 6-DB SQLite/Chroma WAL, worktree, lock, and scratch hygiene engine |
| Engine | `tools/ssot_boundary_auditor.py` | Deterministic 6-dimension cross-subsystem boundary, AST floor, MCP/hook, and config/data SSOT auditor |
| Engine | `tools/validate_eval_rubrics.py` | Deterministic exit-eval rubric `[0.0, 1.0]` bounds, 154-file holdout dataset, and purity validator |
| Engine | `tools/cost_token_budget_auditor.py` | Deterministic 8-pillar tokenomics, multi-tier caching, and dynamic $\text{ROI} \ge 2.5\times$ Pareto benchmark auditor |
| Engine | `tools/audit_mock_reachability.py` | Deterministic 11-root production mock reachability auditor |
| Test | `tests/unit/test_sidecar_separation_governance.py` | Unit tests for schedule retirement, cross-repo isolation, 6-pillar storage/WAL hygiene, and 8-pillar cost/caching audit |

### §"Unified Agent Architecture & Delegation Contracts"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/unified-agent-architecture.md` | 5 Pillars, 4 Foundations, 7-Step Lifecycle, 10-field contract |
| Skill | `.agents/skills/agent-subagent-orchestration/SKILL.md` | Practical orchestration patterns, delegation contracts, and return protocols |
| Skill | `.agents/skills/agent-runtime-engineering/SKILL.md` | Production agent runtime design, supervisor loops, budgets, and retry semantics |
| Tool | `tools/unified_agent_architecture.py` | Mandatory delegation contract & structured return validators |
| Hook | `.agents/hooks.json` → `agents-subagent-delegation-guard` | Pre-tool check on browser_subagent / invoke_subagent |
| Test | `tests/test_unified_agent_architecture.py` | Unit tests for taxonomy, 10-field contracts, budgets, returns |

### §"Git Hooks & Local Quality Verification"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Config | `core.hooksPath` → `.githooks` | Version-controlled deterministic local Git hooks |
| Hook | `.githooks/pre-commit` | Direct-to-main block (`GOVERNED_PR_MERGE=1`), turn gates, staged plans, commit invariants, tests |
| Hook | `.githooks/pre-merge-commit` | Pre-merge receipt verification (`tools/verify_merge_receipt.py`) |
| Hook | `.githooks/pre-push` | Pre-push gate verifying all turn gates, active plans, commit invariants |
| Hook | `.githooks/post-merge` | Post-merge gate automatically pruning merged worktrees and local branches |
| Tool | `tools/pr_governance.py` | Governed PR queue, trunk reservation lock, catch-up under lock, worktree lifecycle |
| Tool | `tools/verify_post_merge.py` | Two-parent merge certification and out-of-tree receipt verification |
| Tool | `tools/prune_merged_chat_worktrees.py` | Automated ancestry-verified worktree and branch pruning tool |
| Tool | `tools/install_githooks.py` | Automated installation and executable permission tool |
| Rule | `.agents/rules/pr-governance.md` | Two-stage PR lifecycle, FIFO queue lock, and moving-target prevention |
| Rule | `.agents/rules/git-branch-per-chat.md` | Mandatory post-PR local worktree and feature branch deletion |
| Test | `tests/test_pr_merge_queue_governance.py` | Trunk lock, FIFO queue, disjoint catch-up, merge receipt, and hook tests |

### §"Adversarial Red-Team & Defense"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Defense | `tools/hitl_governance.py` | Synthetic stop hook auto-approval rejection, plan-only firewall |
| Defense | `tools/lint_model_neutral_naming.py` | Obfuscated model token path scanning |
| Defense | `tools/validate_implementation_plan.py` | Anti-flat, wave-gap, and incomplete milestone rejection |
| Test | `tests/test_governance_adversarial_redteam.py` | 11-attack adversarial regression test suite |

