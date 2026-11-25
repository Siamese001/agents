---
trigger: model_decision
description: Traceability map linking AGENTS.md governance sections to enforcing rules, skills, hooks, tools, and tests.
---

# Conformance Map: `agents` Workspace Overrides

Inherits shared five-layer traceability from `~/.gemini/config/plugins/core-governance/rules/conformance-map.md`. Maps `agents` invariants to repository enforcers and rules.

## Repository Threshold & Invariant Overrides

- **Unbounded File & Scope Floor**: `INV-BUDGET-FILE-LINES` (`0 lines`), `INV-REFACTOR-EXTENT-UNBOUNDED` (`1`), `INV-ZERO-BUGFIX-BLAST-RADIUS-CAP` (`0`) enforced by `tools/zero_bugfix_constraint_gate.py`.
- **HITL & Decisive Turn Gates**: `INV-HITL-AMBIGUITY-MARGIN` (`0.20` / `20%`), `INV-HITL-MIN-CONFIDENCE-FLOOR` (`0.65` / `65%`), and `INV-DECISIVE-RECOMMENDATION` (`0` disjunctive phrases) enforced by `tools/hitl_governance.py` and `tools/hook_dispatch.py`.
- **Centralized Cross-Repo, Judge v3 & Studio Parity**: `INV-GOVERNANCE-HARMONIZATION-GATE` (`0` critical drift findings), `INV-ZERO-DRIFT-CROSS-REPO-PARITY` (`0` violations), `INV-CENTRALIZED-LABELING-STUDIO-ONLY` (`0` violations), `INV-CENTRALIZED-JUDGE-V3-CORE` (`0` violations), `INV-JUDGE-NON-DEGENERATE-WEIGHTS` (`0` violations), and `INV-WAVE-MERGE-WORKTREE-CLOSEOUT-TABLE` (`0` violations) enforced by `tools/audit_governance_harmonization.py`, `tools/validate_judge_rubrics_v3.py`, and `tools/audit_multi_ssot_judge_gate_drift.py`.

## `AGENTS.md` Section -> Repository Enforcer Map

| Section | Rules & Skills | Enforcing Tools, Hooks & Tests |
| :--- | :--- | :--- |
| **Plan First & Wave Protocol** | `.agents/rules/plan-first-enforcement.md`, `.agents/rules/wave-progression.md`, `.agents/rules/scope-containment.md`, `docs/refactoring-wave-protocol.md` | `.agents/hooks.json` (`agents-file-write-guard`), `tools/validate_implementation_plan.py`, `tools/implementation_plan_core/wave_dag.py`, `tests/test_implementation_plan_governance.py` |
| **Constitutional Floor & Brevity** | `.agents/rules/constitutional.md`, `.agents/rules/output-brevity-governance.md` (`<= 450` words) | `tools/verify_commit.py`, `tools/validate_turn_gates.py`, `tools/zero_bugfix_constraint_gate.py` |
| **Production Derivation Integrity** | `.agents/rules/production-derivation-and-anti-overfitting.md`, `.agents/rules/resume-graph-engine.md`, `.agents/rules/apps-research.md` | `tools/lint_production_purity.py`, `tools/lint_no_jd_overfitting.py`, `tools/lint_prompt_validator_vocab_symmetry.py` (`INV-PROMPT-VALIDATOR-VOCAB-SYMMETRY`) |
| **Pytest & Subsystem Boundaries** | `.agents/skills/testing-framework/SKILL.md`, `.agents/skills/agents-governance-hygiene/SKILL.md`, `.mcp.json`, `pytest.ini` (`--timeout=180`) | `tools/adg_impact_tests.py`, `tools/lint_layer_imports.py`, `tools/lint_architecture_boundaries.py`, `tools/ssot_boundary_auditor.py`, `tools/ssot_sprawl_scanner.py` |
| **HITL, Delegation & Sidecars** | `.agents/rules/hitl-decisions.md`, `.agents/rules/unified-agent-architecture.md`, `.agents/rules/sidecar-automation-routing.md`, `.antigravity/runtime-boundary.json` | `tools/hitl_governance.py`, `tools/unified_agent_architecture.py`, `tools/validate_sidecar_separation.py`, `.agents/hooks.json` (`agents-hitl-atomic-guard`, `agents-subagent-delegation-guard`) |
| **PR Queue, Lanes & Eval Shield** | `.agents/rules/pr-governance.md`, `.agents/rules/git-worktree-governance.md`, `.agents/rules/risk-tiered-change-lanes.md`, `.agents/rules/e2e-and-edge-case-coverage.md`, `.agents/rules/flywheel-remediation-governance.md` | `tools/pr_governance.py`, `tools/verify_main_readiness.py`, `tools/audit_governance_harmonization.py`, `tools/audit_eval_construct_validity.py`, `tools/run_diff_scoped_eval_shield.py`, `tools/validate_judge_rubrics_v3.py`, `tools/audit_multi_ssot_judge_gate_drift.py` |
