"""Keyless IDE CLI Transport Adapter for Outreach Engine Judge v3 (`<= 240L`).

Enforces Clean-Slate Judge v3 across Outreach single-draft and multi-touch
sequence judging:
1. Cold-read takeaway generated FIRST before atomic `YES` / `NO` checks.
2. Mandatory non-empty verbatim `evidence_span` on every `NO` check.
3. Mechanical `passed` (`all(critical == YES) and sum(passed_weights) >= pass_threshold`)
   and `normalized_unit_score` in `[0.0, 1.0]` (`None` when `llm_judge_executed=False`).
4. Cross-family drafter-judge orthogonality and governed quota-backup failover via `agy -p`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_eval.graders.judge.v3_evaluator import JudgeV3SchemaError, build_v3_response_schema
from apps_eval.graders.judge.v3_registry import JudgeProfileV3, JudgeRubricRegistryV3, render_v3_rubric_prompt
from apps_lic.runtime.model_registry import OutreachModelRegistry
from infrastructure.sdks_mcps.agy_cli_transport import (
    AGY_CLI_ENV_VAR,
    AgyTransportError,
    ide_cli_ready,
    is_agy_model_quota_cooled_down,
    is_agy_quota_error,
    mark_agy_model_quota_exhausted,
    run_agy,
)

LIC_JUDGE_TRANSPORT_ENV = "APPS_LIC_JUDGE_TRANSPORT"
LIC_JUDGE_TIMEOUT_ENV = "APPS_LIC_IDE_CLI_JUDGE_TIMEOUT_S"
DEFAULT_LIC_JUDGE_TIMEOUT_S = 240
_VALID_TRANSPORTS = frozenset({"ide_cli", "deterministic", "external_api"})


class LicIdeCliJudgeConfigError(RuntimeError):
    """Raised when Outreach IDE CLI judge configuration is missing or invalid (fail closed)."""


def _sequence_v3_profile() -> JudgeProfileV3:
    return JudgeRubricRegistryV3.load().get_profile("outreach_sequence:outreach_multi_touch_sequence")


def _single_draft_v3_profile() -> JudgeProfileV3:
    return JudgeRubricRegistryV3.load().get_profile("outreach_sequence:outreach_single_draft")


OUTREACH_X1D_JUDGE_SCHEMA: dict[str, Any] = build_v3_response_schema(_sequence_v3_profile())
OUTREACH_PANEL_JUDGE_SCHEMA: dict[str, Any] = build_v3_response_schema(_single_draft_v3_profile())


@dataclass(frozen=True)
class LicIdeCliJudgeResult:
    """Model-backed or fail-closed BLOCKED Judge v3 evaluation receipt from headless `agy -p`."""

    slot: str
    model_requested: str
    model_reported: str
    provider_family: str
    transport: str = "ide_cli"
    evaluator_mode: str = "MODEL_BACKED"
    llm_judge_executed: bool = True
    provider_blocked: bool = False
    score: float = 0.0
    normalized_unit_score: float | None = 0.0
    passed: bool = False
    dimension_scores: dict[str, float] = field(default_factory=dict)
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    rationale: str = ""
    violations: tuple[str, ...] = ()
    conversation_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    exact_provider_error: str | None = None
    quota_failover_attempts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "model_requested": self.model_requested,
            "model_reported": self.model_reported,
            "provider_family": self.provider_family,
            "transport": self.transport,
            "evaluator_mode": self.evaluator_mode,
            "llm_judge_executed": self.llm_judge_executed,
            "provider_blocked": self.provider_blocked,
            "score": round(float(self.score), 4),
            "normalized_unit_score": self.normalized_unit_score,
            "passed": self.passed,
            "dimension_scores": {k: round(float(v), 4) for k, v in self.dimension_scores.items()},
            "checks": dict(self.checks),
            "rationale": self.rationale,
            "violations": list(self.violations),
            "conversation_id": self.conversation_id,
            "usage": dict(self.usage),
            "exact_provider_error": self.exact_provider_error,
            "quota_failover_attempts": list(self.quota_failover_attempts),
        }


def _slug_base(slug: str) -> str:
    s = str(slug or "").strip()
    for suf in ("-low", "-medium", "-high", "-xhigh", "-max"):
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def _judging_cfg(config_path: Path | str | None = None) -> dict[str, Any]:
    cfg = OutreachModelRegistry.get_profiles(config_path).get("ide_cli_judging") or {}
    return dict(cfg) if isinstance(cfg, Mapping) else {}


def resolve_lic_judge_transport(
    explicit_transport: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    config_path: Path | str | None = None,
) -> str:
    _ = config_path
    if explicit_transport is not None and str(explicit_transport).strip():
        val = str(explicit_transport).strip().lower()
    else:
        from infrastructure.config.env_loader import snapshot_process_env

        env = snapshot_process_env() if environ is None else environ
        env_val = str(env.get(LIC_JUDGE_TRANSPORT_ENV) or "").strip().lower()
        val = env_val or "deterministic"
    if val not in _VALID_TRANSPORTS:
        raise LicIdeCliJudgeConfigError(f"Unknown Outreach judge transport {val!r}; expected {sorted(_VALID_TRANSPORTS)}")
    return val


def resolve_lic_ide_judge_slots(
    drafter_family: str = "anthropic",
    *,
    config_path: Path | str | None = None,
) -> tuple[str, str, list[str], list[str]]:
    cfg = _judging_cfg(config_path)
    maker = OutreachModelRegistry.normalize_provider_family(drafter_family or "anthropic")
    primary = str(cfg.get("primary_judge_model") or "").strip()
    if not primary:
        raise LicIdeCliJudgeConfigError("ide_cli_judging.primary_judge_model missing.")
    second_map = cfg.get("second_judge_by_writer_maker") or {}
    secondary = str((second_map.get(maker) if isinstance(second_map, Mapping) else "") or "").strip()
    if not secondary:
        raise LicIdeCliJudgeConfigError(f"ide_cli_judging.second_judge_by_writer_maker missing maker {maker!r}.")
    if _slug_base(primary) == _slug_base(secondary):
        raise LicIdeCliJudgeConfigError(f"Primary ({primary}) and secondary ({secondary}) IDE judge bases must differ.")
    p_backups = [str(m).strip() for m in (cfg.get("quota_backup_primary_judge") or []) if str(m).strip()]
    s_map = cfg.get("quota_backup_second_judge_by_writer_maker") or {}
    s_backups = [str(m).strip() for m in ((s_map.get(maker) if isinstance(s_map, Mapping) else []) or []) if str(m).strip()]
    return primary, secondary, p_backups, s_backups


def _score_v3_payload(parsed: Mapping[str, Any], profile: JudgeProfileV3, pass_threshold: float) -> tuple[float, bool, dict[str, float], dict[str, dict[str, Any]], str, tuple[str, ...]]:
    takeaway = str(parsed.get("cold_read_takeaway") or "").strip()
    if len(takeaway) < 5:
        raise JudgeV3SchemaError("Judge v3 response requires non-empty 'cold_read_takeaway' first.")
    raw_checks = parsed.get("checks")
    if not isinstance(raw_checks, Mapping):
        raise JudgeV3SchemaError("Judge v3 response missing 'checks' mapping.")
    dim_scores: dict[str, float] = {}
    sealed_checks: dict[str, dict[str, Any]] = {}
    viols: list[str] = []
    passed_w = 0.0
    crit_veto = False
    for spec in profile.checks:
        entry = raw_checks.get(spec.id)
        if not isinstance(entry, Mapping):
            raise JudgeV3SchemaError(f"Missing atomic check '{spec.id}'.")
        v = str(entry.get("verdict") or "").strip().upper()
        if v not in {"YES", "NO"}:
            raise JudgeV3SchemaError(f"Check '{spec.id}' verdict must be YES or NO.")
        span = str(entry.get("evidence_span") or "").strip()
        if v == "NO":
            if len(span) < 3:
                raise JudgeV3SchemaError(f"Check '{spec.id}' answered NO without verbatim evidence_span.")
            dim_scores[spec.id] = 0.0
            viols.append(f"{spec.id} [{spec.failure_tag}]: {span}")
            if spec.critical:
                crit_veto = True
        else:
            dim_scores[spec.id] = 1.0
            passed_w += spec.weight
        sealed_checks[spec.id] = {"verdict": v, "evidence_span": span, "critical": spec.critical, "weight": spec.weight}
    unit = round(min(1.0, max(0.0, passed_w)), 4)
    eff_th = max(float(pass_threshold), profile.pass_threshold)
    return unit, (not crit_veto and unit >= eff_th), dim_scores, sealed_checks, takeaway, tuple(viols)


def _run_with_failover(
    *,
    prompt: str,
    profile: JudgeProfileV3,
    primary_model: str,
    backup_models: Sequence[str],
    forbidden_bases: set[str],
    slot: str,
    pass_threshold: float,
    agy_bin: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> LicIdeCliJudgeResult:
    from infrastructure.config.env_loader import snapshot_process_env

    env = snapshot_process_env() if environ is None else environ
    bin_path = str(agy_bin or env.get(AGY_CLI_ENV_VAR) or "")
    ok, why = ide_cli_ready(bin_path or None)
    if not ok:
        return LicIdeCliJudgeResult(slot, primary_model, "", OutreachModelRegistry.normalize_provider_family(primary_model), evaluator_mode="BLOCKED_PROVIDER_UNAVAILABLE", llm_judge_executed=False, provider_blocked=True, normalized_unit_score=None, rationale=f"IDE CLI judge unavailable: {why}", violations=(f"IDE_CLI_UNAVAILABLE:{why}",), exact_provider_error=why)
    candidates = [primary_model, *[bm for bm in backup_models if bm and _slug_base(bm) not in forbidden_bases]]
    ordered = [m for m in candidates if not is_agy_model_quota_cooled_down(m)] or list(candidates)
    attempted: list[str] = []
    last_err = ""
    raw_t = str(env.get(LIC_JUDGE_TIMEOUT_ENV) or "").strip()
    timeout_s = int(raw_t) if raw_t.isdigit() and int(raw_t) > 0 else DEFAULT_LIC_JUDGE_TIMEOUT_S
    schema = build_v3_response_schema(profile)

    for model_slug in ordered:
        attempted.append(model_slug)
        try:
            agy_res = run_agy(prompt, model=model_slug, json_schema=schema, timeout_s=timeout_s, agy_bin=bin_path)
        except AgyTransportError as exc:
            last_err = str(exc)
            if is_agy_quota_error(exc):
                mark_agy_model_quota_exhausted(model_slug, last_err)
                continue
            return LicIdeCliJudgeResult(slot, primary_model, model_slug, OutreachModelRegistry.normalize_provider_family(model_slug), evaluator_mode="BLOCKED_PROVIDER_UNAVAILABLE", llm_judge_executed=False, provider_blocked=True, normalized_unit_score=None, rationale=f"IDE CLI judge call failed: {last_err}", violations=(f"IDE_CLI_CALL_FAILED:{last_err[:160]}",), exact_provider_error=last_err, quota_failover_attempts=tuple(attempted))
        try:
            raw_obj = agy_res.structured_output if isinstance(agy_res.structured_output, dict) else json.loads(str(agy_res.response or "").strip().strip("`").lstrip("json").strip())
            unit, passed_flag, dims, checks, takeaway, viols = _score_v3_payload(raw_obj, profile, pass_threshold)
        except (ValueError, TypeError, json.JSONDecodeError, JudgeV3SchemaError) as exc:
            return LicIdeCliJudgeResult(slot, primary_model, agy_res.model_reported, OutreachModelRegistry.normalize_provider_family(agy_res.model_reported), evaluator_mode="BLOCKED_SCHEMA_INVALID", llm_judge_executed=True, provider_blocked=True, normalized_unit_score=None, rationale=f"Malformed Judge v3 output: {exc}", violations=(f"IDE_CLI_SCHEMA_INVALID:{exc}",), conversation_id=agy_res.conversation_id, usage=dict(agy_res.usage), exact_provider_error=str(exc), quota_failover_attempts=tuple(attempted))
        return LicIdeCliJudgeResult(slot, primary_model, agy_res.model_reported, OutreachModelRegistry.normalize_provider_family(agy_res.model_reported), evaluator_mode="MODEL_BACKED", llm_judge_executed=True, provider_blocked=False, score=unit, normalized_unit_score=unit, passed=passed_flag, dimension_scores=dims, checks=checks, rationale=takeaway, violations=viols, conversation_id=agy_res.conversation_id, usage=dict(agy_res.usage), quota_failover_attempts=tuple(attempted))

    return LicIdeCliJudgeResult(slot, primary_model, attempted[-1] if attempted else primary_model, OutreachModelRegistry.normalize_provider_family(primary_model), evaluator_mode="BLOCKED_QUOTA_EXHAUSTED", llm_judge_executed=False, provider_blocked=True, normalized_unit_score=None, rationale=f"All IDE judge pins exhausted quota: {last_err}", violations=(f"IDE_CLI_QUOTA_EXHAUSTED:{last_err[:160]}",), exact_provider_error=last_err or "quota exhausted", quota_failover_attempts=tuple(attempted))


def call_outreach_x1d_ide_cli_judge(*, packet_dict: Mapping[str, Any], rubric: Mapping[str, Any] | None = None, slot: str, drafter_family: str = "anthropic", pass_threshold: float = 0.85, agy_bin: str | os.PathLike[str] | None = None, environ: Mapping[str, str] | None = None, config_path: Path | str | None = None) -> LicIdeCliJudgeResult:
    _ = rubric
    primary, secondary, p_backups, s_backups = resolve_lic_ide_judge_slots(drafter_family=drafter_family, config_path=config_path)
    if slot == "primary":
        target, backups, peer_base = primary, p_backups, _slug_base(secondary)
    elif slot == "secondary":
        target, backups, peer_base = secondary, s_backups, _slug_base(primary)
    else:
        raise LicIdeCliJudgeConfigError(f"Unknown Outreach X1D judge slot {slot!r}.")
    prof = _sequence_v3_profile()
    prompt = f"{render_v3_rubric_prompt(prof)}\n\nGRADE_ONLY_PACKET:\n{json.dumps(dict(packet_dict), ensure_ascii=False, sort_keys=True)}\n"
    return _run_with_failover(prompt=prompt, profile=prof, primary_model=target, backup_models=backups, forbidden_bases={_slug_base(target), peer_base}, slot=slot, pass_threshold=pass_threshold, agy_bin=agy_bin, environ=environ)


def call_outreach_panel_ide_cli_judge(*, subject: str, body: str, channel: str, recipient_class: str, verified_facts: Sequence[str], company_name: str, rubric: Mapping[str, Any] | None = None, pass_threshold: float = 0.80, agy_bin: str | os.PathLike[str] | None = None, environ: Mapping[str, str] | None = None, config_path: Path | str | None = None) -> LicIdeCliJudgeResult:
    _ = rubric
    cfg = _judging_cfg(config_path)
    target = str(cfg.get("rubric_panel_judge_model") or "").strip()
    if not target:
        raise LicIdeCliJudgeConfigError("ide_cli_judging.rubric_panel_judge_model missing.")
    backups = [str(m).strip() for m in (cfg.get("rubric_panel_quota_backups") or []) if str(m).strip()]
    prof = _single_draft_v3_profile()
    payload = {"channel": channel, "recipient_class": recipient_class, "company_name": company_name, "subject": subject, "body": body, "verified_facts": list(verified_facts)}
    prompt = f"{render_v3_rubric_prompt(prof)}\n\nCANDIDATE_DRAFT:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n"
    return _run_with_failover(prompt=prompt, profile=prof, primary_model=target, backup_models=backups, forbidden_bases={_slug_base(target)}, slot="rubric_panel", pass_threshold=pass_threshold, agy_bin=agy_bin, environ=environ)
