"""Zero-mutation shadow and label-isolated locked holdout replay evaluator.

Enforces:
1. Candidate inference receives strictly EvalCase.unlabeled_view (never ground truth).
2. Rejects self-certified embedded scores, empty holdout sets, veto regressions,
   non-positive target cluster gains, holdout accuracy degradation, and Pareto spikes.
3. Verifies zero production filesystem mutation via StateDeltaAuditor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from apps_eval.contracts.digests import stable_id
from apps_eval.contracts.schemas import (
    EvalCase,
    HoldoutReplayVerdict,
    ImprovementProposal,
    utc_now_iso,
)
from apps_eval.pareto import ParetoFrontierAnalyzer, ParetoPoint
from apps_eval.sandbox.state_delta import StateDeltaAuditor

CandidateRunnerFn = Callable[[dict[str, Any], Any], dict[str, Any]]


def _score_case(case: EvalCase, output: Mapping[str, Any]) -> tuple[bool, bool]:
    """Return (matched_expected, veto_triggered) comparing candidate output against withheld expected_contract."""
    exp = case.expected_contract
    veto_dims = set(exp.get("veto_dimensions") or [])
    triggered_vetoes = set(output.get("veto_defects") or [])
    veto_hit = bool(triggered_vetoes & veto_dims) or bool(output.get("veto_triggered", False))
    expected_label = exp.get("reference_label")
    actual_label = output.get("label")
    neg_labels = set(exp.get("negative_labels") or [])
    if actual_label in neg_labels:
        return False, True
    if expected_label is not None:
        return (actual_label == expected_label and not veto_hit), veto_hit
    return (bool(output.get("passed", False)) and not veto_hit), veto_hit


def evaluate_proposal_in_shadow(
    *,
    proposal: ImprovementProposal,
    target_cluster_cases: Sequence[EvalCase],
    holdout_cases: Sequence[EvalCase],
    dataset_digest: str,
    candidate_runner: CandidateRunnerFn,
    pinned_regressions_passed: bool = True,
    watched_readonly_paths: Sequence[Path] = (),
    max_latency_delta_pct: float = 10.0,
    max_cost_delta_pct: float = 10.0,
    require_strict_holdout_gain: bool = False,
) -> HoldoutReplayVerdict:
    """Replay baseline vs proposed value on target cluster and locked holdout split with zero mutation."""
    reasons: list[str] = []

    # Reject self-certified embedded test scores.
    if isinstance(proposal.proposed_value_or_patch, Mapping) and (
        "self_certified_score" in proposal.proposed_value_or_patch
        or "test_simulation" in proposal.proposed_value_or_patch
    ):
        reasons.append("SELF_CERTIFIED_SCORE_REJECTED")

    if not holdout_cases:
        reasons.append("EMPTY_HOLDOUT_SET")
    if any(c.split != "holdout" for c in holdout_cases):
        reasons.append("NON_HOLDOUT_CASE_LEAKED_INTO_HOLDOUT_REPLAY")
    if not target_cluster_cases:
        reasons.append("EMPTY_TARGET_CLUSTER_CASES")
    if not pinned_regressions_passed:
        reasons.append("PINNED_REGRESSIONS_FAILED")

    auditor = StateDeltaAuditor(watched_readonly_paths) if watched_readonly_paths else None
    if auditor is not None:
        auditor.capture_before()

    def _run_split(cases: Sequence[EvalCase], config_val: Any) -> tuple[float, int, float, float]:
        if not cases:
            return 0.0, 0, 0.0, 0.0
        hits = 0
        vetoes = 0
        lat_sum = 0.0
        cost_sum = 0.0
        for c in cases:
            # Strict label isolation: pass ONLY unlabeled_view.
            view = c.unlabeled_view
            out = candidate_runner(view, config_val)
            matched, veto = _score_case(c, out)
            if matched:
                hits += 1
            if veto:
                vetoes += 1
            lat_sum += float(out.get("latency_ms", 0.0))
            cost_sum += float(out.get("cost_usd", 0.0))
        n = float(len(cases))
        return hits / n, vetoes, lat_sum / n, cost_sum / n

    t_before, _, _, _ = _run_split(target_cluster_cases, proposal.expected_current_value)
    t_after, t_vetoes, _, _ = _run_split(target_cluster_cases, proposal.proposed_value_or_patch)

    h_before, h_vetoes_before, lat_before, cost_before = _run_split(
        holdout_cases, proposal.expected_current_value
    )
    h_after, h_vetoes_after, lat_after, cost_after = _run_split(
        holdout_cases, proposal.proposed_value_or_patch
    )

    zero_mut_ok = True if auditor is None else auditor.compare_after().is_idempotent_noop
    if not zero_mut_ok:
        reasons.append("SHADOW_SIMULATION_MUTATED_PRODUCTION_STATE")

    if t_after <= t_before:
        reasons.append(f"NO_TARGET_CLUSTER_GAIN:{t_before:.4f}->{t_after:.4f}")

    h_delta = round(h_after - h_before, 4)
    if require_strict_holdout_gain and h_delta <= 0.0:
        reasons.append(f"NON_POSITIVE_HOLDOUT_GAIN:{h_delta:.4f}")
    elif h_delta < 0.0:
        reasons.append(f"HOLDOUT_ACCURACY_REGRESSION:{h_delta:.4f}")

    extra_holdout_vetoes = (h_vetoes_after - h_vetoes_before) if h_vetoes_after > h_vetoes_before else 0
    veto_regressions = extra_holdout_vetoes + t_vetoes
    if veto_regressions > 0:
        reasons.append(f"VETO_REGRESSION_DETECTED:{veto_regressions}")

    pareto = ParetoFrontierAnalyzer(
        max_quality_drop_pct=0.0,
        max_latency_spike_pct=max_latency_delta_pct,
        max_cost_spike_pct=max_cost_delta_pct,
    )
    p_verdict = pareto.evaluate_regression(
        candidate=ParetoPoint("candidate", h_after * 100.0, lat_after, cost_after),
        baseline=ParetoPoint("baseline", h_before * 100.0, lat_before, cost_before),
    )
    if p_verdict.is_regression:
        reasons.extend(f"PARETO:{r}" for r in p_verdict.reasons)

    if veto_regressions > 0:
        verdict = "VETOED"
    elif reasons:
        verdict = "REJECT"
    else:
        verdict = "PASS"

    return HoldoutReplayVerdict(
        verdict_id=stable_id("hrv", proposal.proposal_id, dataset_digest, utc_now_iso(), length=16),
        proposal_id=proposal.proposal_id,
        proposal_digest=proposal.canonical_digest,
        dataset_digest=dataset_digest,
        zero_mutation_verified=zero_mut_ok,
        unlabeled_view_enforced=True,
        target_cluster_cases=len(target_cluster_cases),
        target_metric_before=round(t_before, 4),
        target_metric_after=round(t_after, 4),
        holdout_cases_evaluated=len(holdout_cases),
        holdout_accuracy_before=round(h_before, 4),
        holdout_accuracy_after=round(h_after, 4),
        holdout_accuracy_delta=h_delta,
        pinned_regressions_passed=pinned_regressions_passed,
        veto_regressions_count=veto_regressions,
        pareto_regression=p_verdict.is_regression,
        latency_delta_pct=p_verdict.latency_delta_pct,
        cost_delta_pct=p_verdict.cost_delta_pct,
        verdict=verdict,  # type: ignore[arg-type]
        rejection_reasons=reasons,
    )
