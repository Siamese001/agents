# Implementation Plan: Remove GitHub Actions Workflows and Obsolete References

## Implementation Status Table

| Wave | Description | Status |
| :--- | :--- | :--- |
| Wave 1 | Decommission GitHub Actions Workflows and Workflow Configurations | COMPLETE |
| Wave 2 | Local Quality Gate & Pre-Commit Verification | COMPLETE |
| Wave 3 | Governed Local-Main Commit | COMPLETE |

## Wave 1: Decommission GitHub Actions Workflows and Workflow Configurations

### Objective & Scope
Permanently remove all GitHub Actions workflow definitions and obsolete CI helper files under `.github/` while preserving all local governance, test, and pre-commit structures.

### Milestones & Deliverables
- [DELETE] `.github/workflows/codex-recovery-bootstrap.yml`
- [DELETE] `.github/workflows/contract-gates.yml`
- [DELETE] `.github/workflows/outreach-pipeline-ci.yml`
- [DELETE] `.github/workflows/resume-pipeline-ci.yml`
- [DELETE] `.github/workflows/reusable-python-gate.yml`
- [DELETE] `.github/actions/python-setup/action.yml`
- [DELETE] `.github/adg_hardening_patch/*`
- [DELETE] `.github/ci-lanes.yaml`
- [DELETE] `.github/workflow-config.yaml`
- [DELETE] `.github/` directory

### Acceptance Criteria
- All 5 remaining workflow files and composite actions under `.github/` are completely removed.
- The `.github/` directory is entirely deleted from the git index.
- Zero git tracking or staging issues remain for deleted workflow files.

### Runtime Receipt & Completion Gate
- Run: `git status --porcelain .github/`
- Expected: All files reported as deleted in index; no untracked files in `.github/`.
- Fail if: Any `.github/` file remains tracked or untracked.

## Wave 2: Local Quality Gate & Pre-Commit Verification

### Objective & Scope
Formally execute the full battery of local pre-commit, turn-gate, architectural, contract, and test validations to ensure zero regression after workflow removal.

### Milestones & Deliverables
- [VERIFY] Tier 1 Pre-Commit Gate: `tools/verify_commit.py` passing across all 5 categories.
- [VERIFY] Pre-Turn & Post-Turn Gates: `tools/validate_turn_gates.py` passing cleanly.
- [VERIFY] Local PR / Main Readiness Gate: `tools/verify_main_readiness.py` passing with 0 defects.
- [VERIFY] Local Platform Health Check: `tools/health_check.py` passing all 29 checks.
- [VERIFY] Fast Governance Pytest Suite: `tests/test_turn_gates.py`, `tests/test_implementation_plan_governance.py`, `tests/test_hitl_governance_enforcement.py`, `tests/test_model_neutral_naming.py`, `tests/test_unified_agent_architecture.py` (59 passed).

### Acceptance Criteria
- 100% pass on Tier 1 Commit Invariants Gate (`tools/verify_commit.py`).
- 100% pass on Tier 2 Main Readiness Gate (`tools/verify_main_readiness.py`).
- 100% pass on Local Health Check (`tools/health_check.py`).
- 100% pass on fast governance test suite (59 passed in pytest).
- No errors or missing dependencies caused by the absence of `.github/`.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/python tools/verify_main_readiness.py`
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest tests/test_turn_gates.py tests/test_implementation_plan_governance.py tests/test_hitl_governance_enforcement.py tests/test_model_neutral_naming.py tests/test_unified_agent_architecture.py --timeout=60 -q`
- Expected: All gates exit with code 0.
- Record: Pass receipts in turn logs.

## Wave 3: Governed Local-Main Commit

### Objective & Scope
Stage the changes, perform a clean conventional commit on the feature branch, and merge into local `main` only without pushing to remote origin.

### Milestones & Deliverables
- [MODIFY] `feat/remove-github-actions`: Commit staged deletions and implementation plan.
- [MERGE] Local `main`: Merge `feat/remove-github-actions` with conventional merge commit.
- [VERIFY] Confirm zero git push to origin; local `main` remains local only.

### Acceptance Criteria
- Clean merge commit on local `main`.
- Working tree on local `main` is clean.
- `origin/main` is not pushed.

### Runtime Receipt & Completion Gate
- Run: `git log -n 3 --oneline` on local `main`
- Run: `git status` on local `main`
- Expected: Local main contains the merge commit; 0 remote pushes.
