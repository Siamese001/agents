"""Keyless IDE CLI transport adapter for Outreach Engine X1D proof judges and ExecutiveOutreachJudgePanel.

Mirrors `apps_rg` ADR-087 fail-closed semantics using canonical `infrastructure.sdks_mcps.agy_cli_transport`:
  * Strips API keys and denies all tools via session-only `--settings`.
  * Enforces drafter-judge maker orthogonality and Slot 1 != Slot 2 model diversity.
  * Routes 429 quota failures through governed `quota_backup_*` pins with cooldown tracking.
  * Never returns a passing score without a real `conversation_id` and `usage.total_tokens > 0`.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

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


OUTREACH_X1D_JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["score", "passed", "dimension_scores", "rationale", "violations"],
    "properties": {
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "passed": {"type": "boolean"},
        "dimension_scores": {
            "type": "object",
            "additionalProperties": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "rationale": {"type": "string"},
        "violations": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}

OUTREACH_PANEL_JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["composite_score", "passed", "lens_scores", "feedback", "remediation_hints"],
    "properties": {
        "composite_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "passed": {"type": "boolean"},
        "lens_scores": {
            "type": "object",
            "additionalProperties": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "feedback": {"type": "array", "items": {"type": "string"}},
        "remediation_hints": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}


@dataclass(frozen=True)
class LicIdeCliJudgeResult:
    """Model-backed or fail-closed BLOCKED judge evaluation receipt from headless `agy -p`."""

    slot: str
    model_requested: str
    model_reported: str
    provider_family: str
    transport: str = "ide_cli"
    evaluator_mode: str = "MODEL_BACKED"
    llm_judge_executed: bool = True
    provider_blocked: bool = False
    score: float = 0.0
    passed: bool = False
    dimension_scores: dict[str, float] = field(default_factory=dict)
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
            "passed": self.passed,
            "dimension_scores": {k: round(float(v), 4) for k, v in self.dimension_scores.items()},
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
    profiles = OutreachModelRegistry.get_profiles(config_path)
    cfg = profiles.get("ide_cli_judging") or {}
    return dict(cfg) if isinstance(cfg, Mapping) else {}


def resolve_lic_judge_transport(
    explicit_transport: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    config_path: Path | str | None = None,
) -> str:
    """Resolve Outreach judge transport: explicit > APPS_LIC_JUDGE_TRANSPORT > deterministic default for offline unit calls."""
    if explicit_transport is not None and str(explicit_transport).strip():
        val = str(explicit_transport).strip().lower()
    else:
        env = os.environ if environ is None else environ
        env_val = str(env.get(LIC_JUDGE_TRANSPORT_ENV) or "").strip().lower()
        val = env_val or "deterministic"
    if val not in _VALID_TRANSPORTS:
        raise LicIdeCliJudgeConfigError(f"Unknown Outreach judge transport {val!r}; expected {sorted(_VALID_TRANSPORTS)}")
    _ = config_path
    return val


def resolve_lic_ide_judge_slots(
    drafter_family: str = "anthropic",
    *,
    config_path: Path | str | None = None,
) -> tuple[str, str, list[str], list[str]]:
    """Return `(primary_model, secondary_model, primary_backups, secondary_backups)` with maker diversity."""
    cfg = _judging_cfg(config_path)
    maker = OutreachModelRegistry.normalize_provider_family(drafter_family or "anthropic")
    primary = str(cfg.get("primary_judge_model") or "").strip()
    if not primary:
        raise LicIdeCliJudgeConfigError("ide_cli_judging.primary_judge_model is missing from provider_profiles.yaml.")
    second_map = cfg.get("second_judge_by_writer_maker") or {}
    secondary = str((second_map.get(maker) if isinstance(second_map, Mapping) else "") or "").strip()
    if not secondary:
        raise LicIdeCliJudgeConfigError(
            f"ide_cli_judging.second_judge_by_writer_maker has no entry for writer maker {maker!r}."
        )
    if _slug_base(primary) == _slug_base(secondary):
        raise LicIdeCliJudgeConfigError(f"Primary ({primary}) and secondary ({secondary}) IDE judge bases must differ.")
    p_backups = [str(m).strip() for m in (cfg.get("quota_backup_primary_judge") or []) if str(m).strip()]
    s_map = cfg.get("quota_backup_second_judge_by_writer_maker") or {}
    s_backups = [
        str(m).strip()
        for m in ((s_map.get(maker) if isinstance(s_map, Mapping) else []) or [])
        if str(m).strip()
    ]
    return primary, secondary, p_backups, s_backups


def _timeout_s(environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    raw = str(env.get(LIC_JUDGE_TIMEOUT_ENV) or "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_LIC_JUDGE_TIMEOUT_S


def _extract_structured_payload(raw_structured: Any, raw_response: str) -> dict[str, Any]:
    if isinstance(raw_structured, dict):
        return raw_structured
    text = str(raw_response or "").strip()
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Judge response JSON must be an object.")
    return parsed


def _build_x1d_prompt(packet_dict: Mapping[str, Any], rubric: Mapping[str, Any], slot: str) -> str:
    return (
        "You are an independent fail-closed proof judge for executive outreach sequences.\n"
        f"Judge slot: {slot}\n"
        "Grade ONLY the target-free packet below against the rubric dimensions on a 0.0 to 1.0 scale.\n"
        "Flag any laundered opportunity metric, unverified candidate metric, cross-touch fact_id collision, "
        "undefined acronym, fake warmth, spam urgency, or subordinate tone as a violation and set passed=false.\n"
        "Return strict JSON matching the provided schema.\n\n"
        f"RUBRIC:\n{json.dumps(dict(rubric), indent=2, sort_keys=True)}\n\n"
        f"GRADE_ONLY_PACKET:\n{json.dumps(dict(packet_dict), indent=2, sort_keys=True)}\n"
    )


def _build_panel_prompt(
    *,
    subject: str,
    body: str,
    channel: str,
    recipient_class: str,
    verified_facts: Sequence[str],
    company_name: str,
    rubric: Mapping[str, Any],
) -> str:
    payload = {
        "channel": channel,
        "recipient_class": recipient_class,
        "company_name": company_name,
        "subject": subject,
        "body": body,
        "verified_facts": list(verified_facts),
    }
    return (
        "You are an executive outreach 6-lens rubric judge.\n"
        "Score each lens (lens1_altitude, lens2_grounding, lens3_resonance, lens4_cta, "
        "lens5_anti_spam, lens6_constraints) on a 0.0 to 1.0 scale and return strict JSON.\n\n"
        f"RUBRIC:\n{json.dumps(dict(rubric), indent=2, sort_keys=True)}\n\n"
        f"CANDIDATE_DRAFT:\n{json.dumps(payload, indent=2, sort_keys=True)}\n"
    )


def _run_with_failover(
    *,
    prompt: str,
    primary_model: str,
    backup_models: Sequence[str],
    forbidden_bases: set[str],
    json_schema: dict[str, Any],
    slot: str,
    pass_threshold: float,
    agy_bin: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> LicIdeCliJudgeResult:
    env = os.environ if environ is None else environ
    bin_path = str(agy_bin or env.get(AGY_CLI_ENV_VAR) or "")
    ok, why = ide_cli_ready(bin_path or None)
    if not ok:
        return LicIdeCliJudgeResult(
            slot=slot,
            model_requested=primary_model,
            model_reported="",
            provider_family=OutreachModelRegistry.normalize_provider_family(primary_model),
            evaluator_mode="BLOCKED_PROVIDER_UNAVAILABLE",
            llm_judge_executed=False,
            provider_blocked=True,
            score=0.0,
            passed=False,
            rationale=f"IDE CLI judge unavailable: {why}",
            violations=(f"IDE_CLI_UNAVAILABLE:{why}",),
            exact_provider_error=why,
        )

    candidates: list[str] = [primary_model]
    for bm in backup_models:
        if bm and _slug_base(bm) not in forbidden_bases and bm not in candidates:
            candidates.append(bm)

    ordered = [m for m in candidates if not is_agy_model_quota_cooled_down(m)] or list(candidates)
    attempted: list[str] = []
    last_err = ""

    for model_slug in ordered:
        attempted.append(model_slug)
        try:
            agy_res = run_agy(
                prompt,
                model=model_slug,
                json_schema=json_schema,
                timeout_s=_timeout_s(env),
                agy_bin=bin_path,
            )
        except AgyTransportError as exc:
            last_err = str(exc)
            if is_agy_quota_error(exc):
                mark_agy_model_quota_exhausted(model_slug, last_err)
                continue
            return LicIdeCliJudgeResult(
                slot=slot,
                model_requested=primary_model,
                model_reported=model_slug,
                provider_family=OutreachModelRegistry.normalize_provider_family(model_slug),
                evaluator_mode="BLOCKED_PROVIDER_UNAVAILABLE",
                llm_judge_executed=False,
                provider_blocked=True,
                score=0.0,
                passed=False,
                rationale=f"IDE CLI judge call failed: {last_err}",
                violations=(f"IDE_CLI_CALL_FAILED:{last_err[:160]}",),
                exact_provider_error=last_err,
                quota_failover_attempts=tuple(attempted),
            )

        try:
            parsed = _extract_structured_payload(agy_res.structured_output, agy_res.response)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return LicIdeCliJudgeResult(
                slot=slot,
                model_requested=primary_model,
                model_reported=agy_res.model_reported,
                provider_family=OutreachModelRegistry.normalize_provider_family(agy_res.model_reported),
                evaluator_mode="BLOCKED_SCHEMA_INVALID",
                llm_judge_executed=True,
                provider_blocked=True,
                score=0.0,
                passed=False,
                rationale=f"Malformed IDE judge JSON output: {exc}",
                violations=(f"IDE_CLI_SCHEMA_INVALID:{exc}",),
                conversation_id=agy_res.conversation_id,
                usage=dict(agy_res.usage),
                exact_provider_error=str(exc),
                quota_failover_attempts=tuple(attempted),
            )

        score_val = float(parsed.get("score", parsed.get("composite_score", 0.0)))
        score_clamped = round(max(0.0, min(1.0, score_val)), 4)
        dims_raw = parsed.get("dimension_scores", parsed.get("lens_scores", {}))
        dims = (
            {str(k): round(max(0.0, min(1.0, float(v))), 4) for k, v in dims_raw.items()}
            if isinstance(dims_raw, Mapping)
            else {}
        )
        raw_viols = parsed.get("violations", parsed.get("feedback", []))
        viols = tuple(str(v).strip() for v in (raw_viols or ()) if str(v).strip())
        passed_flag = bool(parsed.get("passed", False)) and score_clamped >= pass_threshold and not viols
        rationale = str(parsed.get("rationale") or ("; ".join(viols) if viols else "IDE CLI judge completed.")).strip()
        return LicIdeCliJudgeResult(
            slot=slot,
            model_requested=primary_model,
            model_reported=agy_res.model_reported,
            provider_family=OutreachModelRegistry.normalize_provider_family(agy_res.model_reported),
            evaluator_mode="MODEL_BACKED",
            llm_judge_executed=True,
            provider_blocked=False,
            score=score_clamped,
            passed=passed_flag,
            dimension_scores=dims,
            rationale=rationale,
            violations=viols,
            conversation_id=agy_res.conversation_id,
            usage=dict(agy_res.usage),
            quota_failover_attempts=tuple(attempted),
        )

    return LicIdeCliJudgeResult(
        slot=slot,
        model_requested=primary_model,
        model_reported=attempted[-1] if attempted else primary_model,
        provider_family=OutreachModelRegistry.normalize_provider_family(primary_model),
        evaluator_mode="BLOCKED_QUOTA_EXHAUSTED",
        llm_judge_executed=False,
        provider_blocked=True,
        score=0.0,
        passed=False,
        rationale=f"All IDE judge pins exhausted quota: {last_err}",
        violations=(f"IDE_CLI_QUOTA_EXHAUSTED:{last_err[:160]}",),
        exact_provider_error=last_err or "quota exhausted",
        quota_failover_attempts=tuple(attempted),
    )


def call_outreach_x1d_ide_cli_judge(
    *,
    packet_dict: Mapping[str, Any],
    rubric: Mapping[str, Any],
    slot: str,
    drafter_family: str = "anthropic",
    pass_threshold: float = 0.85,
    agy_bin: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
    config_path: Path | str | None = None,
) -> LicIdeCliJudgeResult:
    """Invoke one orthogonal slot (`primary` or `secondary`) of the Outreach X1D proof judge via keyless IDE CLI."""
    primary, secondary, p_backups, s_backups = resolve_lic_ide_judge_slots(
        drafter_family=drafter_family, config_path=config_path
    )
    if slot == "primary":
        target, backups, peer_base = primary, p_backups, _slug_base(secondary)
    elif slot == "secondary":
        target, backups, peer_base = secondary, s_backups, _slug_base(primary)
    else:
        raise LicIdeCliJudgeConfigError(f"Unknown Outreach X1D judge slot {slot!r}; expected 'primary' or 'secondary'.")
    prompt = _build_x1d_prompt(packet_dict, rubric, slot)
    return _run_with_failover(
        prompt=prompt,
        primary_model=target,
        backup_models=backups,
        forbidden_bases={_slug_base(target), peer_base},
        json_schema=OUTREACH_X1D_JUDGE_SCHEMA,
        slot=slot,
        pass_threshold=pass_threshold,
        agy_bin=agy_bin,
        environ=environ,
    )


def call_outreach_panel_ide_cli_judge(
    *,
    subject: str,
    body: str,
    channel: str,
    recipient_class: str,
    verified_facts: Sequence[str],
    company_name: str,
    rubric: Mapping[str, Any],
    pass_threshold: float = 0.75,
    agy_bin: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
    config_path: Path | str | None = None,
) -> LicIdeCliJudgeResult:
    """Invoke the keyless IDE CLI 6-lens Outreach rubric panel judge."""
    cfg = _judging_cfg(config_path)
    target = str(cfg.get("rubric_panel_judge_model") or "").strip()
    if not target:
        raise LicIdeCliJudgeConfigError("ide_cli_judging.rubric_panel_judge_model is missing from provider_profiles.yaml.")
    backups = [str(m).strip() for m in (cfg.get("rubric_panel_quota_backups") or []) if str(m).strip()]
    prompt = _build_panel_prompt(
        subject=subject,
        body=body,
        channel=channel,
        recipient_class=recipient_class,
        verified_facts=verified_facts,
        company_name=company_name,
        rubric=rubric,
    )
    return _run_with_failover(
        prompt=prompt,
        primary_model=target,
        backup_models=backups,
        forbidden_bases={_slug_base(target)},
        json_schema=OUTREACH_PANEL_JUDGE_SCHEMA,
        slot="rubric_panel",
        pass_threshold=pass_threshold,
        agy_bin=agy_bin,
        environ=environ,
    )


__all__ = [
    "DEFAULT_LIC_JUDGE_TIMEOUT_S",
    "LIC_JUDGE_TIMEOUT_ENV",
    "LIC_JUDGE_TRANSPORT_ENV",
    "LicIdeCliJudgeConfigError",
    "LicIdeCliJudgeResult",
    "OUTREACH_PANEL_JUDGE_SCHEMA",
    "OUTREACH_X1D_JUDGE_SCHEMA",
    "call_outreach_panel_ide_cli_judge",
    "call_outreach_x1d_ide_cli_judge",
    "resolve_lic_ide_judge_slots",
    "resolve_lic_judge_transport",
]
