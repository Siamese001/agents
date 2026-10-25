# Implementation Plan: Resume & Outreach Engine Pattern Hardening

## Executive Overview
Apply behavioral patterns from `decision-intelligence-engine` natively across `resume_engine`, `resume_graph_engine`, and `outreach_engine` without copying external code. Enforce sub-400-line CLI modules, lazy package imports, 1.5s exit watchdogs, outbound privacy scrubbing, normalized numeric fact grounding, top-10 search accuracy gates, physical output verification, and per-test environment isolation.

| Wave # | Description / Scope | Status |
| :--- | :--- | :--- |
| Wave 1 | One-Way Code Loading & Fast Command Startup | COMPLETED |
| Wave 2 | Outbound Privacy, Fact Matching & Human Sign-Off | COMPLETED |
| Wave 3 | Top-10 Search Accuracy, Storage Proof & Saved-Step Resume | COMPLETED |
| Wave 4 | Test Isolation & Real Output Folder Protection | COMPLETED |

---

## Wave 1: One-Way Code Loading & Fast Command Startup

### Objective & Scope
- **In Scope**: Split `resume_engine/cli.py` under 400 lines, eliminate bare `except Exception: pass` blocks, add a 1.5s exit watchdog, and make `outreach_engine/__init__.py` and `apps_rg/__init__.py` load heavy runtime modules lazily.
- **Out of Scope**: External provider logic changes.

### Milestones & Deliverables
- [x] `resume_engine/cli.py`: Parse `--help` and `--version` before environment setup and delegate inspection commands.
- [x] `resume_engine/cli_inspectors.py`: Read-only `models` and `cache` handlers with explicit fallback reason tracking and 1.5s exit watchdog.
- [x] `outreach_engine/__init__.py` and `resume_graph_engine/src/apps_rg/__init__.py`: Lazy `__getattr__` exports and deferred `.env` loading.

### Acceptance Criteria
- `resume_engine/cli.py` is under 400 lines with zero bare `except Exception: pass` blocks.
- Importing `outreach_engine` does not eagerly load `apps_lic.judges.evaluator`.
- `E2E-EXEMPT`: Entrypoint and module boundary wave.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest outreach_engine/tests/test_unified_cli.py -v --timeout=60`
- Input: CLI `--help`, `models`, and module import checks.
- Expected: All CLI tests pass with line count of `resume_engine/cli.py` < 400.
- Verify independently: Check `wc -l resume_engine/cli.py` and `sys.modules` lazy state.
- Fail if: `resume_engine/cli.py` >= 400 lines or eager judge import occurs.
- Record: reports/wave1_cli_layering_receipt.json

---

## Wave 2: Outbound Privacy, Fact Matching & Human Sign-Off

### Objective & Scope
- **In Scope**: Add native `OutboundPrivacyValidator`, normalize dollar and percentage matching in `GroundingValidator`, fold `UnsupportedPersonalizationValidator` into `hard_gate_passed`, and add score-gap human sign-off check (`requires_human_signoff`).
- **Out of Scope**: External LLM prompt templates.

### Milestones & Deliverables
- [x] `outreach_engine/src/apps_lic/domain/validators.py`: `OutboundPrivacyValidator` and normalized numeric fact matching in `GroundingValidator`.
- [x] `outreach_engine/src/apps_lic/judges/evaluator.py`: Include privacy and unsupported personalization violations in `hard_gate_passed` and expose `requires_human_signoff`.

### Acceptance Criteria
- Outbound drafts containing secret patterns, internal strategy markers, billing rates, or unverified company claims fail `hard_gate_passed`.
- `$1M` matches `$1,000,000` in declared facts, while `10%` does not falsely match `110%`.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest outreach_engine/tests/test_validators.py outreach_engine/tests/test_pattern_hardening_waves.py -v --timeout=60`
- Input: Synthetic secret strings, formatted dollar/percentage claims, and unverified briefings.
- Expected: 100% pass across validator and judge hardening tests.
- Verify independently: Confirm `verdict.hard_gate_passed is False` on unverified personalization.
- Fail if: Any secret pattern or unverified personalization passes `hard_gate_passed`.
- Record: reports/wave2_privacy_grounding_receipt.json

---

## Wave 3: Top-10 Search Accuracy, Storage Proof & Saved-Step Resume

### Objective & Scope
- **In Scope**: Enforce `top_k <= 10` and zero top-10 rank regression in `c03_ci_ratchet.py`, verify mandatory run outputs on disk with model-neutral filenames in `run_output_contract.py`, and support `resume_or_patch_run` path rebinding in `OutreachOrchestrator`.
- **Out of Scope**: Replacing BGE-M3 weights.

### Milestones & Deliverables
- [x] `resume_graph_engine/src/apps_rg/evals/c03_ci_ratchet.py`: Gate `retrieval_top_k_exceeds_10` and `top_10_rank_regression`.
- [x] `resume_graph_engine/src/apps_rg/runtime/run_output_contract.py`: Add `is_model_neutral_filename` and `verify_physical_run_outputs`.
- [x] `outreach_engine/src/apps_lic/pipeline/orchestrator.py`: Record completed stages in `run_manifest.json` and implement `resume_or_patch_run`.

### Acceptance Criteria
- `verify_physical_run_outputs` confirms non-zero size, SHA-256 digest, valid JSON readback, and model-neutral filenames.
- `resume_or_patch_run` rebinds `artifact_dir` and preserves completed stages.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest outreach_engine/tests/test_pattern_hardening_waves.py -v --timeout=60`
- Input: Ephemeral run directories and stage manifests.
- Expected: Physical output verification and stage resume tests pass.
- Verify independently: Inspect `run_manifest.json` after `resume_or_patch_run`.
- Fail if: Model-branded filename passes or corrupt JSON is accepted.
- Record: reports/wave3_storage_search_resume_receipt.json

---

## Wave 4: Test Isolation & Real Output Folder Protection

### Objective & Scope
- **In Scope**: Isolate per-test cache directories using `tmp_path` in both `resume_graph_engine/tests/conftest.py` and `outreach_engine/tests/conftest.py` and verify all 4 waves with dedicated unit and E2E tests.
- **Out of Scope**: Historical artifact cleanup.

### Milestones & Deliverables
- [x] `resume_graph_engine/tests/conftest.py` and `outreach_engine/tests/conftest.py`: Per-test `tmp_path` cache isolation fixtures.
- [x] `outreach_engine/tests/test_pattern_hardening_waves.py`: End-to-end verification of Waves 1–4.

### Acceptance Criteria
- Every test receives an isolated `tmp_path` cache root and leaves zero untracked artifacts in production directories.

### Runtime Receipt & Completion Gate
- Run: `/Users/amitayer/Git/agents/.venv/bin/pytest outreach_engine/tests/test_pattern_hardening_waves.py outreach_engine/tests/test_replay_integrity_e2e.py -v --timeout=60`
- Input: Full pattern hardening and E2E replay test suites.
- Expected: 100% pass with zero production directory mutations.
- Verify independently: Check `git status --porcelain` confirms no untracked output files.
- Fail if: Any test mutates repository cache or artifact directories.
- Record: reports/wave4_test_isolation_receipt.json
