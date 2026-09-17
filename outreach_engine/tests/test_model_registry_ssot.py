"""Tests for OutreachModelRegistry SSOT and provider profiles configuration."""

from __future__ import annotations

import pytest

from apps_lic.runtime.model_registry import (
    OutreachModelPin,
    OutreachModelRegistry,
    OutreachModelRegistryError,
)


def test_model_registry_load_profiles():
    OutreachModelRegistry.clear_cache()
    profiles = OutreachModelRegistry.get_profiles()
    assert isinstance(profiles, dict)
    assert profiles.get("provider_profile_registry_id") == "outreach_engine::provider_profiles::v1"
    assert "profiles" in profiles


def test_model_registry_role_lookups():
    OutreachModelRegistry.clear_cache()
    pin = OutreachModelRegistry.get_model_pin("executive_outreach_generator")
    assert isinstance(pin, OutreachModelPin)
    assert pin.provider == "openai"
    assert pin.model == "gpt-5.6-luna"
    assert pin.reasoning_effort == "low"

    # Convenience accessors
    assert OutreachModelRegistry.get_model_for_role("executive_outreach_generator") == "gpt-5.6-luna"
    assert OutreachModelRegistry.get_provider_for_role("executive_outreach_generator") == "openai"
    assert OutreachModelRegistry.get_effort_for_role("executive_outreach_generator") == "low"

    # Research and judge roles
    assert OutreachModelRegistry.get_model_for_role("company_brief_generation") == "gpt-5.6-terra"
    assert OutreachModelRegistry.get_model_for_role("handoff_judge") == "gemini-3.8-flash"
    assert OutreachModelRegistry.get_model_for_role("rubric_judge_panel") == "claude-3-5-sonnet-20241022"


def test_model_registry_unregistered_role_fails_closed():
    OutreachModelRegistry.clear_cache()
    with pytest.raises(OutreachModelRegistryError):
        OutreachModelRegistry.get_model_pin("unregistered_speculative_role")

    # Fallback default value if provided
    assert OutreachModelRegistry.get_model_for_role("unregistered_role", default="safe-default") == "safe-default"


def test_model_registry_validation_and_active_models():
    OutreachModelRegistry.clear_cache()
    active = OutreachModelRegistry.list_active_models()
    assert "executive_outreach_generator" in active
    assert "recruiter_outreach_generator" in active
    assert "rubric_judge_panel" in active

    assert OutreachModelRegistry.validate_model("gpt-5.6-luna") is True
    assert OutreachModelRegistry.validate_model("claude-3-5-sonnet-20241022") is True
    assert OutreachModelRegistry.validate_model("unapproved_rogue_model_v9") is False


def test_model_registry_memoization():
    OutreachModelRegistry.clear_cache()
    doc1 = OutreachModelRegistry.get_profiles()
    doc2 = OutreachModelRegistry.get_profiles()
    assert doc1 is doc2  # Object identity via cached memory
