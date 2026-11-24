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
    is_agy_model_quota_cooled_down,
    is_agy_quota_error,
    list_agy_models,
    mark_agy_model_quota_exhausted,
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
    from apps_rg.runtime.env_bootstrap import get_env_str

    if environ is None:
        override = str(get_env_str(JUDGE_TRANSPORT_ENV) or "").strip().lower()
    elif JUDGE_TRANSPORT_ENV in environ:
        override = str(environ.get(JUDGE_TRANSPORT_ENV) or "").strip().lower()
    else:
        override = str(get_env_str(JUDGE_TRANSPORT_ENV) or "").strip().lower()
    value = override or str(_judging_cfg().get("transport") or "external_api").strip().lower()
    if value not in _TRANSPORTS:
        raise IdeCliJudgeConfigError(f"unknown judge transport {value!r}; expected one of {sorted(_TRANSPORTS)}")
    return value


def uses_ide_cli_judges(environ: Mapping[str, str] | None = None) -> bool:
    return judge_transport(environ) == "ide_cli"


def ide_cli_unavailable_reason(environ: Mapping[str, str] | None = None) -> str:
    """Empty string when the headless CLI is configured and genuine; otherwise the reason."""
    from apps_rg.runtime.env_bootstrap import snapshot_process_env

    env = snapshot_process_env() if environ is None else environ
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
    from apps_rg.runtime.env_bootstrap import get_env_str

    raw = str(get_env_str(JUDGE_TIMEOUT_ENV) or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_JUDGE_TIMEOUT_S


def _slug_base(slug: str) -> str:
    s = str(slug or "").strip()
    for suf in ("-low", "-medium", "-high", "-xhigh", "-max"):
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def _step_judge_pin_for_effort(pin_model: str, norm_effort: str | None) -> tuple[str, str | None]:
    from apps_rg.runtime.model_capabilities import try_model_capabilities

    caps = try_model_capabilities(pin_model)
    allowed_efforts = tuple((caps.reasoning_efforts or ()) if caps is not None else ())
    if not norm_effort or (caps is not None and norm_effort not in allowed_efforts):
        return pin_model, None
    cli_slug = pin_model
    if norm_effort in {"low", "medium"} and cli_slug.endswith("-high"):
        cli_slug = f"{cli_slug[:-5]}-{norm_effort}"
    elif norm_effort == "low" and cli_slug.endswith("-medium"):
        cli_slug = f"{cli_slug[:-7]}-low"
    return cli_slug, norm_effort


def _governed_judge_quota_backups(section_id: str, provider_key: str, primary_pin: str) -> list[str]:
    from apps_rg.runtime.model_capabilities import try_model_capabilities
    from apps_rg.runtime.providers.ide_cli_generation import resolve_ide_cli_generation_slug

    cfg = _judging_cfg()
    writer_pin = lane_writer_model(section_id)
    writer_slug = resolve_ide_cli_generation_slug(writer_pin) if writer_pin else ""
    forbidden_bases = {_slug_base(primary_pin)}
    if writer_slug:
        forbidden_bases.add(_slug_base(writer_slug))
    raw_backups: list[Any] = []
    if provider_key == "gemini_pro":
        tier_key = "enhanced" if section_id == "executive_summary" else "standard"
        try:
            slot2_pin, _ = second_judge_model(section_id)
            if slot2_pin:
                forbidden_bases.add(_slug_base(slot2_pin))
        except IdeCliJudgeConfigError:
            pass
        by_tier = cfg.get("quota_backup_first_judge_by_tier") or {}
        if isinstance(by_tier, Mapping):
            raw_backups = list(by_tier.get(tier_key) or [])
    else:
        jm = _profiles().get("judge_models") or {}
        tier_key = "enhanced" if section_id == "executive_summary" else "standard"
        slot1_pin = str(((jm.get(tier_key) or {}) if isinstance(jm, Mapping) else {}).get("gemini_pro") or "")
        if slot1_pin:
            forbidden_bases.add(_slug_base(slot1_pin))
        maker = maker_of(writer_pin) if writer_pin else DEFAULT_WRITER_MAKER
        by_maker = cfg.get("quota_backup_second_judge_by_writer_maker") or {}
        if isinstance(by_maker, Mapping):
            raw_backups = list(by_maker.get(maker) or [])
    valid: list[str] = []
    for item in raw_backups:
        b_pin = str(item or "").strip()
        if not b_pin or _slug_base(b_pin) in forbidden_bases:
            continue
        caps = try_model_capabilities(b_pin)
        if caps is None or not caps.proof_eligible or not caps.supports_endpoint("ide_cli"):
            continue
        if b_pin not in valid:
            valid.append(b_pin)
    return valid


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
    norm_effort = str(reasoning_effort or "").strip().lower() or None
    if norm_effort not in {"low", "medium", "high", "xhigh", "max"}:
        norm_effort = None
    primary_slug, primary_eff = _step_judge_pin_for_effort(model, norm_effort)
    candidates: list[tuple[str, str | None, str]] = [(primary_slug, primary_eff, model)]
    for b_pin in _governed_judge_quota_backups(sid, provider_key, model):
        b_slug, b_eff = _step_judge_pin_for_effort(b_pin, norm_effort)
        if all(c[0] != b_slug for c in candidates):
            candidates.append((b_slug, b_eff, b_pin))
    ordered_candidates = [
        c for c in candidates if not is_agy_model_quota_cooled_down(c[0])
    ] + [
        c for c in candidates if is_agy_model_quota_cooled_down(c[0])
    ]
    cli_model, active_effort, _ = ordered_candidates[0]
    failover_from: str | None = primary_slug if cli_model != primary_slug else None
    req_path = x._artifact_path(provider_key, "provider_request", artifact_base=artifact_base)
    req_payload: dict[str, Any] = {
        "transport": "ide_cli",
        "provider_key": provider_key,
        "section_id": sid,
        "resolved_model": cli_model,
        "model_requested": model_requested or model,
        "reasoning_effort": active_effort,
        "attempt": attempt,
        "input_hash": input_hash,
        "prompt_chars": len(full_prompt),
        "prompt_sha256": hashlib.sha256(full_prompt.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode("utf-8")).hexdigest(),
        "blind_to_deterministic_gates": sid == "executive_summary",
        "prompt_has_deterministic_gate_summary": "deterministic_gate_summary" in full_prompt.lower(),
        "api_key_used": False,
    }
    if failover_from:
        req_payload["quota_failover_from"] = failover_from
    x._write_artifact(req_path, req_payload)
    res = None
    last_exc: AgyTransportError | None = None
    for idx_c, (cand_slug, cand_eff, _cand_pin) in enumerate(ordered_candidates):
        try:
            res = run_agy(
                full_prompt,
                model=cand_slug,
                json_schema=schema,
                effort=cand_eff,
                timeout_s=_timeout_s(),
                agy_bin=agy_bin,
            )
            if cand_slug != cli_model:
                failover_from = primary_slug
                cli_model = cand_slug
                active_effort = cand_eff
                req_payload["resolved_model"] = cli_model
                req_payload["reasoning_effort"] = active_effort
                req_payload["quota_failover_from"] = failover_from
                x._write_artifact(req_path, req_payload)
            break
        except AgyTransportError as exc:
            last_exc = exc
            if is_agy_quota_error(exc) and idx_c + 1 < len(ordered_candidates):
                mark_agy_model_quota_exhausted(cand_slug, str(exc))
                continue
            break
    if res is None:
        blocked = x._make_blocked_output(
            provider_key,
            input_hash,
            "BLOCKED_PROVIDER_UNAVAILABLE",
            "BLOCKED_PROVIDER_UNAVAILABLE",
            f"IDE CLI judge call failed: {last_exc}",
            model_name=model,
        )
        blocked.transport = "ide_cli"
        return blocked
    raw_path = x._artifact_path(provider_key, "provider_response_raw", artifact_base=artifact_base)
    raw_payload: dict[str, Any] = {
        "transport": "ide_cli",
        "model_requested": res.model_requested,
        "model_reported": res.model_reported,
        "conversation_id": res.conversation_id,
        "usage": res.usage,
        "duration_seconds": res.duration_seconds,
        "queue_wait_seconds": res.queue_wait_seconds,
        "response": res.response,
        "structured_output": res.structured_output,
    }
    if failover_from:
        raw_payload["quota_failover_from"] = failover_from
    x._write_artifact(raw_path, raw_payload)
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
    from apps_rg.runtime.env_bootstrap import snapshot_process_env

    env = snapshot_process_env() if environ is None else environ
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
    from apps_rg.runtime.env_bootstrap import snapshot_process_env

    env = snapshot_process_env() if environ is None else environ
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
