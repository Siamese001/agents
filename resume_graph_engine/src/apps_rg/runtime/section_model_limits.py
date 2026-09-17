"""Provider-neutral section model limits and identity for apps_rg generation.

The generator model identity and runtime context budget are read from
``apps_rg/config/provider_profiles.yaml``. Environment variables may provide
credentials and endpoints, but they do not select apps_rg generator models or
runtime LLM budgets.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

# Provider-profile SSOT path (apps_rg/config/provider_profiles.yaml). This module
# lives at apps_rg/runtime/, so parents[1] == apps_rg.
_PROVIDER_PROFILES_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "config" / "provider_profiles.yaml"
)


class SectionModelSSOTError(RuntimeError):
    """Raised when apps_rg generation model SSOT cannot be loaded."""


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    for idx, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:idx]
    return line


def _yaml_scalar(value: str) -> Any:
    raw = value.strip()
    if raw in {"", "null", "Null", "NULL", "~"}:
        return None
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    try:
        if "." not in raw:
            return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _next_yaml_content(lines: list[tuple[int, str]], start_idx: int, parent_indent: int) -> str:
    for indent, content in lines[start_idx:]:
        if indent <= parent_indent:
            return ""
        return content
    return ""


def _parse_provider_profiles_without_yaml(text: str) -> dict[str, Any]:
    """Tiny parser for this repo-owned YAML shape when PyYAML is unavailable."""
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped_comment = _strip_yaml_comment(raw_line).rstrip()
        if not stripped_comment.strip():
            continue
        indent = len(stripped_comment) - len(stripped_comment.lstrip(" "))
        lines.append((indent, stripped_comment.strip()))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    for idx, (indent, content) in enumerate(lines):
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise SectionModelSSOTError(f"Invalid indentation in {_PROVIDER_PROFILES_PATH}")
        parent = stack[-1][1]
        if content.startswith("- "):
            if not isinstance(parent, list):
                raise SectionModelSSOTError(f"Invalid list entry in {_PROVIDER_PROFILES_PATH}: {content}")
            parent.append(_yaml_scalar(content[2:]))
            continue
        key, sep, value = content.partition(":")
        if not sep or not key.strip():
            raise SectionModelSSOTError(f"Invalid mapping entry in {_PROVIDER_PROFILES_PATH}: {content}")
        if not isinstance(parent, dict):
            raise SectionModelSSOTError(f"Invalid nested mapping in {_PROVIDER_PROFILES_PATH}: {content}")
        key = key.strip()
        value = value.strip()
        if value:
            parent[key] = _yaml_scalar(value)
            continue
        next_content = _next_yaml_content(lines, idx + 1, indent)
        child: Any = [] if next_content.startswith("- ") else {}
        parent[key] = child
        stack.append((indent, child))
    return root


def _provider_config() -> dict[str, Any]:
    try:
        import yaml  # noqa: PLC0415

        data = yaml.safe_load(_PROVIDER_PROFILES_PATH.read_text(encoding="utf-8"))
    except ImportError:
        data = _parse_provider_profiles_without_yaml(
            _PROVIDER_PROFILES_PATH.read_text(encoding="utf-8")
        )
    except (AttributeError, OSError, TypeError, UnicodeError, ValueError, yaml.YAMLError) as exc:
        raise SectionModelSSOTError(f"Cannot load apps_rg provider profile SSOT: {_PROVIDER_PROFILES_PATH}") from exc
    if not isinstance(data, dict):
        raise SectionModelSSOTError(f"Invalid apps_rg provider profile SSOT: {_PROVIDER_PROFILES_PATH}")
    return data


def _provider_profiles() -> dict:
    data = _provider_config()
    profiles = (data or {}).get("profiles") or {}
    if not isinstance(profiles, dict):
        raise SectionModelSSOTError(f"Missing profiles block in apps_rg provider profile SSOT: {_PROVIDER_PROFILES_PATH}")
    return profiles


def _runtime_limits() -> dict[str, Any]:
    data = _provider_config()
    limits = data.get("runtime_limits") or {}
    if not isinstance(limits, dict):
        raise SectionModelSSOTError(f"Missing runtime_limits block in apps_rg provider profile SSOT: {_PROVIDER_PROFILES_PATH}")
    return limits


def _runtime_limit_value(path: str) -> Any:
    current: Any = _runtime_limits()
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise SectionModelSSOTError(f"Missing runtime_limits.{path} in {_PROVIDER_PROFILES_PATH}")
        current = current[part]
    return current


def runtime_limit_int(path: str) -> int:
    value = _runtime_limit_value(path)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SectionModelSSOTError(f"runtime_limits.{path} must be an int in {_PROVIDER_PROFILES_PATH}") from exc


def runtime_limit_float(path: str) -> float:
    value = _runtime_limit_value(path)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SectionModelSSOTError(f"runtime_limits.{path} must be a float in {_PROVIDER_PROFILES_PATH}") from exc


def runtime_limit_str(path: str) -> str:
    value = _runtime_limit_value(path)
    if not isinstance(value, str) or not value.strip():
        raise SectionModelSSOTError(f"runtime_limits.{path} must be a non-empty string in {_PROVIDER_PROFILES_PATH}")
    return value.strip()


def runtime_limit_mapping(path: str) -> dict[str, Any]:
    value = _runtime_limit_value(path)
    if not isinstance(value, dict):
        raise SectionModelSSOTError(f"runtime_limits.{path} must be a mapping in {_PROVIDER_PROFILES_PATH}")
    return dict(value)


SECTION_MODEL_MAX_MODEL_LEN: Final[int] = runtime_limit_int("section_context_window")


def _profile_section_mapping(profile_key: str, mapping_key: str) -> dict[str, str]:
    """Return one normalized per-section mapping from a provider profile."""
    profiles = _provider_profiles()
    raw = (profiles.get(profile_key) or {}).get(mapping_key) or {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(k).strip().lower(): str(v).strip()
        for k, v in raw.items()
        if str(k).strip() and str(v).strip()
    }


def _required_section_value(
    profile_key: str,
    mapping_key: str,
    section_id: str | None,
) -> str:
    sid = str(section_id or "").strip().lower()
    if not sid:
        raise SectionModelSSOTError(
            f"Missing section_id for profiles.{profile_key}.{mapping_key} lookup in {_PROVIDER_PROFILES_PATH}"
        )
    by_section = _profile_section_mapping(profile_key, mapping_key)
    model = by_section.get(sid)
    if not model:
        raise SectionModelSSOTError(
            f"Missing profiles.{profile_key}.{mapping_key}.{sid} in {_PROVIDER_PROFILES_PATH}"
        )
    return model


def _required_section_model(profile_key: str, section_id: str | None) -> str:
    return _required_section_value(profile_key, "model_by_section", section_id)


def _anthropic_limit_preflight_active(environ: Mapping[str, str] | None) -> bool:
    # Lazy import avoids making provider routing a module-import prerequisite for
    # the model SSOT constants declared below.
    from apps_rg.runtime.providers.anthropic_limit_preflight import (  # noqa: PLC0415
        resolve_anthropic_limit_preflight_route,
    )

    return resolve_anthropic_limit_preflight_route(environ).active


def _provider_profile_value(provider_profile: object | None) -> str:
    if provider_profile is None:
        return ""
    return str(getattr(provider_profile, "value", provider_profile) or "").strip().lower()


def _selector_models() -> dict[str, dict[str, str]]:
    raw = _provider_config().get("selector_models") or {}
    if not isinstance(raw, dict):
        raise SectionModelSSOTError(f"selector_models must be a mapping in {_PROVIDER_PROFILES_PATH}")
    out: dict[str, dict[str, str]] = {}
    for selector_role, value in raw.items():
        if not isinstance(value, dict):
            raise SectionModelSSOTError(
                f"selector_models.{selector_role} must be a mapping in {_PROVIDER_PROFILES_PATH}"
            )
        provider_key = str(value.get("provider_key") or "").strip()
        model = str(value.get("model") or "").strip()
        reasoning_effort = str(value.get("reasoning_effort") or "").strip().lower()
        if not provider_key or not model:
            raise SectionModelSSOTError(
                f"selector_models.{selector_role} requires provider_key and model in {_PROVIDER_PROFILES_PATH}"
            )
        if reasoning_effort and reasoning_effort not in {
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise SectionModelSSOTError(
                f"selector_models.{selector_role} has invalid reasoning_effort "
                f"{reasoning_effort!r} in {_PROVIDER_PROFILES_PATH}"
            )
        if provider_key == "openai_chatgpt" and not reasoning_effort:
            raise SectionModelSSOTError(
                f"selector_models.{selector_role} requires reasoning_effort for OpenAI "
                f"in {_PROVIDER_PROFILES_PATH}"
            )
        backup = value.get("anthropic_limit_backup") or {}
        if not isinstance(backup, dict):
            raise SectionModelSSOTError(
                f"selector_models.{selector_role}.anthropic_limit_backup must be a mapping "
                f"in {_PROVIDER_PROFILES_PATH}"
            )
        backup_provider_key = str(backup.get("provider_key") or "").strip()
        backup_model = str(backup.get("model") or "").strip()
        backup_effort = str(backup.get("reasoning_effort") or "").strip().lower()
        if backup and (not backup_provider_key or not backup_model):
            raise SectionModelSSOTError(
                f"selector_models.{selector_role}.anthropic_limit_backup requires provider_key "
                f"and model in {_PROVIDER_PROFILES_PATH}"
            )
        if backup_effort and backup_effort not in {
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise SectionModelSSOTError(
                f"selector_models.{selector_role}.anthropic_limit_backup has invalid "
                f"reasoning_effort {backup_effort!r} in {_PROVIDER_PROFILES_PATH}"
            )
        if backup_provider_key == "openai_chatgpt" and not backup_effort:
            raise SectionModelSSOTError(
                f"selector_models.{selector_role}.anthropic_limit_backup requires "
                f"reasoning_effort for OpenAI in {_PROVIDER_PROFILES_PATH}"
            )
        out[str(selector_role).strip().lower()] = {
            "provider_key": provider_key,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "backup_provider_key": backup_provider_key,
            "backup_model": backup_model,
            "backup_reasoning_effort": backup_effort,
        }
    return out


def resolve_selector_provider_model(
    selector_role: str,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str, str]:
    """Return ``(provider_key, model, model_source)`` for an advisory pool selector."""
    role = str(selector_role or "").strip().lower()
    if not role:
        raise SectionModelSSOTError(f"Missing selector role for selector_models lookup in {_PROVIDER_PROFILES_PATH}")
    selectors = _selector_models()
    row = selectors.get(role)
    if row is None:
        raise SectionModelSSOTError(f"Missing selector_models.{role} in {_PROVIDER_PROFILES_PATH}")
    if (
        row["provider_key"] == "anthropic_claude"
        and _anthropic_limit_preflight_active(environ)
    ):
        if not row["backup_provider_key"] or not row["backup_model"]:
            raise SectionModelSSOTError(
                f"Missing selector_models.{role}.anthropic_limit_backup in {_PROVIDER_PROFILES_PATH}"
            )
        return (
            row["backup_provider_key"],
            row["backup_model"],
            "apps_rg/config/provider_profiles.yaml:"
            f"selector_models.{role}.anthropic_limit_backup.model",
        )
    return (
        row["provider_key"],
        row["model"],
        f"apps_rg/config/provider_profiles.yaml:selector_models.{role}.model",
    )


def resolve_selector_reasoning_effort(
    selector_role: str,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return the explicit provider-native effort for an advisory selector."""
    role = str(selector_role or "").strip().lower()
    if not role:
        raise SectionModelSSOTError(
            f"Missing selector role for selector_models lookup in {_PROVIDER_PROFILES_PATH}"
        )
    selectors = _selector_models()
    row = selectors.get(role)
    if row is None:
        raise SectionModelSSOTError(
            f"Missing selector_models.{role} in {_PROVIDER_PROFILES_PATH}"
        )
    if (
        row["provider_key"] == "anthropic_claude"
        and _anthropic_limit_preflight_active(environ)
    ):
        if not row["backup_reasoning_effort"]:
            raise SectionModelSSOTError(
                f"Missing selector_models.{role}.anthropic_limit_backup.reasoning_effort "
                f"in {_PROVIDER_PROFILES_PATH}"
            )
        return row["backup_reasoning_effort"]
    return row["reasoning_effort"]


def selector_role_for_section(section_id: str, *, slot_kind: str | None = None) -> str:
    """Map a section/slot to the selector-model role in provider_profiles.yaml."""
    sid = str(section_id or "").strip().lower()
    kind = str(slot_kind or "").strip().lower()
    if sid == "competencies" and kind == "competencies":
        return "competencies_graph_pool_selector"
    if sid in {"slalom_bullets", "unify_bullets", "ibm_bullets", "insurtech_bullets", "ey_bullets"}:
        return "employment_bullet_pool_selector"
    raise SectionModelSSOTError(f"No selector model configured for section={sid!r} slot_kind={kind!r}")


def _ssot_model_by_section(profile_key: str = "external_claude_generator") -> dict[str, str]:
    """Per-section model pins from the provider-profiles SSOT."""
    return _profile_section_mapping(profile_key, "model_by_section")


def _ssot_effort_by_section(profile_key: str) -> dict[str, str]:
    """Per-section inference effort from the provider-profiles SSOT."""
    return {
        section_id: effort.lower()
        for section_id, effort in _profile_section_mapping(
            profile_key, "effort_by_section"
        ).items()
    }


def resolve_section_generation_effort(
    section_id: str | None,
    environ: Mapping[str, str] | None = None,
    *,
    provider_profile: object | None = None,
) -> str:
    """Resolve one proof-bearing section's provider-native inference effort."""
    sid = str(section_id or "").strip().lower()
    if not sid:
        raise SectionModelSSOTError(
            f"Missing section_id for generation effort resolution in {_PROVIDER_PROFILES_PATH}"
        )
    provider_value = _provider_profile_value(provider_profile)
    if provider_value:
        if provider_value == "external_claude":
            effort = _required_section_value(
                "external_claude_generator", "effort_by_section", sid
            )
        elif provider_value == "external_openai":
            primary = _ssot_effort_by_section("external_openai_generator")
            if sid in primary:
                effort = primary[sid]
            elif _anthropic_limit_preflight_active(environ):
                effort = _required_section_value(
                    "external_openai_generator",
                    "anthropic_limit_backup_effort_by_section",
                    sid,
                )
            else:
                raise SectionModelSSOTError(
                    f"Missing profiles.external_openai_generator.effort_by_section.{sid} "
                    f"and Anthropic-limit preflight is inactive in {_PROVIDER_PROFILES_PATH}"
                )
        else:
            raise SectionModelSSOTError(
                f"Unsupported generation provider_profile={provider_value!r} for section={sid!r}"
            )
        matches = [(provider_value, effort)]
    else:
        matches = [
        (profile_key, efforts[sid])
        for profile_key in ("external_claude_generator", "external_openai_generator")
        for efforts in (_ssot_effort_by_section(profile_key),)
        if sid in efforts
        ]
    if len(matches) != 1:
        detail = "none" if not matches else ", ".join(profile for profile, _effort in matches)
        raise SectionModelSSOTError(
            f"Generation effort for section={sid!r} must resolve exactly once; found {detail} "
            f"in {_PROVIDER_PROFILES_PATH}"
        )
    effort = matches[0][1]
    if effort not in {"low", "medium", "high", "xhigh"}:
        raise SectionModelSSOTError(
            f"Invalid generation effort {effort!r} for section={sid!r} in {_PROVIDER_PROFILES_PATH}"
        )
    return effort


def resolve_section_generation_model(
    section_id: str | None,
    environ: Mapping[str, str] | None = None,
    *,
    provider_profile: object | None = None,
) -> str:
    """THE single resolver for the apps_rg per-section generator model (SSOT-backed).

    Every apps_rg generation dispatch MUST route the model through this function so the
    provider request carries the per-section model and no other source can win.

    Missing/unknown section ids fail closed. Provider-level default models are intentionally not
    supported for proof-bearing apps_rg lanes.
    """
    sid = str(section_id or "").strip().lower()
    if not sid:
        raise SectionModelSSOTError(f"Missing section_id for generation model resolution in {_PROVIDER_PROFILES_PATH}")

    provider_value = _provider_profile_value(provider_profile)
    if provider_value == "external_claude":
        return _required_section_model("external_claude_generator", sid)
    if provider_value == "external_openai":
        primary = _ssot_model_by_section("external_openai_generator")
        if sid in primary:
            return primary[sid]
        if _anthropic_limit_preflight_active(environ):
            return _required_section_value(
                "external_openai_generator",
                "anthropic_limit_backup_model_by_section",
                sid,
            )
        raise SectionModelSSOTError(
            f"Missing profiles.external_openai_generator.model_by_section.{sid} and "
            f"Anthropic-limit preflight is inactive in {_PROVIDER_PROFILES_PATH}"
        )
    if provider_value:
        raise SectionModelSSOTError(
            f"Unsupported generation provider_profile={provider_value!r} for section={sid!r}"
        )

    matches = [
        (profile_key, models[sid])
        for profile_key in ("external_claude_generator", "external_openai_generator")
        for models in (_ssot_model_by_section(profile_key),)
        if sid in models
    ]
    if len(matches) == 1:
        return matches[0][1]
    if len(matches) > 1:
        profiles = ", ".join(profile_key for profile_key, _model in matches)
        raise SectionModelSSOTError(
            f"Ambiguous generation model pin for section={sid!r}; found in profiles {profiles}"
        )
    raise SectionModelSSOTError(
        f"Missing generation model pin for section={sid!r} in {_PROVIDER_PROFILES_PATH}"
    )


def external_claude_generation_model(
    environ: Mapping[str, str] | None = None,
    *,
    section_id: str | None = None,
) -> str:
    """Claude generator model for one explicit section."""
    return resolve_section_generation_model(
        section_id, environ, provider_profile="external_claude"
    )


def external_openai_generation_model(
    environ: Mapping[str, str] | None = None,
    *,
    section_id: str | None = None,
) -> str:
    """OpenAI generator model from apps_rg provider_profiles.yaml.

    OpenAI generator model for one explicit section. Missing/unknown section ids fail closed.
    """
    return resolve_section_generation_model(
        section_id, environ, provider_profile="external_openai"
    )


def external_openai_generation_model_source(
    section_id: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """YAML path that resolved the OpenAI generation model for runtime receipts."""
    sid = str(section_id or "").strip().lower()
    if sid and sid in _ssot_model_by_section("external_openai_generator"):
        return (
            "apps_rg/config/provider_profiles.yaml:"
            f"profiles.external_openai_generator.model_by_section.{sid}"
        )
    if sid and _anthropic_limit_preflight_active(environ):
        backup = _profile_section_mapping(
            "external_openai_generator", "anthropic_limit_backup_model_by_section"
        )
        if sid in backup:
            return (
                "apps_rg/config/provider_profiles.yaml:profiles."
                f"external_openai_generator.anthropic_limit_backup_model_by_section.{sid}"
            )
    raise SectionModelSSOTError(
        f"Missing profiles.external_openai_generator.model_by_section.{sid or '<empty>'} in {_PROVIDER_PROFILES_PATH}"
    )


# Compatibility labels for legacy PA metadata. These are explicit lane pins, not resolver
# fallbacks; runtime dispatch must call the section-aware resolvers above.
SECTION_MODEL_ID: Final[str] = resolve_section_generation_model("competencies")
DEFAULT_EXTERNAL_CLAUDE_MODEL: Final[str] = resolve_section_generation_model("competencies")
DEFAULT_EXTERNAL_OPENAI_MODEL: Final[str] = external_openai_generation_model(section_id="unify_narrative")

__all__ = [
    "DEFAULT_EXTERNAL_CLAUDE_MODEL",
    "DEFAULT_EXTERNAL_OPENAI_MODEL",
    "SECTION_MODEL_ID",
    "SECTION_MODEL_MAX_MODEL_LEN",
    "SectionModelSSOTError",
    "external_claude_generation_model",
    "external_openai_generation_model",
    "external_openai_generation_model_source",
    "resolve_section_generation_effort",
    "resolve_section_generation_model",
    "resolve_selector_provider_model",
    "resolve_selector_reasoning_effort",
    "runtime_limit_float",
    "runtime_limit_mapping",
    "runtime_limit_int",
    "runtime_limit_str",
    "selector_role_for_section",
]
