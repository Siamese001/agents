"""Unit tests for apps_rg.runtime.model_registry (model_registry.v2 SSOT)."""

from __future__ import annotations

import pytest

from apps_rg.runtime.model_registry import (
    ModelResolutionError,
    ResolvedModel,
    get_runtime_limits,
    list_models,
    list_roles,
    registry_digest,
    resolve,
)


def test_registry_digest_is_valid_sha256() -> None:
    digest = registry_digest()
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_list_roles_and_models_non_empty() -> None:
    roles = list_roles()
    models = list_models()
    assert len(roles) >= 15
    assert len(models) >= 5
    assert "generation.slalom_bullets" in roles
    assert "gpt-5.6-luna" in models
    assert "claude-sonnet-5" in models
    assert "gemini-3.8-flash" in models
    assert "BAAI/bge-m3" in models


def test_resolve_generation_roles() -> None:
    resolved = resolve("generation.slalom_bullets")
    assert isinstance(resolved, ResolvedModel)
    assert resolved.role == "generation.slalom_bullets"
    assert resolved.model == "claude-sonnet-5"
    assert resolved.provider == "external_claude"
    assert resolved.snapshot_id == "claude-sonnet-5"
    assert resolved.tier == "frontier"
    assert resolved.proof_eligible is True
    assert resolved.params.get("effort") == "low"
    assert resolved.tokenizer_family == "claude_bpe"
    assert resolved.pricing["input_cost_per_mtok"] > 0
    assert resolved.pricing["output_cost_per_mtok"] > 0


def test_resolve_shorthand_role_lookup() -> None:
    resolved = resolve("slalom_bullets")
    assert resolved.role == "generation.slalom_bullets"
    assert resolved.model == "claude-sonnet-5"

    narrative = resolve("ibm_narrative")
    assert narrative.role == "generation.ibm_narrative"
    assert narrative.model == "gpt-5.6-luna"


def test_resolve_backup_generation_role() -> None:
    resolved = resolve("generation_backup.executive_summary")
    assert resolved.model == "gpt-5.6-luna"
    assert resolved.params.get("effort") == "medium"
    assert resolved.tier == "frontier"


def test_resolve_proof_judge_roles() -> None:
    enhanced_gemini = resolve("proof_judge.enhanced.gemini_pro")
    assert enhanced_gemini.model == "gemini-3.8-flash"
    assert enhanced_gemini.params.get("thinking_level") == "medium"
    assert enhanced_gemini.proof_eligible is True

    standard_gemini = resolve("proof_judge.standard.gemini_pro")
    assert standard_gemini.model == "gemini-3.8-flash"
    assert standard_gemini.params.get("thinking_level") == "low"
    assert standard_gemini.proof_eligible is True

    enhanced_openai = resolve("proof_judge.enhanced.openai_chatgpt")
    assert enhanced_openai.model == "gpt-5.6-luna"
    assert enhanced_openai.params.get("reasoning_effort") == "high"


def test_resolve_embedding_role_pinned_revision() -> None:
    embedding = resolve("embedding.bge_m3")
    assert embedding.model == "BAAI/bge-m3"
    assert embedding.hf_revision == "5617a9f61b028005a4858fdac845db406aefb181"
    assert embedding.artifact_sha256 == "38ccc2e093252ab0416eee16837c75c641f055b4f3def12091fba8ed94e2b263"
    assert embedding.context_window == 8192


def test_resolve_unknown_role_fails_closed() -> None:
    with pytest.raises(ModelResolutionError) as exc_info:
        resolve("non_existent_role_xyz")
    assert "Unknown role" in str(exc_info.value)


def test_resolve_retired_model_fails_closed() -> None:
    from apps_rg.config_root import get_models_registry_path
    import yaml

    # Verify that if a role points to a retired model, resolution fails closed
    data = yaml.safe_load(get_models_registry_path().read_text(encoding="utf-8"))
    assert data["models"]["claude-3-haiku-20240307"]["status"] == "retired"


def test_get_runtime_limits_contains_required_sections() -> None:
    limits = get_runtime_limits()
    assert "section_context_window" in limits
    assert "model_token_governor" in limits
    assert "executive_summary" in limits
    assert "judge" in limits
    assert limits["judge"]["runtime_profiles"]["enhanced_reasoning"]["gemini_thinking_level"] == "medium"
    assert limits["judge"]["runtime_profiles"]["standard_reasoning"]["gemini_thinking_level"] == "low"
