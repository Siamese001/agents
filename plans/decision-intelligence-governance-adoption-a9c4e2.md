# Implementation Plan: Decision Intelligence Governance Adoption

## Implementation Status Table

| Wave | Description | Status | Deliverables |
| :--- | :--- | :--- | :--- |
| Wave 1 | Central Governance Policy Catalog & Pre-Turn Skills Budget Gate | COMPLETED | `config/governance/policy_registry.yaml`, `tools/validate_turn_gates.py` |
| Wave 2 | Live Pre-Tool Question Validation, Margin Bypass & Main-Branch Write Guard | COMPLETED | `tools/hook_dispatch.py`, `.agents/hooks.json` |
| Wave 3 | Post-Tool Decision Ledger Writer & Sub-Agent Delegation Contract Guard | COMPLETED | `tools/hook_dispatch.py`, `tools/hitl_governance.py`, `.agents/hooks.json` |
| Wave 4 | Post-Turn Response Interceptor & End-to-End Governance Verification | COMPLETED | `tools/hook_dispatch.py`, `tools/validate_turn_gates.py`, `tests/test_hook_dispatch.py`, `tests/test_turn_gates.py` |

## Wave 1: Central Governance Policy Catalog & Pre-Turn Skills Budget Gate

### Objective & Scope
Create the machine-readable Single Source of Truth policy catalog (`config/governance/policy_registry.yaml`) modeled on the Decision Intelligence Engine and wire pre-turn policy registry and skills description budget validation into `tools/validate_turn_gates.py`.

### Milestones & Deliverables
- [NEW] `config/governance/policy_registry.yaml`
- [MODIFY] `tools/validate_turn_gates.py`

### Acceptance Criteria
- `config/governance/policy_registry.yaml` defines canonical quantitative and structural thresholds (`INV-BUDGET-FILE-LINES`, `INV-AGENTS-MD-MAX-LINES`, `INV-HITL-AMBIGUITY-MARGIN`, `INV-HITL-MIN-CONFIDENCE-FLOOR`, `INV-TEST-TIMEOUT-HARD`, `INV-WAVE-PLAN-MAX-WORDS`, `INV-OUTPUT-MAX-WORDS`, `INV-OUTPUT-MAX-CHARS`, `INV-SKILLS-BUDGET-MAX-TOKENS`, `INV-DECISIVE-RECOMMENDATION`, `INV-WT-ISOLATION`).
- `validate_pre_turn_gate` verifies both `policy_registry` integrity and `skills_budget` compliance across `.agents/skills/*/SKILL.md`.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python -m pytest tests/test_turn_gates.py --timeout=60 -q`
- Input: `config/governance/policy_registry.yaml`, `tools/validate_turn_gates.py`
- Expected: `validate_pre_turn_gate` returns PASS with `policy_registry` and `skills_budget` checks passing.
- Verify independently: `.venv/bin/python tools/validate_turn_gates.py --mode pre-turn`
- Fail if: Pre-turn gate returns FAIL or policy registry fails schema validation.
- Record: `reports/readiness/wave1_turn_gates_receipt.json`

## Wave 2: Live Pre-Tool Question Validation, Margin Bypass & Main-Branch Write Guard

### Objective & Scope
Replace passive `allow` placeholders in `.agents/hooks.json` with live pre-tool enforcement in `tools/hook_dispatch.py` (`pre_ask_question` and `pre_file_write`), enforcing atomic question presentation, calibrated confidence scores, autonomous margin bypass when spread exceeds 20% with top confidence >= 65%, plain-English question validation, and primary main-worktree write protection.

### Milestones & Deliverables
- [MODIFY] `tools/hook_dispatch.py`
- [MODIFY] `.agents/hooks.json`

### Acceptance Criteria
- `pre_ask_question` rejects batched questions, options < 2, missing confidence scores, and technical jargon in user questions.
- Non-mandatory questions with confidence spread > 20% and top score >= 65% return a margin-bypass deny directing autonomous execution and recording an `AUTONOMOUS` receipt in `HITLDecisionStore`.
- Direct file writes on branch `main` in the primary root worktree are denied while isolated worktree writes pass.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python -m pytest tests/test_hook_dispatch.py tests/test_hitl_governance_enforcement.py --timeout=60 -q`
- Input: `tools/hook_dispatch.py`, `.agents/hooks.json`
- Expected: 0 failures across hook dispatch and HITL enforcement suites.
- Verify independently: `.venv/bin/python tools/hook_dispatch.py --hook pre_ask_question`
- Fail if: Invalid questions pass or compliant questions fail.
- Record: `reports/readiness/wave2_pre_tool_hooks_receipt.json`

## Wave 3: Post-Tool Decision Ledger Writer & Sub-Agent Delegation Contract Guard

### Objective & Scope
Implement `post_ask_question` in `tools/hook_dispatch.py` to automatically persist operator answers and branch merge authorizations into `HITLDecisionStore`, and implement `pre_subagent_delegation` to validate 10-field sub-agent contracts via `tools/unified_agent_architecture.py`.

### Milestones & Deliverables
- [MODIFY] `tools/hook_dispatch.py`
- [MODIFY] `tools/hitl_governance.py`
- [MODIFY] `.agents/hooks.json`

### Acceptance Criteria
- `post_ask_question` normalizes operator answers, infers decision category and branch, and records decisions into `HITLDecisionStore`.
- `pre_subagent_delegation` validates explicit delegation contracts against the 10 mandatory fields and rejects overlapping scopes or missing budgets.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python -m pytest tests/test_hook_dispatch.py tests/test_hitl_governance_enforcement.py --timeout=60 -q`
- Input: `tools/hook_dispatch.py`, `tools/hitl_governance.py`
- Expected: Operator selections persist in `HITLDecisionStore` and malformed delegation contracts are denied.
- Verify independently: `.venv/bin/python tools/hitl_governance.py --metrics`
- Fail if: Post-tool ledger write fails or invalid sub-agent contracts pass.
- Record: `reports/readiness/wave3_ledger_and_subagent_receipt.json`

## Wave 4: Post-Turn Response Interceptor & End-to-End Governance Verification

### Objective & Scope
Implement `post_invocation` and post-turn decisive recommendation checks in `tools/hook_dispatch.py` and `tools/validate_turn_gates.py` to intercept disjunctive fence-sitting prose, unpromoted repository edits, and layman jargon violations, and verify all governance gates end-to-end.

### Milestones & Deliverables
- [MODIFY] `tools/hook_dispatch.py`
- [MODIFY] `tools/validate_turn_gates.py`
- [MODIFY] `tests/test_hook_dispatch.py`
- [MODIFY] `tests/test_turn_gates.py`
- [MODIFY] `.agents/rules/conformance-map.md`

### Acceptance Criteria
- `handle_post_invocation` and `validate_post_turn_gate` detect disjunctive prose ("we can X, or Y"), unpromoted repository file mutations, word-ceiling breaches (>300 words), and technical jargon violations.
- All unit, turn-gate, hook-dispatch, and Tier 1/Tier 2 readiness suites pass with zero regressions.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/python -m pytest tests/test_hook_dispatch.py tests/test_turn_gates.py tests/test_hitl_governance_enforcement.py tests/test_implementation_plan_governance.py --timeout=60 -q`
- Input: `tests/test_hook_dispatch.py`, `tests/test_turn_gates.py`
- Expected: 100% pass rate across all governance test suites and `verify_commit.py --all`.
- Verify independently: `.venv/bin/python tools/validate_implementation_plan.py --file plans/decision-intelligence-governance-adoption-a9c4e2.md`
- Fail if: Any test or pre-commit gate fails.
- Record: `reports/readiness/wave4_e2e_governance_receipt.json`
