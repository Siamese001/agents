# Model Pin Optimization and Adversarial Governance Hardening Plan

| Wave | Description | Status |
| :--- | :--- | :--- |
| Wave 1 | Qualify Claude Haiku 5.5 for Advisory Selection, Right-Size Pool Selectors, and Fix Section Cache Model Salt | COMPLETE |
| Wave 2 | Codify Three-Agent Adversarial Model Selection Rules and Verify Cost and Evaluation Gates | COMPLETE |

## Wave 1: Qualify Claude Haiku 5.5 for Advisory Selection, Right-Size Pool Selectors, and Fix Section Cache Model Salt

### Objective & Scope
Register the Claude Haiku 5.5 model snapshot in the capability and pricing catalogs, migrate non-proof advisory candidate pool selectors and outreach rubric judging to the Haiku tier locked at low effort, and fix the reversed parameter order in section lane cache key salting while keeping `claude-sonnet-5`, `gpt-5.6-luna`, and `gemini-3.8-flash` on primary resume writing and cross-provider proof judging.

### Milestones & Deliverables
- [MODIFY] [model catalog](file:///Users/amitayer/Git/agents/config/model_catalog.json): Register Claude Haiku 5.5 capability metadata with adaptive thinking mode and low effort defaults.
- [MODIFY] [pricing registry](file:///Users/amitayer/Git/agents/resume_graph_engine/config/models/registry.yaml): Add Claude Haiku 5.5 pricing (\$0.10 input / \$0.50 output per million tokens) and update selector role bindings.
- [MODIFY] [primary provider profiles](file:///Users/amitayer/Git/agents/config/provider_profiles.yaml) and [outreach provider profiles](file:///Users/amitayer/Git/agents/outreach_engine/config/provider_profiles.yaml): Right-size advisory candidate pool selectors and outreach rubric panel to the Haiku tier at low effort while retaining `claude-sonnet-5` and `gpt-5.6-luna` on proof-bearing generation.
- [MODIFY] [section lane cache](file:///Users/amitayer/Git/agents/resume_graph_engine/src/apps_rg/cache/section_lane_cache.py): Pass section identifier before provider profile when resolving model salt.

### Acceptance Criteria
- All model pins in both engines resolve cleanly against the updated catalog with zero unapproved token errors.
- Advisory selectors run at low effort to prevent thinking token starvation inside the 4,096-token output ceiling.
- Section lane cache pointer rewrite check passes 6 out of 6 assertions.

### Runtime Receipt & Completion Gate
- Run: Execute the [section cache check](file:///Users/amitayer/Git/agents/resume_graph_engine/tests/unit/apps_rg/test_wave5_fast_cache_and_section_cache.py), [resume model registry check](file:///Users/amitayer/Git/agents/resume_graph_engine/tests/unit/apps_rg/test_model_registry.py), and [outreach model registry check](file:///Users/amitayer/Git/agents/outreach_engine/tests/test_model_registry_ssot.py).
- Input: Updated provider profiles, model catalog, and section lane cache module.
- Expected: Exit code 0 with all 6 section cache checks and all model registry checks passing (`57 passed`).
- Verify independently: Inspect output logs and run the [cost and token budget auditor](file:///Users/amitayer/Git/agents/tools/cost_token_budget_auditor.py) (`8/8 pillars PASS`, `2.6x ROI`).
- Fail if: Any check fails, return ratio drops below 2.5x, or proof-bearing lanes are downgraded.
- Record: `artifacts/governance/wave1_model_pin_optimization_receipt.json`

## Wave 2: Codify Three-Agent Adversarial Model Selection Rules and Verify Cost and Evaluation Gates

### Objective & Scope
Persist the reusable lessons from the three-agent adversarial debate into workspace governance rules and experimental routing documentation, ensuring future model pin reviews evaluate latest industry releases alongside retry-cascade math, adaptive thinking ceilings, and cross-family judge independence.

### Milestones & Deliverables
- [MODIFY] [decision governance rules](file:///Users/amitayer/Git/agents/.agents/rules/hitl-decisions.md): Add the three-pillar adversarial model qualification rule covering industry release checks, thinking budget sharing, and cross-family judge orthogonality.
- [MODIFY] [experimental routing recommendations](file:///Users/amitayer/Git/agents/config/experimental_model_routing_recommendations.yaml): Record the Claude Haiku 5.5 selector allocation and updated cost reduction benchmarks.

### Acceptance Criteria
- Governance turn gates, evaluation rubric checks, and cost budget audits pass with zero violations.
- Updated rule documentation passes all conformance checks.

### Runtime Receipt & Completion Gate
- Run: Execute the [turn gate checker](file:///Users/amitayer/Git/agents/tools/validate_turn_gates.py) across all modes.
- Input: Updated governance rule file and routing recommendations.
- Expected: Exit code 0 with all pre-turn and post-turn checks reporting PASS.
- Verify independently: Run the [evaluation rubric checker](file:///Users/amitayer/Git/agents/tools/validate_eval_rubrics.py) and confirm zero violations (`10/10 rubrics PASS`).
- Fail if: Any turn gate or rubric check reports an error.
- Record: `artifacts/governance/wave2_learning_governance_receipt.json`
