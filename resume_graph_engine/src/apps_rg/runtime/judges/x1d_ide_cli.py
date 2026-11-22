"""IDE CLI transport for the X1D proof judges: keyless, model-pinned, fail-closed.

Selected by ``ide_cli_judging.transport`` in provider_profiles.yaml (env ``APPS_RG_JUDGE_TRANSPORT`` overrides).
When selected, ``resolve_x1d_provider_credentials`` returns ``IDE_CLI_SESSION_MARKER`` instead of an API key
(or an empty string with the reason when the CLI is not ready), and ``_call_gemini`` / ``_call_openai`` route to
``call_ide_cli_judge``. Every failure becomes a BLOCKED ``JudgeOutput``; no path returns a score without a
transport receipt (real token usage and a conversation id, enforced by the transport).
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from apps_rg.config_root import get_provider_profiles_path
from apps_rg.runtime.providers.agy_cli_transport import (
    AGY_CLI_ENV_VAR,
    AgyTransportError,
    ide_cli_ready,
    list_agy_models,
    run_agy,
)

if TYPE_CHECKING:
    from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput

IDE_CLI_SESSION_MARKER = "ide-cli-session"
JUDGE_TRANSPORT_ENV = "APPS_RG_JUDGE_TRANSPORT"
GENERATION_TRANSPORT_ENV = "APPS_RG_GENERATION_TRANSPORT"
JUDGE_TIMEOUT_ENV = "APPS_RG_IDE_CLI_JUDGE_TIMEOUT_S"
DEFAULT_JUDGE_TIMEOUT_S = 300
_TRANSPORTS = frozenset({"external_api", "ide_cli"})
# Sections with no configured writer (for example the whole-resume coherence judge) are treated as written by
# the pipeline's default generator maker, which is Anthropic.
DEFAULT_WRITER_MAKER = "anthropic"


class IdeCliJudgeConfigError(RuntimeError):
    """Raised when the IDE CLI judge configuration is missing or inconsistent (fail closed)."""


@lru_cache(maxsize=4)
def _profiles_cached(path_str: str, mtime_ns: int) -> dict[str, Any]:
    import yaml  # noqa: PLC0415

    _ = mtime_ns  # part of the cache key so edits to the file are picked up
    data = yaml.safe_load(Path(path_str).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise IdeCliJudgeConfigError(f"provider profiles is not a mapping: {path_str}")
    return data


def _profiles() -> dict[str, Any]:
    path = get_provider_profiles_path()
    return _profiles_cached(str(path), path.stat().st_mtime_ns)


def _judging_cfg() -> dict[str, Any]:
    cfg = _profiles().get("ide_cli_judging") or {}
    return cfg if isinstance(cfg, dict) else {}


def judge_transport(environ: Mapping[str, str] | None = None) -> str:
    if environ is None:
        override = str(os.environ.get(JUDGE_TRANSPORT_ENV) or "").strip().lower()
    elif JUDGE_TRANSPORT_ENV in environ:
        override = str(environ.get(JUDGE_TRANSPORT_ENV) or "").strip().lower()
    else:
        override = str(os.environ.get(JUDGE_TRANSPORT_ENV) or "").strip().lower()
    value = override or str(_judging_cfg().get("transport") or "external_api").strip().lower()
    if value not in _TRANSPORTS:
        raise IdeCliJudgeConfigError(f"unknown judge transport {value!r}; expected one of {sorted(_TRANSPORTS)}")
    return value


def uses_ide_cli_judges(environ: Mapping[str, str] | None = None) -> bool:
    return judge_transport(environ) == "ide_cli"


def ide_cli_unavailable_reason(environ: Mapping[str, str] | None = None) -> str:
    """Empty string when the headless CLI is configured and genuine; otherwise the reason."""
    env = os.environ if environ is None else environ
    var = str(_judging_cfg().get("cli_env_var") or AGY_CLI_ENV_VAR)
    ok, why = ide_cli_ready(str(env.get(var) or "") or None)
    return "" if ok else why


def lane_writer_model(section_id: str) -> str | None:
    for profile in (_profiles().get("profiles") or {}).values():
        by_section = (profile or {}).get("model_by_section") or {}
        if section_id in by_section:
            return str(by_section[section_id])
    return None


def maker_of(model_id: str | None) -> str:
    m = str(model_id or "").strip().lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if m.startswith("gemini"):
        return "google"
    raise IdeCliJudgeConfigError(f"cannot determine the maker of writer model {model_id!r}")


def second_judge_model(section_id: str) -> tuple[str, str]:
    """Return (judge model, writer maker): the second judge never shares a maker with the lane's writer."""
    writer = lane_writer_model(section_id)
    maker = maker_of(writer) if writer else DEFAULT_WRITER_MAKER
    mapping = _judging_cfg().get("second_judge_by_writer_maker") or {}
    model = mapping.get(maker) if isinstance(mapping, dict) else None
    if not model:
        raise IdeCliJudgeConfigError(
            f"ide_cli_judging.second_judge_by_writer_maker has no entry for writer maker {maker!r} (section {section_id})"
        )
    return str(model), maker


def _timeout_s() -> int:
    raw = str(os.environ.get(JUDGE_TIMEOUT_ENV) or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_JUDGE_TIMEOUT_S


def call_ide_cli_judge(
    *,
    prompt: str,
    model: str,
    input_hash: str,
    provider_key: str,
    artifact_base: Path | None = None,
    model_requested: str | None = None,
    judge_receipt: dict[str, Any] | None = None,
    reasoning_effort: str | None = None,
    attempt: int = 1,
    section_id: str | None = None,
    response_schema: dict[str, Any] | None = None,
    agy_bin: str | None = None,
) -> JudgeOutput:
    """Run one proof-judge call through the headless CLI and return a JudgeOutput (BLOCKED on any failure)."""
    from apps_rg.runtime.judges import executive_summary_x1d as x  # lazy: avoids an import cycle

    sid = section_id or "executive_summary"
    system_prompt = x.build_x1d_judge_system_prompt(compact=True, section_id=sid)
    full_prompt = (
        f"{system_prompt}\n\n{prompt}\n\n"
        "Return ONLY the JSON object that matches the required schema. Do not use any tools."
    )
    schema = response_schema or x.build_judge_response_schema()
    req_path = x._artifact_path(provider_key, "provider_request", artifact_base=artifact_base)
    x._write_artifact(
        req_path,
        {
            "transport": "ide_cli",
            "provider_key": provider_key,
            "section_id": sid,
            "resolved_model": model,
            "model_requested": model_requested or model,
            "attempt": attempt,
            "input_hash": input_hash,
            "prompt_chars": len(full_prompt),
            "prompt_sha256": hashlib.sha256(full_prompt.encode("utf-8")).hexdigest(),
            "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode("utf-8")).hexdigest(),
            "blind_to_deterministic_gates": sid == "executive_summary",
            "prompt_has_deterministic_gate_summary": "deterministic_gate_summary" in full_prompt.lower(),
            "api_key_used": False,
        },
    )
    try:
        res = run_agy(full_prompt, model=model, json_schema=schema, timeout_s=_timeout_s(), agy_bin=agy_bin)
    except AgyTransportError as exc:
        blocked = x._make_blocked_output(
            provider_key,
            input_hash,
            "BLOCKED_PROVIDER_UNAVAILABLE",
            "BLOCKED_PROVIDER_UNAVAILABLE",
            f"IDE CLI judge call failed: {exc}",
            model_name=model,
        )
        blocked.transport = "ide_cli"
        return blocked
    raw_path = x._artifact_path(provider_key, "provider_response_raw", artifact_base=artifact_base)
    x._write_artifact(
        raw_path,
        {
            "transport": "ide_cli",
            "model_requested": res.model_requested,
            "model_reported": res.model_reported,
            "conversation_id": res.conversation_id,
            "usage": res.usage,
            "duration_seconds": res.duration_seconds,
            "queue_wait_seconds": res.queue_wait_seconds,
            "response": res.response,
            "structured_output": res.structured_output,
        },
    )
    text = json.dumps(res.structured_output) if isinstance(res.structured_output, dict) else res.response
    out = x._finish_judge_text_parse(
        provider_key=provider_key,
        input_hash=input_hash,
        model_name=res.model_reported,
        raw_path=raw_path,
        text=text,
        finish_reason=None,  # the transport already enforced status SUCCESS
        artifact_base=artifact_base,
        judge_receipt=judge_receipt,
        model_requested=model_requested or model,
        section_id=sid,
    )
    out.transport = "ide_cli"
    out.provider_name = f"Antigravity IDE CLI ({res.model_reported})"
    out.reasoning_effort = reasoning_effort
    out.usage = dict(res.usage)
    out.conversation_id = res.conversation_id
    return out


def pinned_ide_models_for_preflight(environ: Mapping[str, str] | None = None) -> dict[str, list[str]]:
    """Return pinned IDE models grouped by role (`judges`, `generation`) active under current transport settings."""
    env = os.environ if environ is None else environ
    data = _profiles()
    out: dict[str, list[str]] = {"judges": [], "generation": []}
    if uses_ide_cli_judges(env):
        jm = data.get("judge_models") or {}
        if isinstance(jm, dict):
            for tier_name in ("enhanced", "standard"):
                tier_cfg = jm.get(tier_name) or {}
                if isinstance(tier_cfg, dict):
                    pin = str(tier_cfg.get("gemini_pro") or "").strip()
                    if pin and pin not in out["judges"]:
                        out["judges"].append(pin)
        sec_map = _judging_cfg().get("second_judge_by_writer_maker") or {}
        if isinstance(sec_map, dict):
            for pin_val in sec_map.values():
                pin = str(pin_val or "").strip()
                if pin and pin not in out["judges"]:
                    out["judges"].append(pin)
    gen_cfg = data.get("ide_cli_generation") or {}
    if isinstance(gen_cfg, dict):
        gen_override = str(env.get(GENERATION_TRANSPORT_ENV) or "").strip().lower()
        gen_transport = gen_override or str(gen_cfg.get("transport") or "external_api").strip().lower()
        if gen_transport not in _TRANSPORTS:
            raise IdeCliJudgeConfigError(
                f"unknown generation transport {gen_transport!r}; expected one of {sorted(_TRANSPORTS)}"
            )
        if gen_transport == "ide_cli":
            model_map = gen_cfg.get("model_map") or {}
            for item in gen_cfg.get("ide_models") or []:
                raw_pin = str(item or "").strip()
                mapped = str(model_map.get(raw_pin) or raw_pin).strip() if isinstance(model_map, dict) else raw_pin
                if mapped and mapped not in out["generation"]:
                    out["generation"].append(mapped)
    return out


def verify_ide_cli_preflight(
    environ: Mapping[str, str] | None = None,
    *,
    agy_bin: str | None = None,
) -> dict[str, Any]:
    """Verify CLI sign-in and confirm every active IDE judge/generation pin is present in `agy models`."""
    env = os.environ if environ is None else environ
    pins_by_role = pinned_ide_models_for_preflight(env)
    required_pins: list[str] = []
    for role_pins in pins_by_role.values():
        for pin in role_pins:
            if pin not in required_pins:
                required_pins.append(pin)
    if not required_pins:
        return {
            "ide_cli_active": False,
            "pinned_models": {},
            "verified_models": [],
            "available_count": 0,
        }
    var = str(_judging_cfg().get("cli_env_var") or AGY_CLI_ENV_VAR)
    resolved_bin = str(agy_bin or env.get(var) or "")
    ok, reason = ide_cli_ready(resolved_bin or None)
    if not ok:
        raise IdeCliJudgeConfigError(f"IDE CLI preflight failed: {reason}")
    available = list_agy_models(resolved_bin)
    available_set = set(available)
    missing = [pin for pin in required_pins if pin not in available_set]
    if missing:
        raise IdeCliJudgeConfigError(
            f"IDE CLI preflight failed: pinned models missing from `agy models`: {missing} (available={available})"
        )
    return {
        "ide_cli_active": True,
        "cli_env_var": var,
        "pinned_models": pins_by_role,
        "verified_models": required_pins,
        "available_count": len(available),
    }


__all__ = [
    "GENERATION_TRANSPORT_ENV",
    "IDE_CLI_SESSION_MARKER",
    "IdeCliJudgeConfigError",
    "call_ide_cli_judge",
    "ide_cli_unavailable_reason",
    "judge_transport",
    "lane_writer_model",
    "maker_of",
    "pinned_ide_models_for_preflight",
    "second_judge_model",
    "uses_ide_cli_judges",
    "verify_ide_cli_preflight",
]
