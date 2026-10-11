# Implementation Plan: Optimize Outreach Engine Research Resolution for Minimum API Cost

## Implementation Status Table

| Wave | Description | Status |
| :--- | :--- | :--- |
| Wave 1 | Research Boundary Policy, Cost Limits, Bounded Timeouts, and Retries | COMPLETE |
| Wave 2 | Provenance-Verified Briefing Reuse, Persisted Artifact Cache, and Freshness Control | COMPLETE |
| Wave 3 | Zero-Provider-Call Invariant, Evidence Safety, and End-to-End Governance Verification | COMPLETE |

## Wave 1: Research Boundary Policy, Cost Limits, Bounded Timeouts, and Retries

### Objective & Scope
Enforce strict cost containment and operational resilience at the `outreach_engine` research boundary before invoking `apps_research`. Introduce configurable cost budgets, execution timeouts, bounded retries, and live call counting.

### Milestones & Deliverables
- [NEW] Research boundary budget specification `ResearchBoundaryPolicy` in `outreach_engine/src/apps_lic/integrations/research_boundary_policy.py` supporting `cost_limit_usd`, `cost_per_call_usd`, `timeout_seconds`, and `max_retries`.
- [MODIFY] `outreach_engine/src/apps_lic/integrations/apps_research_bridge.py`: Add bounded timeout execution and retries around live calls; track cumulative spend and live call invocations. Block calls exceeding cost limit with `ResearchFailureReason.APPS_RESEARCH_COST_LIMIT_EXCEEDED`.
- [MODIFY] `outreach_engine/src/apps_lic/integrations/managed_research_delegation.py`: Add `APPS_RESEARCH_TIMEOUT` and `APPS_RESEARCH_COST_LIMIT_EXCEEDED` to `ResearchFailureReason`; plumb boundary limits into `RequestForOutreachBriefing`.

### Acceptance Criteria
- Live provider calls are bounded by `timeout_seconds` and abort fail-closed upon expiration.
- Transient network or provider invocation errors retry up to `max_retries` before recording dispatch failure.
- When accumulated spend reaches `cost_limit_usd`, further live provider calls are blocked immediately and fall back to hermetic resolution without provider invocation.
- Provider invocation counter (`live_invocation_count`) increments strictly on real provider calls.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/pytest outreach_engine/tests/test_research_cost_optimization.py -k "test_boundary" -v --timeout=60`
- Input: Simulated timeouts, retry triggers, and spend thresholds on `AppsResearchBridge`.
- Expected: All boundary tests pass with exact failure reason codes and verified call counts.
- Verify independently: Inspect bridge call counter and confirm zero calls when budget is exhausted.
- Fail if: Timeouts hang, retries loop infinitely, or calls exceed configured cost limit.
- Record: Pass count and execution receipt in wave ledger.

## Wave 2: Provenance-Verified Briefing Reuse, Persisted Artifact Cache, and Freshness Control

### Objective & Scope
Prevent redundant live research by discovering and reusing existing, freshness-valid, provenance-verified briefings and persisted artifact bundles before calling `apps_research`. Preserve explicit fresh-research overrides.

### Milestones & Deliverables
- [MODIFY] `outreach_engine/src/apps_lic/integrations/apps_research_bridge.py`: Prioritize canonical targeting briefs and discover valid persisted artifact bundles from `artifact_runs_root` prior to live execution.
- [MODIFY] `outreach_engine/src/apps_lic/pipeline/briefing_resolver.py`: Plumb `force_fresh` flag across `GovernedBriefingResolver.resolve` and check persisted artifacts in Path B.
- [MODIFY] `outreach_engine/src/apps_lic/pipeline/orchestrator.py`: Propagate `force_fresh` through `resolve_opportunity_briefing` and draft generation entry points.
- [MODIFY] `outreach_engine/src/apps_lic/integrations/managed_research_delegation.py`: Enforce strict verification of reused persisted bundles; reject blocked, stale, or unverified evidence.

### Acceptance Criteria
- Existing freshness-valid, provenance-verified briefings in `artifact_runs_root` or canonical targeting directories are reused without making live provider calls.
- When `force_fresh=True`, cache and persisted artifact reuse are bypassed, dispatching fresh research.
- Persisted artifacts marked `is_blocked=True`, `status="UNVERIFIED"`, or failing digest checks are never reused and fail closed.
- Airlock sanitization is executed on all reused briefings.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/pytest outreach_engine/tests/test_research_cost_optimization.py -k "test_reuse" -v --timeout=60`
- Input: Valid and invalid persisted research bundles in temporary artifact directories.
- Expected: Zero provider calls for valid bundles; live dispatch or fallback on unverified/tampered bundles.
- Verify independently: Assert `bridge.live_invocation_count == 0` on cache/disk hits.
- Fail if: Provider is invoked despite valid cached artifacts, or unverified artifacts are accepted.
- Record: Pass count and execution receipt in wave ledger.

## Wave 3: Zero-Provider-Call Invariant, Evidence Safety, and End-to-End Governance Verification

### Objective & Scope
Formally prove that cache and persisted artifact hits make zero provider calls while preserving all governance gates, truth invariants, and personalization validators.

### Milestones & Deliverables
- [NEW] Comprehensive test suite `outreach_engine/tests/test_research_cost_optimization.py` covering zero-call proof, cost limits, timeouts, retries, `force_fresh`, and rejection of blocked evidence.
- [MODIFY] `outreach_engine/tests/test_research_governance_truth.py`: Maintain complete compatibility with existing truth gates.

### Acceptance Criteria
- Empirical test proof verifies `live_invocation_count == 0` for both in-memory cache and persisted artifact hits.
- UnsupportedPersonalizationValidator blocks hallucinated claims when unverified or offline fallback briefings are used.
- All existing tests in `test_research_governance_truth.py` and `test_research_briefing.py` pass without regression.
- Tier 1 pre-commit checks pass cleanly with zero lint or contract violations.

### Runtime Receipt & Completion Gate
- Run: `.venv/bin/pytest outreach_engine/tests/test_research_cost_optimization.py -v --timeout=60`
- Input: Synthetic and representative research requests with varied cache states.
- Expected: 100% pass across all zero-call and cost containment assertions.
- Verify independently: Run `tools/verify_commit.py` against modified files.
- Fail if: Any provider call occurs on cache hit or existing governance tests regress.
- Record: Pass count and execution receipt in wave ledger.
