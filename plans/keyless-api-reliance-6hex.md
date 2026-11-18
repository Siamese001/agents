# Implementation Plan: Achieving Zero External API Key Reliance

## Goal Description
The objective is to eliminate the requirement for external API keys in the `agents` repository by transitioning all providers to either local-only execution or a formal "keyless" configuration. The recent attempt to simply remove environment variables failed because the `infrastructure/live_execution.py` runtime enforces strict key validation. We will formalize a `KeylessProvider` interface.

## User Review Required
- **IMPORTANT**: This change will modify the core runtime enforcement logic. While I aim to preserve existing local-only workflows, the strictness of `LiveExecutionError` will be adjusted to allow for intentional "keyless" providers.

## Open Questions
- Are there any specific providers that must continue to use keys for specific production pipelines? (Current plan assumes all are moving to local/keyless).

## Wave 1: Formalize Keyless Runtime Interface
### Objective & Scope
Update the core credential enforcement engine to distinguish between missing keys (errors) and intentionally keyless providers.

### Milestones & Deliverables
- [MODIFY] `infrastructure/live_execution.py`: Add `KEYLESS_PROVIDERS` configuration and update `api_key()` logic.

### Acceptance Criteria
- `api_key()` for a provider in `KEYLESS_PROVIDERS` does not raise `LiveExecutionError` when the environment variable is missing.

### Runtime Receipt & Completion Gate
- **Run:** `python3 -c "from infrastructure.live_execution import api_key; print(api_key('anthropic'))"` (with anthropic in keyless)
- **Input:** None
- **Expected:** Returns "keyless-local" or similar identifier.
- **Verify independently:** Check console output.
- **Fail if:** Raises `LiveExecutionError`.
- **Record:** `artifacts/receipts/wave1_keyless.json`

## Wave 2: Update SDK Client Wrappers
### Objective & Scope
Ensure that SDK wrappers correctly handle the keyless identifier provided by the runtime.

### Milestones & Deliverables
- [MODIFY] `infrastructure/sdks_mcps/client_wrappers.py`: Ensure client initialization does not fail if `api_key()` returns the keyless signal.

### Acceptance Criteria
- Agents can initialize providers using keyless configuration without triggering auth failures in the SDK.

### Runtime Receipt & Completion Gate
- **Run:** `pytest infrastructure/sdks_mcps/test_client_wrappers.py`
- **Input:** Test suite
- **Expected:** All tests pass.
- **Verify independently:** Observe pass count in stdout.
- **Fail if:** Test suite failures or `LiveExecutionError`.
- **Record:** `artifacts/receipts/wave2_sdk_wrappers.json`

## Verification Plan
### Automated Tests
Exact commands to run automated tests:
- `pytest tests/infrastructure/test_live_execution.py`
- `pytest infrastructure/sdks_mcps/test_client_wrappers.py`

### Manual Verification
- Attempt to run a basic agent task with zero API keys set in the environment and confirm no `LiveExecutionError` occurs for the migrated providers.
