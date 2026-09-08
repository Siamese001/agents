"""Section-tier proof judge model resolution (apps_rg only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from pathlib import Path

from apps_rg.runtime.model_capabilities import (
    ModelCapabilityError,
    assert_model_request_capabilities,
    try_model_capabilities,
)
from apps_rg.runtime.section_judge_policy import JudgeTier, get_section_judge_policy, normalize_section_id
from apps_rg.runtime.section_model_limits import runtime_limit_str

# Provider-profiles SSOT (apps_rg/config/provider_profiles.yaml). This module lives at
# apps_rg/runtime/judges/, so parents[2] == apps_rg. The YAML ``judge_models`` block is the
# SSOT-of-record for per-tier judge models.
_PROVIDER_PROFILES_PATH = Path(__file__).resolve().parents[2] / "config" / "provider_profiles.yaml"


class SectionJudgeProfileSSOTError(RuntimeError):
    """Raised when apps_rg judge-model SSOT cannot be loaded."""


def _yaml_judge_models() -> dict:
    """Per-tier judge models from provider_profiles.yaml ``judge_models``."""
    try:
        import yaml  # noqa: PLC0415

        data = yaml.safe_load(_PROVIDER_PROFILES_PATH.read_text(encoding="utf-8"))
        jm = (data or {}).get("judge_models") or {}
    except ImportError as exc:  # guardian: strict SSOT load; caller must see the broken source
        raise SectionJudgeProfileSSOTError(f"Cannot load apps_rg judge-model SSOT: {_PROVIDER_PROFILES_PATH}") from exc
    except (AttributeError, OSError, TypeError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise SectionJudgeProfileSSOTError(f"Cannot load apps_rg judge-model SSOT: {_PROVIDER_PROFILES_PATH}") from exc
    if not isinstance(jm, dict):
        raise SectionJudgeProfileSSOTError(f"Invalid judge_models block in {_PROVIDER_PROFILES_PATH}")
    return jm


def _tier_yaml_label(tier: JudgeTier) -> str:
    return "enhanced" if tier == JudgeTier.ENHANCED_REASONING else "standard"

def openai_chat_completions_eligible(model_id: str) -> bool:
    """Return exact catalog eligibility for the OpenAI Chat Completions endpoint."""
    capabilities = try_model_capabilities(model_id)
    return bool(
        capabilities
        and capabilities.provider == "openai"
        and capabilities.supports_endpoint("chat_completions")
    )

_SUPPORTED_PROVIDER_KEYS = frozenset({"gemini_pro", "openai_chatgpt"})
_ENHANCED_PROFILE = {provider_key: {} for provider_key in _SUPPORTED_PROVIDER_KEYS}
_STANDARD_PROFILE = {provider_key: {} for provider_key in _SUPPORTED_PROVIDER_KEYS}


@dataclass(frozen=True)
class SectionJudgeModelResolution:
    provider_key: str
    section_id: str
    judge_tier: str
    model_requested: str
    model_actual: str
    model_source: str
    model_tier: str
    reasoning_effort: str | None = None
    blocked: bool = False
    block_reason: str | None = None
    advisory_only: bool = False
    proof_eligible_judge: bool = False
    fallback_used: bool = False


def is_forbidden_proof_judge_model(model_id: str) -> bool:
    capabilities = try_model_capabilities(model_id)
    return capabilities is None or not capabilities.proof_eligible


def _model_tier_label(tier: JudgeTier, model_id: str) -> str:
    if is_forbidden_proof_judge_model(model_id):
        return "advisory_weak"
    if tier == JudgeTier.ENHANCED_REASONING:
        return "enhanced_reasoning"
    if tier == JudgeTier.BULLET_REWRITE_QUALITY:
        return "bullet_rewrite_quality"
    if tier == JudgeTier.STANDARD_REASONING:
        return "standard_reasoning"
    return "advisory_taxonomy"


def resolve_section_proof_judge_model(
    section_id: str,
    provider_key: str,
    environ: Mapping[str, str] | None = None,
) -> SectionJudgeModelResolution:
    """Resolve proof judge model for a section; fail closed on missing or weak tiers."""
    _ = environ
    sid = normalize_section_id(section_id)
    policy = get_section_judge_policy(sid)
    tier = policy.judge_tier
    if provider_key not in _SUPPORTED_PROVIDER_KEYS:
        return SectionJudgeModelResolution(
            provider_key=provider_key,
            section_id=sid,
            judge_tier=tier.value,
            model_requested="",
            model_actual="",
            model_source="unknown_provider",
            model_tier="unknown",
            blocked=True,
            block_reason=f"Unknown judge provider key: {provider_key}",
            proof_eligible_judge=False,
        )
    if provider_key not in policy.required_judge_providers:
        return SectionJudgeModelResolution(
            provider_key=provider_key,
            section_id=sid,
            judge_tier=tier.value,
            model_requested="",
            model_actual="",
            model_source="not_section_proof_provider",
            model_tier="advisory_or_blocked",
            blocked=True,
            block_reason=(
                f"Provider {provider_key} is not a proof judge for section={sid}; "
                "selector/advisory providers cannot satisfy X1D proof."
            ),
            advisory_only=True,
            proof_eligible_judge=False,
        )

    yaml_tier = _yaml_judge_models().get(_tier_yaml_label(tier)) or {}
    yaml_model = yaml_tier.get(provider_key) if isinstance(yaml_tier, dict) else None
    if not yaml_model:
        raise SectionJudgeProfileSSOTError(
            f"Missing judge_models.{_tier_yaml_label(tier)}.{provider_key} in {_PROVIDER_PROFILES_PATH}"
        )
    model_id = str(yaml_model)
    source = "yaml_judge_models"

    reasoning_effort: str | None = None
    if provider_key == "gemini_pro":
        reasoning_effort = runtime_limit_str("judge.gemini_proof_thinking_level")
    elif provider_key == "openai_chatgpt":
        reasoning_effort = runtime_limit_str("judge.openai_proof_reasoning_effort")

    provider, endpoint = {
        "gemini_pro": ("google_gemini", "gemini_generate_content_v1beta"),
        "openai_chatgpt": ("openai", "responses"),
    }[provider_key]
    try:
        assert_model_request_capabilities(
            model_id,
            provider=provider,
            endpoint=endpoint,
            reasoning_effort=reasoning_effort,
            structured_output_required=True,
            proof_required=policy.judge_required_for_proof,
        )
    except ModelCapabilityError as exc:
        return SectionJudgeModelResolution(
            provider_key=provider_key,
            section_id=sid,
            judge_tier=tier.value,
            model_requested=model_id,
            model_actual="",
            model_source=source,
            model_tier="blocked",
            reasoning_effort=reasoning_effort,
            blocked=True,
            block_reason=str(exc),
            proof_eligible_judge=False,
        )

    return SectionJudgeModelResolution(
        provider_key=provider_key,
        section_id=sid,
        judge_tier=tier.value,
        model_requested=model_id,
        model_actual=model_id,
        model_source=source,
        model_tier=_model_tier_label(tier, model_id),
        reasoning_effort=reasoning_effort,
        blocked=False,
        advisory_only=not policy.judge_required_for_proof,
        proof_eligible_judge=policy.judge_required_for_proof,
    )


__all__ = [
    "SectionJudgeModelResolution",
    "SectionJudgeProfileSSOTError",
    "is_forbidden_proof_judge_model",
    "openai_chat_completions_eligible",
    "resolve_section_proof_judge_model",
]
