from __future__ import annotations

import json
from tests.helpers import apps_rg_model_pins as pins

import apps_rg.runtime.providers.section_provider_call as subject
from apps_rg.runtime.providers.provider_contract import ProviderResult
from apps_rg.runtime.providers.provider_gateway import ProviderProfile
from apps_rg.runtime.sections.section_generation import build_section_request
from apps_model_telemetry.token_budget_governor import TokenBudgetReservation


class _CapturingGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        profile,
        compiled_prompt,
        *,
        token_budget: int,
        temperature: float = 0.7,
        timeout_seconds: int | float | None = None,
    ) -> ProviderResult:
        self.calls.append(
            {
                "profile": profile,
                "compiled_prompt": compiled_prompt,
                "token_budget": token_budget,
                "temperature": temperature,
                "timeout_seconds": timeout_seconds,
            }
        )
        return ProviderResult(
            provider_requested=str(getattr(profile, "value", profile)),
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="test-model",
            raw_model_output="ok",
            provider_response={"captured": True},
        )


class _PinnedModelGateway(_CapturingGateway):
    """Test double whose result binds to the selected model, like a real provider."""

    def generate(
        self,
        profile,
        compiled_prompt,
        *,
        token_budget: int,
        temperature: float = 0.7,
        timeout_seconds: int | float | None = None,
    ) -> ProviderResult:
        self.calls.append(
            {
                "profile": profile,
                "compiled_prompt": compiled_prompt,
                "token_budget": token_budget,
                "temperature": temperature,
                "timeout_seconds": timeout_seconds,
            }
        )
        return ProviderResult(
            provider_requested=str(getattr(profile, "value", profile)),
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model=pins.OPENAI_GENERATOR_MODEL,
            raw_model_output='{"result":"source-response"}',
            provider_response={"captured": True},
        )


def test_build_section_provider_gateway_registers_external_profiles() -> None:
    gateway = subject.build_section_provider_gateway(
        claude_model=pins.CLAUDE_GENERATOR_MODEL,
        openai_model=pins.OPENAI_GENERATOR_MODEL,
    )

    assert set(gateway.registered_profiles()) == {
        ProviderProfile.EXTERNAL_CLAUDE,
        ProviderProfile.EXTERNAL_OPENAI,
    }


def test_call_section_model_provider_threads_messages_and_overrides(monkeypatch) -> None:
    gateway = _CapturingGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )

    result = subject.call_section_model_provider(
        "claude",
        {
            "messages": [
                {"role": "system", "content": "System guard."},
                {"role": "user", "content": "Write one bullet."},
                {"role": "assistant", "content": ""},
                "invalid",
            ],
            "prompt_hash": "prompt-hash",
            "request_id": "request-1",
            "run_id": "payload-run",
            "_reasoning_section_lane": "competencies",
            "max_tokens": 44,
            "temperature": 0.91,
            "timeout_seconds": 7,
        },
        run_id="explicit-run",
        temperature_override=0.33,
    )

    assert result.runtime_generation_status == "REAL_LLM"
    call = gateway.calls[0]
    compiled = call["compiled_prompt"]
    assert call["profile"] == ProviderProfile.EXTERNAL_CLAUDE
    assert call["token_budget"] == 44
    assert call["temperature"] == 0.33
    assert call["timeout_seconds"] == 7
    assert compiled.compilation_hash == "prompt-hash"
    assert compiled.request_id == "request-1"
    assert compiled.run_id == "explicit-run"
    assert compiled.reasoning_effort == "low"
    assert [(b.role, b.content) for b in compiled.prompt_blocks] == [
        ("system", "System guard."),
        ("user", "Write one bullet."),
    ]


def test_call_section_model_provider_falls_back_to_prompt_and_max_output_tokens(
    monkeypatch,
) -> None:
    gateway = _CapturingGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )

    subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        {
            "messages": [{"role": "user", "content": ""}],
            "prompt": "Fallback prompt body.",
            "run_id": "payload-run",
            "_reasoning_section_lane": "unify_narrative",
            "max_output_tokens": 123,
        },
    )

    call = gateway.calls[0]
    compiled = call["compiled_prompt"]
    assert call["profile"] == ProviderProfile.EXTERNAL_OPENAI
    assert call["token_budget"] == 123
    assert call["temperature"] == 0.45
    assert call["timeout_seconds"] is None
    assert compiled.run_id == "payload-run"
    assert compiled.reasoning_effort == "medium"
    assert [(b.role, b.content) for b in compiled.prompt_blocks] == [
        ("user", "Fallback prompt body."),
    ]


def test_call_section_model_provider_explicit_token_budget_wins(monkeypatch) -> None:
    gateway = _CapturingGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )

    subject.call_section_model_provider(
        None,
        {
            "prompt": "Use defaults.",
            "_reasoning_section_lane": "competencies",
            "max_tokens": 10,
            "max_output_tokens": 20,
        },
        token_budget=77,
    )

    call = gateway.calls[0]
    assert call["profile"] == ProviderProfile.EXTERNAL_CLAUDE
    assert call["token_budget"] == 77


def test_call_section_model_provider_pins_openai_unify_narrative_model(monkeypatch) -> None:
    gateway = _CapturingGateway()
    captured: dict[str, object] = {}

    def fake_build(claude_model=None, openai_model=None):
        captured["claude_model"] = claude_model
        captured["openai_model"] = openai_model
        return gateway

    monkeypatch.setattr(subject, "build_section_provider_gateway", fake_build)

    subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        {
            "_reasoning_section_lane": "unify_narrative",
            "prompt": "Use unify narrative override.",
            "max_tokens": 10,
        },
    )

    assert captured["claude_model"] is None
    assert captured["openai_model"] == pins.OPENAI_GENERATOR_MODEL
    assert gateway.calls[0]["profile"] == ProviderProfile.EXTERNAL_OPENAI
    assert gateway.calls[0]["compiled_prompt"].reasoning_effort == "medium"


def test_call_section_model_provider_fails_closed_before_gateway_when_budget_blocks(monkeypatch, tmp_path) -> None:
    gateway = _CapturingGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )
    monkeypatch.setattr(
        subject,
        "reserve_apps_rg_model_tokens",
        lambda **_kwargs: TokenBudgetReservation(
            allowed=False,
            reason="RUN_RESERVED_TOKEN_CAP_EXCEEDED",
            estimated_input_tokens=100,
            reserved_output_tokens=20,
            reserved_total_tokens=120,
            prior_reserved_total_tokens=249_990,
            max_reserved_tokens_per_run=250_000,
            event={"decision": "BLOCKED"},
        ),
    )

    result = subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        {"prompt": "Would have been sent.", "_reasoning_section_lane": "unify_narrative"},
        artifact_dir=tmp_path,
    )

    assert result.runtime_generation_status == "BLOCKED"
    assert result.provider_attempted is False
    assert "token budget preflight blocked" in (result.exact_provider_error or "").lower()
    assert gateway.calls == []


def test_call_section_model_provider_fails_closed_on_malformed_budget_ledger(monkeypatch, tmp_path) -> None:
    gateway = _CapturingGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )
    (tmp_path / "external_model_token_reservations.jsonl").write_text("not-json\n", encoding="utf-8")

    result = subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        {"prompt": "Would have been sent.", "_reasoning_section_lane": "unify_narrative"},
        artifact_dir=tmp_path,
    )

    assert result.runtime_generation_status == "BLOCKED"
    assert "token budget ledger invalid" in (result.exact_provider_error or "").lower()
    assert gateway.calls == []


def test_idempotent_exact_response_reuse_skips_second_transport_and_reservation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPS_RG_EXACT_RESPONSE_REUSE", "1")
    gateway = _PinnedModelGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )
    payload = {
        "prompt": "Return the governed Unify narrative JSON.",
        "_reasoning_section_lane": "unify_narrative",
        "max_tokens": 101,
        "exact_response_reuse": True,
    }

    first = subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        payload,
        artifact_dir=tmp_path,
        run_id="run-w2-reuse",
    )
    second = subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        payload,
        artifact_dir=tmp_path,
        run_id="run-w2-reuse",
    )

    assert first.runtime_generation_status == "REAL_LLM"
    assert first.provider_response["exact_response_reuse"]["cache_store_status"] == "STORED"
    assert second.runtime_generation_status == "REAL_LLM"
    assert second.raw_model_output == first.raw_model_output
    assert second.provider_response["exact_response_reuse"]["reuse_mode"] == "IN_RUN_EXACT_RESPONSE_REUSE"
    assert second.provider_response["exact_response_reuse"]["transport_executed_this_invocation"] is False
    assert len(gateway.calls) == 1

    cache_text = (tmp_path / "external_model_exact_response_cache.jsonl").read_text(encoding="utf-8")
    assert "Return the governed" not in cache_text
    cache_row = json.loads(cache_text)
    assert cache_row["identity"]["run_id"] == "run-w2-reuse"
    reservations = (tmp_path / "external_model_token_reservations.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(reservations) == 1


def test_exact_response_reuse_does_not_cross_section_or_unmarked_sampling(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPS_RG_EXACT_RESPONSE_REUSE", "1")
    gateway = _PinnedModelGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )
    source = {
        "prompt": "Same prompt text.",
        "_reasoning_section_lane": "unify_narrative",
        "exact_response_reuse": "IDEMPOTENT",
    }
    subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        source,
        artifact_dir=tmp_path,
        run_id="run-w2-boundary",
    )
    subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        {**source, "_reasoning_section_lane": "ibm_narrative"},
        artifact_dir=tmp_path,
        run_id="run-w2-boundary",
    )
    subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        {key: value for key, value in source.items() if key != "exact_response_reuse"},
        artifact_dir=tmp_path,
        run_id="run-w2-boundary",
    )

    assert len(gateway.calls) == 3


def test_section_request_marks_one_shot_replay_idempotent_but_never_self_consistency(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPS_RG_EXACT_RESPONSE_REUSE", "1")
    _request, payload = build_section_request(
        messages=[{"role": "user", "content": "Generate a standard section."}],
        prompt_hash="one-shot-hash",
        input_payload_hash="payload-hash",
        model="gpt-5.4-mini-2026-03-17",
        provider_requested="external_openai",
        idempotent_replay_safe=True,
    )
    assert payload["exact_response_reuse"] == "IDEMPOTENT"

    gateway = _PinnedModelGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )
    self_consistency = {
        **payload,
        "_reasoning_section_lane": "unify_narrative",
        "anthropic_workload_kind": "SELF_CONSISTENCY",
        "sc_path_index": 0,
    }
    subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        self_consistency,
        artifact_dir=tmp_path,
        run_id="run-w2-samples",
    )
    subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        self_consistency,
        artifact_dir=tmp_path,
        run_id="run-w2-samples",
    )

    assert len(gateway.calls) == 2
    assert not (tmp_path / "external_model_exact_response_cache.jsonl").exists()


def test_exact_response_reuse_fails_closed_on_tampered_cache_before_gateway(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APPS_RG_EXACT_RESPONSE_REUSE", "1")
    gateway = _PinnedModelGateway()
    monkeypatch.setattr(
        subject,
        "build_section_provider_gateway",
        lambda claude_model=None, openai_model=None: gateway,
    )
    (tmp_path / "external_model_exact_response_cache.jsonl").write_text("not-json\n", encoding="utf-8")

    result = subject.call_section_model_provider(
        ProviderProfile.EXTERNAL_OPENAI,
        {
            "prompt": "Would otherwise be paid.",
            "_reasoning_section_lane": "unify_narrative",
            "exact_response_reuse": True,
        },
        artifact_dir=tmp_path,
        run_id="run-w2-corrupt",
    )

    assert result.runtime_generation_status == "BLOCKED"
    assert "reuse cache invalid" in (result.exact_provider_error or "").lower()
    assert gateway.calls == []
