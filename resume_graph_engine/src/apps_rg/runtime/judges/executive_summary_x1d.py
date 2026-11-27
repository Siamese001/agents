"""Clean-Slate Judge v3 Public Facade for `apps_rg` X1D Judges (`<= 260L`)."""
from __future__ import annotations

from apps_rg.config.runtime_env import get_runtime_env_str, get_runtime_environ
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import time
from typing import Any, Callable, Mapping

from apps_eval.graders.judge.v3_evaluator import JudgeV3SchemaError
from apps_rg.runtime.env_bootstrap import bootstrap_process_env_if_needed
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import (
    dimension_verdicts_json_schema_fragment,
    ensure_dimension_verdicts,
    section_dimension_veto_passes,
)
from apps_rg.runtime.judges.v3_section_judge import (
    DEFAULT_THRESHOLD,
    JUDGE_RUBRIC_VERSION,
    V3_JUDGE_SYSTEM_PROMPT,
    JudgeOutput,
    build_section_v3_response_schema,
    evaluate_v3_judge_response_to_dict,
    render_section_v3_rubric,
)
from apps_rg.runtime.judges.x1d_ide_cli import IDE_CLI_SESSION_MARKER, call_ide_cli_judge
from apps_rg.runtime.model_capabilities import try_model_capabilities
from apps_rg.runtime.providers.wallclock_http_guard import (
    DaemonWorkerPool,
    is_lane_cancelled,
    is_lane_or_dir_cancelled,
    resolve_judge_total_budget_s,
)
from apps_rg.runtime.section_judge_policy import get_section_judge_policy, normalize_section_id
from apps_rg.runtime.section_model_limits import runtime_limit_float, runtime_limit_int

JUDGE_INPUT_PROMPT_VERSION = "judge_v3_cold_read_v1"
VALID_SCORE_SCALES = frozenset({"0_to_1", "0_to_5"})
JUDGE_REQUIRED_FIELDS = ("score_scale", "score", "threshold", "pass")
JUDGE_COMPACT_SYSTEM = V3_JUDGE_SYSTEM_PROMPT
JUDGE_GRADE_ONLY_AUTHORITY = "GRADE_ONLY blind evaluation: evaluate candidate_output strictly against allowed_fact_packet."
JUDGE_SCORE_SCHEMA = "Return strict JSON with cold_read_takeaway first, atomic YES/NO checks, and failure_tags."
JUDGE_COMPACT_OUTPUT = JUDGE_SCORE_SCHEMA
RUBRIC = render_section_v3_rubric("executive_summary")
JUDGE_USER_PROMPT_RUBRIC = RUBRIC

PROVIDERS = {
    "gemini_pro": {"provider_name": "Gemini 4 Argon", "env": "GOOGLE_API_KEY", "env_fallbacks": ("GEMINI_API_KEY",)},
    "openai_chatgpt": {"provider_name": "OpenAI ChatGPT", "env": "OPENAI_API_KEY"},
}
_ARTIFACT_ALIASES = {"gemini_pro": "gemini", "openai_chatgpt": "openai"}


def _filesystem_path(path: Path) -> str:
    return str(path)

def _artifact_path(provider_key: str, suffix: str, *, artifact_base: Path | None = None) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
    base = artifact_base or Path("artifacts/apps_rg/runtime_proofs/executive_summary")
    base.mkdir(parents=True, exist_ok=True)
    return base / f"x1d_{_ARTIFACT_ALIASES.get(provider_key, provider_key)}_{suffix}_{ts}.json"

def _write_artifact(path: Path, data: Any) -> str:
    if not is_lane_or_dir_cancelled(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return str(path)

def _resolved_x1d_judge_max_output_tokens(*, attempt: int = 1) -> int:
    base = max(512, runtime_limit_int("judge.x1d_max_output_tokens"))
    return min(max(base, runtime_limit_int("judge.x1d_max_output_tokens_hard_cap")), base * min(max(1, attempt), 2))

_resolved_openai_judge_max_completion_tokens = _resolved_x1d_judge_max_output_tokens

def _resolved_section_x1d_judge_max_output_tokens(section_id: str, *, attempt: int = 1) -> int:
    return get_section_judge_policy(section_id).judge_runtime_profile.resolved_max_output_tokens(attempt=attempt)

def _section_x1d_judge_max_attempts(section_id: str) -> int:
    return get_section_judge_policy(section_id).judge_runtime_profile.max_attempts

def _openai_chat_uses_max_completion_tokens(model: str) -> bool:
    caps = try_model_capabilities(model)
    return bool(caps and caps.provider == "openai" and caps.max_output_tokens_parameter_for("chat_completions") == "max_completion_tokens")

def build_x1d_judge_system_prompt(*, compact: bool = True, section_id: str | None = None) -> str:
    _ = (compact, section_id)
    return V3_JUDGE_SYSTEM_PROMPT

def build_judge_response_schema(dimension_ids: tuple[str, ...] | None = None) -> dict[str, Any]:
    if dimension_ids is None:
        return build_section_v3_response_schema("executive_summary")
    props = {"rationale": {"type": "string"}, "score_scale": {"type": "string", "enum": ["0_to_1", "0_to_5"]}, "score": {"type": "number"}, "threshold": {"type": "number"}, "pass": {"type": "boolean"}, "decisive_failure": {"type": "boolean"}, "findings": {"type": "array", "items": {"type": "string"}}, "cited_sentence_indexes": {"type": "array", "items": {"type": "integer"}}, "remediation_suggestions": {"type": "array", "items": {"type": "string"}}, "dimension_verdicts": dimension_verdicts_json_schema_fragment(dimension_ids)}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}

GEMINI_JUDGE_RESPONSE_SCHEMA = build_section_v3_response_schema("executive_summary")

def _gemini_generation_config(*, thinking_level: str, attempt: int = 1, section_id: str | None = None, response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
    lvl = str(thinking_level or "").strip().lower()
    if not lvl:
        raise ValueError("Gemini proof judge thinking_level must be explicit")
    sid = section_id or "executive_summary"
    return {"thinkingConfig": {"thinkingLevel": lvl}, "maxOutputTokens": _resolved_section_x1d_judge_max_output_tokens(sid, attempt=attempt), "responseMimeType": "application/json", "responseSchema": response_schema or build_section_v3_response_schema(sid)}


def _policy_model_name(provider_key: str, section_id: str, fallback: str = "unknown") -> str:
    from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
    try:
        res = resolve_section_proof_judge_model(section_id, provider_key)
        return res.model_requested or res.model_actual or fallback
    except Exception:  # guardian: allow-broad-exception -- fallback model label on missing policy
        return fallback


def _resolve_gemini_model(meta: dict[str, Any], *, section_id: str = "executive_summary") -> tuple[str, str]:
    from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
    _ = meta
    res = resolve_section_proof_judge_model(section_id, "gemini_pro")
    if res.model_actual and not res.blocked:
        return res.model_actual, res.model_source
    raise RuntimeError(res.block_reason or f"proof judge model unavailable for {section_id}")


def resolve_x1d_provider_credentials(provider_key: str, environ: Mapping[str, str]) -> tuple[str, list[str]]:
    bootstrap_process_env_if_needed(environ)
    meta = PROVIDERS.get(provider_key)
    if not meta:
        return "", []
    from apps_rg.runtime.judges.x1d_ide_cli import ide_cli_unavailable_reason, uses_ide_cli_judges
    if uses_ide_cli_judges(environ):
        reason = ide_cli_unavailable_reason(environ)
        return ("" if reason else IDE_CLI_SESSION_MARKER), [reason or "ide_cli"]
    consulted: list[str] = []
    for name in (str(meta.get("env") or ""), *[str(x) for x in (meta.get("env_fallbacks") or ())]):
        if not name or name in consulted:
            continue
        consulted.append(name)
        val = str(environ.get(name) or "").strip()
        if val and not any(p in val.lower() for p in ("placeholder", "dummy", "replace_me", "sk-local-dev-key")):
            return val, consulted
    return "", consulted


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    s = str(text or "").strip()
    for cand in [s, *(m.group(1).strip() for m in re.finditer(r"```(?:json)?\s*(.*?)\s*```", s, re.DOTALL))]:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    start, end = s.find("{"), s.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(s[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _judge_live_https_allowed_under_pytest() -> bool:
    return (not get_runtime_env_str("PYTEST_CURRENT_TEST")) or str(get_runtime_env_str("APPS_RG_ENABLE_NETWORK_TESTS") or "").strip().lower() in {"1", "true", "yes", "on"}

def _make_blocked_output(provider_key: str, input_hash: str, evaluator_mode: str, provider_status: str, error: str, raw_response_ref: str | None = None, model_name: str = "", original_model: str | None = None, fallback_model: str | None = None) -> JudgeOutput:
    p_name = PROVIDERS.get(provider_key, {"provider_name": provider_key})["provider_name"]
    return JudgeOutput(f"x1d_{provider_key}_exec_summary", p_name, provider_key, evaluator_mode, provider_status, model_name or _policy_model_name(provider_key, "executive_summary"), False, True, error, raw_response_ref, original_model, fallback_model, input_hash=input_hash, findings=["Judge blocked - see exact_provider_error."])

def _pytest_network_disabled_blocked_output(*, provider_key: str, input_hash: str, model: str, service_label: str) -> JudgeOutput:
    return _make_blocked_output(provider_key, input_hash, "BLOCKED_PROVIDER_UNAVAILABLE", "NETWORK_TESTS_NOT_ENABLED", f"{service_label} HTTPS disabled under pytest.", model_name=model)

def _is_retriable_judge_output(output: JudgeOutput) -> bool:
    return bool(output.provider_blocked and output.provider_status in {"BLOCKED_TIMEOUT", "BLOCKED_RATE_LIMIT", "BLOCKED_RESPONSE_PARSE_ERROR", "BLOCKED_SCHEMA_VALIDATION_ERROR"})


def _invoke_judge_with_bounded_retries(invoke: Callable[[int], JudgeOutput], *, provider_key: str, section_id: str | None = None) -> JudgeOutput:
    max_attempts = _section_x1d_judge_max_attempts(section_id) if section_id else max(1, min(5, runtime_limit_int("judge.x1d_max_attempts")))
    deadline = time.monotonic() + resolve_judge_total_budget_s()
    last: JudgeOutput | None = None
    for attempt in range(1, max_attempts + 1):
        if is_lane_cancelled():
            raise TimeoutError(f"Judge {provider_key} cancelled")
        last = invoke(attempt)
        if not _is_retriable_judge_output(last) or attempt >= max_attempts or (deadline - time.monotonic()) <= 0.1:
            return last
        time.sleep(min(runtime_limit_float("judge.retry_backoff_base_seconds") + random.uniform(0.05, 0.25), max(0.0, deadline - time.monotonic())))
    assert last is not None
    return last


def _make_model_backed_output(provider_key: str, input_hash: str, model_name: str, result: dict[str, Any], raw_response_ref: str | None = None, original_model: str | None = None, fallback_model: str | None = None, *, deterministic_gate_summary: dict[str, Any] | None = None, section_id: str | None = None, candidate_text: str | None = None) -> JudgeOutput:
    try:
        proj = evaluate_v3_judge_response_to_dict(result, section_id=section_id or "executive_summary", candidate_text=candidate_text)
    except JudgeV3SchemaError as exc:
        return _make_blocked_output(provider_key, input_hash, "BLOCKED_SCHEMA_VALIDATION_ERROR", "BLOCKED_SCHEMA_VALIDATION_ERROR", str(exc), raw_response_ref=raw_response_ref, model_name=model_name)
    proj, dv_inf = ensure_dimension_verdicts(proj, deterministic_gate_summary=deterministic_gate_summary, section_id=section_id)
    scale = str(proj.get("score_scale") or "0_to_1").strip()
    if scale not in VALID_SCORE_SCALES:
        return _make_blocked_output(provider_key, input_hash, "BLOCKED_SCHEMA_VALIDATION_ERROR", "BLOCKED_SCHEMA_VALIDATION_ERROR", f"Invalid score_scale {scale!r}", raw_response_ref=raw_response_ref, model_name=model_name)
    raw_sc = float(proj.get("score", 0.0))
    raw_th = float(proj.get("threshold", DEFAULT_THRESHOLD if scale == "0_to_1" else 4.0))
    n_sc, n_th = (raw_sc, raw_th) if scale == "0_to_1" else (raw_sc / 5.0, raw_th / 5.0)
    decisive, findings = bool(proj.get("decisive_failure", False)), list(proj.get("findings") or [])
    if not dv_inf:
        veto_ok, veto_reasons = section_dimension_veto_passes(proj.get("dimension_verdicts"))
        if not veto_ok:
            decisive = True
            findings.extend(r for r in veto_reasons if r not in findings)
    passed = n_sc >= n_th and not decisive
    out_h = hashlib.sha256(json.dumps(proj, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    p_name = PROVIDERS.get(provider_key, {"provider_name": provider_key})["provider_name"]
    return JudgeOutput(f"x1d_{provider_key}_{section_id or 'exec_summary'}", p_name, provider_key, "MODEL_BACKED", "MODEL_BACKED_PASS" if passed else "MODEL_BACKED_FAIL", model_name, True, False, None, raw_response_ref, original_model, fallback_model, input_hash=input_hash, output_hash=out_h, score=raw_sc, score_scale=scale, normalized_score=n_sc, threshold=raw_th, normalized_threshold=n_th, pass_=passed, decisive_failure=decisive, findings=findings, cited_sentence_indexes=list(proj.get("cited_sentence_indexes") or []), remediation_suggestions=list(proj.get("remediation_suggestions") or []), rationale=str(proj.get("rationale") or "") or None, fail_reasons=list(proj.get("fail_reasons") or []), unsupported_claims=list(proj.get("unsupported_claims") or []), quality_flags=list(proj.get("quality_flags") or []), dimension_verdicts=dict(proj.get("dimension_verdicts") or {}), dimension_verdicts_inferred=dv_inf, model_requested=model_name, model_actual=model_name, section_id=section_id)


def _finish_judge_text_parse(*, provider_key: str, input_hash: str, model_name: str, raw_path: Path, text: str, finish_reason: str | None = None, artifact_base: Path | None = None, judge_receipt: dict[str, Any] | None = None, model_requested: str | None = None, section_id: str | None = None) -> JudgeOutput:
    _ = (finish_reason, artifact_base)
    parsed = _extract_json_from_text(text)
    if parsed is None:
        return _make_blocked_output(provider_key, input_hash, "BLOCKED_RESPONSE_PARSE_ERROR", "BLOCKED_RESPONSE_PARSE_ERROR", "Failed to extract JSON from judge response.", raw_response_ref=str(raw_path), model_name=model_name)
    out = _make_model_backed_output(provider_key, input_hash, model_name, parsed, raw_response_ref=str(raw_path), section_id=section_id)
    if model_requested:
        out.model_requested = model_requested
    if judge_receipt:
        out.judge_packet_hash = judge_receipt.get("judge_packet_hash")
        out.judge_packet_ref = judge_receipt.get("judge_packet_ref")
    return out


def _call_gemini(api_key: str, prompt: str, model: str, input_hash: str, provider_key: str = "gemini_pro", *, model_source: str = "", artifact_base: Path | None = None, model_requested: str | None = None, judge_receipt: dict[str, Any] | None = None, thinking_level: str | None = None, attempt: int = 1, section_id: str | None = None, response_schema: dict[str, Any] | None = None) -> JudgeOutput:
    _ = model_source
    if api_key == IDE_CLI_SESSION_MARKER:
        return call_ide_cli_judge(prompt=prompt, model=model, input_hash=input_hash, provider_key=provider_key, artifact_base=artifact_base, model_requested=model_requested, judge_receipt=judge_receipt, reasoning_effort=thinking_level, attempt=attempt, section_id=section_id, response_schema=response_schema)
    if not _judge_live_https_allowed_under_pytest():
        return _pytest_network_disabled_blocked_output(provider_key=provider_key, input_hash=input_hash, model=model, service_label="Gemini")
    return _make_blocked_output(provider_key, input_hash, "BLOCKED_PROVIDER_UNAVAILABLE", "EXTERNAL_HTTP_DISABLED_USE_IDE_CLI", "Use ide_cli transport.", model_name=model)


def _call_openai(api_key: str, prompt: str, model: str, input_hash: str, provider_key: str = "openai_chatgpt", *, artifact_base: Path | None = None, reasoning_effort: str | None = None, model_requested: str | None = None, judge_receipt: dict[str, Any] | None = None, attempt: int = 1, model_env_source: str = "", section_id: str | None = None, response_schema: dict[str, Any] | None = None) -> JudgeOutput:
    _ = model_env_source
    if api_key == IDE_CLI_SESSION_MARKER:
        return call_ide_cli_judge(prompt=prompt, model=model, input_hash=input_hash, provider_key=provider_key, artifact_base=artifact_base, model_requested=model_requested, judge_receipt=judge_receipt, reasoning_effort=reasoning_effort, attempt=attempt, section_id=section_id, response_schema=response_schema)
    if not _judge_live_https_allowed_under_pytest():
        return _pytest_network_disabled_blocked_output(provider_key=provider_key, input_hash=input_hash, model=model, service_label="OpenAI")
    return _make_blocked_output(provider_key, input_hash, "BLOCKED_PROVIDER_UNAVAILABLE", "EXTERNAL_HTTP_DISABLED_USE_IDE_CLI", "Use ide_cli transport.", model_name=model)


def _build_judge_user_prompt(resume_display_text: str, claim_ledger: list[dict[str, Any]]) -> str:
    return f"{RUBRIC}\n\nRESUME_DISPLAY_TEXT:\n{resume_display_text}\n\nCLAIM_LEDGER:\n{json.dumps(claim_ledger, separators=(',', ':'))}"


def _is_test_environment() -> bool:
    return bool(get_runtime_env_str("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)


def _mocked_output(provider_key: str, input_hash: str) -> JudgeOutput:
    if get_runtime_env_str("APPS_RG_PRODUCTION_RUN", "").strip() == "1" or not _is_test_environment():
        raise RuntimeError("MOCK_JUDGE_FORBIDDEN")
    p_name = PROVIDERS.get(provider_key, {"provider_name": provider_key})["provider_name"]
    return JudgeOutput(f"x1d_{provider_key}_exec_summary", p_name, provider_key, "MOCKED", "MOCKED", _policy_model_name(provider_key, "executive_summary"), False, False, None, input_hash=input_hash, output_hash="mocked-output", score=0.80, score_scale="0_to_1", normalized_score=0.80, threshold=DEFAULT_THRESHOLD, normalized_threshold=0.80, pass_=True, findings=["MOCKED plumbing judge."])


def run_llm_judges(*, resume_display_text: str, claim_ledger: list[dict[str, Any]], judge_keys: list[str], mode: str = "blocked_if_unavailable", artifact_base: Path | None = None, judge_packet: dict[str, Any] | None = None, judge_packet_ref: str | None = None, compiled_prompt: str | None = None, section_id: str = "executive_summary") -> list[JudgeOutput]:
    from apps_rg.runtime.judges.executive_summary_judge_packet import judge_contract_hash as _exec_contract, judge_packet_hash as _exec_h, render_judge_prompt_from_packet as _exec_r
    from apps_rg.runtime.judges.grade_only_judge_packet import judge_packet_hash as _gen_h, render_judge_prompt_from_packet as _gen_r
    from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model

    _ = compiled_prompt
    sid = normalize_section_id(section_id or (judge_packet or {}).get("section", "executive_summary"))
    if judge_packet is not None:
        is_exec = "executive_summary" in str(judge_packet.get("judge_packet_version", ""))
        input_hash, prompt = (_exec_h if is_exec else _gen_h)(judge_packet), (_exec_r if is_exec else _gen_r)(judge_packet)
        if mode != "mocked":
            from apps_rg.runtime.judges.x1d_panel_bridge import run_grade_only_judges_via_core_panel
            return run_grade_only_judges_via_core_panel(judge_keys=judge_keys, judge_packet=judge_packet, user_prompt=prompt, input_hash=input_hash, section_id=sid, mode=mode, artifact_base=artifact_base, judge_packet_ref=judge_packet_ref, contract_hash=_exec_contract(judge_packet) if is_exec else None)
    else:
        prompt = _build_judge_user_prompt(resume_display_text, claim_ledger)
        input_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]

    def _eval_one(key: str) -> JudgeOutput:
        if key not in PROVIDERS:
            return _make_blocked_output(key, input_hash, "BLOCKED_PROVIDER_UNAVAILABLE", "BLOCKED_PROVIDER_UNAVAILABLE", f"Unknown judge provider key: {key}")
        if mode == "mocked":
            if get_runtime_env_str("APPS_RG_PRODUCTION_RUN", "").strip() == "1" or not _is_test_environment():
                raise RuntimeError("MOCK_JUDGE_FORBIDDEN")
            return _mocked_output(key, input_hash)
        api_key, env_checked = resolve_x1d_provider_credentials(key, get_runtime_environ())
        if not api_key:
            return _make_blocked_output(key, input_hash, "BLOCKED_PROVIDER_UNAVAILABLE", "BLOCKED_PROVIDER_UNAVAILABLE", f"Credentials unavailable: {env_checked}")
        res = resolve_section_proof_judge_model(sid, key)
        if res.blocked:
            return _make_blocked_output(key, input_hash, "BLOCKED_MODEL_CONFIG", "BLOCKED_MODEL_CONFIG", res.block_reason or "model blocked", model_name=res.model_requested or "unconfigured")
        caller = _call_openai if key == "openai_chatgpt" else _call_gemini
        return _invoke_judge_with_bounded_retries(lambda att: caller(api_key, prompt, res.model_actual, input_hash, key, artifact_base=artifact_base, model_requested=res.model_requested, attempt=att, section_id=sid), provider_key=key, section_id=sid)

    if mode != "mocked" and len(judge_keys) > 1:
        with DaemonWorkerPool(max_workers=len(judge_keys), thread_name_prefix="apps-rg-v3-judge") as pool:
            return [f.result() for f in [pool.submit(_eval_one, k) for k in judge_keys]]
    return [_eval_one(k) for k in judge_keys]
