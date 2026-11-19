"""Wave 2 tests: IDE CLI judge adapter, transport routing, writer-maker pairing, preflight, and fail-closed behaviour."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.judges import executive_summary_x1d as x
from apps_rg.runtime.judges import x1d_ide_cli as ide
from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
from apps_rg.runtime.providers.agy_cli_transport import (
    AgyResult,
    AgyTransportError,
    parse_models_output,
)
from apps_rg.runtime.section_judge_policy import get_section_judge_policy

GOOD_RESULT = {
    "score_scale": "0_to_5",
    "score": 4.6,
    "threshold": 4.0,
    "pass": True,
    "decisive_failure": False,
    "findings": ["Grounded in the allowed facts."],
    "cited_sentence_indexes": [1],
    "remediation_suggestions": [],
}


@pytest.fixture
def ide_on(monkeypatch):
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "ide_cli")
    monkeypatch.setattr(ide, "ide_cli_unavailable_reason", lambda environ=None: "")
    monkeypatch.setattr(
        "apps_rg.runtime.judges.executive_summary_x1d.ide_cli_unavailable_reason",
        ide.ide_cli_unavailable_reason,
        raising=False,
    )


def _fake_agy(monkeypatch, *, structured=None, error=None, model_reported=None):
    calls = []

    def fake(prompt, *, model, json_schema=None, effort=None, timeout_s=600, agy_bin=None):
        calls.append({"prompt": prompt, "model": model, "schema": json_schema})
        if error:
            raise AgyTransportError(error)
        return AgyResult(
            model_requested=model,
            model_reported=model_reported or model,
            status="SUCCESS",
            response=json.dumps(structured or GOOD_RESULT),
            structured_output=structured or GOOD_RESULT,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            duration_seconds=2.5,
            conversation_id="conv-123",
        )

    monkeypatch.setattr(ide, "run_agy", fake)
    return calls


# --- transport selection & policy ------------------------------------------------------------------------------


def test_product_config_selects_ide_cli(monkeypatch):
    monkeypatch.delenv("APPS_RG_JUDGE_TRANSPORT", raising=False)
    assert ide.judge_transport() == "ide_cli"


def test_env_override_wins_and_unknown_value_fails_closed(monkeypatch):
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "external_api")
    assert ide.judge_transport() == "external_api"
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "carrier_pigeon")
    with pytest.raises(ide.IdeCliJudgeConfigError):
        ide.judge_transport()


def test_every_proof_lane_requires_dual_panel_under_ide_cli(ide_on):
    for lane in (
        "headline",
        "executive_summary",
        "competencies",
        "slalom_bullets",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "slalom_narrative",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
    ):
        policy = get_section_judge_policy(lane)
        assert policy.required_judge_providers == ("gemini_pro", "openai_chatgpt")


def test_credentials_return_session_marker_when_cli_ready(ide_on):
    key, why = x.resolve_x1d_provider_credentials("gemini_pro", {})
    assert key == ide.IDE_CLI_SESSION_MARKER and why == ["ide_cli"]


def test_credentials_empty_with_reason_when_cli_not_ready(monkeypatch):
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "ide_cli")
    monkeypatch.setattr(ide, "ide_cli_unavailable_reason", lambda environ=None: "AGY_CLI_BIN is not set")
    key, why = x.resolve_x1d_provider_credentials("openai_chatgpt", {})
    assert key == "" and "AGY_CLI_BIN" in why[0]


def test_api_keys_in_environment_are_ignored_under_ide_transport(ide_on):
    key, _ = x.resolve_x1d_provider_credentials("gemini_pro", {"GOOGLE_API_KEY": "real-looking-key"})
    assert key == ide.IDE_CLI_SESSION_MARKER


# --- writer-maker pairing --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lane",
    [
        "headline",
        "executive_summary",
        "competencies",
        "slalom_bullets",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
    ],
)
def test_anthropic_written_lanes_get_non_anthropic_second_judge(lane):
    model, maker = ide.second_judge_model(lane)
    assert maker == "anthropic" and not model.startswith("claude")


@pytest.mark.parametrize(
    "lane",
    ["slalom_narrative", "unify_narrative", "ibm_narrative", "insurtech_narrative"],
)
def test_openai_written_lanes_get_non_openai_second_judge(lane):
    model, maker = ide.second_judge_model(lane)
    assert maker == "openai" and not model.startswith(("gpt", "o1", "o3"))


def test_section_without_configured_writer_defaults_to_anthropic_maker():
    model, maker = ide.second_judge_model("full_resume_coherence")
    assert maker == "anthropic" and not model.startswith("claude")


def test_resolution_pins_slot_one_to_argon_and_slot_two_by_maker(ide_on):
    from apps_rg.runtime.providers.ide_cli_generation import resolve_ide_cli_generation_slug

    one = resolve_section_proof_judge_model("executive_summary", "gemini_pro")
    two = resolve_section_proof_judge_model("executive_summary", "openai_chatgpt")
    exec_writer = resolve_ide_cli_generation_slug(ide.lane_writer_model("executive_summary") or "")
    assert not one.blocked and "argon" in one.model_actual and one.model_source == "yaml_judge_models"
    assert not two.blocked and two.model_actual != one.model_actual and two.model_actual != exec_writer
    assert "writer_maker=anthropic" in two.model_source
    nar_one = resolve_section_proof_judge_model("unify_narrative", "gemini_pro")
    nar = resolve_section_proof_judge_model("unify_narrative", "openai_chatgpt")
    nar_writer = resolve_ide_cli_generation_slug(ide.lane_writer_model("unify_narrative") or "")
    assert not nar.blocked and nar.model_actual != nar_one.model_actual and nar.model_actual != nar_writer
    assert "writer_maker=openai" in nar.model_source


def test_resolution_blocks_an_unregistered_second_judge(ide_on, monkeypatch):
    monkeypatch.setattr(ide, "second_judge_model", lambda sid: ("model-not-in-catalog", "anthropic"))
    monkeypatch.setattr("apps_rg.runtime.judges.x1d_ide_cli.second_judge_model", ide.second_judge_model)
    res = resolve_section_proof_judge_model("executive_summary", "openai_chatgpt")
    assert res.blocked and "MODEL_CAPABILITY_NOT_REGISTERED" in (res.block_reason or "")


# --- preflight against `agy models` ----------------------------------------------------------------------------


def test_parse_models_output_handles_spinner_frames():
    sample = (
        "\r⠋ Fetching available models...\r⠦ Fetching available models...\r"
        "gemini-4-argon-high            Gemini 4 Argon (High)\n"
        "gpt-oss-120b-medium            GPT-OSS 120B (Medium)\n"
    )
    assert parse_models_output(sample) == ["gemini-4-argon-high", "gpt-oss-120b-medium"]


def test_verify_ide_cli_preflight_passes_when_all_pins_present_and_fails_on_missing(monkeypatch):
    env = {
        "APPS_RG_JUDGE_TRANSPORT": "ide_cli",
        "APPS_RG_GENERATION_TRANSPORT": "ide_cli",
        "AGY_CLI_BIN": "/fake/agy",
    }
    monkeypatch.setattr(ide, "ide_cli_ready", lambda b=None: (True, ""))
    all_needed = sorted(
        {
            *ide.pinned_ide_models_for_preflight(env)["judges"],
            *ide.pinned_ide_models_for_preflight(env)["generation"],
        }
    )
    monkeypatch.setattr(ide, "list_agy_models", lambda b=None: list(all_needed))
    receipt = ide.verify_ide_cli_preflight(env)
    assert receipt["ide_cli_active"] is True
    assert set(receipt["verified_models"]) == set(all_needed)

    monkeypatch.setattr(ide, "list_agy_models", lambda b=None: all_needed[:-1])
    with pytest.raises(ide.IdeCliJudgeConfigError, match="missing from `agy models`"):
        ide.verify_ide_cli_preflight(env)


# --- the call itself -------------------------------------------------------------------------------------------


def test_good_call_is_model_backed_with_real_receipt_fields(ide_on, monkeypatch, tmp_path: Path):
    calls = _fake_agy(monkeypatch)
    out = x._call_gemini(
        ide.IDE_CLI_SESSION_MARKER,
        "JUDGE PROMPT",
        "gemini-4-argon-high",
        "hash1",
        "gemini_pro",
        artifact_base=tmp_path,
        thinking_level="high",
        section_id="executive_summary",
    )
    assert out.evaluator_mode == "MODEL_BACKED" and not out.provider_blocked
    assert out.transport == "ide_cli" and out.conversation_id == "conv-123"
    assert out.usage == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    assert out.model_name == "gemini-4-argon-high" and out.score == 4.6
    assert "Antigravity IDE CLI" in out.provider_name and out.score != 4.85 and out.score != 4.80
    assert calls[0]["model"] == "gemini-4-argon-high" and "JUDGE PROMPT" in calls[0]["prompt"]
    assert any(p.name.startswith("x1d_gemini_provider_request_") for p in tmp_path.iterdir())
    raw = next(p for p in tmp_path.iterdir() if "provider_response_raw" in p.name)
    assert json.loads(raw.read_text(encoding="utf-8"))["conversation_id"] == "conv-123"


def test_openai_slot_routes_to_ide_cli_too(ide_on, monkeypatch, tmp_path: Path):
    _fake_agy(monkeypatch)
    out = x._call_openai(
        ide.IDE_CLI_SESSION_MARKER,
        "JUDGE PROMPT",
        "gpt-oss-120b-medium",
        "hash2",
        "openai_chatgpt",
        artifact_base=tmp_path,
        section_id="executive_summary",
    )
    assert out.evaluator_mode == "MODEL_BACKED" and out.transport == "ide_cli" and out.model_name == "gpt-oss-120b-medium"


@pytest.mark.parametrize(
    "err",
    [
        "agy timed out after 300s",
        "tool calls attempted despite deny-all settings: ['write_file']",
        "model mismatch: requested 'a', CLI reported 'b'",
        "agy status=ERROR: boom",
    ],
)
def test_every_transport_failure_is_blocked_never_a_score(ide_on, monkeypatch, tmp_path: Path, err):
    _fake_agy(monkeypatch, error=err)
    out = x._call_gemini(
        ide.IDE_CLI_SESSION_MARKER,
        "P",
        "gemini-4-argon-high",
        "h",
        "gemini_pro",
        artifact_base=tmp_path,
        thinking_level="high",
        section_id="executive_summary",
    )
    assert out.provider_blocked and out.evaluator_mode == "BLOCKED_PROVIDER_UNAVAILABLE"
    assert out.score is None and out.pass_ is False and out.proof_eligible_judge is False
    assert "IDE CLI judge call failed" in (out.exact_provider_error or "")


def test_timeout_block_is_retriable_but_model_mismatch_is_not(ide_on, monkeypatch, tmp_path: Path):
    _fake_agy(monkeypatch, error="agy timed out after 300s")
    t = x._call_gemini(ide.IDE_CLI_SESSION_MARKER, "P", "m", "h", "gemini_pro", artifact_base=tmp_path, thinking_level="high")
    assert x._is_retriable_judge_output(t)
    _fake_agy(monkeypatch, error="model mismatch: requested 'a', CLI reported 'b'")
    m = x._call_gemini(ide.IDE_CLI_SESSION_MARKER, "P", "m", "h", "gemini_pro", artifact_base=tmp_path, thinking_level="high")
    assert not x._is_retriable_judge_output(m)


def test_unparseable_response_is_blocked_with_parse_status(ide_on, monkeypatch, tmp_path: Path):
    def fake(prompt, *, model, json_schema=None, effort=None, timeout_s=600, agy_bin=None):
        return AgyResult(model, model, "SUCCESS", "not json at all", None, {"total_tokens": 5}, 1.0, "c")

    monkeypatch.setattr(ide, "run_agy", fake)
    out = x._call_gemini(ide.IDE_CLI_SESSION_MARKER, "P", "m", "h", "gemini_pro", artifact_base=tmp_path, thinking_level="high")
    assert out.provider_blocked and out.score is None and out.evaluator_mode.startswith("BLOCKED")
