# Implementation Plan: Harden WorkflowExecutionEngine and Agents Health Checks

## Implementation Status Table

| Wave | Description | Status |
| :--- | :--- | :--- |
| Wave 1 | WorkflowExecutionEngine Primitives and Idempotency Contracts | COMPLETE |
| Wave 2 | WorkflowExecutionEngine Hardening (Idempotency, Checkpoints, Bounded Timeouts, Diagnostics) | COMPLETE |
| Wave 3 | Agents Health Check Hardening (`agents/health.py`) | COMPLETE |
| Wave 4 | Comprehensive Test Suite & Redundant Call Verification | COMPLETE |
| Wave 5 | Governance Verification, Pre-Commit Audit, and Worktree Hygiene | COMPLETE |


---

## Wave 1: WorkflowExecutionEngine Primitives and Idempotency Contracts

### Objective & Scope
Enhance the foundational orchestration primitives in `agents/orchestration/primitives.py` and result structures in `agents/orchestration/engine.py` to carry explicit idempotency declarations, product stage markers, bounded timeout parameters, and structured failure diagnostic containers.

### Milestones & Deliverables
- [UPDATE] `agents/orchestration/primitives.py`:
  - Enhance `WorkflowStep` with:
    - `idempotent: bool = False`: Declare whether the step handler is safe to re-execute on transient failures without side-effects or duplicate billing.
    - `is_product_stage: bool = False`: Declare whether the step generates primary product deliverables (e.g. resume generation, outreach generation).
    - `timeout: float | None = None`: Optional per-step execution deadline in seconds.
- [UPDATE] `agents/orchestration/engine.py`:
  - Enhance `StepExecutionResult` with:
    - `failure_kind: str = ""` (authoritative `FailureKind` string).
    - `recovery_action: str = ""` (authoritative `RecoveryAction` string).
    - `diagnostics: dict[str, Any] = field(default_factory=dict)`: Detailed failure diagnostics (reason, root cause, retry blocked status, duration, timeout enforcement).
  - Enhance `WorkflowExecutionReport` with:
    - `failure_diagnostics: dict[str, Any] = field(default_factory=dict)`: Top-level failure diagnostics packet for failed workflows.

### Acceptance Criteria
- `WorkflowStep` cleanly defaults `idempotent=False`, `is_product_stage=False`, and `timeout=None` with 100% backward compatibility for existing callers.
- `StepExecutionResult.as_dict()` and `WorkflowExecutionReport.as_dict()` include the new diagnostic fields.
- Existing orchestration tests compile and pass without regressions.

### Verification Commands
```bash
/Users/amitayer/Git/agents/.venv/bin/pytest tests/unit/test_orchestration_runtime_hardening.py -q
```

---

## Wave 2: WorkflowExecutionEngine Hardening (Idempotency, Checkpoints, Bounded Timeouts, Diagnostics)

### Objective & Scope
Harden `WorkflowExecutionEngine` in `agents/orchestration/engine.py` to:
1. Never retry completed product stages for transport failures.
2. Retry only failed idempotent operations within existing SSOT budgets (`RecoveryBudget`).
3. Enforce bounded timeouts on step execution to eliminate unbounded hanging.
4. Incrementally persist and preserve successful checkpoints on disk (`workflow_state.json`).
5. Emit exact failure diagnostics and suppress redundant provider calls.
6. Align `agents/cli.py` workflow steps with explicit idempotency and stage markers.

### Milestones & Deliverables
- [UPDATE] `agents/orchestration/engine.py`:
  - Integrate `RecoveryBudget` (default `RecoveryBudget()`) as the Single Source of Truth (SSOT) recovery budget.
  - Maintain `RecoveryCounters` across execution.
  - Checkpoint Preservation:
    - Write an updated checkpoint to `workflow_state.json` immediately upon each successful step completion, ensuring intermediate progress is safely saved even if a later step fails.
    - Support checkpoint resumption: if a step is already marked `PASSED` / completed in existing state or checkpoint, reuse the result without re-executing.
  - Stage Protection:
    - Once a product stage is completed (`is_product_stage=True` and status `PASSED`), strictly block re-execution or retry on subsequent transport failures.
  - Idempotency & SSOT Budget Enforced Retries:
    - On transient transport failures (`FailureKind.TRANSPORT` or transient error string):
      - Check idempotency: If `not (step.idempotent or step.metadata.get("idempotent", False))`, immediately suppress retry, transition to failure, and record diagnostic `retry_blocked="non_idempotent_operation"`.
      - Check SSOT budget: Verify `counters.transport_retries < budget.max_transport_retries`. If budget exhausted, stop retries and emit `retry_blocked="budget_exhausted"`.
      - Only retry when step is idempotent AND budget remains available.
  - Bounded Step Timeout:
    - Execute `step.handler(ctx)` inside bounded timeout (`step.timeout or self.default_step_timeout`, default 30.0s) using a worker executor.
    - Catch timeouts and emit exact failure diagnostics (`timeout_enforced=True`, duration).
  - Exact Failure Diagnostics:
    - Emit comprehensive failure metadata including `failure_kind`, `recovery_action`, root cause, attempt history, and diagnostic codes in `StepExecutionResult` and `WorkflowExecutionReport`.
- [UPDATE] `agents/cli.py`:
  - Declare `company_research` as `idempotent=True`, `is_product_stage=True`.
  - Declare `resume_tailoring` and `executive_outreach` as `is_product_stage=True`, `idempotent=False` (preventing redundant regeneration on downstream failures).

### Acceptance Criteria
- Completed product stages are never retried when transport errors occur downstream.
- Non-idempotent steps never execute more than 1 attempt upon transport failure (zero redundant provider calls).
- Idempotent steps retry only up to `budget.max_transport_retries` with exponential backoff.
- Step execution exceeding timeout fails closed within the bounded limit.
- `workflow_state.json` preserves successful checkpoints before failure occurs.

### Verification Commands
```bash
/Users/amitayer/Git/agents/.venv/bin/pytest tests/unit/test_orchestration_runtime_hardening.py -v
```

---

## Wave 3: Agents Health Check Hardening (`agents/health.py`)

### Objective & Scope
Harden the sovereign health check runner (`agents/health.py` and `tools/health_check.py`) to work seamlessly across worktrees and standalone environments, enforce bounded timeouts, isolate per-domain results, and emit exact failure diagnostics.

### Milestones & Deliverables
- [UPDATE] `agents/health.py`:
  - Resilient pytest resolution (`_resolve_pytest_cmd`):
    - Check local `.venv/bin/pytest`.
    - Check worktree parent `.venv/bin/pytest` (`_REPO_ROOT.parent.parent / ".venv" / "bin" / "pytest"`).
    - Check `Path(sys.executable).parent / "pytest"`.
    - Fall back to `[sys.executable, "-m", "pytest"]`.
  - Bounded Subprocess Execution:
    - Add explicit bounded timeout (`timeout=180` total or 60s per domain) to `subprocess.run`.
    - Catch `subprocess.TimeoutExpired` and emit exact timeout diagnostics.
  - Domain Isolation & Independent Outcome Reporting:
    - Execute and evaluate checks per domain or map outcomes per test file so that a failure in one domain does NOT mark unrelated passing domains as FAILED.
  - Exact Failure Diagnostics:
    - Extract and report exact failed test targets and error messages from pytest output into `domain_results[...]["failures"]` and the top-level report.
    - Format verbose and CLI summary outputs with exact failure locations.
  - Domain Registry Update:
    - Register new engine hardening checks under the `Orchestration` and `Failure Handling` domains.

### Acceptance Criteria
- `python -m agents check` and `python tools/health_check.py` execute successfully in worktree environments without `[Errno 2] No such file or directory: 'pytest'`.
- Subprocess execution enforces a strict timeout (never hangs indefinitely).
- If a check fails, only its specific domain is marked `FAILED`; healthy domains retain `PASSED`.
- Exact failure traces and root causes are surfaced in `--json` and CLI output.

### Verification Commands
```bash
/Users/amitayer/Git/agents/.venv/bin/python -m agents check --domain orchestration
/Users/amitayer/Git/agents/.venv/bin/python -m agents check --json
```

---

## Wave 4: Comprehensive Test Suite & Redundant Call Verification

### Objective & Scope
Author a rigorous, dedicated test suite verifying all newly hardened invariants: idempotency gating, checkpoint preservation, bounded timeouts, exact failure diagnostics, and zero redundant provider calls.

### Milestones & Deliverables
- [CREATE] `tests/unit/test_workflow_execution_engine_hardening.py`:
  - `test_never_retry_completed_product_stages_on_transport_failure`: Verify completed stage is not re-executed when downstream fails or upon workflow retry.
  - `test_retry_only_failed_idempotent_operations_within_ssot_budget`: Verify non-idempotent operation fails with 0 retries; idempotent operation retries up to `RecoveryBudget.max_transport_retries`.
  - `test_enforce_bounded_timeouts_prevents_unbounded_execution`: Verify slow handler times out cleanly without blocking execution indefinitely.
  - `test_preserve_successful_checkpoints_on_failure`: Verify intermediate `workflow_state.json` contains successful step outputs when subsequent steps fail.
  - `test_emit_exact_failure_diagnostics`: Verify structured diagnostic fields in result and report.
  - `test_verify_no_redundant_provider_calls`: Use call counter mock to assert exactly 1 invocation on non-idempotent failure and bounded invocations on idempotent failures.
  - `test_health_checks_domain_isolation_and_diagnostics`: Verify health check runner accurately isolates domain statuses and extracts error details.

### Acceptance Criteria
- All newly added tests pass with 100% determinism.
- Existing unit tests in `test_orchestration_runtime_hardening.py` and `test_agents_cli_e2e.py` pass without regression.

### Verification Commands
```bash
/Users/amitayer/Git/agents/.venv/bin/pytest tests/unit/test_workflow_execution_engine_hardening.py -v
/Users/amitayer/Git/agents/.venv/bin/pytest tests/unit/test_orchestration_runtime_hardening.py -v
/Users/amitayer/Git/agents/.venv/bin/python -m agents check
```

---

## Wave 5: Governance Verification, Pre-Commit Audit, and Worktree Hygiene

### Objective & Scope
Verify code quality, architectural compliance, layer boundaries, and file budgets across the worktree before finalizing the worktree branch.

### Milestones & Deliverables
- Run repository pre-commit and architectural verification tools:
  - `tools/verify_commit.py`
  - `tools/lint_file_budgets.py`
  - `tools/lint_architecture_boundaries.py`
- Verify git status, diff purity, and clean worktree state.

### Acceptance Criteria
- All architectural linters and commit verification gates pass with code 0.
- No credential leakage or unsolicited refactoring.

### Verification Commands
```bash
/Users/amitayer/Git/agents/.venv/bin/python tools/verify_commit.py
git status --short
```
