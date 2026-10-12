# Wave-Based Implementation Plan Template

Canonical reference template for wave-based engineering implementation plans in this repository. All implementation plans (including planning-mode artifacts and stored plans) must adhere to the structural and governance rules defined in [.agents/rules/wave-progression.md](../../.agents/rules/wave-progression.md).

## Governance Summary

- **Wave Decomposition**: Deconstruct engineering work into sequential numbered waves (`## Wave 1: <Title>`, `## Wave 2: <Title>`) starting at Wave 0 or 1 with no gaps.
- **Mandatory Subsections**: Each wave must contain exactly four subsections: `### Objective & Scope`, `### Milestones & Deliverables`, `### Acceptance Criteria`, and `### Runtime Receipt & Completion Gate`.
- **Completion Gate Fields**: Every wave completion gate must explicitly specify all six runtime evidence fields: `Run:`, `Input:`, `Expected:`, `Verify independently:`, `Fail if:`, and `Record:`.
- **Word Budget (`INV-WAVE-PLAN-MAX-WORDS`)**: The entire plan should normally target 500–800 words, with a hard maximum of 1,000 words. Keep descriptions bounded, precise, and free of conversational padding.
- **Chat Reporting Separation**: Do not dump all-wave status tables into ordinary chat turns. Chat completion responses target ~120 words (hard max 300 words).

---

## Wave 1: Core Subsystem Foundation & Interface Contracts

### Objective & Scope
Establish the bounded foundation for the subsystem change. Define typed interface contracts, data models, and baseline validators without modifying production dispatch logic or introducing unverified downstream dependencies.

### Milestones & Deliverables
- [NEW] `infrastructure/core/subsystem_protocol.py`: Define runtime protocol interfaces and abstract gateway contracts.
- [NEW] `infrastructure/core/models.py`: Immutable data transfer models with strict attribute type annotations.
- [MODIFY] `infrastructure/core/__init__.py`: Export public interface types and versioned symbols.
- [NEW] `tests/unit/test_subsystem_protocol.py`: Comprehensive unit tests verifying schema adherence and boundary enforcement.

### Acceptance Criteria
- Protocol interfaces pass static typing validation with zero diagnostics.
- All unit tests in `tests/unit/test_subsystem_protocol.py` pass synchronously under `--timeout=60`.
- Interface definitions introduce zero circular dependencies across subsystem layers.
- Contract schemas reject missing or improperly typed payload attributes with deterministic errors.

### Runtime Receipt & Completion Gate
- Run: `pytest tests/unit/test_subsystem_protocol.py -v --timeout=60`
- Input: Canonical mock event payloads covering nominal and malformed schema variants.
- Expected: 4 passed, 0 failed, exit code 0.
- Verify independently: Inspect test run stdout confirming all schema boundary invariants pass.
- Fail if: Any unit test fails, timeout exceeds 60 seconds, or circular imports are reported.
- Record: `reports/wave1_protocol_foundation_receipt.json`

---

## Wave 2: Execution Engine Integration & Wiring

### Objective & Scope
Integrate the core subsystem protocols into the primary processing pipeline. Wire dispatch routines and ensure state propagation operates within isolated sandboxes without mutating live production state.

### Milestones & Deliverables
- [MODIFY] `agents/runtime_dispatcher.py`: Wire the new protocol handler into pipeline event dispatch.
- [MODIFY] `agents/configuration_resolver.py`: Register subsystem configuration flags and runtime defaults.
- [NEW] `tests/integration/test_dispatcher_wiring.py`: Integration test verifying end-to-end dispatch through new protocol handlers.
- [DELETE] `infrastructure/core/legacy_protocol_stub.py`: Remove obsolete protocol shim superseded by Wave 1.

### Acceptance Criteria
- Dispatcher cleanly routes incoming requests through the new subsystem protocol without unhandled exceptions.
- Integration tests confirm correct state transition across intermediate execution boundaries.
- No existing dispatch paths or unassociated handlers suffer performance or behavior regression.
- Regression suite for adjacent dispatcher handlers passes with 100% success.

### Runtime Receipt & Completion Gate
- Run: `pytest tests/integration/test_dispatcher_wiring.py -v --timeout=60`
- Input: Synthetic integration workload executing 10 representative dispatch sequences.
- Expected: All integration assertions pass, exit code 0.
- Verify independently: Verify execution log traces confirming proper event lifecycle invocation.
- Fail if: Dispatcher raises unhandled exceptions, fails to propagate state, or alters canonical store.
- Record: `reports/wave2_dispatcher_wiring_receipt.json`

---

## Wave 3: End-to-End Verification & Verification Closeout

### Objective & Scope
Perform rigorous end-to-end validation across the unified pipeline. Validate failure modes, boundary error handling, and performance under stress before promoting to main.

### Milestones & Deliverables
- [NEW] `tests/end_to_end/test_subsystem_pipeline_e2e.py`: End-to-end pipeline test covering nominal and adversarial scenarios.
- [NEW] `reports/subsystem_e2e_benchmark_receipt.json`: Telemetry benchmark verifying execution latency remains within budgets.
- [MODIFY] `docs/reference/subsystem_architecture.md`: Document updated interface architecture and runtime contracts.

### Acceptance Criteria
- End-to-end execution completes successfully across all standard user entry paths in sandbox runtime.
- Adversarial tests confirm fail-closed behavior on corrupted inputs with zero state leakage.
- Latency benchmarks confirm processing overhead is within the allowable performance envelope (<50ms per call).
- Full wave-scoped test suite passes cleanly with durable provenance recorded.

### Runtime Receipt & Completion Gate
- Run: `pytest tests/end_to_end/test_subsystem_pipeline_e2e.py -v --timeout=60`
- Input: Production-representative test dataset executed in an isolated temporary test sandbox.
- Expected: Nominal flows succeed, adversarial flows fail closed safely, exit code 0.
- Verify independently: Verify receipt JSON contains valid execution timestamps, pass counts, and run hashes.
- Fail if: Any E2E scenario fails, unexpected side-effects observed, or benchmark threshold violated.
- Record: `reports/wave3_pipeline_e2e_receipt.json`
