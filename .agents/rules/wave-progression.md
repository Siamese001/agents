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

Status values: `COMPLETE`, `OPEN`, `BLOCKED`, `NOT_STARTED`. Sequential enforcement: never advance to Wave N+1 until Wave N and earlier waves meet the behavior and evidence conditions above. Ordinary engineering completion reports in user chat do NOT render this table, adhering to [.agents/rules/output-brevity-governance.md](output-brevity-governance.md) (target ~150-250 words, max 450 words; strictly NO all-wave status tables dumped into chat).

---

## Wave-Based Implementation Plan Standard
All implementation plans—including planning-mode artifacts (`implementation_plan.md`) and repository markdown plans in `plans/` or `docs/`—must strictly adhere to the wave-based governance architecture. Monolithic, flat, or unstructured plans fail closed. Wave plans have no artificial word-count or wave-count ceiling (`INV-WAVE-PLAN-MAX-WORDS = 0`), allowing full multi-wave architectural specifications and cross-repo refactoring plans of any required extent.

### Required Plan Structure
1. Top-level `# <Plan Title>`.
2. Sequential or Fork-Join Sharded Numbered Waves: `## Wave 1: <Title>`, `## Wave 2A: <Title>`, `## Wave 2B: <Title>`, `## Wave 3: <Title>`, incrementing consecutively without base-number gaps (starting at Wave 0 or Wave 1). Sharded waves may declare `Depends On: Wave 1` (validated for acyclicity by `tools/implementation_plan_core/wave_dag.py`) and an optional fenced ```` ```yaml shard-manifest ```` / ```` ```json shard-manifest ```` annex (`minItems: 1`, non-empty `scope_in`, non-empty `verify_independently`).
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

## Wave & Sharded Progression Discipline
1. **Unconstrained Root-Cause & Sharded Execution**: Parallel `/boost` and `/swarm` shards may execute concurrently across waves, and newly discovered root-cause bugs may be fixed immediately across any connected files (`agents/`, `outreach_engine/`, `resume_graph_engine/`, `apps_research/`, `infrastructure/`, `tools/`, `tests/`) without artificial scope freezes, while preserving directional inter-subsystem and storage import boundaries.
2. **Prerequisites for Wave Completion**:
   - All declared acceptance criteria for the wave have passed in the observed run.
   - Produced behavior/state has been independently checked against the declared expectation; the result is not inferred from a receipt or test harness self-report alone.
   - Durable runtime provenance and evidence links are recorded in the wave ledger table.
   - Any genuine HITL ambiguity ($\Delta \le 20\%$) is resolved.
3. **Failure-Closed Verification**: If a criterion fails, diagnose and repair the root cause before marking the wave `COMPLETE`.
4. **Distinct Engineering-Wave Scope vs Production Isolation**: Engineering waves and test suites verify code changes and contracts within isolated worktrees/sandboxes without mutating external repositories.

---

## pytest Run Protocol
All pytest invocations fall into debug/verification runs or wave receipt runs:

### Class A — Debug & Verification run
Used during bug fixes, `/boost`, `/swarm`, and refactoring cycles to verify changes across any number of impacted files or suites.
- Scope may be a single test file, a single named test case, any coupled multi-file producer+contract+consumer test slice (no file-count cap), or full subsystem/repository test directories (`pytest tests/ --timeout=60`, `pytest resume_graph_engine/tests/ --timeout=60`, etc.). Use `.venv/bin/python tools/adg_impact_tests.py --changed-files <files>` to compute all transitive impacted test files across all 6 test roots.
- Must include `--timeout=60` (or `--timeout=180` for broad E2E/integration suites).
- Must be synchronous (`WaitMsBeforeAsync >= 10000`).

### Class B — Receipt run
Used at wave completion after all fixes pass.
- Scope covers all declared acceptance and impacted regression test files.
- Must include `--timeout=60` (or `--timeout=180`). Synchronous (`WaitMsBeforeAsync >= 10000`).
- Produces wave runtime receipt; pass count recorded in wave ledger.

### Prohibited patterns
- Skipping or weakening tests to conceal regressions.

---

## Wave Implementation Status Tracking & Reporting Separation
Wave implementation progress is tracked durably within repository artifacts and persistent ledgers:

1. **Durable Ledger Tracking**: Every wave declared in the plan must be explicitly tracked internally with discrete status indicators (`COMPLETE`, `OPEN`, `BLOCKED`), empirical evidence, and explicit execution receipts (file path, test run command with pass counts, or commit SHA).
2. **User-Facing Completion Response Separation**: User-facing completion messages for engineering turns MUST conform strictly to [.agents/rules/output-brevity-governance.md](output-brevity-governance.md) and repository output budget invariants (~150-250 words target, 450 words maximum). Agents must NOT output all-wave implementation status tables or wave ledger tables in ordinary conversational completion turns. Full status tables are reserved for persistent artifacts or explicit operator diagnostic requests.
