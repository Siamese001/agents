---
trigger: model_decision
description: Traceability map linking AGENTS.md governance sections to enforcing rules, skills, hooks, tools, and tests.
---

# Conformance Map: AGENTS.md -> Enforceable Artifacts

Traces every `AGENTS.md` section to enforceable rules, skills, hooks, tools, and tests in `.agents/` and `tools/`.

## Control Mapping

### §"Plan First. Execute Second."
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/plan-first-enforcement.md` | Native plan mode vs direct root-cause execution |
| Rule | `.agents/rules/scope-containment.md` | Full-ripple dependency inspection and drift prevention |
| Skill | `.agents/skills/scope-containment/SKILL.md` | Cohesive producer-consumer-validator alignment |
| Hook | `.agents/hooks.json` -> `agents-file-write-guard` | Unified pre-write validation (plans, model neutrality, worktree isolation) |
| Tool | `tools/validate_turn_gates.py` | Pre-turn contract integrity check |

### §"Wave Refactoring Protocol"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Policy | `docs/refactoring-wave-protocol.md` | Subtraction-first unbounded wave & sharded `/boost`/`/swarm` convergence |
| Rule | `.agents/rules/wave-progression.md` | Wave plan structure, 6-field completion gates, and pytest protocol |
| Dispatcher | `tools/hook_dispatch.py` | Antigravity native lifecycle hook dispatcher |
| Tool | `tools/validate_implementation_plan.py` | Wave plan and completion gate validator |
| Tool | `tools/implementation_plan_core/wave_dag.py` | Fork-join wave DAG (`Wave 2A`/`2B`) and `shard-manifest` validator |
| Test | `tests/test_implementation_plan_governance.py` | Plan governance invariant tests |
| Test | `tests/test_hook_dispatch.py` | Hook dispatcher regression tests |

### §"MCP Quick Reference"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Config | `.mcp.json` | Sole repository MCP Server-of-Record (SSOT) |
| Tool | `tools/ssot_sprawl_scanner.py` | MCP configuration SSOT sprawl prevention (global `mcp-engineering` skill handles protocol design) |
| Skill | `.agents/skills/agents-governance-hygiene/SKILL.md` | Repository boundary and infrastructure hygiene |

### §"Constitutional floor"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/constitutional.md` | Subprocess timeouts, pytest skip rules, exception handling, zero-deferral |
| Rule | `.agents/rules/output-brevity-governance.md` | Output brevity (`<= 450` words) and direct inquiry grounding |
| Tool | `tools/verify_commit.py` | Tier 1 commit gate (syntax, boundaries, purity, schemas, secrets) |
| Tool | `tools/zero_bugfix_constraint_gate.py` | Anti-regression floor preventing blast-radius/file-count caps |

### §"Production Derivation Integrity"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Rule | `.agents/rules/production-derivation-and-anti-overfitting.md` | Derivation integrity and ban on company/JD branches |
| Rule | `.agents/rules/resume-graph-engine.md` | Resume graph provenance, acronym clarity, and C0/X2 invariants |
| Rule | `.agents/rules/apps-research.md` | Fail-closed research targeting brief and handoff envelope |
| Tool | `tools/lint_production_purity.py` | AST scanner detecting golden fixtures imported in production |
| Tool | `tools/lint_no_jd_overfitting.py` | Tier 1 anti-overfitting linter with ratchet |

### §"Pytest & Subsystems"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Config | `pytest.ini` | Autoload ON, `--timeout=180` |
| Tool | `tools/adg_impact_tests.py` | Transitive dependency impact test selector across test roots |
| Skill | `.agents/skills/testing-framework/SKILL.md` | Impacted pytest verification protocol |
| Tool | `tools/lint_layer_imports.py` | Unidirectional layer import linter |
| Tool | `tools/lint_architecture_boundaries.py` | Cross-subsystem storage and layer boundary linter |
| Tool | `tools/ssot_boundary_auditor.py` | 10-dimension SSOT, boundary, and config sprawl auditor |

### §"HITL Decisions, Delegation & Antigravity Adapter"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Policy | `config/governance/policy_registry.yaml` | Machine-readable SSOT for governance thresholds |
| Rule | `.agents/rules/hitl-decisions.md` | Atomic presentation, 20% margin rule, calibrated confidence |
| Rule | `.agents/rules/unified-agent-architecture.md` | 5 Pillars, delegation contracts, and A2A guardrails |
| Rule | `.agents/rules/sidecar-automation-routing.md` | On-demand assurance workflows and zero daily schedules |
| Tool | `tools/hitl_governance.py` | Calibrated margin evaluator and SQLite decision store |
| Tool | `tools/unified_agent_architecture.py` | Delegation contract and return validators |
| Tool | `tools/validate_sidecar_separation.py` | Schedule retirement and cross-repo isolation validator |
| Hook | `.agents/hooks.json` -> `agents-hitl-atomic-guard` | Pre/Post `ask_question` and `PostInvocation` guards |
| Hook | `.agents/hooks.json` -> `agents-subagent-delegation-guard` | Subagent delegation and scope lease guards |
| Boundary | `.antigravity/runtime-boundary.json` | Workspace runtime boundary and path containment |

### §"Git Hooks, PR Queue & AI-SDLC Risk Lanes"
| Type | Path | Coverage |
| :--- | :--- | :--- |
| Hooks | `.githooks/{pre-commit,pre-merge-commit,pre-push,post-merge,commit-msg}` | Version-controlled Git hooks (`core.hooksPath = .githooks`) |
| Policy | `config/governance/risk_lanes_policy.json` | Fail-closed Lane 0/1/2 classification and soft caps |
| Rule | `.agents/rules/pr-governance.md` | Governed PR queue, FIFO trunk lock, and dirty-worktree recovery |
| Rule | `.agents/rules/git-worktree-governance.md` | Isolated worktree lifecycle and post-merge cleanup |
| Rule | `.agents/rules/risk-tiered-change-lanes.md` | 3-lane risk tiering and fail-closed escalation |
| Rule | `.agents/rules/e2e-and-edge-case-coverage.md` | Unmocked E2E pinning, pinned judge negative controls, and bilateral recall-precision gates |
| Rule | `.agents/rules/resume-graph-engine.md` | Verified candidate fact provenance, zero post-LLM mutators, and multi-JD generalization |
| Rule | `.agents/rules/flywheel-remediation-governance.md` | Hybrid Tier A/B/C auto-apply with immutable candidate-truth and blind-judge floor locks |
| Tool | `tools/pr_governance.py` | Governed PR queue, trunk lock, and merge train |
| Tool | `tools/verify_main_readiness.py` | Tier 2 10-stage local main readiness gate |
| Tool | `tools/audit_governance_harmonization.py` | Cross-surface threshold, context budget, and broken-ref auditor |
| Tool | `tools/audit_eval_construct_validity.py` | Eval construct validity and unmocked E2E pinning gate |
| Tool | `tools/run_diff_scoped_eval_shield.py` | Diff-scoped unmocked domain eval shield |
