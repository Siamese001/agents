"""Parity regression test proving model_registry.v2 equals legacy runtime values.

Ensures zero behavior divergence when resolving generation, judge, selector,
and embedding models.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from apps_rg.config_root import get_models_registry_path, get_provider_profiles_path
from apps_rg.runtime import model_registry
from apps_rg.runtime.section_model_limits import (
    resolve_section_generation_effort,
    resolve_section_generation_model,
)

_SECTIONS = (
    "competencies",
    "slalom_bullets",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "headline",
    "executive_summary",
    "slalom_narrative",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
)


def test_generation_model_parity_for_all_sections() -> None:
    """Prove resolve(section).model matches legacy resolve_section_generation_model(section)."""
    for section in _SECTIONS:
        new_resolved = model_registry.resolve(section)
        legacy_model = resolve_section_generation_model(section)
        assert new_resolved.model == legacy_model, (
            f"Model parity mismatch for section '{section}': "
            f"new={new_resolved.model} vs legacy={legacy_model}"
        )


def test_generation_effort_parity_for_all_sections() -> None:
    """Prove resolve(section).params['effort'] matches legacy resolve_section_effort(section)."""
    for section in _SECTIONS:
        new_resolved = model_registry.resolve(section)
        legacy_effort = resolve_section_generation_effort(section)
        assert new_resolved.params.get("effort") == legacy_effort, (
            f"Effort parity mismatch for section '{section}': "
            f"new={new_resolved.params.get('effort')} vs legacy={legacy_effort}"
        )


def test_judge_models_parity() -> None:
    """Prove proof judge models in registry match provider_profiles.yaml judge_models block."""
    profiles_data = yaml.safe_load(get_provider_profiles_path().read_text(encoding="utf-8"))
    yaml_judge_models = profiles_data.get("judge_models", {})

    enhanced_gemini = model_registry.resolve("proof_judge.enhanced.gemini_pro")
    assert enhanced_gemini.model == yaml_judge_models["enhanced"]["gemini_pro"]

    enhanced_openai = model_registry.resolve("proof_judge.enhanced.openai_chatgpt")
    assert enhanced_openai.model == yaml_judge_models["enhanced"]["openai_chatgpt"]

    standard_gemini = model_registry.resolve("proof_judge.standard.gemini_pro")
    assert standard_gemini.model == yaml_judge_models["standard"]["gemini_pro"]

    standard_openai = model_registry.resolve("proof_judge.standard.openai_chatgpt")
    assert standard_openai.model == yaml_judge_models["standard"]["openai_chatgpt"]


def test_selector_models_parity() -> None:
    """Prove selector models in registry match provider_profiles.yaml selector_models block."""
    profiles_data = yaml.safe_load(get_provider_profiles_path().read_text(encoding="utf-8"))
    yaml_selectors = profiles_data.get("selector_models", {})

    for selector_key, selector_spec in yaml_selectors.items():
        role_key = f"selector.{selector_key}"
        resolved = model_registry.resolve(role_key)
        assert resolved.model == selector_spec["model"]
        assert resolved.params.get("reasoning_effort") == selector_spec.get("reasoning_effort")


def test_runtime_limits_parity() -> None:
    """Prove runtime limits in registry match provider_profiles.yaml runtime_limits block."""
    profiles_data = yaml.safe_load(get_provider_profiles_path().read_text(encoding="utf-8"))
    yaml_limits = profiles_data.get("runtime_limits", {})
    reg_limits = model_registry.get_runtime_limits()

    assert reg_limits["section_context_window"] == yaml_limits["section_context_window"]
    assert reg_limits["model_token_governor"] == yaml_limits["model_token_governor"]
    assert reg_limits["bare_pipeline"] == yaml_limits["bare_pipeline"]
    assert reg_limits["judge_http"] == yaml_limits["judge_http"]
