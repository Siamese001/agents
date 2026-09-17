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
| Skill | `.agents/skills/structured-reasoning/SKILL.md` | Decomposition and retrieval guidance in plan mode |
| Hook | `.agents/hooks.json` → `agents-pre-edit-plan-guard` | Mechanical edit blocking on core/apps without approved plan |
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
| Skill | `.agents/skills/mcp-integration/SKILL.md` | Procedures for GitKraken, ADG SQLite, deepwiki, memory, etc. |
| Skill | `.agents/skills/adg-sqlite/SKILL.md` | Structural dependency analysis and graph queries |

### §"Notion Workspace Map"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Doc | `.agents/skills/mcp-integration/agents-tier1-companion.md` | Procedural routing for Notion databases (Backlog, Plans) |
| Config | `AGENTS.md` L55–L75 | Data source IDs, database write targets, read/write patterns |

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
| Hook | `.agents/hooks.json` → `agents-background-task-reaper` | Intercepts background tests and kills tasks running > 2 min |

### §"Core vs apps (summary)"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `agentic_core/AGENTS.md` | Layer boundary enforcement; apps customize inputs, core enforces |
| Tool | `tools/lint_layer_imports.py` | Unidirectional layer import linter (L0–L6) |

### §"Rules & Skills SSOT"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rules | `.agents/rules/*.md` | Active governance rules |
| Skills | `.agents/skills/*/SKILL.md` | Reusable procedural adapters |
| Hook | `.agents/hooks.json` | Native Antigravity lifecycle hook registry |
| Tool | `tools/validate_turn_gates.py` | Mechanical pre-turn & post-turn turn gate validator |
| Tool | `tools/verify_commit.py` | Tier 1 structural pre-commit gate |

### §"HITL Decisions & Ambiguity Gating"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/hitl-decisions.md` | Atomic presentation, 20% calibrated margin rule, multi-factor confidence, synthetic firewall |
| Tool | `tools/hitl_governance.py` | Calibrated margin evaluator, multi-factor confidence model, SQLite persistent store |
| Hook | `.agents/hooks.json` → `agents-hitl-atomic-guard` | Pre-tool check on ask_question |
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

### §"Unified Agent Architecture & Delegation Contracts"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/unified-agent-architecture.md` | 5 Pillars, 4 Foundations, 7-Step Lifecycle, 10-field contract |
| Tool | `tools/unified_agent_architecture.py` | Mandatory delegation contract & structured return validators |
| Hook | `.agents/hooks.json` → `agents-subagent-delegation-guard` | Pre-tool check on browser_subagent / invoke_subagent |
| Test | `tests/test_unified_agent_architecture.py` | Unit tests for taxonomy, 10-field contracts, budgets, returns |

### §"Git Hooks & Local Quality Verification"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Config | `core.hooksPath` → `.githooks` | Version-controlled deterministic local Git hooks |
| Hook | `.githooks/pre-commit` | Pre-commit gate running turn gates, staged plans, commit invariants, tests |
| Hook | `.githooks/pre-push` | Pre-push gate verifying all turn gates, active plans, commit invariants |
| Tool | `tools/install_githooks.py` | Automated installation and executable permission tool |

### §"Adversarial Red-Team & Defense"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Defense | `tools/hitl_governance.py` | Synthetic stop hook auto-approval rejection, plan-only firewall |
| Defense | `tools/lint_model_neutral_naming.py` | Obfuscated model token path scanning |
| Defense | `tools/validate_implementation_plan.py` | Anti-flat, wave-gap, and incomplete milestone rejection |
| Test | `tests/test_governance_adversarial_redteam.py` | 11-attack adversarial regression test suite |

