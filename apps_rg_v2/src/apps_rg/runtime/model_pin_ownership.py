"""Fail-closed ownership audit and active manifest for cross-app LLM pins."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from apps_research.config.model_pins import active_model_manifest as research_model_manifest
from apps_rg.runtime.model_capabilities import ModelCapabilityError, assert_model_request_capabilities
from apps_rg.runtime.section_judge_policy import REQUIRED_JUDGE_PROVIDER_KEYS

_APPS_RG_ROOT = Path(__file__).resolve().parents[1]
PROVIDER_PROFILES_PATH = _APPS_RG_ROOT / "config" / "provider_profiles.yaml"
MODEL_CATALOG_PATH = _APPS_RG_ROOT.parents[1] / "config" / "model_catalog.json"

_PROVIDER_BY_KEY = {
    "anthropic_claude": "anthropic",
    "external_claude": "anthropic",
    "external_openai": "openai",
    "gemini_pro": "google_gemini",
    "google_gemini": "google_gemini",
    "openai_chatgpt": "openai",
}


@dataclass(frozen=True)
class ModelPinOwnershipViolation:
    code: str
    detail: str


def _load_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    profiles = yaml.safe_load(PROVIDER_PROFILES_PATH.read_text(encoding="utf-8")) or {}
    catalog = json.loads(MODEL_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(profiles, dict) or not isinstance(catalog, dict):
        raise ValueError("model pin ownership sources must be mappings")
    return profiles, catalog


def build_active_model_manifest() -> tuple[dict[str, Any], ...]:
    """Inventory requested model pins without becoming a routing authority."""
    profiles, _catalog = _load_sources()
    rows: list[dict[str, Any]] = []

    for profile_key, profile in (profiles.get("profiles") or {}).items():
        if not isinstance(profile, dict):
            continue
        model_by_section = profile.get("model_by_section")
        if not isinstance(model_by_section, dict):
            continue
        effort_by_section = profile.get("effort_by_section")
        effort_by_section = effort_by_section if isinstance(effort_by_section, dict) else {}
        provider_key = str(profile.get("provider_profile") or "")
        for section_id, model in model_by_section.items():
            rows.append(
                {
                    "app_id": "apps_rg",
                    "role_type": "generator",
                    "role_id": str(section_id),
                    "provider_key": provider_key,
                    "model": str(model),
                    "effort": str(effort_by_section.get(section_id) or ""),
                    "endpoint": (
                        "anthropic_messages"
                        if provider_key == "external_claude"
                        else "responses"
                    ),
                    "structured_output_required": True,
                    "owner": str(profile.get("pin_owner") or ""),
                    "review_after": str(profile.get("pin_review_after") or ""),
                    "proof_eligible": False,
                    "source": (
                        "apps_rg/config/provider_profiles.yaml:"
                        f"profiles.{profile_key}.model_by_section.{section_id}"
                    ),
                }
            )

        backup_models = profile.get("anthropic_limit_backup_model_by_section")
        backup_models = backup_models if isinstance(backup_models, dict) else {}
        backup_efforts = profile.get("anthropic_limit_backup_effort_by_section")
        backup_efforts = backup_efforts if isinstance(backup_efforts, dict) else {}
        for section_id, model in backup_models.items():
            rows.append(
                {
                    "app_id": "apps_rg",
                    "role_type": "generator_backup",
                    "role_id": f"anthropic_limit.{section_id}",
                    "provider_key": provider_key,
                    "model": str(model),
                    "effort": str(backup_efforts.get(section_id) or ""),
                    "endpoint": "responses",
                    "structured_output_required": True,
                    "owner": str(profile.get("pin_owner") or ""),
                    "review_after": str(profile.get("pin_review_after") or ""),
                    "proof_eligible": False,
                    "source": (
                        "apps_rg/config/provider_profiles.yaml:"
                        f"profiles.{profile_key}."
                        f"anthropic_limit_backup_model_by_section.{section_id}"
                    ),
                }
            )

    judge_governance = profiles.get("judge_model_governance") or {}
    judge_limits = ((profiles.get("runtime_limits") or {}).get("judge") or {})
    judge_effort_by_provider = {
        "gemini_pro": str(judge_limits.get("gemini_proof_thinking_level") or ""),
        "openai_chatgpt": str(judge_limits.get("openai_proof_reasoning_effort") or ""),
    }
    for tier, tier_models in (profiles.get("judge_models") or {}).items():
        if not isinstance(tier_models, dict):
            continue
        for provider_key, model in tier_models.items():
            rows.append(
                {
                    "app_id": "apps_rg",
                    "role_type": "proof_judge",
                    "role_id": f"{tier}.{provider_key}",
                    "provider_key": str(provider_key),
                    "model": str(model),
                    "effort": judge_effort_by_provider.get(str(provider_key), ""),
                    "endpoint": (
                        "responses"
                        if provider_key == "openai_chatgpt"
                        else "gemini_generate_content_v1beta"
                    ),
                    "structured_output_required": True,
                    "owner": str(judge_governance.get("owner") or ""),
                    "review_after": str(judge_governance.get("review_after") or ""),
                    "proof_eligible": bool(judge_governance.get("proof_eligible")),
                    "source": (
                        "apps_rg/config/provider_profiles.yaml:"
                        f"judge_models.{tier}.{provider_key}"
                    ),
                }
            )

    for selector_role, selector in (profiles.get("selector_models") or {}).items():
        if not isinstance(selector, dict):
            continue
        rows.append(
            {
                "app_id": "apps_rg",
                "role_type": str(selector.get("role") or ""),
                "role_id": str(selector_role),
                "provider_key": str(selector.get("provider_key") or ""),
                "model": str(selector.get("model") or ""),
                "effort": str(selector.get("reasoning_effort") or ""),
                "endpoint": (
                    "anthropic_messages"
                    if selector.get("provider_key") == "anthropic_claude"
                    else "chat_completions"
                ),
                "structured_output_required": True,
                "owner": str(selector.get("owner") or ""),
                "review_after": str(selector.get("review_after") or ""),
                "proof_eligible": bool(selector.get("proof_eligible")),
                "source": (
                    "apps_rg/config/provider_profiles.yaml:"
                    f"selector_models.{selector_role}.model"
                ),
            }
        )
        backup = selector.get("anthropic_limit_backup") or {}
        if isinstance(backup, dict) and backup:
            backup_provider_key = str(backup.get("provider_key") or "")
            rows.append(
                {
                    "app_id": "apps_rg",
                    "role_type": "advisory_selector_backup",
                    "role_id": f"anthropic_limit.{selector_role}",
                    "provider_key": backup_provider_key,
                    "model": str(backup.get("model") or ""),
                    "effort": str(backup.get("reasoning_effort") or ""),
                    "endpoint": (
                        "anthropic_messages"
                        if backup_provider_key == "anthropic_claude"
                        else "chat_completions"
                    ),
                    "structured_output_required": True,
                    "owner": str(selector.get("owner") or ""),
                    "review_after": str(selector.get("review_after") or ""),
                    "proof_eligible": False,
                    "source": (
                        "apps_rg/config/provider_profiles.yaml:"
                        f"selector_models.{selector_role}.anthropic_limit_backup.model"
                    ),
                }
            )

    for pin in research_model_manifest():
        rows.append(
            {
                "app_id": "apps_research",
                "role_type": (
                    "proof_judge" if pin.role.endswith("judge") else "generator"
                ),
                "role_id": pin.role,
                "provider_key": pin.provider_key,
                "model": pin.model,
                "effort": pin.reasoning_effort,
                "endpoint": (
                    "gemini_generate_content_v1beta"
                    if pin.provider == "google_gemini"
                    else "chat_completions"
                ),
                "structured_output_required": True,
                "owner": pin.owner,
                "review_after": pin.review_after,
                "proof_eligible": pin.role.endswith("judge"),
                "source": "apps_research/config/domain_contract",
            }
        )
    return tuple(rows)


def audit_model_pin_ownership() -> tuple[ModelPinOwnershipViolation, ...]:
    """Verify app-owned routing, role separation, and capability coverage."""
    profiles, catalog = _load_sources()
    violations: list[ModelPinOwnershipViolation] = []
    ownership = profiles.get("model_pin_ownership") or {}
    expected_ownership = {
        "routing_ssot": "apps_rg/config/provider_profiles.yaml",
        "shared_catalog_role": "capability_metadata_only",
        "environment_model_override_allowed": False,
        "receipt_identity_source": "observed_provider_response",
    }
    for key, expected in expected_ownership.items():
        if ownership.get(key) != expected:
            violations.append(
                ModelPinOwnershipViolation(
                    "ownership_contract_mismatch",
                    f"model_pin_ownership.{key} expected {expected!r}, got {ownership.get(key)!r}",
                )
            )

    if catalog.get("catalog_role") != "capability_metadata_only" or catalog.get(
        "routing_allowed"
    ) is not False:
        violations.append(
            ModelPinOwnershipViolation(
                "catalog_role_mismatch",
                "shared catalog must be capability_metadata_only with routing_allowed=false",
            )
        )
    compatibility = catalog.get("compatibility_policy") or {}
    if compatibility.get("generic_role_aliases_allowed") is not False or compatibility.get(
        "semantic_aliases_allowed"
    ) is not False:
        violations.append(
            ModelPinOwnershipViolation(
                "catalog_alias_policy_mismatch",
                "shared catalog must prohibit generic and semantic model aliases",
            )
        )
    for legacy_provider_bucket in ("openai", "anthropic", "gemini"):
        if legacy_provider_bucket in catalog:
            violations.append(
                ModelPinOwnershipViolation(
                    "generic_catalog_alias_present",
                    f"legacy provider alias bucket remains: {legacy_provider_bucket}",
                )
            )

    profile_map = profiles.get("profiles") or {}
    for profile_key, profile in profile_map.items():
        if not isinstance(profile, dict):
            continue
        capabilities = set(profile.get("capabilities") or [])
        provider_class = str(profile.get("provider_class") or "").lower()
        if "text_generation" in capabilities and provider_class in {"stub", "local_vllm", "local"}:
            violations.append(
                ModelPinOwnershipViolation(
                    "local_generator_forbidden",
                    f"generation profile {profile_key!r} uses forbidden provider_class={provider_class!r}",
                )
            )

    required = set(REQUIRED_JUDGE_PROVIDER_KEYS)
    for tier in ("enhanced", "standard"):
        actual = set(((profiles.get("judge_models") or {}).get(tier) or {}))
        if actual != required:
            violations.append(
                ModelPinOwnershipViolation(
                    "proof_judge_roster_mismatch",
                    f"judge_models.{tier} expected {sorted(required)!r}, got {sorted(actual)!r}",
                )
            )

    manifest = build_active_model_manifest()
    capability_models = catalog.get("models") or {}
    seen_roles: set[tuple[str, str, str]] = set()
    for row in manifest:
        identity = (str(row["app_id"]), str(row["role_type"]), str(row["role_id"]))
        if identity in seen_roles:
            violations.append(
                ModelPinOwnershipViolation(
                    "duplicate_manifest_role", f"duplicate active model role {identity!r}"
                )
            )
        seen_roles.add(identity)
        for required_field in (
            "provider_key",
            "model",
            "endpoint",
            "owner",
            "review_after",
            "source",
        ):
            if not str(row.get(required_field) or "").strip():
                violations.append(
                    ModelPinOwnershipViolation(
                        "manifest_metadata_missing",
                        f"{identity!r} is missing {required_field}",
                    )
                )
        model = str(row.get("model") or "")
        capability = capability_models.get(model)
        if not isinstance(capability, dict):
            violations.append(
                ModelPinOwnershipViolation(
                    "catalog_capability_missing", f"active model {model!r} is absent from catalog"
                )
            )
            continue
        expected_provider = _PROVIDER_BY_KEY.get(str(row.get("provider_key") or ""))
        if expected_provider and capability.get("provider") != expected_provider:
            violations.append(
                ModelPinOwnershipViolation(
                    "catalog_provider_mismatch",
                    f"{model!r} expected provider {expected_provider!r}, got {capability.get('provider')!r}",
                )
            )
        effort = str(row.get("effort") or "")
        try:
            resolved_capability = assert_model_request_capabilities(
                model,
                provider=str(expected_provider or capability.get("provider") or ""),
                endpoint=str(row.get("endpoint") or ""),
                reasoning_effort=effort or None,
                structured_output_required=bool(row.get("structured_output_required")),
                proof_required=bool(row.get("proof_eligible")),
            )
        except ModelCapabilityError as exc:
            violations.append(
                ModelPinOwnershipViolation(
                    "model_capability_mismatch",
                    f"{identity!r}: {exc}",
                )
            )
            resolved_capability = None
        if (
            resolved_capability
            and bool(row.get("proof_eligible"))
            and not resolved_capability.proof_eligible
        ):
            violations.append(
                ModelPinOwnershipViolation(
                    "model_proof_role_mismatch",
                    f"{identity!r} requires proof capability but catalog declares "
                    f"proof_eligible={resolved_capability.proof_eligible!r}",
                )
            )
        if row.get("role_type") in {
            "advisory_selector",
            "advisory_selector_backup",
        } and row.get("proof_eligible") is not False:
            violations.append(
                ModelPinOwnershipViolation(
                    "selector_proof_role_violation",
                    f"selector {identity!r} must be proof_eligible=false",
                )
            )

    return tuple(violations)


def assert_model_pin_ownership() -> None:
    violations = audit_model_pin_ownership()
    if violations:
        details = "\n".join(f"[{v.code}] {v.detail}" for v in violations)
        raise AssertionError(f"model pin ownership violations:\n{details}")


__all__ = [
    "MODEL_CATALOG_PATH",
    "PROVIDER_PROFILES_PATH",
    "ModelPinOwnershipViolation",
    "assert_model_pin_ownership",
    "audit_model_pin_ownership",
    "build_active_model_manifest",
]
