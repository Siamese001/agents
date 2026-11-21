"""Wave 1 unit & behavioral tests for closed eval contracts, hermetic sandboxes, cassette replay, trajectory, and stress stability."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apps_eval.contracts.digests import canonical_sha256, verify_canonical_digest
from apps_eval.contracts.schemas import EvalCase, EvalReceipt, RunTrace
from apps_eval.graders.trajectory import (
    ToolSchemaValidator,
    TrajectoryEvaluator,
    TrajectoryStep,
    TrajectoryTrace,
)
from apps_eval.runner.hermetic import (
    compare_eval_receipts,
    detect_case_regressions,
    run_hermetic_eval_suite,
    run_stress_suite,
)
from apps_eval.sandbox import (
    ChaosFaultSpec,
    ChaosInjector,
    SandboxEnvironment,
    StateDeltaAuditor,
    prune_expired_failed_workspaces,
)
from infrastructure.sdks_mcps.wire_cassette import CassetteRegistry, WireExchange, compute_request_signature


def test_canonical_digest_rejects_nan_and_closed_schema_rejects_extra_keys() -> None:
    with pytest.raises(ValueError, match="Non-finite"):
        canonical_sha256({"score": float("nan")})

    trace = RunTrace(
        trace_id="trace-1",
        app_id="apps_research",
        run_id="run-1",
        session_id="sess-1",
        git_sha="a" * 40,
        config_digest="b" * 64,
        started_at_utc="2026-11-21T00:00:00Z",
        finished_at_utc="2026-11-21T00:01:00Z",
        terminal_status="PASS",
    )
    assert trace.verify_digest()
    assert verify_canonical_digest(trace.to_dict())

    raw = trace.to_dict()
    raw["unexpected_extra_key"] = "boom"
    with pytest.raises(ValueError, match="additionalProperties=false"):
        RunTrace.from_dict(raw)


def test_sandbox_lifecycle_deletes_pass_retains_fail_and_prunes_expired(tmp_path: Path) -> None:
    work_root = tmp_path / "eval_work"
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "input.txt").write_text("immutable seed", encoding="utf-8")

    auditor = StateDeltaAuditor([seed_dir])
    auditor.capture_before()

    with SandboxEnvironment(case_id="pass-case", work_root=work_root, seed_dir=seed_dir) as sb:
        assert sb.workspace_dir is not None
        (sb.workspace_dir / "input.txt").write_text("mutated inside sandbox only", encoding="utf-8")
        pass_dir = sb.workspace_dir

    assert not pass_dir.exists()
    assert auditor.compare_after().is_idempotent_noop

    with SandboxEnvironment(case_id="fail-case", work_root=work_root, seed_dir=seed_dir, retention_days=7) as sb:
        assert sb.workspace_dir is not None
        fail_dir = sb.workspace_dir
        sb.mark_failed("deliberate failure")

    assert fail_dir.exists()
    assert (fail_dir / ".retention.json").is_file()

    # Not expired today -> preserved; expired +8 days -> pruned.
    assert prune_expired_failed_workspaces(work_root, now_utc=datetime.now(timezone.utc)) == []
    assert fail_dir.exists()
    future = datetime.now(timezone.utc) + timedelta(days=8)
    pruned = prune_expired_failed_workspaces(work_root, now_utc=future)
    assert pruned == [fail_dir.name]
    assert not fail_dir.exists()


def test_chaos_injector_fails_exact_trigger_count_then_recovers() -> None:
    injector = ChaosInjector(ChaosFaultSpec(fault_kind="timeout", trigger_count=2))
    wrapped = injector.wrap(lambda x: x * 2)

    with pytest.raises(TimeoutError):
        wrapped(3)
    with pytest.raises(TimeoutError):
        wrapped(3)
    assert wrapped(3) == 6
    assert injector.metrics.faults_injected == 2
    assert injector.metrics.recovered_calls == 1


def test_trajectory_evaluator_detects_loops_oscillations_and_bool_as_int() -> None:
    validator = ToolSchemaValidator(
        {
            "search": {
                "properties": {
                    "limit": {"type": "integer"},
                    "query": {"type": "string", "minLength": 2},
                },
                "required": ["query"],
                "additionalProperties": False,
            }
        }
    )
    ok_bool_int, errs = validator.validate("search", {"query": "ai", "limit": True})
    assert not ok_bool_int
    assert "type_mismatch:limit:expected_integer" in errs

    ok_extra, errs2 = validator.validate("search", {"query": "ai", "limit": 5, "unknown": 1})
    assert not ok_extra
    assert "unexpected_property:unknown" in errs2

    good_trace = TrajectoryTrace(
        trace_id="good-1",
        optimal_step_count=2,
        terminal_task_success=True,
        steps=[
            TrajectoryStep(0, "tool_call", "search", {"query": "ai", "limit": 5}),
            TrajectoryStep(1, "final_response", "reply", {}),
        ],
    )
    good_card = TrajectoryEvaluator(validator).evaluate(good_trace)
    assert good_card.passed
    assert good_card.composite_score >= 95.0

    osc_trace = TrajectoryTrace(
        trace_id="osc-1",
        optimal_step_count=2,
        terminal_task_success=True,
        steps=[
            TrajectoryStep(0, "tool_call", "search", {"query": "a1", "limit": 1}),
            TrajectoryStep(1, "tool_call", "search", {"query": "b1", "limit": 2}),
            TrajectoryStep(2, "tool_call", "search", {"query": "a1", "limit": 1}),
            TrajectoryStep(3, "tool_call", "search", {"query": "b1", "limit": 2}),
        ],
    )
    osc_card = TrajectoryEvaluator(validator).evaluate(osc_trace)
    assert not osc_card.passed
    assert osc_card.oscillation_count == 1


def test_hermetic_cassette_replay_non_compensating_compare_and_stress(tmp_path: Path) -> None:
    cassette_dir = tmp_path / "cassettes"
    cassette_dir.mkdir()
    cassette_file = cassette_dir / "sample_cassette.json"
    sig = compute_request_signature("POST", "https://api.example.test/v1/eval", b'{"q":"hello"}')
    reg = CassetteRegistry()
    reg._exchanges[sig] = WireExchange(
        signature_hash=sig,
        method="POST",
        url="https://api.example.test/v1/eval",
        request_headers={"Authorization": "Bearer secret-token"},
        request_body={"q": "hello"},
        response_status=200,
        response_headers={"content-type": "application/json"},
        response_body={"label": "SUPPORTED"},
    )
    reg.save(cassette_file)
    assert "secret-token" not in cassette_file.read_text(encoding="utf-8")

    case1 = EvalCase(
        case_id="case-cassette-1",
        suite_id="agents_core.cassette.v1",
        app_id="agents_core",
        split="development",
        execution_mode="cassette_replay",
        source_kind="curated",
        grounding_tier="OFFLINE_BENCHMARK_GROUNDED",
        unlabeled_input={"cassette_path": "sample_cassette.json", "sig": sig},
        expected_contract={"reference_label": "SUPPORTED"},
    )
    case2 = EvalCase(
        case_id="case-cassette-2",
        suite_id="agents_core.cassette.v1",
        app_id="apps_research",
        split="development",
        execution_mode="snapshot",
        source_kind="curated",
        grounding_tier="OFFLINE_BENCHMARK_GROUNDED",
        unlabeled_input={"text": "verified output"},
        expected_contract={"reference_label": "OK"},
    )

    def _exec(view: dict, ws: Path, cassette: CassetteRegistry | None) -> dict:
        (ws / "scratch.txt").write_text("temp", encoding="utf-8")
        if cassette is not None:
            ex = cassette._exchanges[view["unlabeled_input"]["sig"]]
            return {"label": ex.response_body["label"], "candidate": "grounded output", "score": 1.0}
        return {"label": "OK", "candidate": "grounded output", "score": 1.0}

    work_root = tmp_path / "work"
    rcpt = run_hermetic_eval_suite(
        suite_id="agents_core.cassette.v1",
        cases=[case1, case2],
        executor_fn=_exec,
        execution_mode="cassette_replay",
        work_root=work_root,
        cassette_root=cassette_dir,
    )
    assert rcpt.verdict == "PASS"
    assert rcpt.verify_digest()

    # Non-compensating flip check: flipping case1 PASS->FAIL fails comparison even if another case improves.
    regs, imps = detect_case_regressions(
        [{"case_id": "c1", "status": "PASS"}, {"case_id": "c2", "status": "FAIL"}],
        [{"case_id": "c1", "status": "FAIL"}, {"case_id": "c2", "status": "PASS"}],
    )
    assert regs == ["c1"]
    assert imps == ["c2"]

    degraded = EvalReceipt(
        receipt_id="rcpt-degraded",
        suite_id=rcpt.suite_id,
        suite_digest=rcpt.suite_digest,
        rubric_version=rcpt.rubric_version,
        pipeline_version="pipeline.v2",
        git_sha=rcpt.git_sha,
        execution_mode=rcpt.execution_mode,
        grounding_tier=rcpt.grounding_tier,
        deterministic_tier1=rcpt.deterministic_tier1,
        blind_judge_tier2=rcpt.blind_judge_tier2,
        case_results=[
            {**rcpt.case_results[0], "status": "FAIL", "score": 0.0},
            rcpt.case_results[1],
        ],
        pareto_point=rcpt.pareto_point,
        non_compensating_regressions=["case-cassette-1"],
        verdict="FAIL",
    )
    cmp = compare_eval_receipts(rcpt, degraded)
    assert cmp.comparable
    assert cmp.verdict == "FAIL"
    assert cmp.case_regressions == ["case-cassette-1"]

    stress = run_stress_suite(
        suite_id="agents_core.cassette.v1",
        cases=[case1, case2],
        executor_fn=_exec,
        repetitions=3,
        work_root=work_root,
        cassette_root=cassette_dir,
    )
    assert stress.verdict == "PASS"
    assert len(stress.unique_behavior_signatures) == 1
    assert stress.all_workspaces_cleaned
