---
trigger: always_on
---

# Wave Progression Rules

Governs wave-based plans, implementations, remediations, and continuations. Sourced from `AGENTS.md`.

## Execution-Evidence-Gated Progression
A wave is `COMPLETE` only when:
1. All declared acceptance criteria pass against the behavior the wave is meant to deliver.
2. The declared workflow has actually run with representative inputs in the stated target or isolated runtime, and observable outputs/state have been independently checked against expected results.
3. The run has durable provenance (scope and input digests, runtime, command or run ID, timestamp, terminal outcome, and links/digests for raw logs and validation artifacts).

Receipts record runs; they do not prove that runs worked. Never accept a self-authored receipt, status field, screenshot of a receipt, mocked return value, or generated summary as sole evidence of functionality. Inspect source run output and verify produced behavior/state through an independent path. Keep failures and retries visible; a later success supersedes a failure only when it reruns the same declared scope and passes every criterion. Simulations and mocks may support component checks, but must be labeled and cannot qualify a real workflow or production-readiness claim.

For every new wave plan, define each wave gate around a concrete runnable behavior using these 6 exact fields:
- `Run:`
- `Input:`
- `Expected:`
- `Verify independently:`
- `Fail if:`
- `Record:`

Prefer an end-to-end run where practical, then targeted tests for boundaries and regressions. The receipt is the traceable record of this evidence, never the acceptance criterion itself.

Wave status, observed run result, and provenance are recorded internally in durable receipts and the wave ledger:
`| Wave | Status | Expected behavior | Observed run and independent check | Evidence path | Open blocker / next authorization |`

Status values: `COMPLETE`, `OPEN`, `BLOCKED`, `NOT_STARTED`. Sequential enforcement: never advance to Wave N+1 until Wave N and earlier waves meet the behavior and evidence conditions above. Ordinary engineering completion reports in user chat do NOT render this table, adhering to [.agents/rules/output-brevity-governance.md](output-brevity-governance.md) (target ~120 words, max 300 words; strictly NO all-wave status tables dumped into chat).

---

## Wave-Based Implementation Plan Standard
All implementation plans—including planning-mode artifacts (`implementation_plan.md`) and repository markdown plans in `plans/` or `docs/`—must strictly adhere to the wave-based governance architecture. Monolithic, flat, or unstructured plans fail closed. New wave plans must be concise enough to execute and review without hiding required behavior or gates: use the shortest plan that fully specifies the work, normally 500–800 words, with a hard limit of 1,000 words (`INV-WAVE-PLAN-MAX-WORDS`). Small changes may need fewer than 500 words.

### Required Plan Structure
1. Top-level `# <Plan Title>`.
2. Sequential Numbered Waves: `## Wave 1: <Title>`, `## Wave 2: <Title>`, incrementing consecutively without gaps (starting at Wave 0 or Wave 1).
3. Mandatory Subsections Per Wave:
   - `### Objective & Scope`: Exact bounded sub-goal and boundary.
   - `### Milestones & Deliverables`: Itemized list (`[NEW]`, `[MODIFY]`, `[DELETE]`, schemas, configs, artifacts).
   - `### Acceptance Criteria`: Objective, deterministic pass/fail conditions centered on working behavior.
   - `### Runtime Receipt & Completion Gate`: Exact execution entry point, inputs, expected observable results, independent check, failure conditions, and provenance record with 6 exact fields:
     - `Run:` Command or execution entry point.
     - `Input:` Explicit test fixture or execution input.
     - `Expected:` Observable success criteria and exit code.
     - `Verify independently:` Independent assertion, query, or file inspection.
     - `Fail if:` Explicit failure or regression conditions.
     - `Record:` Durable receipt artifact path.

Plans must pass validation by `python tools/validate_implementation_plan.py`. Any historical plan being edited is subject to the strict new-plan contract before it is restaged.

---

## Sequential Wave Progression Gate Lock
1. **Strict Execution Boundary**: Forbidden from modifying code (`agents/`, `outreach_engine/`, `resume_graph_engine/`, `infrastructure/`), generating tests (`tests/`), or executing mutating commands for Wave N+1 until Wave N is verified `COMPLETE`.
2. **Prerequisites for Advancing**:
   - All declared acceptance criteria for Wave N have passed in the observed run.
   - Produced behavior/state has been independently checked against the declared expectation; the result is not inferred from a receipt or test harness self-report alone.
   - Durable runtime provenance and evidence links are recorded in the wave ledger table.
   - All HITL design decisions for Wave N resolved.
3. **Failure-Closed Halt**: If any milestone or criterion in Wave N fails, wave status is `BLOCKED`. Execution halts immediately.
4. **Distinct Engineering-Wave Scope vs Production Isolation**: Engineering waves and test suites verify code changes and contracts within disposable, isolated temporary sandboxes and MUST NEVER mutate deployment or canonical production environments.

---

## pytest Run Protocol
All pytest invocations fall into exactly one of two classes. No other class is permitted.

### Class A — Debug run
Used during fix cycle to verify a specific change.
- Scope MUST be a single test file or single named test case (`pytest tests/test_foo.py -v` or `pytest tests/test_foo.py::ClassName::test_method -v`). Multi-file or full suite (`pytest tests/`) is forbidden.
- Must include `--timeout=60` (per-test hard limit).
- Must be synchronous (`WaitMsBeforeAsync >= 15000`). Does not produce a receipt.
- **Background forbidden**: If run exceeds `WaitMsBeforeAsync`, something is wrong — kill immediately; do not send to background.

### Class B — Receipt run
Used exactly once per wave at wave completion after all fixes pass.
- Scope MUST be only the wave's declared acceptance test files.
- Must include `--timeout=60`. Synchronous (`WaitMsBeforeAsync >= 120000`).
- Produces wave runtime receipt; pass count recorded in wave ledger.
- Full suite runs require explicit user authorization.

### Prohibited patterns
- `pytest` (no args) or `pytest tests/` (unbounded full suite).
- pytest sent to background (`WaitMsBeforeAsync` too short).
- Multi-file pytest during fix cycle.
- pytest without `--timeout=60`.
- Running pytest again after it already passed.

---

## Wave Implementation Status Tracking & Reporting Separation
Wave implementation progress is tracked durably within repository artifacts and persistent ledgers:

1. **Durable Ledger Tracking**: Every wave declared in the plan must be explicitly tracked internally with discrete status indicators (`COMPLETE`, `OPEN`, `BLOCKED`), empirical evidence, and explicit execution receipts (file path, test run command with pass counts, or commit SHA).
2. **User-Facing Completion Response Separation**: User-facing completion messages for engineering turns MUST conform strictly to [.agents/rules/output-brevity-governance.md](output-brevity-governance.md) and repository output budget invariants (~120 words target, 300 words maximum). Agents must NOT output all-wave implementation status tables or wave ledger tables in ordinary conversational completion turns. Full status tables are reserved for persistent artifacts or explicit operator diagnostic requests.
