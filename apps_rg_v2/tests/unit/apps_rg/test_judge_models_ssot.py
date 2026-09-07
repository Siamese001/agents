"""W2 SSOT parity guard (plan apps-rg-config-ssot-consolidation): provider_profiles.yaml
``judge_models`` is the source-of-record for per-tier proof-judge models."""
from __future__ import annotations

from pathlib import Path

import yaml

from apps_rg.repository_layout import resolve_apps_rg_path
from apps_rg.runtime.judges.section_judge_profile import (
    SectionJudgeProfileSSOTError,
    _ENHANCED_PROFILE,
    _STANDARD_PROFILE,
)

_YAML = resolve_apps_rg_path(
    Path(__file__).resolve().parents[3], "config", "provider_profiles.yaml"
)


def _judge_models() -> dict:
    data = yaml.safe_load(_YAML.read_text(encoding="utf-8"))
    return (data or {}).get("judge_models") or {}


def test_judge_models_block_present_and_complete():
    jm = _judge_models()
    assert set(jm) >= {"enhanced", "standard"}
    for tier in ("enhanced", "standard"):
        assert set(jm[tier]) == {"gemini_pro", "openai_chatgpt"}
        assert jm[tier]["openai_chatgpt"] == "gpt-5.6-sol"


def test_code_profiles_do_not_carry_model_fallbacks():
    """Profiles can carry env metadata, but model IDs live in provider_profiles.yaml."""
    for profile in (*_ENHANCED_PROFILE.values(), *_STANDARD_PROFILE.values()):
        assert "profile_defaults" not in profile


def test_yaml_enhanced_covers_code_profile_providers():
    jm = _judge_models()["enhanced"]
    assert set(jm) >= set(_ENHANCED_PROFILE)


def test_yaml_standard_covers_code_profile_providers():
    jm = _judge_models()["standard"]
    assert set(jm) >= set(_STANDARD_PROFILE)


def test_resolver_sources_enhanced_gemini_from_yaml_when_env_absent():
    # W3 repoint: with no APPS_RG_*_JUDGE_MODEL_* env overrides, the resolver sources the model
    # from the YAML judge_models SSOT. enhanced/gemini_pro avoids the standard-only google_ai_pro
    # special-case, so the YAML candidate is the first non-forbidden one.
    from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model

    res = resolve_section_proof_judge_model("executive_summary", "gemini_pro", environ={})
    assert res.model_actual == _judge_models()["enhanced"]["gemini_pro"]
    assert res.model_source == "yaml_judge_models"
    assert not res.blocked


def test_resolver_rejects_anthropic_as_unknown_proof_provider():
    from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model

    res = resolve_section_proof_judge_model("unify_narrative", "anthropic_claude", environ={})
    assert res.model_actual == ""
    assert res.model_source == "unknown_provider"
    assert res.blocked
    assert res.proof_eligible_judge is False


def test_missing_judge_model_ssot_entry_fails_closed(monkeypatch):
    from apps_rg.runtime.judges import section_judge_profile as sjp

    monkeypatch.setattr(sjp, "_yaml_judge_models", lambda: {"enhanced": {}, "standard": {}})
    try:
        sjp.resolve_section_proof_judge_model("executive_summary", "openai_chatgpt", environ={})
    except SectionJudgeProfileSSOTError:
        return
    raise AssertionError("missing judge model SSOT entry did not fail closed")
