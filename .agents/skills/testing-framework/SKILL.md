---
name: testing-framework
description: Design, select, and run rigorous graph-backed tests, manage skips and collection integrity, and validate regression coverage under pytest timeout rules.
---

# Testing Framework

Use tests to prove behavior rather than to conceal defects. Editing tests is legitimate when the intended contract evolves, a regression test is added, or test infrastructure is defective; weakening assertions or adding broad mocks merely to pass a test suite is strictly prohibited.

## 1. Class A vs Class B Pytest Protocol

All pytest invocations fall into exactly one of two classes:

### Class A: Debug Run (Fix Cycle)
- Scope MUST be a single test file or single named test case:
  ```bash
  .venv/bin/pytest tests/unit/test_foo.py -v --timeout=60
  .venv/bin/pytest tests/unit/test_foo.py::TestClass::test_method -v --timeout=60
  ```
- Unscoped runs (`pytest` or `pytest tests/`) are strictly forbidden.
- Synchronous execution only; hard limit `--timeout=60` per test.
- Background execution is prohibited.

### Class B: Receipt Run (Wave Completion)
- Executed exactly once per wave after all fixes pass.
- Scoped strictly to the wave's declared acceptance test files.
- Mandatory `--timeout=60`.
- Pass counts and durable receipt paths are recorded in governance ledgers.

## 2. Test-First & Determinism Requirements

1. **Sequence**:
   - Write the test (confirming failure on baseline).
   - Write the minimal production code to pass.
   - Re-run the test (confirming pass).
   - Verify zero regressions on adjacent tests.
2. **Determinism**:
   - Explicit fixed seeds (no random inputs).
   - Injected timestamps (no wall-clock dependencies).
   - Identical inputs must yield identical outputs.
3. **Mock Discipline**:
   - Mocks are permitted ONLY for external services, hardware, or inaccessible CI environments.
   - Mocks must NEVER bypass validation, authorization, routing, replay protection, or side-effect guards.
   - Production imports of mock factories or mock objects are strictly blocked by `tools/audit_mock_reachability.py`.

## 3. Collection, Skip & XFail Integrity

- **Count Invariants**: `collected == executed` for every targeted run. Unexpected deselections or count drops fail closed.
- **Skip Rules**: `pytest.mark.skip` or `pytest.mark.skipif` requires explicit `reason=` and ownership tracking. Empty reasons (`"broken"`, `"TODO"`, `"skip for now"`) are constitutional violations.
- **XFail Rules**: `@pytest.mark.xfail` must strictly declare `strict=True`.

## 4. Application-Owned Testing Model (`apps_*`)

App-owned test surfaces (`tests/apps_*/`, `tests/unit/apps_*/`, `tests/_apps_contract/`) protect governed product behavior, not internal implementation details:
- **LAW**: Protects system authority, provenance, non-fabrication, and spine authority.
- **APP CONTRACT**: Validates CLI behavior, dispatch adapters, artifact schemas, and exit codes.
- **SPINE BINDING**: Verifies subsystem routes through governed canonical pipelines.
- **EVAL CONTRACT**: Verifies evaluators grade completed snapshots without mutating or rescuing.
- **HARNESS**: Test fixtures, environment setup, and platform-specific collection.

## 5. Verification Commands

```bash
.venv/bin/pytest <exact-nodeids-or-file> -v --timeout=60
.venv/bin/python tools/testing_gaps_auditor.py --include-uncovered-backlog --json
.venv/bin/python tools/audit_mock_reachability.py
```
