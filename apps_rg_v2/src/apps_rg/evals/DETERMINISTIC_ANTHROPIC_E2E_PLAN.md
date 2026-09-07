# Deterministic Anthropic Partnership E2E plan and feasibility boundary

## Goal

Create a repeatable, zero-provider, no-LLM **test fixture** for the Anthropic
`Manager of Applied AI Architecture, Partnerships` JD. It must reach
post-runtime Apps Eval and L6 shadow artifacts, and report their actual
disposition.

This is an integration-proof surface.  It is not a production execution mode,
does not authorize a resume for delivery, and must not relax the product CLI's
live-provider or live-judge requirements.

## Feasibility result

A successful **product** E2E run with no LLM/provider calls is not available
under the current contract. This is intentional: the product entrypoint
requires live generation and live X1D judges, while the offline contract stub
is disabled.

A controlled probe confirmed the smaller test-only path can execute the real
outer spine through U0, L1, L0, a labelled deterministic L2 seam, and the real
Apps Eval/L6 emission path. The evaluator then correctly classified the source
run as release-blocked: 110 required runtime microsteps were `NOT_OBSERVED` and
13 required artifacts were missing. The probe used `MockAppsResearchBridge`;
although it made no network call, its synthetic receipt says a provider was
attempted. It is therefore unsuitable as the final no-provider acceptance
proof. The final fixture must emit explicit `TEST_FIXTURE_ONLY` observations
with `provider_call_attempted=false` instead. Neither result may be relabelled
as a successful product run or bypassed with synthetic success flags.

Therefore the minimum honest deliverable has two distinct success definitions:

1. **Fixture-integration success:** a pytest run exits successfully after
   proving the zero-provider path and asserting the evaluator's sealed record
   and actual blocked/PENDING disposition.
2. **Product-E2E success:** remains unavailable without live providers and the
   ordinary authority gates. Achieving this in deterministic mode would require
   an explicitly governed, separately named fixture qualification policy; it
   is not a CLI flag or an evaluator relaxation.

## Why a test fixture is the minimum scope

`python -m apps_rg` deliberately requires a live provider and live X1D judges.
The legacy offline contract stub is permanently disabled for product runs.
Therefore, making the product CLI silently accept deterministic content would
weaken the release contract and would not prove the requested no-LLM behavior
honestly.

The deterministic harness must exercise the real outer flow up to L2:

```text
Anthropic JD fixture
  -> fixture-backed Apps Research handoff
  -> U0 validation
  -> deterministic L1 plan
  -> deterministic L0 route
  -> fixture-backed L2/Exit result
  -> deterministic Apps Eval current-snapshot record
  -> L6 shadow bridge
```

Only the provider-backed research generation and L2 content execution are
replaced.  They are replaced by explicit, versioned fixtures, not mock values
that claim to be production evidence.

## Smallest implementation

1. Add one integration test, `tests/unit/apps_rg/test_anthropic_deterministic_e2e.py`.
   It uses the canonical JD at
   `src/apps_rg/config/targeting/jd_anthropic_partnerships_2026.json` and
   asserts the exact company and role.
2. Add a pytest-only, run-scoped handoff fixture producer before U0. It must
   use the existing handoff schema and identity validation but declare
   `TEST_FIXTURE_ONLY`, `provider_call_attempted=false`, and no observed model.
   Do not use `MockAppsResearchBridge` for the acceptance fixture because its
   compatibility receipt claims a provider attempt. The test must reject a
   static targeting brief and prove the handoff is bound to the current run
   identity.
3. Inject a deterministic L2 fixture at the external-spine seam.  It must
   contain a minimal valid resume payload plus explicit `fixture_only` and
   `no_provider_calls` markers.  A provider-gateway sentinel must fail the test
   if invoked.
4. Materialize signed, byte-bound test evidence solely under `tmp_path`, then
   call `normalize_existing_apps_rg_run_snapshot()` and
   `run_current_snapshot_eval(..., deterministic_only=True)`.
5. Assert Apps Eval record, package seal, and L6 shadow bridge exist, are
   deterministic, and do not mutate the source fixture run. Assert the real
   coverage disposition (currently release-blocked), not a forged pass. The
   assertion is evaluation completion and evidence integrity, not
   protected-holdout or production qualification.
6. Do not change the default Apps Eval microstep registry to make this test
   pass. If a future deterministic fixture needs a green evaluation, introduce
   a separately governed fixture-only suite whose required observations match
   the fixture contract, then validate that suite independently. It must emit
   `TEST_FIXTURE_ONLY` and remain ineligible for product authorization.

## Green fixture-evaluation profile (governance-gated)

The integration test above establishes the zero-provider E2E plumbing. A
green result is possible only for a *separate fixture contract*; it must never
mean the default product Apps Eval contract passed. Before implementation, the
fixture-contract owner must approve a written policy that names its scope,
required observations, non-qualification status, and change-control owner.

The implementation surface is deliberately narrow:

1. Add a versioned `apps_rg.anthropic_deterministic_fixture.v1` contract bundle
   under `src/apps_eval/registries/`. Its observations cover only the actual
   fixture spine: canonical JD binding, pre-U0 handoff identity, U0/L1/L0
   receipts, labelled L2 fixture output, zero-provider proof, deterministic
   source digest, Apps Eval package seal, and L6 non-mutation. It must not
   include product X1D, UWG, W6, holdout, or release-promotion gates.
2. Add a separately named suite in `src/apps_eval/registry/suites.yaml` and a
   fixture-specific threshold. The suite may be selected only by its explicit
   suite ID; do not add a CLI switch that changes a product suite's contract.
3. Extend `src/apps_eval/coverage/apps_rg.py` and
   `src/apps_eval/runner/core.py` to resolve the contract profile from that
   suite, bind its digest into every scorecard row, and reject fixture profiles
   for `current_snapshot`, `live_adapter`, non-deterministic, holdout, or
   release-gate evaluation modes. The existing production profile remains the
   default and must retain its current digest and semantics.
4. Carry `TEST_FIXTURE_ONLY`, `provider_call_attempted=false`,
   `product_eligible=false`, and the profile ID through fixture provenance,
   the completed eval record, package seal, and L6 bridge. Add a negative test
   that a fixture record cannot be consumed as product authorization evidence.
5. Add the canonical Anthropic fixture tree plus contract-selection, digest
   isolation, product-profile rejection, and L6-provenance tests. The fixture
   profile may pass only after all of *its* required observations are present;
   the same source must still fail or block under the default product profile.

This phase creates a green **fixture-integration** verdict, not a green
product-E2E or release-qualification verdict. It remains blocked on the
written fixture policy until that policy exists; no W6 or product authority is
fabricated to advance it.

## Explicit non-goals

- Do not add a product CLI offline flag or reactivate
  `APPS_RG_PROVIDER_MODEL_OFFLINE_CONTRACT_STUB`.
- Do not represent a fixture-backed result as `REAL_LLM`, X3 production
  authorization, W6 authority, or release qualification.
- Do not copy a historical live run and relabel it as zero-provider proof.
- Do not require QREL, protected-holdout, or human-release authority for this
  deterministic integration test.

## Acceptance criteria

- The test performs zero provider, judge, or network calls.
- The canonical Anthropic JD and required role are consumed before U0.
- A run-scoped Apps Research handoff exists before U0 and passes its identity
  validation.
- U0, L1, and L0 execute without monkeypatching their implementations.
- The deterministic fixture result is clearly labelled `TEST_FIXTURE_ONLY`.
- Apps Eval emits a current-snapshot record, package seal, scorecard, and L6
  shadow bridge under the test run root.
- The test asserts the evaluator's real coverage verdict; it does not claim a
  green default Apps Eval qualification from partial fixture evidence.
- The source run's byte manifest is unchanged by evaluation.
- The focused test and the existing whole-run/post-X3/evaluator regression
  tests pass.

## Validation commands

```powershell
$env:PYTHONPATH = 'C:\Git\apps_rg_v2\src'
python -m pytest -q tests/unit/apps_rg/test_anthropic_deterministic_e2e.py
python -m pytest -q tests/unit/apps_rg/test_r3r4_whole_run_reachability.py tests/unit/apps_rg/test_post_x3_completion.py src/apps_eval/tests/test_apps_rg_current_snapshot_evidence.py
```

The completed test is evidence of deterministic integration coverage only.  A
live product E2E remains separately gated by live providers, W6 authority, and
all product release requirements.
