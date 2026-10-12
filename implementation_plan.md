# Implementation Plan: Wave Plan Governance and Output Brevity Enforcement

## Executive Overview
Replicate the strict wave plan governance specification from `decision-intelligence-engine` to the `agents` repository. This standard enforces 4 mandatory subsections per wave (Objective & Scope, Milestones & Deliverables, Acceptance Criteria, Runtime Receipt & Completion Gate with 6 evidence fields), caps plan word count at 1,000 words, makes status tables optional, silences automatic stdout all-wave status table dumps during engineering turns, and updates all verification test suites.

---

## Wave 1: Governance Rules & Documentation Replication

### Objective & Scope
Replicate canonical wave progression rules, templates, and plan-first enforcement documentation to govern all future implementation plans.

### Milestones & Deliverables
- [NEW] `.agents/rules/wave-progression.md`: Canonical wave progression and execution-evidence rules.
- [NEW] `docs/templates/wave_plan_template.md`: Canonical template for compliant wave plans.
- [MODIFY] `.agents/rules/plan-first-enforcement.md`: Reference wave progression invariants and output brevity rules.

### Acceptance Criteria
- Wave progression rules declare the 4 required wave subsections and 6 execution evidence fields.
- Plan word cap is formally specified at 1,000 words.
- Chat output brevity rule (~120 words target, 300 words ceiling) explicitly forbids all-wave status table dumps.

### Runtime Receipt & Completion Gate
- Run: `python3 -c "import pathlib; assert pathlib.Path('.agents/rules/wave-progression.md').is_file()"`
- Input: `.agents/rules/wave-progression.md`
- Expected: Zero errors and exit code 0.
- Verify independently: `git status --short .agents/rules/`
- Fail if: Any rule file is missing or unreferenced.
- Record: receipts/wave1_rules.json

---

## Wave 2: Validator Core & Mechanical Evidence Enforcement

### Objective & Scope
Implement execution evidence parsing and length validation in `tools/implementation_plan_core/` and update `tools/validate_implementation_plan.py` to enforce the new schema while making status tables optional.

### Milestones & Deliverables
- [NEW] `tools/implementation_plan_core/__init__.py`: Package initialization.
- [NEW] `tools/implementation_plan_core/evidence_requirements.py`: 1000-word limit and 6 completion gate fields validation.
- [MODIFY] `tools/validate_implementation_plan.py`: Integrate evidence validation, add Objective & Scope requirement, and make status tables optional.

### Acceptance Criteria
- Validator requires `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate`.
- Validator enforces the 6 gate fields (`Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, `Record:`).
- Plans without status tables pass validation cleanly.

### Runtime Receipt & Completion Gate
- Run: `python3 -m unittest tests/test_implementation_plan_governance.py`
- Input: `tests/test_implementation_plan_governance.py`
- Expected: 24 tests pass with exit code 0.
- Verify independently: Inspect test runner pass count.
- Fail if: Non-zero exit code or validator regression.
- Record: receipts/wave2_validator.json

---

## Wave 3: Hook Dispatcher Silencing & Integration Gatekeeping

### Objective & Scope
Update Antigravity lifecycle hooks in `tools/hook_dispatch.py` to silence automatic chat-polluting table outputs, maintain the 8-hook turn gate invariant in `.agents/hooks.json`, and update hook test suites.

### Milestones & Deliverables
- [MODIFY] `tools/hook_dispatch.py`: Silence `handle_stop_wave_summary` and allow status table omission in `handle_pre_edit_plan`.
- [MODIFY] `.agents/hooks.json`: Retain all 8 hooks with `stop_wave_summary` silenced.
- [MODIFY] `tests/test_hook_dispatch.py`: Test silenced stop hook and updated plan validation.
- [MODIFY] `tests/test_implementation_plan_governance.py`: Comprehensive test coverage for new wave plan schema.

### Acceptance Criteria
- `stop_wave_summary` outputs `{}` without emitting markdown tables to stdout.
- `hook_count` in `.agents/hooks.json` remains >= 7 (8 active hooks).
- `tests/test_hook_dispatch.py` and `tests/test_turn_gates.py` pass with 100% success.

### Runtime Receipt & Completion Gate
- Run: `python3 -m unittest tests/test_hook_dispatch.py tests/test_turn_gates.py`
- Input: Hook dispatch and turn gate test suites.
- Expected: All unit tests pass with exit code 0.
- Verify independently: Verify pre-turn and post-turn gates pass via `python3 tools/validate_turn_gates.py`.
- Fail if: Hook count < 7 or any gate check fails.
- Record: receipts/wave3_hooks.json
