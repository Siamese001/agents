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
