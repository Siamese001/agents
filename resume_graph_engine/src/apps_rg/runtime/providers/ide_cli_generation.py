"""IDE CLI generation transport for Anthropic-pinned section writers and selectors: keyless, model-pinned, fail-closed.

Selected by ``ide_cli_generation.transport`` in ``provider_profiles.yaml`` (env ``APPS_RG_GENERATION_TRANSPORT`` overrides).
When selected and the requested model is listed in ``ide_cli_generation.ide_models``, ``ExternalProvider`` invokes the
headless Antigravity CLI (``agy -p``) with API-key env vars stripped, session-only deny-all tool permissions, and
strict ``init.model == requested_model`` verification. Any transport or CLI error raises ``ProviderGatewayError``
so ``ExternalProvider.generate`` returns ``runtime_generation_status="BLOCKED"`` — never canned content.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from apps_rg.config_root import get_provider_profiles_path
from apps_rg.runtime.providers.agy_cli_transport import (
    AGY_CLI_ENV_VAR,
    AgyTransportError,
    ide_cli_ready,
    run_agy,
)
from apps_rg.runtime.providers.provider_gateway import ProviderGatewayError

IDE_CLI_GENERATION_MARKER = "ide-cli-session"
GENERATION_TRANSPORT_ENV = "APPS_RG_GENERATION_TRANSPORT"
GENERATION_TIMEOUT_ENV = "APPS_RG_IDE_CLI_GENERATION_TIMEOUT_S"
DEFAULT_GENERATION_TIMEOUT_S = 300
_TRANSPORTS = frozenset({"external_api", "ide_cli"})


@lru_cache(maxsize=4)
def _profiles_cached(path_str: str, mtime_ns: int) -> dict[str, Any]:
    import yaml  # noqa: PLC0415

    _ = mtime_ns
    data = yaml.safe_load(Path(path_str).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ProviderGatewayError(f"provider profiles is not a mapping: {path_str}")
    return data


def _generation_cfg() -> dict[str, Any]:
    path = get_provider_profiles_path()
    data = _profiles_cached(str(path), path.stat().st_mtime_ns)
    cfg = data.get("ide_cli_generation") or {}
    return cfg if isinstance(cfg, dict) else {}


def generation_transport(environ: Mapping[str, str] | None = None) -> str:
    if environ is None:
        override = str(os.environ.get(GENERATION_TRANSPORT_ENV) or "").strip().lower()
    elif GENERATION_TRANSPORT_ENV in environ:
        override = str(environ.get(GENERATION_TRANSPORT_ENV) or "").strip().lower()
    else:
        override = str(os.environ.get(GENERATION_TRANSPORT_ENV) or "").strip().lower()
    value = override or str(_generation_cfg().get("transport") or "external_api").strip().lower()
    if value not in _TRANSPORTS:
        raise ProviderGatewayError(
            f"unknown generation transport {value!r}; expected one of {sorted(_TRANSPORTS)}"
        )
    return value


def ide_cli_generation_models() -> tuple[str, ...]:
    raw = _generation_cfg().get("ide_models") or []
    if not isinstance(raw, list):
        return ()
    return tuple(str(item).strip() for item in raw if str(item).strip())


def resolve_ide_cli_generation_slug(model: str) -> str:
    """Resolve a configured section model pin through `ide_cli_generation.model_map` (identity if unmapped)."""
    pin = str(model or "").strip()
    mapping = _generation_cfg().get("model_map") or {}
    if isinstance(mapping, Mapping) and pin in mapping and str(mapping[pin]).strip():
        return str(mapping[pin]).strip()
    return pin


def _strip_outer_json_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", cleaned)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped
    return cleaned


def uses_ide_cli_generation(
    environ: Mapping[str, str] | None = None,
    *,
    model: str | None = None,
) -> bool:
    if generation_transport(environ) != "ide_cli":
        return False
    if model is None:
        return True
    return str(model).strip() in ide_cli_generation_models()


def _resolved_agy_bin(environ: Mapping[str, str] | None = None, agy_bin: str | None = None) -> str | None:
    if agy_bin:
        return str(agy_bin)
    var = str(_generation_cfg().get("cli_env_var") or AGY_CLI_ENV_VAR)
    if environ is not None and var in environ:
        val = str(environ.get(var) or "").strip()
        if val:
            return val
    val = str(os.environ.get(var) or "").strip()
    return val or None


def ide_cli_generation_unavailable_reason(
    environ: Mapping[str, str] | None = None,
    *,
    agy_bin: str | None = None,
) -> str:
    """Empty string when the headless CLI is configured and genuine; otherwise the reason."""
    ok, why = ide_cli_ready(_resolved_agy_bin(environ, agy_bin))
    return "" if ok else why


def _flatten_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if isinstance(block, str) and block.strip():
                parts.append(block.strip())
            elif isinstance(block, Mapping):
                text = str(block.get("text") or block.get("content") or "").strip()
                if text:
                    parts.append(text)
        return "\n\n".join(parts)
    if isinstance(value, Mapping):
        return str(value.get("text") or value.get("content") or "").strip()
    return ""


def build_ide_cli_generation_prompt(
    *,
    system: Any,
    messages: Any,
    fallback_prompt: str = "",
) -> str:
    sections: list[str] = []
    sys_text = _flatten_content(system)
    msg_sections: list[str] = []
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, Mapping):
                continue
            role = str(msg.get("role") or "user").strip().upper()
            body = _flatten_content(msg.get("content"))
            if body:
                msg_sections.append(f"[{role}]\n{body}")
    if sys_text and (msg_sections or sys_text != "Return compact JSON only."):
        sections.append(f"[SYSTEM INSTRUCTIONS]\n{sys_text}")
    sections.extend(msg_sections)
    if not msg_sections and fallback_prompt.strip():
        sections.append(f"[USER]\n{fallback_prompt.strip()}")
    if not msg_sections and not fallback_prompt.strip() and sys_text in {"", "Return compact JSON only."}:
        raise ProviderGatewayError("IDE CLI generation received an empty prompt")
    sections.append(
        "Return ONLY the requested output (raw JSON if JSON was requested, with no markdown code fences "
        "and no commentary). Do not invoke any tools."
    )
    return "\n\n".join(sections)


def _normalize_usage(raw_usage: Mapping[str, Any]) -> dict[str, Any]:
    in_tok = int(raw_usage.get("input_tokens") or 0)
    out_tok = int(raw_usage.get("output_tokens") or 0)
    total_tok = int(raw_usage.get("total_tokens") or (in_tok + out_tok))
    cache_read = int(raw_usage.get("cache_read_tokens") or raw_usage.get("cache_read_input_tokens") or 0)
    thinking_tok = int(raw_usage.get("thinking_tokens") or 0)
    return {
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "total_tokens": total_tok,
        "thinking_tokens": thinking_tok,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": cache_read,
    }


def _resolved_timeout_s(
    request_timeout_s: float | None,
    environ: Mapping[str, str] | None = None,
) -> int:
    env = os.environ if environ is None else environ
    raw = str(env.get(GENERATION_TIMEOUT_ENV) or os.environ.get(GENERATION_TIMEOUT_ENV) or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    if request_timeout_s is not None and request_timeout_s > 0:
        return max(10, int(request_timeout_s))
    return DEFAULT_GENERATION_TIMEOUT_S


def call_ide_cli_generation(
    *,
    request: Mapping[str, Any],
    body: Mapping[str, Any],
    environ: Mapping[str, str] | None = None,
    timeout_s: float | None = None,
    evidence: Any = None,
    agy_bin: str | None = None,
    downgrade_high_effort: bool = False,
) -> dict[str, Any]:
    """Execute one generation request via `agy -p` and return the ExternalProvider transport dict."""
    requested_model = str(body.get("model") or request.get("model") or "").strip()
    if not requested_model:
        raise ProviderGatewayError("IDE CLI generation requires a non-empty model slug")
    cli_slug = resolve_ide_cli_generation_slug(requested_model)
    effort_raw = str(request.get("reasoning_effort") or "").strip().lower()
    effort = effort_raw if effort_raw in {"low", "medium", "high", "xhigh"} else None
    if downgrade_high_effort and cli_slug.endswith("-high"):
        cli_slug = cli_slug[:-5] + "-medium"
    elif effort in {"low", "medium"} and cli_slug.endswith("-high"):
        stepped_slug = cli_slug[:-5] + f"-{effort}"
        if stepped_slug in ide_cli_generation_models():
            cli_slug = stepped_slug
    prompt = build_ide_cli_generation_prompt(
        system=body.get("system"),
        messages=body.get("messages"),
        fallback_prompt=str(request.get("prompt") or ""),
    )
    resolved_bin = _resolved_agy_bin(environ, agy_bin)
    effective_timeout = _resolved_timeout_s(timeout_s, environ)

    progress = request.get("progress_sink")
    progress = progress if isinstance(progress, dict) else None
    started_wall = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    if progress is not None:
        progress.update(
            {
                "started_at": started_wall,
                "first_byte_after_s": None,
                "last_progress_after_s": None,
                "chunk_count": 0,
                "raw_output_chars": 0,
                "completed": False,
                "transport": "ide_cli",
            }
        )

    try:
        res = run_agy(
            prompt,
            model=cli_slug,
            effort=effort,
            timeout_s=effective_timeout,
            agy_bin=resolved_bin,
        )
    except AgyTransportError as exc:
        raise ProviderGatewayError(f"IDE CLI generation failed: {exc}") from exc

    completed_after_s = round(time.monotonic() - t0, 4)
    text = _strip_outer_json_fence(str(res.response or ""))
    usage = _normalize_usage(res.usage)
    if evidence is not None:
        if hasattr(evidence, "mark_first_byte") and not getattr(evidence, "first_byte_received", False):
            evidence.mark_first_byte()
        if hasattr(evidence, "mark_sdk_response"):
            evidence.mark_sdk_response(
                observed_model=res.model_reported,
                provider_response_id=str(res.conversation_id or ""),
            )
        elif hasattr(evidence, "finish"):
            evidence.finish(
                observed_model=res.model_reported,
                provider_response_id=str(res.conversation_id or ""),
            )

    timing = {
        "started_at": started_wall,
        "first_byte_after_s": completed_after_s,
        "last_progress_after_s": completed_after_s,
        "completed_after_s": completed_after_s,
        "chunk_count": 1,
        "read_iterations": 1,
        "raw_output_chars": len(text),
        "stream": False,
        "transport": "ide_cli",
        "cli_duration_seconds": res.duration_seconds,
        "queue_wait_seconds": res.queue_wait_seconds,
    }
    if progress is not None:
        progress.update(
            {
                "first_byte_after_s": completed_after_s,
                "last_progress_after_s": completed_after_s,
                "completed_after_s": completed_after_s,
                "chunk_count": 1,
                "raw_output_chars": len(text),
                "completed": True,
            }
        )
    return {
        "text": text,
        "model": res.model_reported,
        "transport": "ide_cli",
        "conversation_id": res.conversation_id,
        "usage": usage,
        "transport_timing": timing,
        "raw_response": {
            "id": res.conversation_id,
            "conversation_id": res.conversation_id,
            "transport": "ide_cli",
            "model": res.model_reported,
            "model_requested": requested_model,
            "cli_slug": cli_slug,
            "usage": usage,
            "stop_reason": "end_turn",
            "stop_details": None,
            "stream": False,
            "transport_timing": timing,
            "content": [{"type": "text", "text": text}],
        },
    }


__all__ = [
    "GENERATION_TIMEOUT_ENV",
    "GENERATION_TRANSPORT_ENV",
    "IDE_CLI_GENERATION_MARKER",
    "build_ide_cli_generation_prompt",
    "call_ide_cli_generation",
    "generation_transport",
    "ide_cli_generation_models",
    "ide_cli_generation_unavailable_reason",
    "resolve_ide_cli_generation_slug",
    "uses_ide_cli_generation",
]
