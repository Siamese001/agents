"""Keyless IDE CLI Transport for Clean-Slate Judge v3 (`<= 260L`)."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from apps_rg.config_root import get_provider_profiles_path
from apps_rg.runtime.judges.v3_section_judge import V3_JUDGE_SYSTEM_PROMPT, build_section_v3_response_schema
from apps_rg.runtime.providers.agy_cli_transport import (
    AGY_CLI_ENV_VAR, AgyTransportError, ide_cli_ready, is_agy_model_quota_cooled_down,
    is_agy_quota_error, list_agy_models, mark_agy_model_quota_exhausted, run_agy,
)
import yaml

if TYPE_CHECKING:
    from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput

IDE_CLI_SESSION_MARKER = "ide-cli-session"
JUDGE_TRANSPORT_ENV = "APPS_RG_JUDGE_TRANSPORT"
GENERATION_TRANSPORT_ENV = "APPS_RG_GENERATION_TRANSPORT"
JUDGE_TIMEOUT_ENV = "APPS_RG_IDE_CLI_JUDGE_TIMEOUT_S"
DEFAULT_JUDGE_TIMEOUT_S = 300
_TRANSPORTS = frozenset({"external_api", "ide_cli"})
DEFAULT_WRITER_MAKER = "anthropic"


class IdeCliJudgeConfigError(RuntimeError):
    """Raised when IDE CLI judge configuration is missing or inconsistent (fail closed)."""


@lru_cache(maxsize=4)
def _profiles_cached(path_str: str, mtime_ns: int) -> dict[str, Any]:
    _ = mtime_ns
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
    override = str((environ.get(JUDGE_TRANSPORT_ENV) if (environ is not None and JUDGE_TRANSPORT_ENV in environ) else get_env_str(JUDGE_TRANSPORT_ENV)) or "").strip().lower()
    value = override or str(_judging_cfg().get("transport") or "external_api").strip().lower()
    if value not in _TRANSPORTS:
        raise IdeCliJudgeConfigError(f"unknown judge transport {value!r}; expected {sorted(_TRANSPORTS)}")
    return value


def uses_ide_cli_judges(environ: Mapping[str, str] | None = None) -> bool:
    return judge_transport(environ) == "ide_cli"


def ide_cli_unavailable_reason(environ: Mapping[str, str] | None = None) -> str:
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


def actual_lane_writer_model(section_id: str, environ: Mapping[str, str] | None = None) -> str | None:
    raw_writer = lane_writer_model(section_id)
    if not raw_writer:
        return None
    env = os.environ if environ is None else environ
    gen_cfg = _profiles().get("ide_cli_generation") or {}
    if isinstance(gen_cfg, Mapping):
        gen_override = str(env.get(GENERATION_TRANSPORT_ENV) or "").strip().lower()
        gen_transport = gen_override or str(gen_cfg.get("transport") or "external_api").strip().lower()
        if gen_transport == "ide_cli":
            model_map = gen_cfg.get("model_map") or {}
            if isinstance(model_map, Mapping) and raw_writer in model_map:
                return str(model_map[raw_writer])
    return raw_writer


def maker_of(model_id: str | None) -> str:
    m = str(model_id or "").strip().lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if m.startswith("gemini"):
        return "google"
    raise IdeCliJudgeConfigError(f"cannot determine the maker of writer model {model_id!r}")


def _ide_family_token(slug: str | None) -> str:
    low = str(slug or "").strip().lower()
    for fam in ("neon", "carbon", "argon"):
        if fam in low.replace("_", "-").split("-") or low == fam:
            return fam
    return ""


def _collides_with_writer(judge_slug: str | None, writer_slug: str | None) -> bool:
    if not judge_slug or not writer_slug:
        return False
    if _slug_base(judge_slug) == _slug_base(writer_slug):
        return True
    jf, wf = _ide_family_token(judge_slug), _ide_family_token(writer_slug)
    return bool(jf and wf and jf == wf)


def second_judge_model(section_id: str) -> tuple[str, str]:
    writer = lane_writer_model(section_id)
    maker = maker_of(writer) if writer else DEFAULT_WRITER_MAKER
    actual_writer = actual_lane_writer_model(section_id)
    mapping = _judging_cfg().get("second_judge_by_writer_maker") or {}
    model = mapping.get(maker) if isinstance(mapping, dict) else None
    if model and actual_writer and _collides_with_writer(str(model), actual_writer) and isinstance(mapping, dict):
        alt = mapping.get(maker_of(actual_writer))
        if alt and not _collides_with_writer(str(alt), actual_writer):
            model = alt
    if not model:
        raise IdeCliJudgeConfigError(f"ide_cli_judging.second_judge_by_writer_maker missing writer maker {maker!r} ({section_id})")
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
    allowed = tuple((caps.reasoning_efforts or ()) if caps is not None else ())
    if not norm_effort or (caps is not None and norm_effort not in allowed):
        return pin_model, None
    cli_slug = f"{pin_model[:-5]}-medium" if (norm_effort == "medium" and pin_model.endswith("-high")) else pin_model
    return cli_slug, norm_effort


def _governed_judge_quota_backups(section_id: str, provider_key: str, primary_pin: str) -> list[str]:
    from apps_rg.runtime.model_capabilities import try_model_capabilities
    from apps_rg.runtime.providers.ide_cli_generation import resolve_ide_cli_generation_slug

    cfg = _judging_cfg()
    writer_pin = lane_writer_model(section_id)
    actual_writer = actual_lane_writer_model(section_id) or ""
    writer_slug = actual_writer or (resolve_ide_cli_generation_slug(writer_pin) if writer_pin else "")
    forbidden_bases = {_slug_base(primary_pin)}
    if writer_slug:
        forbidden_bases.add(_slug_base(writer_slug))
    tier_key = "enhanced" if section_id == "executive_summary" else "standard"
    if provider_key == "gemini_pro":
        try:
            slot2_pin, _ = second_judge_model(section_id)
            if slot2_pin:
                forbidden_bases.add(_slug_base(slot2_pin))
        except IdeCliJudgeConfigError:
            pass
        raw_backups = list(((cfg.get("quota_backup_first_judge_by_tier") or {}).get(tier_key)) or [])
    else:
        jm = _profiles().get("judge_models") or {}
        slot1_pin = str(((jm.get(tier_key) or {}) if isinstance(jm, Mapping) else {}).get("gemini_pro") or "")
        if slot1_pin:
            forbidden_bases.add(_slug_base(slot1_pin))
        eff_maker = maker_of(actual_writer) if actual_writer else (maker_of(writer_pin) if writer_pin else DEFAULT_WRITER_MAKER)
        decl_maker = maker_of(writer_pin) if writer_pin else DEFAULT_WRITER_MAKER
        bmap = cfg.get("quota_backup_second_judge_by_writer_maker") or {}
        raw_backups = list((bmap.get(decl_maker) or [])) + [m for m in (bmap.get(eff_maker) or []) if m not in (bmap.get(decl_maker) or [])]
    valid: list[str] = []
    for item in raw_backups:
        b_pin = str(item or "").strip()
        caps = try_model_capabilities(b_pin) if b_pin else None
        if (
            b_pin
            and _slug_base(b_pin) not in forbidden_bases
            and not _collides_with_writer(b_pin, writer_slug)
            and caps
            and caps.proof_eligible
            and caps.supports_endpoint("ide_cli")
            and b_pin not in valid
        ):
            valid.append(b_pin)
    return valid


def call_ide_cli_judge(*, prompt: str, model: str, input_hash: str, provider_key: str, artifact_base: Path | None = None, model_requested: str | None = None, judge_receipt: dict[str, Any] | None = None, reasoning_effort: str | None = None, attempt: int = 1, section_id: str | None = None, response_schema: dict[str, Any] | None = None, agy_bin: str | None = None) -> JudgeOutput:
    """Execute one Judge v3 atomic binary evaluation via `agy -p` (fail-closed BLOCKED on error)."""
    from apps_rg.runtime.judges import executive_summary_x1d as x

    sid = section_id or "executive_summary"
    full_prompt = f"{V3_JUDGE_SYSTEM_PROMPT}\n\n{prompt}\n"
    schema = response_schema or build_section_v3_response_schema(sid)
    norm_effort = str(reasoning_effort or "").strip().lower() or None
    if norm_effort not in {"low", "medium", "high", "xhigh", "max"}:
        norm_effort = None
    primary_slug, primary_eff = _step_judge_pin_for_effort(model, norm_effort)
    candidates: list[tuple[str, str | None, str]] = [(primary_slug, primary_eff, model)]
    for b_pin in _governed_judge_quota_backups(sid, provider_key, model):
        b_slug, b_eff = _step_judge_pin_for_effort(b_pin, norm_effort)
        if all(c[0] != b_slug for c in candidates):
            candidates.append((b_slug, b_eff, b_pin))
    ordered = [c for c in candidates if not is_agy_model_quota_cooled_down(c[0])] + [c for c in candidates if is_agy_model_quota_cooled_down(c[0])]
    cli_model, active_effort, _ = ordered[0]
    req_path = x._artifact_path(provider_key, "provider_request", artifact_base=artifact_base)
    x._write_artifact(req_path, {"transport": "ide_cli", "provider_key": provider_key, "section_id": sid, "resolved_model": cli_model, "model_requested": model_requested or model, "reasoning_effort": active_effort, "attempt": attempt, "input_hash": input_hash, "prompt_sha256": hashlib.sha256(full_prompt.encode("utf-8")).hexdigest(), "blind_to_deterministic_gates": True, "api_key_used": False})
    res, last_exc = None, None
    for idx_c, (cand_slug, cand_eff, _) in enumerate(ordered):
        try:
            res = run_agy(full_prompt, model=cand_slug, json_schema=schema, effort=cand_eff, timeout_s=_timeout_s(), agy_bin=agy_bin)
            break
        except AgyTransportError as exc:
            last_exc = exc
            if is_agy_quota_error(exc) and idx_c + 1 < len(ordered):
                mark_agy_model_quota_exhausted(cand_slug, str(exc))
                continue
            break
    if res is None:
        err_low = str(last_exc or "").lower()
        b_status = "BLOCKED_RATE_LIMIT" if (last_exc and is_agy_quota_error(last_exc)) else ("BLOCKED_TIMEOUT" if "timed out" in err_low else "BLOCKED_PROVIDER_UNAVAILABLE")
        blocked = x._make_blocked_output(provider_key, input_hash, "BLOCKED_PROVIDER_UNAVAILABLE", b_status, f"IDE CLI judge call failed: {last_exc}", model_name=model)
        blocked.transport = "ide_cli"
        return blocked
    raw_path = x._artifact_path(provider_key, "provider_response_raw", artifact_base=artifact_base)
    x._write_artifact(raw_path, {"transport": "ide_cli", "model_reported": res.model_reported, "conversation_id": res.conversation_id, "usage": res.usage, "structured_output": res.structured_output})
    text = json.dumps(res.structured_output) if isinstance(res.structured_output, dict) else res.response
    out = x._finish_judge_text_parse(provider_key=provider_key, input_hash=input_hash, model_name=res.model_reported, raw_path=raw_path, text=text, finish_reason=None, artifact_base=artifact_base, judge_receipt=judge_receipt, model_requested=model_requested or model, section_id=sid)
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
        for tier_name in ("enhanced", "standard"):
            pin = str(((data.get("judge_models") or {}).get(tier_name) or {}).get("gemini_pro") or "").strip()
            if pin and pin not in out["judges"]:
                out["judges"].append(pin)
        for pin_val in (_judging_cfg().get("second_judge_by_writer_maker") or {}).values():
            pin = str(pin_val or "").strip()
            if pin and pin not in out["judges"]:
                out["judges"].append(pin)
    return out


def verify_ide_cli_preflight(environ: Mapping[str, str] | None = None, *, agy_bin: str | None = None) -> dict[str, Any]:
    """Verify CLI sign-in and confirm every active IDE judge/generation pin is present in `agy models`."""
    from apps_rg.runtime.env_bootstrap import snapshot_process_env
    env = snapshot_process_env() if environ is None else environ
    pins_by_role = pinned_ide_models_for_preflight(env)
    required = [p for role_pins in pins_by_role.values() for p in role_pins]
    if not required:
        return {"ide_cli_active": False, "pinned_models": {}, "verified_models": [], "available_count": 0}
    var = str(_judging_cfg().get("cli_env_var") or AGY_CLI_ENV_VAR)
    resolved_bin = str(agy_bin or env.get(var) or "")
    ok, reason = ide_cli_ready(resolved_bin or None)
    if not ok:
        raise IdeCliJudgeConfigError(f"IDE CLI preflight failed: {reason}")
    available = list_agy_models(resolved_bin)
    missing = [p for p in required if p not in set(available)]
    if missing:
        raise IdeCliJudgeConfigError(f"IDE CLI preflight: pinned models {missing} missing from `agy models`")
    return {"ide_cli_active": True, "cli_env_var": var, "pinned_models": pins_by_role, "verified_models": required, "available_count": len(available)}
