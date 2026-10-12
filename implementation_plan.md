# Implementation Plan: Authoritative E2E Lifecycle Output and Child Output Isolation

## Executive Overview
Ensure `python -m agents e2e --json` emits exactly one authoritative JSON lifecycle record on stdout containing stage statuses, artifact hashes, latency metrics, and failure reasons. Child output from sub-engines is completely isolated into artifact log files. Bounded integration tests validate success, blocked, research-enabled, and resume-skipped lifecycles, and a live smoke run verifies real artifacts.

| Wave # | Description / Scope | Status |
| :--- | :--- | :--- |
| Wave 1 | Authoritative Lifecycle Output & Child Output Isolation | COMPLETED |
| Wave 2 | Bounded Integration Test Suite for Lifecycle Flows | COMPLETED |
| Wave 3 | Real E2E Smoke & Artifact Verification | COMPLETED |

---

## Wave 1: Authoritative Lifecycle Output & Child Output Isolation

### Objective & Scope
Isolate child engine stdout/stderr during E2E runs and ensure the top-level CLI emits exactly one authoritative JSON object on stdout when `--json` is supplied, across both nominal completions and error/blocked paths.

### Milestones & Deliverables
- [x] `agents/e2e_output.py`: Output isolation context manager and canonical E2E lifecycle JSON serializer.
- [x] `agents/cli.py`: Integrate output isolation around sub-engine stages, suppress child `--json` forwarding, measure per-stage and overall latency, and emit single authoritative lifecycle JSON.
- [x] `agents/e2e_artifacts.py`: Populate consolidated failure reasons, stage latencies, artifact hashes, and sealing statuses.

### Acceptance Criteria
- Child engines (`apps_rg`, `apps_lic`, `apps_research`) write outputs to run log files rather than leaking to top-level stdout.
- `python -m agents e2e --json` emits exactly one parseable JSON payload on stdout with exit code 0 on success or non-zero on failure.
- Emitted JSON strictly contains `status`, `workflow_status`, `stages` (statuses, latencies, failure reasons), `artifact_hashes`, `artifact_proofs`, `latency` (total and per-stage), and `failure_reasons`.
- Preflight failures, stage execution failures, and deliverable sealing failures cleanly emit the authoritative JSON contract.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest tests/unit/test_agents_cli_e2e.py -v --timeout=60`
- Input: Existing CLI e2e test suite updated for authoritative output contract.
- Expected: All unit tests pass, exit code 0.
- Verify independently: Verify test stdout confirms 0 child output leakage.
- Fail if: Any unit test fails or child output pollutes stdout during `--json` execution.
- Record: reports/wave1_authoritative_json_receipt.json

---

## Wave 2: Bounded Integration Test Suite for Lifecycle Flows

### Objective & Scope
Create a dedicated bounded integration test suite exercising the four mandatory lifecycle flows: nominal success, blocked failure, research-enabled execution, and resume-skipped execution.

### Milestones & Deliverables
- [x] `tests/integration/test_agents_cli_e2e_json.py`: Comprehensive bounded integration suite for all 4 flows under `--json`.
- [x] `tests/unit/test_agents_cli_e2e.py`: Verify JSON schema completeness and strict single-object stdout emission.

### Acceptance Criteria
- Success flow test verifies all stage statuses are `PASSED`, artifact hashes are populated, latency > 0, failure reasons empty, and exactly one JSON object on stdout.
- Blocked flow test verifies status is `FAILED` or `BLOCKED`, failure reasons are populated with descriptive diagnostic strings, and exit code is non-zero.
- Research-enabled flow test (`--with-research`) verifies research stage runs, emits `brief_sha256`, hands off briefing, and passes.
- Resume-skipped flow test (`--skip-resume`) verifies resume stage is marked `SKIPPED`, outreach executes, and valid JSON is emitted.
- All integration tests complete synchronously within bounded per-test timeout (`--timeout=60`).

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest tests/integration/test_agents_cli_e2e_json.py -v --timeout=60`
- Input: Bounded integration test scenarios covering nominal and failure modes.
- Expected: 4 passed, 0 failed, exit code 0.
- Verify independently: Verify stdout captures contain exactly one JSON parseable root object.
- Fail if: Any test fails, exceeds 60s timeout, or child stdout contamination occurs.
- Record: reports/wave2_integration_flows_receipt.json

---

## Wave 3: Real E2E Smoke & Artifact Verification

### Objective & Scope
Execute real end-to-end smoke verification using active environment credentials where permitted, inspect emitted JSON payload, and cryptographically verify all generated artifacts on disk.

### Milestones & Deliverables
- [x] `reports/e2e_authoritative_json_smoke_receipt.json`: Signed runtime execution receipt confirming artifact verification.
- [x] `ops_scripts/run_e2e_authoritative_smoke.py`: Helper script running real E2E smoke and verifying artifact files on disk.

### Acceptance Criteria
- Real E2E execution runs cleanly with authorized credentials.
- Emitted stdout parses as valid JSON with zero extraneous characters.
- Every artifact path referenced in `artifact_hashes` exists on disk with non-zero bytes and exact matching SHA-256.
- PASS is reported only with verified physical artifacts present on disk.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/python ops_scripts/run_e2e_authoritative_smoke.py`
- Input: Canonical demo inputs with real credentials bootstrap.
- Expected: Status `PASSED`, all artifact files verified on disk, exit code 0.
- Verify independently: Inspect hashes of generated artifacts against emitted JSON payload.
- Fail if: JSON parsing fails, stdout has stray logs, or any artifact hash does not match disk content.
- Record: reports/e2e_authoritative_json_smoke_receipt.json
