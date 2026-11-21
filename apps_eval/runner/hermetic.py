"""Hermetic evaluation runner supporting sandbox isolation, cassette replay, non-compensating comparisons, and stress trials."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from apps_eval.contracts.digests import canonical_sha256, stable_id
from apps_eval.contracts.schemas import (
    EvalCase,
    EvalComparison,
    EvalReceipt,
    ExecutionModeV2,
    GroundingTier,
    StressResult,
    utc_now_iso,
)
from apps_eval.graders.judge.blind_protocol import (
    build_sealed_blind_judge_bundle,
    validate_blind_judge_verdict_provenance,
)
from apps_eval.graders.judge.pre_judge import run_tier1_deterministic_pre_judge
from apps_eval.sandbox.environment import SandboxEnvironment
from apps_eval.sandbox.state_delta import StateDeltaAuditor


def detect_case_regressions(
    baseline_results: Sequence[Mapping[str, Any]],
    candidate_results: Sequence[Mapping[str, Any]],
) -> tuple[list[str], list[str]]:
    """Return (regressed_case_ids, improved_case_ids) without allowing pass-rate compensation."""
    base_map = {str(r.get("case_id") or ""): str(r.get("status") or "").upper() for r in baseline_results}
    cand_map = {str(r.get("case_id") or ""): str(r.get("status") or "").upper() for r in candidate_results}
    regressions: list[str] = []
    improvements: list[str] = []
    for cid in sorted(set(base_map) | set(cand_map)):
        if not cid:
            continue
        b_status = base_map.get(cid, "MISSING")
        c_status = cand_map.get(cid, "MISSING")
        if b_status == "PASS" and c_status != "PASS":
            regressions.append(cid)
        elif b_status != "PASS" and c_status == "PASS":
            improvements.append(cid)
    return regressions, improvements


def compare_eval_receipts(
    baseline: EvalReceipt,
    candidate: EvalReceipt,
) -> EvalComparison:
    """Compare two EvalReceipts fail-closed; any single PASS->FAIL flip fails the comparison."""
    incomp_reasons: list[str] = []
    if baseline.suite_id != candidate.suite_id:
        incomp_reasons.append(f"SUITE_ID_MISMATCH:{baseline.suite_id}!={candidate.suite_id}")
    if baseline.suite_digest != candidate.suite_digest:
        incomp_reasons.append("SUITE_DIGEST_MISMATCH")
    if baseline.rubric_version != candidate.rubric_version:
        incomp_reasons.append(f"RUBRIC_VERSION_MISMATCH:{baseline.rubric_version}!={candidate.rubric_version}")

    if incomp_reasons:
        return EvalComparison(
            suite_id=candidate.suite_id,
            baseline_receipt_id=baseline.receipt_id,
            candidate_receipt_id=candidate.receipt_id,
            comparable=False,
            incomparability_reasons=incomp_reasons,
            case_regressions=[],
            case_improvements=[],
            pass_rate_delta=0.0,
            latency_delta_ms=0.0,
            cost_delta_usd=0.0,
            verdict="NOT_COMPARABLE",
        )

    regressions, improvements = detect_case_regressions(baseline.case_results, candidate.case_results)
    base_pass_rate = (
        sum(1 for c in baseline.case_results if c.get("status") == "PASS") / float(len(baseline.case_results))
        if baseline.case_results
        else 0.0
    )
    cand_pass_rate = (
        sum(1 for c in candidate.case_results if c.get("status") == "PASS") / float(len(candidate.case_results))
        if candidate.case_results
        else 0.0
    )
    base_lat = float(baseline.pareto_point.get("latency_ms", 0.0))
    cand_lat = float(candidate.pareto_point.get("latency_ms", 0.0))
    base_cost = float(baseline.pareto_point.get("cost_usd", 0.0))
    cand_cost = float(candidate.pareto_point.get("cost_usd", 0.0))

    passed = len(regressions) == 0 and candidate.verdict == "PASS"
    return EvalComparison(
        suite_id=candidate.suite_id,
        baseline_receipt_id=baseline.receipt_id,
        candidate_receipt_id=candidate.receipt_id,
        comparable=True,
        incomparability_reasons=[],
        case_regressions=regressions,
        case_improvements=improvements,
        pass_rate_delta=round(cand_pass_rate - base_pass_rate, 4),
        latency_delta_ms=round(cand_lat - base_lat, 2),
        cost_delta_usd=round(cand_cost - base_cost, 6),
        verdict="PASS" if passed else "FAIL",
    )


def _load_cassette_registry_if_configured(case: EvalCase, cassette_root: Path | None) -> Any | None:
    """Optionally bind infrastructure.sdks_mcps.wire_cassette.CassetteRegistry for cassette_replay cases."""
    if case.execution_mode != "cassette_replay":
        return None
    cassette_rel = str(case.unlabeled_input.get("cassette_path") or "")
    if not cassette_rel:
        return None
    cassette_path = (cassette_root / cassette_rel) if cassette_root is not None else Path(cassette_rel)
    if not cassette_path.is_file():
        raise FileNotFoundError(f"Cassette fixture missing for case {case.case_id}: {cassette_path}")
    from infrastructure.sdks_mcps.wire_cassette import CassetteRegistry

    return CassetteRegistry(cassette_path)


def run_hermetic_eval_suite(
    *,
    suite_id: str,
    cases: Sequence[EvalCase],
    executor_fn: Callable[[dict[str, Any], Path, Any | None], dict[str, Any]],
    rubric_version: str = "rubric.v1",
    pipeline_version: str = "pipeline.v1",
    git_sha: str = "0" * 40,
    execution_mode: ExecutionModeV2 = "snapshot",
    grounding_tier: GroundingTier = "OFFLINE_BENCHMARK_GROUNDED",
    work_root: Path | None = None,
    seed_dir: Path | None = None,
    cassette_root: Path | None = None,
    blind_judge_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    author_model_family: str = "anthropic",
    repo_root: Path | None = None,
) -> EvalReceipt:
    """Execute EvalCases inside isolated sandboxes with Tier-1 pre-checks and optional Tier-2 blind judging."""
    if not cases:
        raise ValueError(f"Cannot run empty evaluation suite: {suite_id}")

    suite_digest = canonical_sha256([c.to_dict() for c in cases])
    seed_auditor = StateDeltaAuditor([seed_dir]) if seed_dir is not None and seed_dir.exists() else None
    if seed_auditor is not None:
        seed_auditor.capture_before()

    case_results: list[dict[str, Any]] = []
    tier1_failed_all: list[str] = []
    total_latency_ms = 0.0
    total_cost_usd = 0.0
    blind_judge_meta: dict[str, Any] = {
        "executed": False,
        "deterministic_priming_stripped": True,
        "author_model_family": author_model_family,
        "judge_model_families": [],
        "position_swap_passed": True,
        "persona_score_spread": 0.0,
        "dimension_scores": {},
        "veto_triggered": False,
        "bundle_digest": "",
    }

    for case in cases:
        with SandboxEnvironment(case_id=case.case_id, work_root=work_root, seed_dir=seed_dir) as sb:
            assert sb.workspace_dir is not None
            t0 = time.perf_counter()
            failed_gates: list[str] = []
            score = 0.0
            cost_usd = 0.0
            try:
                cassette = _load_cassette_registry_if_configured(case, cassette_root)
                output = executor_fn(case.unlabeled_view, sb.workspace_dir, cassette)
                cost_usd = float(output.get("cost_usd", 0.0))

                req_keys = tuple(case.expected_contract.get("required_keys") or ())
                req_ids = tuple(case.expected_contract.get("required_grounding_ids") or ())
                tier1 = run_tier1_deterministic_pre_judge(
                    output.get("candidate", output),
                    required_keys=req_keys,
                    required_grounding_ids=req_ids,
                    enforce_anti_ai_filter=bool(case.expected_contract.get("enforce_anti_ai_filter", False)),
                )
                if not tier1.passed:
                    failed_gates.extend(tier1.failed_gates)
                    tier1_failed_all.extend(f"{case.case_id}:{g}" for g in tier1.failed_gates)

                expected_label = case.expected_contract.get("reference_label")
                actual_label = output.get("label")
                if expected_label is not None and actual_label != expected_label:
                    failed_gates.append(f"label_mismatch:{actual_label}!={expected_label}")

                if blind_judge_fn is not None and not failed_gates:
                    bundle = build_sealed_blind_judge_bundle(
                        artifact_id=case.case_id,
                        raw_input=output,
                        author_model_family=author_model_family,
                        rubric_id=rubric_version,
                        repo_root=repo_root,
                    )
                    j_verdict = blind_judge_fn(bundle.to_dict())
                    prov_ok, prov_errs = validate_blind_judge_verdict_provenance(
                        j_verdict,
                        expected_bundle_digest=bundle.bundle_digest,
                        expected_artifact_sha256=bundle.artifact_sha256,
                        require_no_deterministic_priming=True,
                    )
                    blind_judge_meta["executed"] = True
                    blind_judge_meta["bundle_digest"] = bundle.bundle_digest
                    j_fam = str(j_verdict.get("judge_model_family") or "")
                    if j_fam and j_fam not in blind_judge_meta["judge_model_families"]:
                        blind_judge_meta["judge_model_families"].append(j_fam)
                    if not prov_ok:
                        failed_gates.extend(prov_errs)
                        blind_judge_meta["veto_triggered"] = True
                    elif str(j_verdict.get("verdict") or "").upper() != "PASS":
                        failed_gates.append("blind_judge_rejected")
                        blind_judge_meta["veto_triggered"] = True

                score = float(output.get("score", 1.0 if not failed_gates else 0.0))
                status = "PASS" if not failed_gates else "FAIL"
                if status != "PASS":
                    sb.mark_failed(";".join(failed_gates))
            except (ValueError, RuntimeError, FileNotFoundError, KeyError, TypeError) as exc:
                failed_gates.append(f"execution_error:{type(exc).__name__}:{exc}")
                status = "BLOCKED"
                sb.mark_failed(str(exc))

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            total_latency_ms += elapsed_ms
            total_cost_usd += cost_usd
            case_results.append(
                {
                    "case_id": case.case_id,
                    "status": status,
                    "score": round(score, 4),
                    "latency_ms": elapsed_ms,
                    "cost_usd": round(cost_usd, 6),
                    "failed_gates": failed_gates,
                }
            )

    seed_mutated = False
    if seed_auditor is not None:
        delta = seed_auditor.compare_after()
        if not delta.is_idempotent_noop:
            seed_mutated = True
            tier1_failed_all.append(f"SEED_DIR_MUTATED:{delta.total_mutations}")

    pass_count = sum(1 for c in case_results if c["status"] == "PASS")
    mean_score_pct = round(
        (sum(float(c["score"]) for c in case_results) / float(len(case_results))) * 100.0,
        2,
    )
    all_passed = pass_count == len(case_results) and not seed_mutated
    verdict = "PASS" if all_passed else ("BLOCKED" if seed_mutated else "FAIL")
    receipt_id = stable_id("rcpt", suite_id, suite_digest, git_sha, utc_now_iso(), length=16)

    return EvalReceipt(
        receipt_id=receipt_id,
        suite_id=suite_id,
        suite_digest=suite_digest,
        rubric_version=rubric_version,
        pipeline_version=pipeline_version,
        git_sha=git_sha,
        execution_mode=execution_mode,
        grounding_tier=grounding_tier,
        deterministic_tier1={
            "passed": len(tier1_failed_all) == 0,
            "tokens_spent": 0,
            "failed_gates": tier1_failed_all,
            "evaluator_kind": "deterministic_gate",
        },
        blind_judge_tier2=blind_judge_meta,
        case_results=case_results,
        pareto_point={
            "quality_score": mean_score_pct,
            "latency_ms": round(total_latency_ms, 2),
            "cost_usd": round(total_cost_usd, 6),
            "is_pareto_optimal": True,
        },
        non_compensating_regressions=[],
        verdict=verdict,  # type: ignore[arg-type]
    )


def _behavior_signature(receipt: EvalReceipt) -> str:
    """Hash semantic case outcomes ignoring timestamps, receipt IDs, and wall-clock latency."""
    semantic_rows = [
        {
            "case_id": row["case_id"],
            "status": row["status"],
            "score": row["score"],
            "failed_gates": sorted(row.get("failed_gates") or []),
        }
        for row in sorted(receipt.case_results, key=lambda r: str(r["case_id"]))
    ]
    return canonical_sha256({"verdict": receipt.verdict, "cases": semantic_rows})


def run_stress_suite(
    *,
    suite_id: str,
    cases: Sequence[EvalCase],
    executor_fn: Callable[[dict[str, Any], Path, Any | None], dict[str, Any]],
    repetitions: int = 3,
    work_root: Path | None = None,
    seed_dir: Path | None = None,
    cassette_root: Path | None = None,
) -> StressResult:
    """Run suite across repetitions in [2, 20] fresh workspaces and verify behavior signature stability."""
    if repetitions < 2 or repetitions > 20:
        raise ValueError(f"repetitions must be in [2, 20], got {repetitions}")

    seed_auditor = StateDeltaAuditor([seed_dir]) if seed_dir is not None and seed_dir.exists() else None
    if seed_auditor is not None:
        seed_auditor.capture_before()

    signatures: list[str] = []
    pass_rates: list[float] = []
    for _ in range(repetitions):
        rcpt = run_hermetic_eval_suite(
            suite_id=suite_id,
            cases=cases,
            executor_fn=executor_fn,
            work_root=work_root,
            seed_dir=seed_dir,
            cassette_root=cassette_root,
        )
        signatures.append(_behavior_signature(rcpt))
        rate = sum(1 for c in rcpt.case_results if c["status"] == "PASS") / float(len(rcpt.case_results))
        pass_rates.append(round(rate, 4))

    unique_sigs = sorted(set(signatures))
    seed_unchanged = True if seed_auditor is None else seed_auditor.compare_after().is_idempotent_noop
    all_cleaned = True
    if work_root is not None and work_root.is_dir():
        leftover_passing = [
            d for d in work_root.iterdir() if d.is_dir() and not (d / ".retention.json").is_file()
        ]
        all_cleaned = len(leftover_passing) == 0

    reasons: list[str] = []
    if len(unique_sigs) != 1:
        reasons.append(f"NON_DETERMINISTIC_BEHAVIOR_SIGNATURES:{len(unique_sigs)}")
    if not seed_unchanged:
        reasons.append("SEED_STATE_MUTATED")
    if not all_cleaned:
        reasons.append("PASSING_WORKSPACES_LEAKED")

    return StressResult(
        suite_id=suite_id,
        repetitions=repetitions,
        unique_behavior_signatures=unique_sigs,
        pass_rate_by_trial=pass_rates,
        all_workspaces_cleaned=all_cleaned,
        seed_state_unchanged=seed_unchanged,
        verdict="PASS" if not reasons else "FAIL",
        failure_reasons=reasons,
    )
