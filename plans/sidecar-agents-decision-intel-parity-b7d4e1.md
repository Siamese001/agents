# Wave-Based Implementation Plan: Sidecar Agents Decision Intelligence Structural Parity

## Executive Summary

Upgrade all 7 `agents-*` sidecar automation specifications (`automations/prompts/agents_*_agent.md`) and `automations/prompts/_shared_governance_contract.md` in `/Users/amitayer/Git/agents` so they match the exact structural rigor, control-matrix headers (`C01–C12`), unconditional wave-plan generation mandate (`UNCONDITIONAL_WAVE_PLAN_MANDATE`), Phase 0 worktree provisioning (`Step 0.1`), Phase 1/1.5 executable forensic scanners, Phase 2 Dimension Findings Table + `tools/validate_implementation_plan.py` gate + 20% SSOT margin `HITLDecisionStore` calibration, and Phase 3 5-Point Counterfactual Runtime Proof (`INV-RUNTIME-PROOF-5POINT`) used by the Decision Intelligence Engine sidecar agents, while preserving strict cross-repository isolation (`INV-REPO-SEPARATION-AGENTS-ONLY`).

---

## Wave 1: Shared Contract & Foundation Sidecar Agents (Stages I–II)

### Objective & Scope
Upgrade the shared governance contract and the first two causal stages (`05:30 ET` Storage & Worktree Hygiene and `05:45 ET` SSOT & Boundary Governance) to full Decision Intelligence Engine structural parity, including `C01–C12` control matrix bindings, `UNCONDITIONAL_WAVE_PLAN_MANDATE` across both `MODE: scheduled` and `MODE: interactive`, Phase 0 `Step 0.1` isolated worktree creation, Phase 1/1.5 executable forensic scanners, Phase 2 Dimension Findings Tables, and Phase 3 5-Point Counterfactual Runtime Proof gates.

### Milestones & Deliverables
- `[MODIFY]` `automations/prompts/_shared_governance_contract.md` — Add full `C01–C12` Common Control Matrix (`urn:agents:scheduled-task-common-control-matrix:1.0.0`), `UNCONDITIONAL_WAVE_PLAN_MANDATE`, `INV-WT-EPHEMERAL-SCHEDULED`, `INV-RUNTIME-PROOF-5POINT`, and `INV-AUTOMATION-PERSISTENT-LEARNING-LOOP`.
- `[MODIFY]` `automations/prompts/agents_storage_worktree_hygiene_agent.md` — Upgrade Stage I (Order 1/7, `05:30 ET`) to the 4-phase Decision Intelligence template with 6-pillar hygiene audit, executable scanner commands, wave plan template, and Dimension Findings Table.
- `[MODIFY]` `automations/prompts/agents_ssot_boundary_agent.md` — Upgrade Stage II (Order 2/7, `05:45 ET`) to the 4-phase Decision Intelligence template with 6-dimension boundary audit (`outreach_engine`, `resume_engine`, `resume_graph_engine`, `apps_research`, `infrastructure`), executable AST scanners, wave plan template, and Dimension Findings Table.

### Acceptance Criteria
- `_shared_governance_contract.md`, `agents_storage_worktree_hygiene_agent.md`, and `agents_ssot_boundary_agent.md` contain `C01–C12` headers, `UNCONDITIONAL_WAVE_PLAN_MANDATE`, `Phase 0` (`Step 0.1`), `Phase 1`, `Phase 2`, and `Phase 3` (`INV-RUNTIME-PROOF-5POINT`).
- Zero references to `/Users/amitayer/Git/decision-intelligence-engine` exist in any prompt.

### Runtime Receipt & Completion Gate
- **Run:** `python3 tools/validate_sidecar_separation.py --json`
- **Input:** `automations/prompts/_shared_governance_contract.md`, `automations/prompts/agents_storage_worktree_hygiene_agent.md`, and `automations/prompts/agents_ssot_boundary_agent.md`.
- **Expected:** Exit code `0` with `"status": "PASS"` and verified `C01–C12` and 4-phase markers in Stages I–II.
- **Verify independently:** Inspect file headers and phase sections across the 3 modified markdown files.
- **Fail if:** Any Stage I–II prompt lacks `UNCONDITIONAL_WAVE_PLAN_MANDATE`, `Step 0.1`, or `validate_implementation_plan.py`.
- **Record:** `artifacts/sidecar_runs/wave1_foundation_parity_receipt.json`

---

## Wave 2: Core Pipeline, Retrieval, Evals, Cost & Testing Sidecar Agents (Stages III–IV)

### Objective & Scope
Upgrade the remaining 5 sidecar agent specifications (`06:05 ET` Outreach & Resume E2E Functionality, `06:15 ET` Research & Retrieval Surface, `06:30 ET` Evals & Judge Validity, `06:45 ET` Cost & Token Budget, and `07:00 ET` Testing Gaps Assurance) to full Decision Intelligence Engine structural parity.

### Milestones & Deliverables
- `[MODIFY]` `automations/prompts/agents_e2e_functionality_assurance_agent.md` — Upgrade Stage III-A (Order 3/7, `06:05 ET`) with 6-pillar audit across `outreach_engine`, `resume_engine`, `resume_graph_engine`, and `apps_research`, 8-field E2E Criticality Admission Proof, and wave-based plan mandate.
- `[MODIFY]` `automations/prompts/agents_research_retrieval_surface_agent.md` — Upgrade Stage III-B (Order 4/7, `06:15 ET`) with 7-pillar `apps_research` & `resume_graph_engine` hybrid retrieval audit, executable forensic scanners, and wave-based plan mandate.
- `[MODIFY]` `automations/prompts/agents_evals_judge_assurance_agent.md` — Upgrade Stage III-C (Order 5/7, `06:30 ET`) with 6-pillar judge rubric, golden dataset, and production purity (`tools/lint_production_purity.py`) audit and wave-based plan mandate.
- `[MODIFY]` `automations/prompts/agents_cost_token_budget_agent.md` — Upgrade Stage IV-A (Order 6/7, `06:45 ET`) with 6-pillar tokenomics audit, $\text{ROI} \ge 2.5\times$ admission gate, `config/provider_profiles.yaml` conformance, and wave-based plan mandate.
- `[MODIFY]` `automations/prompts/agents_testing_gaps_assurance_agent.md` — Upgrade Stage IV-B (Order 7/7, `07:00 ET`) with 6-pillar test gap audit, 6-field E2E Criticality Admission Proof, Class A/B `--timeout=60` pytest gate, and wave-based plan mandate.

### Acceptance Criteria
- All 5 Stage III–IV prompts include `C01–C12` headers, `UNCONDITIONAL_WAVE_PLAN_MANDATE`, Phase 0 `Step 0.1`, Phase 1/1.5 executable scanners, Phase 2 Dimension Findings Table + `validate_implementation_plan.py`, and Phase 3 5-Point Counterfactual Runtime Proof.

### Runtime Receipt & Completion Gate
- **Run:** `python3 tools/validate_sidecar_separation.py --json`
- **Input:** All 7 `automations/prompts/agents_*_agent.md` files.
- **Expected:** Exit code `0` with all 7 prompts passing structural parity and repository separation checks.
- **Verify independently:** Verify every `automations/prompts/agents_*_agent.md` file contains `UNCONDITIONAL_WAVE_PLAN_MANDATE`, `Step 0.1`, `validate_implementation_plan.py`, and `INV-RUNTIME-PROOF-5POINT`.
- **Fail if:** Any prompt omits the 4-phase lifecycle or wave plan validation gate.
- **Record:** `artifacts/sidecar_runs/wave2_core_agents_parity_receipt.json`

---

## Wave 3: Mechanical Parity Validator, Unit Tests & Mainline Merge

### Objective & Scope
Strengthen `tools/validate_sidecar_separation.py` and `tests/unit/test_sidecar_separation_governance.py` to mechanically enforce Decision Intelligence structural parity across all 7 `agents-*` sidecars, verify all repository turn/commit gates, and merge cleanly to local `main`.

### Milestones & Deliverables
- `[MODIFY]` `tools/validate_sidecar_separation.py` — Add structural parity validation requiring `C01–C12`, `UNCONDITIONAL_WAVE_PLAN_MANDATE`, `INV-RUNTIME-PROOF-5POINT`, `INV-AUTOMATION-PERSISTENT-LEARNING-LOOP`, `Phase 0`, `Phase 1`, `Phase 2`, `Phase 3`, and `validate_implementation_plan.py` in all 7 `agents_*_agent.md` prompts.
- `[MODIFY]` `tests/unit/test_sidecar_separation_governance.py` — Add unit tests verifying positive parity compliance and negative failure detection when wave-plan or 4-phase invariants are missing.

### Acceptance Criteria
- `pytest tests/unit/test_sidecar_separation_governance.py -v --timeout=60` passes 100%.
- `python3 tools/validate_sidecar_separation.py --json`, `python3 tools/validate_turn_gates.py --mode all`, and `python3 tools/verify_commit.py` pass with zero errors.

### Runtime Receipt & Completion Gate
- **Run:** `/Users/amitayer/Git/agents/.venv/bin/pytest tests/unit/test_sidecar_separation_governance.py -v --timeout=60`
- **Input:** `tools/validate_sidecar_separation.py` and `tests/unit/test_sidecar_separation_governance.py`.
- **Expected:** All unit tests pass (`exit code 0`), `validate_sidecar_separation.py` returns `"status": "PASS"`, and changes merge cleanly into `/Users/amitayer/Git/agents` (`main`).
- **Verify independently:** Run `git -C /Users/amitayer/Git/agents status -sb` and `python3 tools/validate_sidecar_separation.py --json`.
- **Fail if:** Any test or commit gate fails or cross-repo leakage occurs.
- **Record:** `artifacts/sidecar_runs/wave3_parity_verification_receipt.json`

---

## Wave Implementation & Completion Status Table

| Wave | Description / Scope | Status |
| :--- | :--- | :--- |
| **Wave 1** | Shared Governance Contract & Stages I–II Sidecar Agents (`05:30–05:45 ET`) Decision Intelligence Parity | COMPLETED |
| **Wave 2** | Core Pipeline, Retrieval, Evals, Cost & Testing Sidecar Agents (`06:05–07:00 ET`) Decision Intelligence Parity | COMPLETED |
| **Wave 3** | Mechanical Parity Validator, Unit Tests, Turn Gates & Mainline Merge | COMPLETED |
