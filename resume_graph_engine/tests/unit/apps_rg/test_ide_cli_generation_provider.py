"""Wave 3 tests: faked-CLI tests for IDE CLI generation provider (shape, usage, wrong model, tool use, timeout, missing sign-in)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from apps_rg.runtime.providers import ide_cli_generation as icg
from apps_rg.runtime.providers.agy_cli_transport import AgyResult, AgyTransportError
from apps_rg.runtime.providers.external_provider import ExternalProvider
from apps_rg.runtime.providers.provider_gateway import ProviderGatewayError, ProviderProfile


@pytest.fixture
def ide_gen_env(monkeypatch):
    monkeypatch.setenv("APPS_RG_GENERATION_TRANSPORT", "ide_cli")
    monkeypatch.setattr(icg, "ide_cli_generation_unavailable_reason", lambda environ=None, agy_bin=None: "")


def _fake_agy_gen(monkeypatch, *, response_text=None, error=None, effort_sink=None):
    calls: list[dict] = []
    default_payload = json.dumps(
        {
            "executive_summary_sentences": [
                {"sentence_index": 1, "text": "Led 45 engineers delivering cloud AI modernization.", "source_fact_ids": ["bul_1"]}
            ],
            "claim_ledger": [{"sentence_index": 1, "source_fact_ids": ["bul_1"]}],
        }
    )

    def fake(prompt, *, model, json_schema=None, effort=None, timeout_s=600, agy_bin=None):
        calls.append({"prompt": prompt, "model": model, "effort": effort, "timeout_s": timeout_s})
        if effort_sink is not None:
            effort_sink.append(effort)
        if error:
            raise AgyTransportError(error)
        return AgyResult(
            model_requested=model,
            model_reported=model,
            status="SUCCESS",
            response=default_payload if response_text is None else response_text,
            structured_output=None,
            usage={
                "input_tokens": 12400,
                "output_tokens": 620,
                "thinking_tokens": 310,
                "cache_read_tokens": 8000,
                "total_tokens": 13330,
            },
            duration_seconds=18.4,
            conversation_id="conv-gen-001",
        )

    monkeypatch.setattr(icg, "run_agy", fake)
    return calls


def test_product_config_selects_ide_cli_for_sonnet_pins_and_keeps_luna_on_external(monkeypatch):
    monkeypatch.delenv("APPS_RG_GENERATION_TRANSPORT", raising=False)
    assert icg.generation_transport() == "ide_cli"
    assert icg.uses_ide_cli_generation(model="claude-sonnet-5-5-high") is True
    assert icg.uses_ide_cli_generation(model="claude-sonnet-5-5-medium") is True
    assert icg.uses_ide_cli_generation(model="gpt-5.6-luna") is False


def test_unknown_generation_transport_fails_closed(monkeypatch):
    monkeypatch.setenv("APPS_RG_GENERATION_TRANSPORT", "smoke_signal")
    with pytest.raises(ProviderGatewayError, match="unknown generation transport"):
        icg.generation_transport()


def test_successful_ide_cli_generation_returns_keyed_response_shape_and_real_usage(ide_gen_env, monkeypatch):
    calls = _fake_agy_gen(monkeypatch)
    prov = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
        model="claude-sonnet-5-5-high",
        environ={"APPS_RG_GENERATION_TRANSPORT": "ide_cli", "AGY_CLI_BIN": "/fake/agy"},
    )
    compiled = SimpleNamespace(
        reasoning_effort="medium",
        prompt_blocks=[
            SimpleNamespace(role="system", content="You are a resume writer."),
            SimpleNamespace(role="user", content="Write JSON."),
        ],
        anthropic_payload={
            "system": [{"type": "text", "text": "You are a resume writer.", "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": "Write JSON."}],
        },
        anthropic_cache_receipt_seed={"section_id": "executive_summary"},
    )
    res = prov.generate(compiled, token_budget=1800, timeout_seconds=120)
    expected_slug = icg.resolve_ide_cli_generation_slug("claude-sonnet-5-5-high")
    assert res.runtime_generation_status == "REAL_LLM"
    assert res.provider_attempted is True and res.provider_available is True
    assert res.exact_provider_error is None
    assert res.model == expected_slug
    parsed = json.loads(res.raw_model_output)
    assert parsed["executive_summary_sentences"][0]["source_fact_ids"] == ["bul_1"]

    tr = res.provider_response["transport_response"]
    assert tr["transport"] == "ide_cli"
    assert tr["conversation_id"] == "conv-gen-001"
    assert tr["raw_response"]["id"] == "conv-gen-001"
    assert tr["raw_response"]["model_requested"] == "claude-sonnet-5-5-high"
    assert tr["raw_response"]["cli_slug"] == expected_slug
    assert tr["raw_response"]["usage"]["input_tokens"] == 12400
    assert tr["raw_response"]["usage"]["output_tokens"] == 620
    assert tr["raw_response"]["usage"]["cache_read_input_tokens"] == 8000
    assert res.provider_response["anthropic_prompt_cache_transport"] == {
        "cache_directives_requested": True,
        "cache_directives_transmitted": False,
        "capability_source": "ide_cli_transport",
    }
    assert calls[0]["model"] == expected_slug
    assert "[SYSTEM INSTRUCTIONS]" in calls[0]["prompt"]
    assert "[USER]\nWrite JSON." in calls[0]["prompt"]


@pytest.mark.parametrize(
    "err",
    [
        "model mismatch: requested 'claude-sonnet-5-5-high', CLI reported 'gemini-3.8-flash-low'",
        "tool calls attempted despite deny-all settings: ['command']",
        "agy timed out after 300s",
        "agy exit=1, result=missing: not signed in",
        "non-JSON line in agy stream: 'corrupt'",
    ],
)
def test_every_cli_error_becomes_blocked_provider_result(ide_gen_env, monkeypatch, err):
    _fake_agy_gen(monkeypatch, error=err)
    prov = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
        model="claude-sonnet-5-5-medium",
        environ={"APPS_RG_GENERATION_TRANSPORT": "ide_cli", "AGY_CLI_BIN": "/fake/agy"},
    )
    compiled = SimpleNamespace(
        user_instruction="Write bullets",
    )
    res = prov.generate(compiled, token_budget=900, timeout_seconds=60)
    assert res.runtime_generation_status == "BLOCKED"
    assert res.provider_attempted is True
    assert res.provider_available is False
    assert res.raw_model_output == ""
    assert "IDE CLI generation failed" in (res.exact_provider_error or "")


def test_empty_cli_text_becomes_blocked_provider_result(ide_gen_env, monkeypatch):
    _fake_agy_gen(monkeypatch, response_text="   ")
    prov = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
        model="claude-sonnet-5-5-medium",
        environ={"APPS_RG_GENERATION_TRANSPORT": "ide_cli", "AGY_CLI_BIN": "/fake/agy"},
    )
    compiled = SimpleNamespace(user_instruction="Write bullets")
    res = prov.generate(compiled, token_budget=900, timeout_seconds=60)
    assert res.runtime_generation_status == "BLOCKED"
    assert res.raw_model_output == ""
    assert "empty text" in (res.exact_provider_error or "")


def test_empty_compiled_prompt_fails_closed_before_cli(ide_gen_env, monkeypatch):
    calls = _fake_agy_gen(monkeypatch)
    prov = ExternalProvider(
        provider_profile=ProviderProfile.EXTERNAL_CLAUDE,
        model="claude-sonnet-5-5-medium",
        environ={"APPS_RG_GENERATION_TRANSPORT": "ide_cli", "AGY_CLI_BIN": "/fake/agy"},
    )
    res = prov.generate(SimpleNamespace(), token_budget=900, timeout_seconds=60)
    assert res.runtime_generation_status == "BLOCKED"
    assert "empty prompt" in (res.exact_provider_error or "")
    assert calls == []
