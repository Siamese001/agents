"""P1 model-pin ownership gates for apps_research."""

from __future__ import annotations

import json

import pytest
import yaml

import apps_research.config.model_pins as model_pins
from apps_research.config.model_pins import (
    COMPANY_BRIEF_JUDGE_PROFILE_PATH,
    COMPANY_BRIEF_PROVIDER_PROFILE_PATH,
    active_model_manifest,
    AppsResearchModelPinError,
    apps_rg_handoff_judge_pin,
    company_brief_generation_pin,
)
from apps_rg.runtime.model_pin_ownership import MODEL_CATALOG_PATH


def test_company_brief_has_one_executable_fail_closed_lane() -> None:
    profile = yaml.safe_load(
        COMPANY_BRIEF_PROVIDER_PROFILE_PATH.read_text(encoding="utf-8")
    )
    assert set(profile["approved_model_lanes"]) == {"primary"}
    assert profile["lane_selection"] == {
        "strategy": "single_lane_fail_closed",
        "executable_lane_count": 1,
    }
    assert profile["gateway"]["error_handling"]["on_provider_error"] == "fail_closed"
    assert "fallback_1" not in profile["approved_model_lanes"]
    assert "fallback_cascade" not in profile


def test_provider_and_judge_profiles_are_the_only_requested_pin_sources() -> None:
    generation = company_brief_generation_pin()
    judge = apps_rg_handoff_judge_pin()
    judge_profile = yaml.safe_load(
        COMPANY_BRIEF_JUDGE_PROFILE_PATH.read_text(encoding="utf-8")
    )
    assert generation.role == "company_brief_generation"
    assert generation.owner == "apps_research.company_brief"
    assert generation.model == "gpt-5.6-terra"
    assert (generation.provider_key, generation.provider) == (
        "openai_chatgpt",
        "external_openai",
    )
    assert generation.reasoning_effort == "medium"
    assert judge.role == "apps_rg_handoff_judge"
    assert judge.model == "gemini-3.6-flash"
    assert (judge.provider_key, judge.provider) == ("gemini_pro", "google_gemini")
    assert judge.model == judge_profile["apps_rg_handoff_judge"]["model"]
    assert judge.reasoning_effort == "high"
    assert active_model_manifest() == (generation, judge)


def test_apps_research_rejects_claude_provider_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    original = model_pins._load_profile

    def drifted(path):
        payload = original(path)
        if path == COMPANY_BRIEF_PROVIDER_PROFILE_PATH:
            payload["approved_model_lanes"]["primary"].update(
                {"provider_key": "anthropic_claude", "provider": "external_claude"}
            )
        return payload

    monkeypatch.setattr(model_pins, "_load_profile", drifted)
    with pytest.raises(AppsResearchModelPinError, match="external_openai"):
        company_brief_generation_pin()


def test_apps_research_active_models_have_shared_capability_records() -> None:
    catalog = json.loads(MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
    capability_models = catalog["models"]
    for pin in active_model_manifest():
        assert pin.model in capability_models
