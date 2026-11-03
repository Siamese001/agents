"""Unit tests for Wave 1-4 performance, concurrency, and anti-spin invariants."""

from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.assembly.full_resume_llm_coherence import (
    _build_prompt,
    run_full_resume_coherence_judges,
)
from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.judges.bullet_pool_claude_selector import PoolSelectionResult
from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput
from apps_rg.runtime.judges.section_judge_profile import SectionJudgeModelResolution
from apps_rg.runtime.orchestration import patch_run as pr
from apps_rg.runtime.orchestration.patch_run import build_patch_plan
from apps_rg.runtime.reasoning.bullet_lane_generation import (
    generate_bullet_lane_with_sc_and_claude,
)
from apps_rg.runtime.reasoning.bullet_lane_self_consistency import SelfConsistencyPath
from apps_rg.runtime.sections.executive_summary_judge_remediation import (
    evaluate_judge_remediation_trigger,
)
from apps_rg.runtime.validators.ibm_bullets_x2 import IBM_BULLET_IDS


def _load_sibling_module(filename: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(f"_sib_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _soft_fail_judge(provider_key: str, *, findings: list[str], score: float = 0.5) -> dict:
    return {
        "provider_key": provider_key,
        "provider_name": provider_key,
        "evaluator_mode": "MODEL_BACKED",
        "provider_status": "MODEL_BACKED_FAIL",
        "pass": False,
        "decisive_failure": False,
        "normalized_score": score,
        "normalized_threshold": 0.8,
        "findings": findings,
        "fail_reasons": [],
        "remediation_suggestions": [],
    }


def _coherence_judge(*, key: str, pass_: bool) -> JudgeOutput:
    sc = 0.9 if pass_ else 0.2
    return JudgeOutput(
        judge_id=f"x1d_{key}_full_resume_coherence",
        provider_name=key,
        provider_key=key,
        evaluator_mode="LIVE",
        provider_status="OK",
        model_name="test",
        provider_available=True,
        provider_blocked=False,
        exact_provider_error=None,
        rubric_version="test",
        input_hash="abc",
        output_hash="def",
        score=sc,
        score_scale="0_to_1",
        normalized_score=sc,
        threshold=0.8,
        normalized_threshold=0.8,
        pass_=pass_,
        decisive_failure=not pass_,
        findings=[],
        fail_reasons=[],
        remediation_suggestions=[],
        dimension_verdicts={},
        raw_response={},
    )


def test_two_path_sc_batch_runs_concurrently_without_serial_prewarm(monkeypatch) -> None:
    """Wave 2 concurrency contract: 2-path employment batches overlap in ThreadPoolExecutor."""
    from apps_rg.runtime.reasoning import bullet_lane_self_consistency as sc_mod

    barrier = threading.Barrier(2, timeout=5.0)
    timestamps: list[tuple[int, float]] = []

    def fake_one_path(**kwargs):
        idx = int(kwargs["path_index"])
        timestamps.append((idx, time.monotonic()))
        barrier.wait()
        return SelfConsistencyPath(
            path_index=idx,
            temperature=float(kwargs["temperature"]),
            runtime_generation_status="REAL_LLM",
            raw_output="{}",
            parsed={"bullets": [], "claim_ledger": []},
            parse_error="",
            provider_result=None,
        )

    monkeypatch.setattr(sc_mod, "_run_one_self_consistency_path", fake_one_path)
    monkeypatch.setenv("APPS_RG_BULLET_SC_PARALLEL", "1")
    monkeypatch.setenv("APPS_RG_ANTHROPIC_PROMPT_CACHE_FANOUT", "1")
    monkeypatch.delenv("APPS_RG_ANTHROPIC_PROMPT_CACHE_PREWARM", raising=False)

    paths, _ = sc_mod.run_provider_self_consistency_paths(
        section_lane="unify_bullets",
        provider_payload={"model": "test"},
        parse_model_json=lambda _raw: ({"bullets": [], "claim_ledger": []}, ""),
        artifact_dir=None,
        run_id="run_w2",
        temperature_bounds=(0.35, 0.55),
        base_temperature=0.4,
        path_count=2,
    )

    assert len(paths) == 2
    assert len(timestamps) == 2


def test_frozen_allocation_materialized_caps_sc_to_single_path_zero_regen(monkeypatch) -> None:
    """Wave 2 anti-spin contract: frozen allocation lanes execute 1 path and 0 regen rounds."""
    from apps_rg.runtime.reasoning import bullet_lane_generation as gen_mod

    calls = {"sc_batches": 0, "paths_requested": 0}

    def fake_sc(**kwargs):
        calls["sc_batches"] += 1
        calls["paths_requested"] += int(kwargs["path_count"])
        return (
            [
                SelfConsistencyPath(
                    path_index=0,
                    temperature=0.4,
                    runtime_generation_status="REAL_LLM",
                    raw_output="{}",
                    parsed={
                        "bullets": [
                            {"bullet_id": bid, "bullet_text": f"low {bid}"}
                            for bid in IBM_BULLET_IDS
                        ],
                        "claim_ledger": [],
                    },
                    parse_error="",
                    provider_result=None,
                )
            ],
            None,
        )

    def fake_selector(**_kwargs):
        return PoolSelectionResult(
            merged_parsed={
                "bullets": [{"bullet_id": IBM_BULLET_IDS[0], "bullet_text": "partial"}],
                "claim_ledger": [],
            },
            selections=[
                {"bullet_id": IBM_BULLET_IDS[0], "path_index": 0, "score": 0.40, "passes": False}
            ],
            judge_output=None,
            selection_mode="claude_pool_selector",
            source_path_by_slot={IBM_BULLET_IDS[0]: 0},
        )

    monkeypatch.setattr(gen_mod, "run_provider_self_consistency_paths", fake_sc)
    monkeypatch.setattr(gen_mod, "run_claude_bullet_pool_selection", fake_selector)

    _, _, _, _, meta = generate_bullet_lane_with_sc_and_claude(
        section_lane="ibm_bullets",
        slot_kind="bullets",
        provider_payload={"model": "test"},
        parse_model_json=lambda _r: ({}, ""),
        normalize_parsed=lambda p: p,
        artifact_dir=None,
        run_id="run_w2_frozen",
        temperature_bounds=(0.35, 0.55),
        base_temperature=0.4,
        required_bullet_ids=IBM_BULLET_IDS,
        targeting_context={"frozen_allocation_materialized": True},
        judge_mode="blocked_if_unavailable",
        provider_profile="external_claude",
    )

    assert calls["sc_batches"] == 1
    assert calls["paths_requested"] == 1
    assert meta["regen_rounds_executed"] == 0


def test_upstream_allocation_defect_short_circuits_writer_remediation_in_zero_retries() -> None:
    judges = [
        {
            **_soft_fail_judge(
                "openai_chatgpt",
                findings=["Off-domain BCBS 239 clutter on AI Partnerships role"],
                score=0.68,
            ),
            "decisive_failure": True,
            "defect_origin": "UPSTREAM_ALLOCATION_DEFECT",
        }
    ]
    ok, receipt = evaluate_judge_remediation_trigger(
        judges, runtime_generation_status="REAL_LLM", x2_passed=True
    )
    assert ok is False
    assert receipt["reason"] == "upstream_allocation_defect_short_circuit"
    assert receipt["defect_origin"] == "UPSTREAM_ALLOCATION_DEFECT"


def test_full_resume_coherence_judges_run_concurrently_and_deduplicate_prompt(monkeypatch) -> None:
    """Wave 3 contract: dual coherence judges overlap in ThreadPoolExecutor and omit duplicate visible_claims."""
    import apps_rg.runtime.assembly.full_resume_llm_coherence as coh_mod

    packet = {
        "schema": "apps_rg.full_resume_candidate_evidence_packet.v1",
        "authority_semantics": ["Whole-resume allocation rule."],
        "sections": [
            {
                "section_id": "executive_summary",
                "allocation_plan_digest": "dig_1",
                "claim_binding_pass": True,
                "visible_claims": [
                    {"claim_text": "DUPLICATE_VISIBLE_SENTENCE_BLOB", "source_fact_ids": ["f1"]}
                ],
                "selected_candidate_facts": [
                    {
                        "fact_id": "f1",
                        "claim_text": "Generated $22M IP-led revenue.",
                        "metric_outcome_ids": ["m1"],
                        "metric_values": ["$22M"],
                    }
                ],
                "graph_claim_bindings": [
                    {
                        "visible_claim_text": "DUPLICATE_VISIBLE_SENTENCE_BLOB",
                        "fact_ids": ["f1"],
                        "metric_outcome_id": "m1",
                        "metric_value": "$22M",
                        "binding_status": "BOUND",
                    }
                ],
            }
        ],
    }
    prompt = _build_prompt(
        full_resume_text="EXECUTIVE SUMMARY\nGenerated $22M IP-led revenue.",
        target_company="Anthropic",
        target_role="Applied AI Partnerships",
        jd_context="Partner architecture.",
        evidence_packet=packet,
    )
    assert "DUPLICATE_VISIBLE_SENTENCE_BLOB" not in prompt
    assert '"fact_id":"f1"' in prompt
    assert '"metric_outcome_id":"m1"' in prompt

    barrier = threading.Barrier(2, timeout=5.0)
    monkeypatch.setattr(coh_mod, "resolve_x1d_provider_credentials", lambda k, _e: ("key", "ENV"))
    monkeypatch.setattr(
        coh_mod,
        "resolve_section_proof_judge_model",
        lambda sid, k: SectionJudgeModelResolution(
            provider_key=k,
            section_id=sid,
            judge_tier="standard",
            model_requested="m",
            model_actual="m",
            model_source="yaml",
            model_tier="standard",
            reasoning_effort="high",
            blocked=False,
            advisory_only=False,
            proof_eligible_judge=True,
        ),
    )

    def fake_invoke(_fn, *, provider_key: str, section_id: str):
        barrier.wait()
        return _coherence_judge(key=provider_key, pass_=True)

    monkeypatch.setattr(coh_mod, "_invoke_judge_with_bounded_retries", fake_invoke)
    results = run_full_resume_coherence_judges(
        full_resume_text="Resume text",
        target_company="Anthropic",
        target_role="Applied AI Partnerships",
        evidence_packet=packet,
        judge_roster=["gemini_pro", "openai_chatgpt"],
        mode="blocked_if_unavailable",
    )
    assert [r.provider_key for r in results] == ["gemini_pro", "openai_chatgpt"]


def test_sync_split_pointer_roots_mirrors_fresher_lanes_pointer_into_modular_sections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    tpr = _load_sibling_module("test_patch_run.py")
    _repo, run_dir = tpr._seed_integrated_run(tmp_path)
    lanes_root = run_dir / "lanes"
    tpr._write_json(lanes_root / "sections_root_manifest.json", {"schema_version": "1.0"})
    stale_ptr = {
        "run_id": "exec_old",
        "run_dir": "artifacts/apps_rg/e2e_aig_verify/attempt_fixture/modular_r4/sections/executive_summary/real/p_old",
        "generated_at_utc": "2026-11-02T21:56:39+00:00",
        "section_id": "executive_summary",
    }
    fresh_ptr = {
        "run_id": "exec_fresh",
        "run_dir": "artifacts/apps_rg/e2e_aig_verify/attempt_fixture/modular_r4/sections/executive_summary/real/p_fresh",
        "generated_at_utc": "2026-11-02T22:41:11+00:00",
        "section_id": "executive_summary",
    }
    tpr._write_json(
        run_dir / "modular_r4" / "sections" / "executive_summary" / "latest_successful_real_run.json",
        stale_ptr,
    )
    tpr._write_json(
        lanes_root / "executive_summary" / "latest_successful_real_run.json",
        fresh_ptr,
    )
    pr._sync_split_pointer_roots(run_dir)
    synced_mod = json.loads(
        (
            run_dir
            / "modular_r4"
            / "sections"
            / "executive_summary"
            / "latest_successful_real_run.json"
        ).read_text(encoding="utf-8")
    )
    assert synced_mod["run_id"] == "exec_fresh"


def test_dispatch_patch_lanes_runs_independent_wave_lanes_concurrently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPS_RG_TEST_HARNESS", "1")
    tpr = _load_sibling_module("test_patch_run.py")
    repo, run_dir = tpr._seed_integrated_run(
        tmp_path,
        green=tuple(
            l
            for l in GENERATED_LANES
            if l not in ("slalom_bullets", "unify_bullets", "ibm_bullets", "ibm_narrative")
        ),
        blocked=("slalom_bullets", "unify_bullets", "ibm_bullets"),
    )
    import apps_rg.runtime.validators.companion_bullet_finalization as cbf

    monkeypatch.setattr(cbf, "companion_accepted_in_modular_sections_root", lambda *a, **k: True)
    plan = build_patch_plan(run_dir)
    assert plan.target_lanes == [
        "slalom_bullets",
        "unify_bullets",
        "ibm_bullets",
        "ibm_narrative",
    ]

    lock = threading.Lock()
    intervals: dict[str, tuple[float, float]] = {}

    def _concurrent_stub(*, plan: Any, lane: str, lane_provider: str) -> dict[str, Any]:
        t0 = time.monotonic()
        time.sleep(0.08)
        t1 = time.monotonic()
        with lock:
            intervals[lane] = (t0, t1)
        rd = tpr._seed_lane_run(repo, run_dir, lane, f"{lane}_20261102_230000")
        return {
            "exit_status": "success",
            "x3_disposition": "X3_ALLOW",
            "artifact_dir": str(rd),
        }

    res = pr._dispatch_patch_lanes(
        plan,
        lane_provider="",
        dispatch_fn=_concurrent_stub,
    )
    assert set(res) == {"slalom_bullets", "unify_bullets", "ibm_bullets", "ibm_narrative"}
    latest_bullet_start = max(
        intervals["slalom_bullets"][0],
        intervals["unify_bullets"][0],
        intervals["ibm_bullets"][0],
    )
    earliest_bullet_end = min(
        intervals["slalom_bullets"][1],
        intervals["unify_bullets"][1],
        intervals["ibm_bullets"][1],
    )
    assert latest_bullet_start < earliest_bullet_end
    assert intervals["ibm_narrative"][0] >= intervals["ibm_bullets"][1] - 0.005
