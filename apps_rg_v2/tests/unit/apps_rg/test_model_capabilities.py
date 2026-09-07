"""SSOT contract tests for exact model capability metadata."""

import pytest

from apps_rg.runtime.model_capabilities import (
    ModelCapabilityError,
    assert_model_request_capabilities,
    model_capabilities,
)


def test_luna_generation_capabilities_are_exact() -> None:
    capability = assert_model_request_capabilities(
        "gpt-5.6-luna",
        provider="openai",
        endpoint="responses",
        reasoning_effort="medium",
        structured_output_required=True,
    )
    assert capability.temperature_parameter == "omit"
    assert capability.proof_eligible is False
    assert capability.max_output_tokens_parameter_for("responses") == "max_output_tokens"
    assert (
        capability.max_output_tokens_parameter_for("chat_completions")
        == "max_completion_tokens"
    )


def test_terra_decision_capabilities_are_exact_but_not_proof_eligible() -> None:
    capability = model_capabilities("gpt-5.6-terra")
    assert capability.endpoints == ("responses", "chat_completions")
    assert capability.reasoning_efforts == (
        "none",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    )
    assert capability.structured_output is True
    assert capability.proof_eligible is False
    assert (
        capability.max_output_tokens_parameter_for("chat_completions")
        == "max_completion_tokens"
    )
    assert capability.max_output_tokens_parameter_for("responses") == "max_output_tokens"


def test_sol_proof_judge_capabilities_are_exact() -> None:
    capability = assert_model_request_capabilities(
        "gpt-5.6-sol",
        provider="openai",
        endpoint="responses",
        reasoning_effort="high",
        structured_output_required=True,
        proof_required=True,
    )
    assert capability.proof_eligible is True


def test_claude_selector_and_generator_efforts_are_exact_but_not_proof_eligible() -> None:
    capability = model_capabilities("claude-sonnet-5")
    assert capability.endpoints == ("anthropic_messages",)
    assert capability.reasoning_efforts == ("low", "medium", "high", "xhigh")
    assert capability.temperature_parameter == "omit"
    assert capability.thinking_mode == "adaptive"
    assert capability.proof_eligible is False


def test_gemini_is_the_only_non_openai_proof_capability() -> None:
    capability = assert_model_request_capabilities(
        "gemini-3.6-flash",
        provider="google_gemini",
        endpoint="gemini_generate_content_v1beta",
        reasoning_effort="high",
        structured_output_required=True,
        proof_required=True,
    )
    assert capability.reasoning_efforts == ("low", "medium", "high")
    assert capability.temperature_parameter == "omit"
    assert capability.thinking_mode == "thinking_level"
    assert capability.proof_eligible is True


def test_unknown_or_invalid_capability_combinations_fail_closed() -> None:
    with pytest.raises(ModelCapabilityError, match="MODEL_CAPABILITY_NOT_REGISTERED"):
        model_capabilities("gpt-invented")
    with pytest.raises(ModelCapabilityError, match="MODEL_ENDPOINT_CAPABILITY_MISMATCH"):
        assert_model_request_capabilities(
            "gpt-5.6-sol",
            provider="openai",
            endpoint="anthropic_messages",
            proof_required=True,
        )
