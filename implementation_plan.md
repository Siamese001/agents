# Implementation Plan: 8-Agent Adversarial Model Analysis

## Implementation Status Table

| Wave | Description | Status |
| :--- | :--- | :--- |
| Wave 1 | Empirical Benchmark Matrix & Model Cost Profile Assembly | COMPLETE |
| Wave 2 | 8-Agent Adversarial Stress-Testing & Panel Deliberation | COMPLETE |
| Wave 3 | Multi-Dimensional Pareto Analysis & Section Rebalancing | COMPLETE |
| Wave 4 | Governance Catalog Updates, CI Pin Verification & Receipts | COMPLETE |

---

## Wave 1: Empirical Benchmark Matrix & Model Cost Profile Assembly

### Objective & Scope
Construct an empirical benchmark dataset capturing pricing, context windows, and parameters across approved models (`claude-sonnet-5`, `gpt-5.6-luna`, `gemini-3.8-flash`, `gpt-5.6-terra`, `gpt-5.6-sol`, `claude-haiku-4-5-20251001`) and local models (`Qwen-3.8-27B`, `BAAI/bge-m3`).

### Milestones & Deliverables
- [CREATE] `reports/adversarial_model_benchmarks_matrix.json`: Pricing, context, and reasoning limits.
- [CREATE] `tests/adversarial/test_model_cost_governance.py`: Unit test verifying pricing and 300k token spend ceiling.

### Acceptance Criteria
- Complete pricing and capability metadata compiled for all evaluated models without missing fields.
- Cost calculations account for prompt caching discounts.
- Spend governor ceiling strictly respects 300,000 tokens limit.

### Verification & Completion Gate
- **Run**: `/Users/amitayer/Git/decision-intelligence-engine/.venv/bin/pytest tests/adversarial/test_model_cost_governance.py -q`
- **Input**: `reports/adversarial_model_benchmarks_matrix.json` and model pricing tables.
- **Expected**: All 3 test cases pass with exit code 0.
- **Verify independently**: `python3 tools/lint_model_pins.py --report`
- **Fail if**: Unpriced models, schema validation errors, or spend governor ceiling violation.
- **Record**: Record execution results in `reports/adversarial_model_benchmarks_matrix.json`.

---

## Wave 2: 8-Agent Adversarial Stress-Testing & Panel Deliberation

### Objective & Scope
Deploy 8 specialized adversarial agents (Cost, Efficiency, Reasoning, Dual-Judge, Selector, Grounding, Local Edge, Governance) to audit model trade-offs.

### Milestones & Deliverables
- [CREATE] `reports/adversarial_8agent_council_deliberation.md`: Transcripts across all 8 agents.
- [CREATE] `reports/model_stress_test_findings.json`: Scores per model across all 8 vectors.

### Acceptance Criteria
- All 8 agents provide independent evaluation scores grounded in real prompt/schema fixtures.
- Specific boundary failure modes identified.

### Verification & Completion Gate
- **Run**: `/Users/amitayer/Git/decision-intelligence-engine/.venv/bin/pytest outreach_engine/tests/test_adversarial_council_remediation.py -q`
- **Input**: Candidate prompt fixtures and rubric configurations.
- **Expected**: Council test suite passes cleanly with zero unhandled exceptions.
- **Verify independently**: Check `reports/model_stress_test_findings.json` has scores for all 8 agents.
- **Fail if**: Missing agent verdicts or uncalibrated reasoning failure modes.
- **Record**: Record findings in `reports/adversarial_8agent_council_deliberation.md`.

---

## Wave 3: Multi-Dimensional Pareto Analysis & Section Rebalancing

### Objective & Scope
Synthesize findings into a Pareto efficiency frontier and determine optimal section-by-section model allocations.

### Milestones & Deliverables
- [CREATE] `reports/model_pareto_efficiency_analysis.md`: Cost vs Reasoning curves and section proposals.
- [CREATE] `config/experimental_model_routing_recommendations.yaml`: Proposed model assignments and fallback paths.

### Acceptance Criteria
- Quantified cost savings or reasoning improvements clearly documented.
- Executive summary enhanced reasoning preserves fact-grounding floor with token cap.

### Verification & Completion Gate
- **Run**: `/Users/amitayer/Git/decision-intelligence-engine/.venv/bin/python3 -c "import yaml; yaml.safe_load(open('config/experimental_model_routing_recommendations.yaml'))"`
- **Input**: `config/experimental_model_routing_recommendations.yaml`.
- **Expected**: YAML parses validly and matches section schema.
- **Verify independently**: Audit routing allocations against `config/provider_profiles.yaml`.
- **Fail if**: Invalid YAML, missing fallback paths, or broken schema bindings.
- **Record**: Record analysis in `reports/model_pareto_efficiency_analysis.md`.

---

## Wave 4: Governance Catalog Updates, CI Pin Verification & Receipts

### Objective & Scope
Apply approved model pin updates to configuration files, ensure strict CI gate compliance, and issue audit receipts.

### Milestones & Deliverables
- [UPDATE] `config/model_catalog.json`: Model revisions and deprecation schedules.
- [UPDATE] `config/provider_profiles.yaml`: Per-section assignments, reasoning parameters, and fallbacks.
- [CREATE] `reports/adversarial_analysis_audit_receipt.json`: Audit receipt capturing evaluation hashes.

### Acceptance Criteria
- `tools/lint_model_pins.py --strict` exits 0 with zero floating, preview, or mislabelled pins.
- All unit, integration, and contract tests pass with 100% green exit codes.

### Verification & Completion Gate
- **Run**: `python3 tools/lint_model_pins.py --strict`
- **Input**: Modified repository configuration files and catalogs.
- **Expected**: Strict model pin linter exits 0 with 0 findings.
- **Verify independently**: `git -C /Users/amitayer/Git/agents/.worktrees/feat-adversarial-model-analysis status --porcelain`
- **Fail if**: Any lint violations, unapproved pins, or test regressions.
- **Record**: Write audit receipt to `reports/adversarial_analysis_audit_receipt.json`.
