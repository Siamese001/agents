"""Regression tests for RC-1 through RC-7 resume pipeline latency and regen RCA fixes."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from apps_rg.runtime.judges import x1d_ide_cli as ide
from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
from apps_rg.runtime.providers import agy_cli_transport as agy_t
from apps_rg.runtime.providers import ide_cli_generation as icg
from apps_rg.runtime.providers.agy_cli_transport import AgyResult
from apps_rg.runtime.sections.authority_repairs.citation_and_mechanism import (
    _expand_short_exec_summary_sentence,
    repair_exec_summary_thin_sentence_weave,
)
from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import (
    rescore_snapshot_or_reuse_full_panel,
)
from apps_rg.runtime.sections.executive_summary_candidate_pool import (
    SCORES_FRESHNESS_FULL_PANEL,
    SCORES_FRESHNESS_SOFT_FAILED_ONLY,
    CandidatePool,
    freeze_candidate_snapshot,
)
from apps_rg.runtime.sections.executive_summary_judge_remediation import (
    _flatten_delta_sections,
    _is_model_backed_soft_fail,
    _soft_failed_model_judges,
    _verbatim_soft_failed_judge_feedback_lines,
    evaluate_g3_trigger_judge_monotonicity,
    rerun_soft_failed_judges,
)
from apps_rg.runtime.sections.executive_summary_local_regen import (
    AnchorClassification,
    DefectClass,
    IncrementalRepairContract,
    SameAuthorityRegenRunner,
    TriggerSource,
)
from apps_rg.runtime.sections.executive_summary_regen_support import (
    PromptMessages,
    compute_system_prefix_hash,
    sha256_hex,
)


# ---------------------------------------------------------------------------
# RC-1: Medium IDE CLI pins + effort_by_section step-down
# ---------------------------------------------------------------------------


def test_rc1_ide_cli_pins_use_medium_orthogonal_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "ide_cli")
    monkeypatch.setenv("APPS_RG_GENERATION_TRANSPORT", "ide_cli")

    exec_pin = ide.lane_writer_model("executive_summary") or ""
    comp_pin = ide.lane_writer_model("competencies") or ""
    assert icg.resolve_ide_cli_generation_slug(exec_pin) == "gemini-4-neon-medium"
    assert icg.resolve_ide_cli_generation_slug(comp_pin) == "gemini-4-neon-medium"

    exec_slot1 = resolve_section_proof_judge_model("executive_summary", "gemini_pro")
    exec_slot2 = resolve_section_proof_judge_model("executive_summary", "openai_chatgpt")
    assert not exec_slot1.blocked and "argon" in exec_slot1.model_actual and exec_slot1.model_actual.endswith("-high")
    assert not exec_slot2.blocked and exec_slot2.model_actual == "gemini-3.8-flash-medium"
    assert exec_slot2.model_actual != icg.resolve_ide_cli_generation_slug(exec_pin)

    nar_slot1 = resolve_section_proof_judge_model("unify_narrative", "gemini_pro")
    nar_slot2 = resolve_section_proof_judge_model("unify_narrative", "openai_chatgpt")
    assert not nar_slot1.blocked and "argon" in nar_slot1.model_actual and nar_slot1.model_actual.endswith("-medium")
    assert not nar_slot2.blocked and nar_slot2.model_actual == "gemini-4-neon-medium"
    assert nar_slot2.model_actual != nar_slot1.model_actual


def test_rc1_generation_steps_down_high_slug_when_effort_is_medium(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    def fake_run_agy(prompt, *, model, json_schema=None, effort=None, timeout_s=600, agy_bin=None):
        captured.append({"model": model, "effort": effort})
        return AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response='{"ok": true}',
            structured_output=None,
            usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            duration_seconds=3.2,
            conversation_id="conv-rc1",
            queue_wait_seconds=0.45,
        )

    monkeypatch.setattr(icg, "run_agy", fake_run_agy)
    monkeypatch.setattr(icg, "resolve_ide_cli_generation_slug", lambda m: "gemini-4-neon-high")
    out = icg.call_ide_cli_generation(
        request={"model": "gemini-4-neon-high", "reasoning_effort": "medium", "prompt": "Write JSON."},
        body={"model": "gemini-4-neon-high", "messages": [{"role": "user", "content": "Write JSON."}]},
        environ={"AGY_CLI_BIN": "/fake/agy"},
    )
    assert captured[0]["model"] == "gemini-4-neon-medium"
    assert out["transport_timing"]["queue_wait_seconds"] == 0.45


# ---------------------------------------------------------------------------
# RC-2: stage_remediation_draft preserves x2_regen and _x2_failed in ctx
# ---------------------------------------------------------------------------


def test_rc2_stage_remediation_draft_syncs_x2_regen_and_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.sections.executive_summary import stage_remediation_draft as srd

    fake_gates = [
        {"gate_id": "g_ok", "pass": True},
        {"gate_id": "g_fail", "pass": False},
    ]
    captured_ctx: dict[str, object] = {}

    def fake_eval(ctx: dict) -> str:
        captured_ctx["x2_regen"] = list(ctx["x2_regen"])
        captured_ctx["_x2_failed"] = list(ctx["_x2_failed"])
        return "evaluated"

    monkeypatch.setattr(srd, "evaluate_remediation_draft_post_x2", fake_eval)
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_regen_loop.prepare_parsed_after_judge_regen",
        lambda parsed, **kw: (parsed, {"ok": True}),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_regen_loop.preserve_judge_regen_claim_ledger_from_baseline",
        lambda parsed, **kw: (parsed, {"ok": True}),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_regen_loop.sync_claim_ledger_metrics_from_facts",
        lambda parsed, **kw: (parsed, {"passed": True}),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_regen_delta_policy.evaluate_g5_delta_scope_v2",
        lambda *a, **kw: {"passed": True},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_remediation.rerun_x2_after_judge_remediation",
        lambda **kw: list(fake_gates),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_regen_loop.post_regen_x2_repair_eligible",
        lambda failed: False,
    )
    monkeypatch.setattr(srd, "build_sentence_claim_coverage", lambda *a, **kw: {"covered": True})
    monkeypatch.setattr(srd, "enrich_parsed_for_x2", lambda parsed, **kw: dict(parsed))

    parsed_base = {
        "resume_display_text": "Sentence one. Sentence two. Sentence three.",
        "claim_ledger": [{"claim_text": "c1", "source_fact_ids": ["f1"]}],
    }
    ctx = {
        "args": SimpleNamespace(target_company="Truist"),
        "artifact_dir": tmp_path,
        "runtime_payload": {"run_id": "r1"},
        "pool": SimpleNamespace(proof_pool_ref="", proof_pool_digest=""),
        "selected_fact_plan": {"facts": []},
        "allowed_fact_ids": {"f1"},
        "provider_payload": {},
        "raw_output": "{}",
        "runtime_generation_status": "REAL_LLM",
        "parsed_regen": dict(parsed_base),
        "parsed": dict(parsed_base),
        "parsed_for_x2": dict(parsed_base),
        "resume_display_text": parsed_base["resume_display_text"],
        "claim_ledger": list(parsed_base["claim_ledger"]),
        "coverage": {},
        "l2_output": {},
        "x1d": [],
        "x2": [{"gate_id": "pre", "pass": True}],
        "model_name": "gemini-4-neon-medium",
        "prompt_hash": "ph",
        "compiled_prompt": "cp",
        "temperature": 0.0,
        "input_payload_hash": "iph",
        "pp_x2": None,
        "proof_pool_x2_active": False,
        "selected_facts_for_x2": [],
        "_judge_jd": "jd",
        "_cycle_idx": 0,
        "_max_judge_cycles": 3,
        "_regen_messages": [],
        "_prior_regen_output_hash": None,
        "_cycles_receipt": {"cycles": []},
        "_cycle_record": {},
        "_draft_parse_ok": True,
        "_j_receipt": {},
        "_pre_parsed": dict(parsed_base),
        "_pre_raw": "{}",
        "_pre_resume": parsed_base["resume_display_text"],
        "_pre_ledger": list(parsed_base["claim_ledger"]),
        "_pre_x2": [{"gate_id": "pre", "pass": True}],
        "_x1d_before_regen": [],
        "_scores_before_regen": {},
        "_cycle_delta_class": "voice",
        "_strategy_exec_regen": None,
        "_operator_judge_floor": 4.7,
        "_judge_prompt_x1d": [],
        "_regen_incremental_anchor_parsed": None,
        "_regen_prior_cycle_judges": None,
        "_last_regen_candidate": None,
        "_regen_attempt_parsed_snapshot": None,
    }

    res = srd.process_remediation_draft(ctx)
    assert res == "evaluated"
    assert captured_ctx["x2_regen"] == fake_gates
    assert captured_ctx["_x2_failed"] == [{"gate_id": "g_fail", "pass": False}]


# ---------------------------------------------------------------------------
# RC-3: Concurrency default = 6 + queue_wait_seconds persisted in receipts
# ---------------------------------------------------------------------------


def test_rc3_default_concurrency_is_six_and_judge_persists_queue_wait(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(agy_t.AGY_MAX_CONCURRENCY_ENV_VAR, raising=False)
    assert agy_t.DEFAULT_AGY_MAX_CONCURRENCY == 6
    assert agy_t.resolve_agy_max_concurrency() == 6

    good = {
        "score_scale": "0_to_5",
        "score": 4.8,
        "threshold": 4.7,
        "pass": True,
        "decisive_failure": False,
        "findings": [],
        "cited_sentence_indexes": [],
        "remediation_suggestions": [],
    }
    monkeypatch.setattr(
        ide,
        "run_agy",
        lambda *a, **kw: AgyResult(
            model_requested="gemini-3.8-flash-medium",
            model_reported="gemini-3.8-flash-medium",
            status="SUCCESS",
            response=json.dumps(good),
            structured_output=good,
            usage={"input_tokens": 200, "output_tokens": 40, "total_tokens": 240},
            duration_seconds=8.1,
            conversation_id="conv-rc3",
            queue_wait_seconds=1.25,
        ),
    )
    out = ide.call_ide_cli_judge(
        prompt="Judge this.",
        model="gemini-3.8-flash-medium",
        input_hash="h1",
        provider_key="openai_chatgpt",
        artifact_base=tmp_path,
        section_id="executive_summary",
    )
    assert out.score == 4.8
    raw_file = next(p for p in tmp_path.iterdir() if "provider_response_raw" in p.name)
    raw_payload = json.loads(raw_file.read_text(encoding="utf-8"))
    assert raw_payload["queue_wait_seconds"] == 1.25


# ---------------------------------------------------------------------------
# RC-4: Full-panel post-regen snapshot preserves FULL_PANEL freshness
# ---------------------------------------------------------------------------


def test_rc4_full_panel_regen_snapshot_reused_without_redundant_rescore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps_rg.runtime.sections.executive_summary import stage_remediation_draft_eval as eval_mod

    x2_pass = [{"gate_id": "g1", "pass": True}]
    x1d_pass = [
        {
            "provider_key": "gemini_pro",
            "evaluator_mode": "MODEL_BACKED",
            "provider_status": "MODEL_BACKED_PASS",
            "pass": True,
            "score": 4.8,
            "normalized_score": 0.96,
            "normalized_threshold": 0.94,
            "decisive_failure": False,
        },
        {
            "provider_key": "openai_chatgpt",
            "evaluator_mode": "MODEL_BACKED",
            "provider_status": "MODEL_BACKED_PASS",
            "pass": True,
            "score": 4.8,
            "normalized_score": 0.96,
            "normalized_threshold": 0.94,
            "decisive_failure": False,
        },
    ]
    pool = CandidatePool()

    monkeypatch.setattr(eval_mod, "resolve_judge_packet_for_parity", lambda *a, **kw: {})
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_remediation.rescore_judges_after_regen",
        lambda **kw: (x1d_pass, {"rescore_mode": "full_panel", "scores_after": {}, "score_deltas": []}),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_remediation.evaluate_g3_trigger_judge_monotonicity",
        lambda **kw: {"passed": True, "g3_verdict_per_trigger_judge": []},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_regen_loop.advance_regen_thread_for_next_cycle",
        lambda msgs, **kw: (msgs, x1d_pass),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_regen_loop.extend_regen_thread_after_success",
        lambda msgs, raw: msgs,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_regen_loop.write_judge_regen_x2_snapshot",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_regen_observability.finalize_regen_cycle_observability",
        lambda *a, **kw: ("h", False),
    )
    monkeypatch.setattr(eval_mod, "_emit_dimension_upstream_triangulation", lambda *a, **kw: None)
    monkeypatch.setattr(eval_mod, "_write_x1d_judge_artifacts", lambda *a, **kw: None)
    monkeypatch.setattr(eval_mod, "write_x2_gate_outputs", lambda *a, **kw: None)
    monkeypatch.setattr(
        "apps_rg.runtime.section_repair_ledger.record_repair", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "apps_rg.runtime.section_repair_ledger.load_ledger", lambda *a, **kw: {"x2_runs": []}
    )
    monkeypatch.setattr(
        "apps_rg.runtime.section_repair_ledger.record_x2_run", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "apps_rg.runtime.section_repair_ledger.set_authoritative_attempt", lambda *a, **kw: None
    )

    parsed = {"resume_display_text": "One. Two. Three.", "claim_ledger": [{"claim_text": "c", "source_fact_ids": ["f1"]}]}
    ctx = {
        "args": SimpleNamespace(target_company="Truist", target_title="Head of FDE"),
        "artifact_dir": tmp_path,
        "runtime_payload": {},
        "allowed_fact_ids": {"f1"},
        "raw_output": "{}",
        "parsed": dict(parsed),
        "parsed_for_x2": dict(parsed),
        "resume_display_text": parsed["resume_display_text"],
        "claim_ledger": list(parsed["claim_ledger"]),
        "coverage": {},
        "l2_output": {},
        "x1d": [],
        "x2": x2_pass,
        "x2_regen": x2_pass,
        "_x2_failed": [],
        "model_name": "gemini-4-neon-medium",
        "prompt_hash": "ph",
        "compiled_prompt": "cp",
        "selected_facts_for_x2": [],
        "_judge_jd": "jd",
        "_judge_briefing": "bf",
        "judge_keys": ["gemini_pro", "openai_chatgpt"],
        "judge_mode": "real",
        "judge_packet": {},
        "_cycle_idx": 0,
        "_max_judge_cycles": 3,
        "_regen_messages": [],
        "_prior_regen_output_hash": None,
        "_cycles_receipt": {"cycles": []},
        "_candidate_pool": pool,
        "_provider_lane": "ide_cli",
        "_cycle_record": {},
        "_draft_parse_ok": True,
        "_j_receipt": {},
        "_pre_parsed": dict(parsed),
        "_pre_raw": "{}",
        "_pre_resume": parsed["resume_display_text"],
        "_pre_ledger": list(parsed["claim_ledger"]),
        "_pre_x2": x2_pass,
        "_x1d_before_regen": [],
        "_scores_before_regen": {},
        "_operator_judge_floor": 4.7,
        "_judge_prompt_x1d": [],
        "_regen_incremental_anchor_parsed": None,
        "_regen_prior_cycle_judges": None,
        "_last_regen_candidate": None,
        "_regen_attempt_parsed_snapshot": None,
    }

    action = eval_mod.evaluate_remediation_draft_post_x2(ctx)
    assert action == "break"
    assert len(pool.entries()) == 1
    snap = pool.entries()[0]
    assert snap.scores_freshness == SCORES_FRESHNESS_FULL_PANEL

    refresh_called = False

    def _should_not_run(**kw):
        nonlocal refresh_called
        refresh_called = True
        return ([], {})

    reused_judges, receipt = rescore_snapshot_or_reuse_full_panel(
        snap,
        full_panel_token=SCORES_FRESHNESS_FULL_PANEL,
        build_coverage_fn=lambda *a, **kw: {},
        enrich_x2_fn=lambda p, **kw: p,
        refresh_x1d_fn=_should_not_run,
        allowed_fact_ids={"f1"},
        input_payload_hash="iph",
        runtime_payload={},
        selected_facts_for_x2=[],
        target_title="Head of FDE",
        target_company="Truist",
        jd_text="jd",
        briefing_text="bf",
        judge_keys=["gemini_pro", "openai_chatgpt"],
        judge_mode="real",
        artifact_dir=tmp_path,
        compiled_prompt="cp",
        prior_judges=[],
        graph_targeting_capsule=None,
        material_targeting_bundle=None,
        graph_bindings=None,
        repo_root=tmp_path,
    )
    assert not refresh_called
    assert receipt["rescore_mode"] == "reused_full_panel_snapshot"
    assert len(reused_judges) == 2


# ---------------------------------------------------------------------------
# RC-5: No blind suffix-append stutter on short LLM sentences
# ---------------------------------------------------------------------------


def test_rc5_thin_sentence_weave_never_appends_stutter_tail() -> None:
    clean = "Directs agentic platform delivery across regulated enterprise workloads."
    assert _expand_short_exec_summary_sentence(clean) == clean

    parsed = {
        "resume_display_text": (
            f"{clean} "
            "Delivered $22M in platform product revenue across multi-cloud client engagements. "
            "Chartered FSA grounding technical architecture in institutional risk governance."
        ),
        "claim_ledger": [
            {"claim": "s1", "claim_text": clean, "source_fact_ids": ["f1"]},
            {"claim": "s2", "claim_text": "s2", "source_fact_ids": ["f2"]},
            {"claim": "s3", "claim_text": "s3", "source_fact_ids": ["f3"]},
        ],
        "change_log": [],
    }
    repairs = repair_exec_summary_thin_sentence_weave(parsed)
    assert repairs == []
    assert "across enterprise production environments" not in parsed["resume_display_text"]
    assert "across regulated enterprise workloads across" not in parsed["resume_display_text"]


# ---------------------------------------------------------------------------
# RC-6: ExecutiveVoiceRepairAgent works keyless under IDE CLI & never sends
#       ANTHROPIC_API_KEY to OpenAI
# ---------------------------------------------------------------------------


def test_rc6_voice_repair_keyless_ide_cli_routes_auditor_and_blocks_key_bleed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps_rg.runtime.sections import ExecutiveVoiceRepairAgent as evra

    # 1) HTTP fallback for auditor MUST NOT bleed ANTHROPIC_API_KEY into OpenAI
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-anthropic-token-for-unit-test")
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "external_api")
    called_http = False

    def _boom_urlopen(*a, **kw):
        nonlocal called_http
        called_http = True
        raise AssertionError("Must not call OpenAI HTTP with ANTHROPIC_API_KEY")

    monkeypatch.setattr("apps_rg.runtime.providers.external_provider.urlopen_provider_request", _boom_urlopen)
    assert evra._call_llm_repair("executive_summary", "Audit prompt", model=evra.DEFAULT_AUDITOR_MODEL) is None
    assert not called_http

    # 2) Under keyless IDE CLI mode (no API keys, outside pytest), repair succeeds via run_agy
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("APPS_RG_GENERATION_TRANSPORT", "ide_cli")
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "ide_cli")
    monkeypatch.setattr(icg, "ide_cli_generation_unavailable_reason", lambda environ=None, agy_bin=None: "")
    monkeypatch.setattr(ide, "ide_cli_unavailable_reason", lambda environ=None: "")

    agy_models_called: list[str] = []
    three_sentences = (
        "Enterprise AI executive directing governed agentic delivery across regulated financial institutions. "
        "Architected platform modernization generating $22M in IP-led revenue across global cloud teams. "
        "Chartered FSA aligning production AI controls with institutional risk governance."
    )

    def _fake_agy(prompt, *, model, json_schema=None, effort=None, timeout_s=600, agy_bin=None):
        agy_models_called.append(model)
        payload = (
            {"repaired_text": three_sentences}
            if len(agy_models_called) == 1
            else {"disposition": "PASS", "violated_facts": [], "repair_hint": ""}
        )
        return AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response=json.dumps(payload),
            structured_output=None,
            usage={"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
            duration_seconds=4.0,
            conversation_id=f"conv-{len(agy_models_called)}",
        )

    monkeypatch.setattr(agy_t, "run_agy", _fake_agy)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("APPS_RG_TEST_HARNESS", raising=False)
    with mock.patch.dict(sys.modules):
        sys.modules.pop("pytest", None)
        updated, receipt = evra.repair_section_with_executive_voice_agent(
            section_id="executive_summary",
            candidate_data={"resume_display_text": "Old broken draft."},
            diagnostic={"repair_needed": True, "findings": ["Stutter phrase"]},
            allowed_facts=[{"assertion_id": "f1", "fact_text": "$22M IP-led revenue"}],
            mock_mode=False,
        )

    assert receipt.repair_succeeded is True
    assert receipt.repair_mechanism == "a2a_socratic_repair_loop"
    assert updated["resume_display_text"] == three_sentences
    assert len(agy_models_called) == 2
    assert agy_models_called[0] == "gemini-4-neon-medium"
    assert agy_models_called[1] == "gemini-3.8-flash-medium"
    assert agy_models_called[0] != agy_models_called[1]


# ---------------------------------------------------------------------------
# RC-7: decisive_failure=True feedback/G3/rescore + uncapped SameAuthorityRegenRunner
#       + incremental protected_keys
# ---------------------------------------------------------------------------


def test_rc7_decisive_failure_included_in_feedback_g3_and_rescore(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    decisive_judge = {
        "provider_key": "openai_chatgpt",
        "provider_name": "Antigravity IDE CLI (gemini-3.8-flash-medium)",
        "evaluator_mode": "MODEL_BACKED",
        "provider_status": "MODEL_BACKED_FAIL",
        "pass": False,
        "decisive_failure": True,
        "score": 2.8,
        "normalized_score": 0.56,
        "normalized_threshold": 0.94,
        "findings": ["Duplicate phrase stutter in S1."],
        "remediation_suggestions": ["Remove duplicate tail clause."],
        "cited_sentence_indexes": [1],
    }

    assert _is_model_backed_soft_fail(decisive_judge) is True
    soft = _soft_failed_model_judges([decisive_judge])
    assert len(soft) == 1
    lines = _verbatim_soft_failed_judge_feedback_lines(soft)
    assert any("Duplicate phrase stutter in S1." in ln for ln in lines)

    regressed = dict(decisive_judge, score=2.4, normalized_score=0.48)
    g3 = evaluate_g3_trigger_judge_monotonicity(
        prior_judges=[decisive_judge],
        after_judges=[regressed],
    )
    assert g3["passed"] is False
    assert g3["reject_gate"] == "trigger_judge_regression"
    assert g3["trigger_provider_keys"] == ["openai_chatgpt"]

    rescored_keys: list[str] = []

    def _fake_run_judges(**kw):
        rescored_keys.extend(kw["judge_keys"])
        return [dict(decisive_judge, score=4.8, normalized_score=0.96, pass_=True, decisive_failure=False)]

    monkeypatch.setattr(
        "apps_rg.runtime.judges.executive_summary_x1d.run_llm_judges",
        _fake_run_judges,
    )
    rerun_soft_failed_judges(
        resume_display_text="Clean text.",
        claim_ledger=[{"claim_text": "Clean text.", "source_fact_ids": ["f1"]}],
        judge_packet={"allowed_fact_ids": ["f1"]},
        judge_packet_ref="p.json",
        compiled_prompt="cp",
        artifact_dir=tmp_path,
        judge_keys=["gemini_pro", "openai_chatgpt"],
        judge_mode="real",
        prior_judges=[decisive_judge],
    )
    assert rescored_keys == ["openai_chatgpt"]


def test_rc7_same_authority_runner_honors_large_contract_budget_and_flatten_protects_incremental() -> None:
    sections = {
        "incremental": [f"- INC_{i}" for i in range(6)],
        "dimension": ["- DIM_1", "- DIM_2"],
        "judge_feedback": [f"- FB_{i}" for i in range(20)],
        "floors": ["- FLOOR_1"],
        "guards": ["- GUARD_1"],
    }
    packed = _flatten_delta_sections(sections, max_lines=15)
    assert len(packed) == 15
    assert packed[:6] == sections["incremental"]
    assert packed[-1] == "- GUARD_1"

    pmsgs = PromptMessages(slot_map={"SYSTEM": "SYS", "USER": "USR"})
    anchor = '{"resume_display_text":"A."}'
    big_delta = tuple(f"LINE_{i}: " + ("word " * 60) for i in range(25))
    contract = IncrementalRepairContract(
        request_id="req1",
        run_id="run1",
        trace_root="tr1",
        parent_contract_ref="p",
        parent_attempt_receipt_id="pa",
        replay_key="rk",
        policy_hash="ph",
        blueprint_hash="bh",
        registry_digest_set=("d1",),
        frozen_compile_ref="fc",
        prompt_hash="prh",
        provider_lane="ide_cli",
        model_lane="gemini-4-neon-medium",
        parent_provider_lane="ide_cli",
        parent_model_lane="gemini-4-neon-medium",
        anchor_output_hash=sha256_hex(anchor),
        anchor_output_text=anchor,
        anchor_classification=AnchorClassification.LAST_APPROVED,
        defect_class=DefectClass.SOFT_REPAIRABLE,
        trigger_source=TriggerSource.X3_JUDGE,
        delta_lines=big_delta,
        semantic_regen_attempt_index=1,
        transport_retry_count=0,
        max_semantic_regen_attempts=3,
        max_delta_tokens=2_000_000,
        max_delta_lines=1_000_000,
        prompt_messages=pmsgs,
        expected_system_prefix_hash=compute_system_prefix_hash(pmsgs.system_text()),
        nested_heal_without_new_attempt=False,
        runtime_gate_refs=(),
        l5_governance_context_digest="lgd",
    )
    res = SameAuthorityRegenRunner().run(
        contract,
        provider_generate=lambda msgs: {"content": '{"resume_display_text":"B."}'},
    )
    assert res.accepted is True
    assert res.refusal is None
    assert res.receipt is not None and res.receipt.delta_line_count == 25


# ---------------------------------------------------------------------------
# RC-8 & RC-9: Voice-repair claim_ledger sync + no "audit-grade audit lineage"
# ---------------------------------------------------------------------------


def test_rc8_voice_repair_syncs_claim_ledger_sentences(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps_rg.runtime.sections import ExecutiveVoiceRepairAgent as evra

    repaired = (
        "Engineering executive scaling governed AI platforms across regulated financial institutions. "
        "Owned a multi-layer agentic control plane with governed route selection and isolated execution. "
        "Scaled 7 reusable cloud accelerators across 10+ global financial institutions, driving 24% renewal lift."
    )
    prior_ledger = [
        {"claim": "old 1", "claim_text": "Old sentence one.", "source_fact_ids": ["f1"]},
        {"claim": "old 2", "claim_text": "Old sentence two.", "source_fact_ids": ["f2"]},
        {"claim": "old 3", "claim_text": "Old sentence three.", "source_fact_ids": ["f3"]},
    ]
    calls = 0

    def _fake_call(sec: str, prompt: str, model: str = evra.DEFAULT_REPAIR_MODEL):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"repaired_text": repaired}
        return {"disposition": "PASS", "violated_facts": [], "repair_hint": ""}

    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-anthropic-token-for-unit-test")
    monkeypatch.setattr(evra, "_call_llm_repair", _fake_call)
    updated, receipt = evra.repair_section_with_executive_voice_agent(
        section_id="executive_summary",
        candidate_data={"resume_display_text": "Old sentence one. Old sentence two. Old sentence three.", "claim_ledger": prior_ledger},
        diagnostic={"repair_needed": True, "findings": ["Improve executive hook"]},
        allowed_facts=[{"assertion_id": "f1", "fact_text": "7 accelerators 24% renewal lift"}],
        mock_mode=False,
    )
    assert receipt.repair_succeeded is True
    assert updated["resume_display_text"] == repaired
    assert len(updated["claim_ledger"]) == 3
    for row in updated["claim_ledger"]:
        assert row["claim_text"] in repaired
    assert updated["claim_ledger"][0]["source_fact_ids"] == ["f1"]
    assert updated["claim_ledger"][2]["source_fact_ids"] == ["f3"]


def test_rc9_mechanism_repair_never_produces_audit_grade_audit_lineage() -> None:
    from apps_rg.runtime.sections.authority_repairs.citation_and_mechanism import (
        _normalize_mechanism_repair_text,
        _MECHANISM_INVENTORY_REWRITES,
    )

    text = "Engineered outcome-based evaluation harnesses and audit-grade OpenTelemetry lineage for regulated workloads."
    out = text
    for pat, repl in _MECHANISM_INVENTORY_REWRITES:
        out = pat.sub(repl, out)
    out = _normalize_mechanism_repair_text(out)
    assert "audit-grade audit lineage" not in out.lower()
    assert "audit-grade execution lineage" in out.lower()


# ---------------------------------------------------------------------------
# Post-review RCA fixes: voice-repair X2 enforcement, RC-4 hash guard,
# patch closeout integrity, eval --json, orthogonal auditor, low-effort step
# ---------------------------------------------------------------------------


def test_voice_repair_runs_full_x2_and_rolls_back_on_x2_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse
    from types import SimpleNamespace
    from apps_rg.runtime.sections import ExecutiveVoiceRepairAgent as evra
    from apps_rg.runtime.sections import executive_summary_judge_remediation as rem
    from apps_rg.runtime.sections.executive_summary import stage_remediation as sr

    orig_text = (
        "Engineering executive scaling governed AI platforms for regulated financial enterprises. "
        "Directed multi-region production control planes across global banking programs. "
        "Delivered 24% renewal lift across 10+ enterprise institutions."
    )
    bad_repaired = (
        "SVP-level executive with sandboxed tool execution and OpenTelemetry lineage. "
        "Directed multi-region production control planes across global banking programs. "
        "Delivered 24% renewal lift across 10+ enterprise institutions."
    )
    orig_ledger = [
        {"claim": "c1", "claim_text": "Engineering executive scaling governed AI platforms for regulated financial enterprises.", "source_fact_ids": ["f1"]},
        {"claim": "c2", "claim_text": "Directed multi-region production control planes across global banking programs.", "source_fact_ids": ["f2"]},
        {"claim": "c3", "claim_text": "Delivered 24% renewal lift across 10+ enterprise institutions.", "source_fact_ids": ["f3"]},
    ]
    orig_x2 = [
        {"gate_id": "x2_exec_summary_no_mechanism_inventory", "pass": True},
        {"gate_id": "x2_resume_graph_claim_binding", "pass": True},
    ]
    refresh_calls: list[str] = []

    def _fake_refresh(**kwargs):
        refresh_calls.append(kwargs["resume_display_text"])
        return [
            {"provider_key": "gemini_pro", "evaluator_mode": "MODEL_BACKED", "score": 4.2, "pass": False, "rationale": "Hook weak"},
            {"provider_key": "openai_chatgpt", "evaluator_mode": "MODEL_BACKED", "score": 4.3, "pass": False, "rationale": "Hook weak"},
        ], {"rescore_mode": "full_panel"}

    def _fake_rerun_x2(**kwargs):
        return [
            {"gate_id": "x2_exec_summary_no_mechanism_inventory", "pass": False},
            {"gate_id": "x2_x1d_required_judges_present", "pass": False},
        ]

    monkeypatch.setattr(rem, "refresh_x1d_judges_after_full_x2", _fake_refresh)
    monkeypatch.setattr(rem, "rerun_x2_after_judge_remediation", _fake_rerun_x2)
    monkeypatch.setattr(
        evra,
        "repair_section_with_executive_voice_agent",
        lambda **kwargs: (
            {"resume_display_text": bad_repaired, "claim_ledger": orig_ledger},
            SimpleNamespace(repair_succeeded=True),
        ),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.judges.x1d_panel_harness.extract_x1d_diagnostic",
        lambda x1d, sec: {"repair_needed": True, "findings": ["Improve hook"]},
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_repair_policy.judge_regeneration_enabled",
        lambda: False,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.section_repair_policy.judge_remediation_regen_allowed",
        lambda: False,
    )
    monkeypatch.setattr(sr, "publish_targeting_parity_and_usage_ledger", lambda **kw: ({}, kw.get("usage_doc") or {}))
    monkeypatch.setattr(sr, "resolve_judge_packet_for_parity", lambda *a, **k: {})
    monkeypatch.setattr(sr, "parity_allows_judge_regen", lambda *a, **k: (False, "test"))
    monkeypatch.setattr(sr, "_write_x1d_judge_artifacts", lambda *a, **k: None)
    monkeypatch.setattr(sr, "_emit_dimension_upstream_triangulation", lambda *a, **k: None)
    monkeypatch.setattr(sr, "write_x2_gate_outputs", lambda *a, **k: None)
    monkeypatch.setattr(
        "apps_rg.runtime.validators.executive_summary_x2.append_executive_summary_x1d_x2_gate_dicts",
        lambda **kw: [],
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.section_authority_repairs.apply_exec_summary_display_authority_repairs",
        lambda parsed, **kw: parsed,
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_voice_repair.finalize_executive_summary_coherence",
        lambda parsed, **kw: (parsed, {}),
    )
    monkeypatch.setattr(
        "apps_rg.runtime.sections.executive_summary_judge_regen_loop.sync_claim_ledger_metrics_from_facts",
        lambda parsed, **kw: (parsed, {"passed": True}),
    )

    ctx = {
        "args": argparse.Namespace(target_company="Truist", target_role="Head of FDE", target_title="Head of FDE", provider="external_claude", mode="live"),
        "artifact_dir": tmp_path,
        "runtime_payload": {"run_id": "test_run"},
        "token_budget_receipt": {},
        "usage_doc": {},
        "allowed_fact_ids": {"f1", "f2", "f3"},
        "raw_output": "{}",
        "runtime_generation_status": "REAL_LLM",
        "parsed": {"resume_display_text": orig_text, "claim_ledger": orig_ledger},
        "resume_display_text": orig_text,
        "claim_ledger": list(orig_ledger),
        "coverage": {"uncovered_sentences": []},
        "l2_output": {"resume_display_text": orig_text, "claim_ledger": orig_ledger},
        "_word_budget_repair_accepted": False,
        "parsed_for_x2": {"resume_display_text": orig_text, "claim_ledger": orig_ledger},
        "x2": list(orig_x2),
        "x1d": [],
        "_generation_material": SimpleNamespace(generation_material_digest="d"),
        "_bundle_mat": SimpleNamespace(to_dict=lambda: {}),
        "_targeting_parity": {},
        "selected_facts_for_x2": [],
        "selected_fact_plan": {"facts": []},
        "_judge_jd": "",
        "_judge_briefing": "",
        "judge_keys": ["gemini_pro", "openai_chatgpt"],
        "judge_mode": "live",
        "compiled_prompt": "",
        "pool": SimpleNamespace(proof_pool_ref="ref", proof_pool_digest="dig"),
        "model_name": "m",
        "prompt_hash": "ph",
        "temperature": 0.4,
    }
    sr.run_remediation_stage(ctx, emit_initial_gate_artifacts=False)

    # Voice repair broke X2 -> must roll back text/artifacts and NOT re-invoke judges on broken draft
    assert ctx["resume_display_text"] == orig_text
    assert (tmp_path / "resume_display_text.txt").read_text(encoding="utf-8").strip() == orig_text
    assert len(refresh_calls) == 1
    refresh_receipt = json.loads((tmp_path / "post_x2_x1d_refresh_receipt.json").read_text(encoding="utf-8"))
    assert refresh_receipt["voice_repair_rejected_x2_failed_gates"] == ["x2_exec_summary_no_mechanism_inventory"]


def test_rc4_rescore_judges_after_regen_guards_missing_and_stale_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps_rg.runtime.sections import executive_summary_judge_remediation as rem

    monkeypatch.setenv("APPS_RG_EXEC_SUMMARY_POST_REGEN_JUDGE_MODE", "soft_failed_only")

    # Case A: gemini_pro has NO hash and was NOT rescored; openai_chatgpt rescored with hash_v1 -> MUST be soft_failed_only
    prior_missing = [
        {"provider_key": "gemini_pro", "evaluator_mode": "MODEL_BACKED", "score": 4.8, "normalized_score": 0.96, "pass": True},
        {"provider_key": "openai_chatgpt", "evaluator_mode": "MODEL_BACKED", "score": 4.2, "normalized_score": 0.84, "pass": False},
    ]
    monkeypatch.setattr(
        rem,
        "rerun_soft_failed_judges",
        lambda **kw: [
            dict(prior_missing[0]),
            {"provider_key": "openai_chatgpt", "evaluator_mode": "MODEL_BACKED", "score": 4.8, "normalized_score": 0.96, "pass": True, "judge_packet_hash": "hash_v1"},
        ],
    )
    _, rcpt_a = rem.rescore_judges_after_regen(
        x2_gates=[], resume_display_text="Draft.", claim_ledger=[], allowed_fact_packet=[],
        allowed_fact_ids=set(), target_title="T", target_company="C", jd_text="", briefing_text="",
        parsed_output=None, judge_keys=["gemini_pro", "openai_chatgpt"], judge_mode="live",
        artifact_dir=tmp_path, compiled_prompt="", prior_judges=prior_missing,
        judge_packet={}, judge_packet_ref="",
    )
    assert rcpt_a["rescore_mode"] == rem.POST_REGEN_JUDGE_RESCORE_SOFT_ONLY
    assert rcpt_a["judges_rescored_count"] == 1

    # Case B: gemini_pro kept stale hash_v0; openai_chatgpt returned same hash_v0 -> MUST be soft_failed_only
    prior_stale = [
        {"provider_key": "gemini_pro", "evaluator_mode": "MODEL_BACKED", "score": 4.8, "normalized_score": 0.96, "pass": True, "judge_packet_hash": "hash_v0"},
        {"provider_key": "openai_chatgpt", "evaluator_mode": "MODEL_BACKED", "score": 4.2, "normalized_score": 0.84, "pass": False, "judge_packet_hash": "hash_v0"},
    ]
    monkeypatch.setattr(
        rem,
        "rerun_soft_failed_judges",
        lambda **kw: [
            dict(prior_stale[0]),
            {"provider_key": "openai_chatgpt", "evaluator_mode": "MODEL_BACKED", "score": 4.8, "normalized_score": 0.96, "pass": True, "judge_packet_hash": "hash_v0"},
        ],
    )
    _, rcpt_b = rem.rescore_judges_after_regen(
        x2_gates=[], resume_display_text="Draft.", claim_ledger=[], allowed_fact_packet=[],
        allowed_fact_ids=set(), target_title="T", target_company="C", jd_text="", briefing_text="",
        parsed_output=None, judge_keys=["gemini_pro", "openai_chatgpt"], judge_mode="live",
        artifact_dir=tmp_path, compiled_prompt="", prior_judges=prior_stale,
        judge_packet={}, judge_packet_ref="",
    )
    assert rcpt_b["rescore_mode"] == rem.POST_REGEN_JUDGE_RESCORE_SOFT_ONLY

    # Case C: both judges refreshed onto new hash_v1 -> MUST be full_panel with deltas for BOTH keys
    monkeypatch.setattr(
        rem,
        "rerun_soft_failed_judges",
        lambda **kw: [
            {"provider_key": "gemini_pro", "evaluator_mode": "MODEL_BACKED", "score": 4.9, "normalized_score": 0.98, "pass": True, "judge_packet_hash": "hash_v1"},
            {"provider_key": "openai_chatgpt", "evaluator_mode": "MODEL_BACKED", "score": 4.8, "normalized_score": 0.96, "pass": True, "judge_packet_hash": "hash_v1"},
        ],
    )
    _, rcpt_c = rem.rescore_judges_after_regen(
        x2_gates=[], resume_display_text="Draft.", claim_ledger=[], allowed_fact_packet=[],
        allowed_fact_ids=set(), target_title="T", target_company="C", jd_text="", briefing_text="",
        parsed_output=None, judge_keys=["gemini_pro", "openai_chatgpt"], judge_mode="live",
        artifact_dir=tmp_path, compiled_prompt="", prior_judges=prior_stale,
        judge_packet={}, judge_packet_ref="",
    )
    assert rcpt_c["rescore_mode"] == rem.POST_REGEN_JUDGE_RESCORE_FULL_PANEL
    assert rcpt_c["judges_rescored_count"] == 2
    assert {d["provider_key"] for d in rcpt_c["score_deltas"]} == {"gemini_pro", "openai_chatgpt"}


def test_patch_product_closeout_denied_x3_marks_fail_and_preserves_blockers(tmp_path: Path) -> None:
    from apps_rg.runtime.orchestration.patch_product_closeout import refresh_root_spine_bundle_after_patch

    refresh_root_spine_bundle_after_patch(
        tmp_path,
        x3_disposition="X3A_DENY_REROUTE",
        blockers=["producer-owned lane X3 is not an exact allow code for lanes [unify_narrative]"],
        decisive_reason="STRUCTURAL_BLOCK: unify_narrative soft-failed",
    )
    x3_doc = json.loads((tmp_path / "x3_disposition_receipt.json").read_text(encoding="utf-8"))
    assert x3_doc["status"] == "FAIL"
    assert x3_doc["proceed_to_runtime"] is False
    assert x3_doc["x3_disposition"] == "X3A_DENY_REROUTE"
    assert x3_doc["disposition"] == "X3A_DENY_REROUTE"
    assert "STRUCTURAL_BLOCK" in x3_doc["decisive_reason"]
    assert x3_doc["blockers"] == ["producer-owned lane X3 is not an exact allow code for lanes [unify_narrative]"]
    r4_doc = json.loads((tmp_path / "r4_run_manifest.json").read_text(encoding="utf-8"))
    assert r4_doc["status"] == "FAIL"
    assert r4_doc["outcome_authorized"] is False
    assert r4_doc["apps_rg_product_outcome_authorized"] is False


def test_patch_run_default_timeout_and_eval_json_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from apps_rg.runtime.orchestration.patch_run import DEFAULT_PATCH_LANE_TIMEOUT_SECONDS
    from resume_engine import cli as re_cli

    assert DEFAULT_PATCH_LANE_TIMEOUT_SECONDS >= 600.0
    monkeypatch.setattr(
        "apps_rg.__main__._evaluate_product_run",
        lambda path: {"status": "PASS", "x3_disposition": "X3D_ALLOW_FINISH", "pipeline_complete": True},
    )
    rc = re_cli.main(["eval", "--run-dir", str(tmp_path), "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "PASS"
    assert parsed["x3_disposition"] == "X3D_ALLOW_FINISH"


def test_rc6_voice_repair_auditor_orthogonal_on_openai_lane_and_parses_prose_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps_rg.runtime.providers import agy_cli_transport as act
    from apps_rg.runtime.providers.ide_cli_generation import resolve_ide_cli_generation_slug
    from apps_rg.runtime.sections import ExecutiveVoiceRepairAgent as evra

    seen_models: list[str] = []

    def _fake_run_agy(prompt: str, *, model: str, **kwargs):
        seen_models.append(model)
        return act.AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response='Here is the audit result:\n{"disposition": "PASS", "violated_facts": [], "repair_hint": ""}\nDone.',
            structured_output=None,
            usage={"input_tokens": 10, "output_tokens": 5},
            duration_seconds=1.0,
            conversation_id="c1",
        )

    monkeypatch.setattr(act, "run_agy", _fake_run_agy)
    monkeypatch.setattr("apps_rg.runtime.judges.x1d_ide_cli.uses_ide_cli_judges", lambda env: True)
    monkeypatch.setattr("apps_rg.runtime.judges.x1d_ide_cli.ide_cli_unavailable_reason", lambda env: "")

    res = evra._call_llm_repair("unify_narrative", "Audit this.", model=evra.DEFAULT_AUDITOR_MODEL)
    assert res == {"disposition": "PASS", "violated_facts": [], "repair_hint": ""}
    drafter_slug = resolve_ide_cli_generation_slug(evra.DEFAULT_REPAIR_MODEL)
    assert seen_models and seen_models[0] != drafter_slug


def test_rc1_generation_steps_down_medium_slug_when_effort_is_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps_rg.runtime.providers import agy_cli_transport as act
    from apps_rg.runtime.providers import ide_cli_generation as icg

    captured: dict[str, Any] = {}

    def _fake_run_agy(prompt: str, *, model: str, effort: str | None = None, **kwargs):
        captured["model"] = model
        captured["effort"] = effort
        return act.AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response='{"ok": true}',
            structured_output=None,
            usage={"input_tokens": 5, "output_tokens": 5},
            duration_seconds=0.5,
            conversation_id="c-low",
        )

    base = icg.resolve_ide_cli_generation_slug(icg.ide_cli_generation_models()[0])
    assert base.endswith("-medium")
    low_slug = base[:-7] + "-low"
    monkeypatch.setattr(icg, "ide_cli_generation_models", lambda: (*icg._generation_cfg().get("ide_models", ()), low_slug))
    monkeypatch.setattr(icg, "run_agy", _fake_run_agy)

    icg.call_ide_cli_generation(
        request={"model": base, "reasoning_effort": "low", "prompt": "select"},
        body={"model": base, "messages": [{"role": "user", "content": "select"}]},
        environ={"AGY_CLI_BIN": "/fake/agy"},
        agy_bin="/fake/agy",
    )
    assert captured["model"] == low_slug


def test_recovery_agent_temperature_respects_all_section_recipe_bounds(tmp_path: Path) -> None:
    from apps_rg.runtime.orchestration.ResumeRunRecoveryAgent import ResumeRunRecoveryAgent
    from apps_rg.runtime.sections.executive_summary.lane_constants import EXEC_SUMMARY_TEMP_RANGE
    from apps_rg.runtime.sections.ibm_bullets.lane_constants import IBM_TEMP_RANGE
    from apps_rg.runtime.sections.ibm_narrative_lane import IBM_NARRATIVE_TEMP_RANGE
    from apps_rg.runtime.sections.unify_bullets.lane_constants import UNIFY_TEMP_RANGE
    from apps_rg.runtime.sections.unify_narrative_lane import NARRATIVE_TEMP_RANGE

    bounds = {
        "executive_summary": EXEC_SUMMARY_TEMP_RANGE,
        "ibm_bullets": IBM_TEMP_RANGE,
        "ibm_narrative": IBM_NARRATIVE_TEMP_RANGE,
        "unify_bullets": UNIFY_TEMP_RANGE,
        "unify_narrative": NARRATIVE_TEMP_RANGE,
    }
    agent = ResumeRunRecoveryAgent(artifact_dir=tmp_path)
    for diag_msg in ("Non-authorizing X3 disposition (X3A_DENY_REROUTE)", "Failed X2 deterministic gate (1 violations)"):
        plan = agent._call_strategy_re_planner(
            {"failing_lanes_diagnostics": {lane: diag_msg for lane in bounds}}
        )
        for lane, (lo, hi) in bounds.items():
            temp = plan["lane_overrides"][lane]["temperature"]
            assert lo <= temp <= hi, f"{lane} recovery temp {temp} outside [{lo}, {hi}]"


def test_section_dispatch_timeouts_support_exec_summary_regen(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps_rg.runtime.providers.wallclock_http_guard import (
        resolve_section_lane_timeout_s,
        resolve_section_run_timeout_s,
    )

    monkeypatch.delenv("APPS_RG_SECTION_LANE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("APPS_RG_SECTION_RUN_TIMEOUT_SECONDS", raising=False)
    assert resolve_section_lane_timeout_s() >= 600.0
    assert resolve_section_run_timeout_s() >= 1200.0


def test_exec_summary_regen_dispatch_never_clamps_timeout_to_45s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace
    from apps_rg.runtime.sections import executive_summary_regen_dispatch as rd

    captured: dict[str, Any] = {}

    def _fake_generate(payload: dict[str, Any], **kwargs):
        captured["timeout_seconds"] = payload.get("timeout_seconds")
        return SimpleNamespace(
            runtime_generation_status="REAL_LLM",
            raw_model_output='{"resume_display_text": "Ok."}',
            provider_response={"ok": True},
            to_dict=lambda: {"runtime_generation_status": "REAL_LLM"},
        )

    monkeypatch.setattr(rd, "generate_section", _fake_generate)
    rd.budgeted_regen_call(
        {"model": "m", "provider": "external_claude", "timeout_seconds": 300},
        messages=[{"role": "user", "content": "Repair draft."}],
        phase="judge_regen",
        call_site="test_regen_timeout",
        cycle_index=0,
        attempt_index=0,
        artifact_dir=tmp_path,
    )
    assert captured["timeout_seconds"] == 300

    rd.budgeted_regen_call(
        {"model": "m", "provider": "external_claude"},
        messages=[{"role": "user", "content": "Repair draft."}],
        phase="judge_regen",
        call_site="test_regen_timeout_default",
        cycle_index=0,
        attempt_index=1,
        artifact_dir=tmp_path,
    )
    assert int(captured["timeout_seconds"]) >= 180


def test_sync_section_input_usage_ledger_claims_updates_claim_count_after_regen(tmp_path: Path) -> None:
    from apps_rg.runtime.sections.exec_summary_perf_sync_helpers import (
        sync_section_input_usage_ledger_claims,
    )

    initial_usage = {
        "schema_version": "section_input_usage_ledger_v1",
        "claim_support_summary": {
            "displayed_claim_count": 3,
            "claims_supported_by_selected_resume_facts": 3,
            "claims_with_targeting_input_in_source_fact_ids": 0,
            "claims_with_context_input_in_source_fact_ids": 0,
            "unsupported_claim_count": 0,
            "orphan_source_fact_id_count": 0,
        },
    }
    ledger_path = tmp_path / "section_input_usage_ledger.json"
    ledger_path.write_text(json.dumps(initial_usage), encoding="utf-8")

    four_claims = [
        {"claim_text": f"Sentence {i} grounded claim.", "source_fact_ids": [f"f{i}"]}
        for i in range(1, 5)
    ]
    updated = sync_section_input_usage_ledger_claims(
        artifact_dir=tmp_path,
        usage_doc=None,
        claim_ledger=four_claims,
        allowed_fact_ids={"f1", "f2", "f3", "f4"},
        write_json_fn=lambda p, d: p.write_text(json.dumps(d), encoding="utf-8"),
    )
    assert updated is not None
    assert updated["claim_support_summary"]["displayed_claim_count"] == 4
    assert updated["claim_support_summary"]["claims_supported_by_selected_resume_facts"] == 4
    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert persisted["claim_support_summary"]["displayed_claim_count"] == 4
