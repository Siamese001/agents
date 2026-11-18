"""Tests for OutreachModelRegistry SSOT and provider profiles configuration."""

from __future__ import annotations

import pytest

from apps_model_telemetry.pricing import get_model_pricing, price_usage
from apps_lic.runtime.model_registry import (
    OutreachModelPin,
    OutreachModelRegistry,
    OutreachModelRegistryError,
)


def test_model_registry_load_profiles() -> None:
    OutreachModelRegistry.clear_cache()
    profiles = OutreachModelRegistry.get_profiles()
    assert isinstance(profiles, dict)
    assert profiles.get("provider_profile_registry_id") == "outreach_engine::provider_profiles::v1"
    assert "profiles" in profiles


def test_model_registry_role_lookups() -> None:
    OutreachModelRegistry.clear_cache()
    pin = OutreachModelRegistry.get_model_pin("executive_outreach_generator")
    assert isinstance(pin, OutreachModelPin)
    assert pin.provider == "anthropic"
    assert pin.model == "claude-sonnet-5-5-high"
    assert pin.backup_provider == "openai"
    assert pin.backup_model == "gpt-5.6-luna"
    assert pin.reasoning_effort == "low"
    assert pin.thinking_budget_tokens == 2048
    assert pin.proof_eligible is False

    # Convenience accessors
    assert OutreachModelRegistry.get_model_for_role("executive_outreach_generator") == "claude-sonnet-5-5-high"
    assert OutreachModelRegistry.get_provider_for_role("executive_outreach_generator") == "anthropic"
    assert OutreachModelRegistry.get_effort_for_role("executive_outreach_generator") == "low"
    assert OutreachModelRegistry.get_thinking_budget_for_role("executive_outreach_generator") == 2048

    # Research, advisory selector, and dual X1D proof judge roles
    assert OutreachModelRegistry.get_model_for_role("company_brief_generation") == "gpt-5.6-terra"
    assert OutreachModelRegistry.get_model_for_role("handoff_judge") == "gemini-3.8-flash"
    assert OutreachModelRegistry.get_model_for_role("rubric_judge_panel") == "claude-sonnet-5-5-medium"
    assert OutreachModelRegistry.is_advisory_only_role("rubric_judge_panel") is True
    assert OutreachModelRegistry.is_proof_eligible_role("rubric_judge_panel") is False

    p_judge, s_judge = OutreachModelRegistry.get_x1d_proof_judge_pins()
    assert p_judge.model == "gemini-3.8-flash"
    assert p_judge.proof_eligible is True
    assert p_judge.reasoning_effort == "low"
    assert p_judge.thinking_budget_tokens == 1024
    assert s_judge.model == "gpt-5.6-luna"
    assert s_judge.proof_eligible is True
    assert s_judge.reasoning_effort == "low"
    assert s_judge.thinking_budget_tokens == 1024


def test_model_registry_cross_family_orthogonality_and_pricing() -> None:
    OutreachModelRegistry.clear_cache()
    # Primary drafter is anthropic (claude-sonnet-5) -> both Gemini and OpenAI X1D judges are orthogonal
    assert OutreachModelRegistry.verify_cross_family_orthogonality(
        "anthropic", "x1d_proof_judge_primary"
    ) is True
    assert OutreachModelRegistry.verify_cross_family_orthogonality(
        "anthropic", "x1d_proof_judge_secondary"
    ) is True
    # Advisory selector is never eligible for X1D proof judging
    assert OutreachModelRegistry.verify_cross_family_orthogonality(
        "openai", "rubric_judge_panel"
    ) is False
    # If backup drafter (openai / gpt-5.6-luna) drafted the sequence, OpenAI secondary judge is NOT orthogonal
    assert OutreachModelRegistry.verify_cross_family_orthogonality(
        "openai", "x1d_proof_judge_secondary"
    ) is False

    # Verify pricing resolution for all outreach roles and models
    for role_or_model in (
        "executive_outreach_generator",
        "rubric_judge_panel",
        "x1d_proof_judge_primary",
        "x1d_proof_judge_secondary",
        "claude-sonnet-5-5-high",
        "claude-sonnet-5-5-medium",
        "claude-sonnet-5",
        "gpt-5.6-luna",
        "claude-haiku-5-5",
        "gemini-3.8-flash",
    ):
        pricing, version = get_model_pricing(role_or_model)
        assert pricing is not None, f"Missing pricing for {role_or_model}"
        assert version is not None
        cost, _, _ = price_usage(role_or_model, {"prompt_tokens": 1000, "output_tokens": 250})
        assert cost is not None and cost > 0.0


def test_model_registry_unregistered_role_fails_closed() -> None:
    OutreachModelRegistry.clear_cache()
    with pytest.raises(OutreachModelRegistryError):
        OutreachModelRegistry.get_model_pin("unregistered_speculative_role")

    # Fallback default value if provided
    assert OutreachModelRegistry.get_model_for_role("unregistered_role", default="safe-default") == "safe-default"


def test_model_registry_validation_and_active_models() -> None:
    OutreachModelRegistry.clear_cache()
    active = OutreachModelRegistry.list_active_models()
    assert "executive_outreach_generator" in active
    assert "recruiter_outreach_generator" in active
    assert "rubric_judge_panel" in active
    assert "x1d_proof_judge_primary" in active
    assert "x1d_proof_judge_secondary" in active

    assert OutreachModelRegistry.validate_model("claude-sonnet-5-5-high") is True
    assert OutreachModelRegistry.validate_model("claude-sonnet-5-5-medium") is True
    assert OutreachModelRegistry.validate_model("gpt-5.6-luna") is True
    assert OutreachModelRegistry.validate_model("gemini-3.8-flash") is True
    assert OutreachModelRegistry.validate_model("unapproved_rogue_model_v9") is False


def test_model_registry_memoization() -> None:
    OutreachModelRegistry.clear_cache()
    doc1 = OutreachModelRegistry.get_profiles()
    doc2 = OutreachModelRegistry.get_profiles()
    assert doc1 is doc2  # Object identity via cached memory
