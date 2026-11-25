"""Clean-Slate Judge v3 Runner for `apps_research` Company & Targeting Briefs (`<= 190L`).

Separates Stage A deterministic preflight (prompt injection, empty text, buzzwords,
missing source citations) from Stage B atomic binary evaluation (`YES` / `NO` +
verbatim `evidence_span` on `NO`) bound to `company_research_brief` profiles in
`config/governance/judge_rubrics_v3.json`. Emits `llm_judge_executed=False` and
`normalized_unit_score=None` when Stage A blocks or LLM execution is offline.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
import yaml

from apps_eval.graders.judge._core_governance_bridge import get_judge_ide_router_v3
from apps_eval.graders.judge.preflight_lint import PreflightLintReceipt, run_preflight_lint
from apps_eval.graders.judge.v3_evaluator import (
    JudgeV3SchemaError,
    JudgeV3Scorecard,
    build_skipped_v3_scorecard,
    build_v3_evaluation_bundle,
    build_v3_response_schema,
    parse_and_seal_v3_verdict,
)
from apps_eval.graders.judge.v3_registry import JudgeRubricRegistryV3

RESEARCH_JUDGE_TRANSPORT_ENV = "APPS_RESEARCH_JUDGE_TRANSPORT"
RESEARCH_JUDGE_TIMEOUT_ENV = "APPS_RESEARCH_IDE_CLI_JUDGE_TIMEOUT_S"
DEFAULT_RESEARCH_JUDGE_TIMEOUT_S = 240


def _default_research_judge_model_id() -> str:
    cfg_path = Path(__file__).resolve().parents[3] / "config" / "provider_profiles.yaml"
    if cfg_path.is_file():
        doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        pin = str(((doc.get("judge_models") or {}).get("standard") or {}).get("gemini_pro") or "").strip()
        if pin:
            return pin
    raise RuntimeError("Missing judge_models.standard.gemini_pro in config/provider_profiles.yaml")


def run_research_brief_preflight(
    brief_payload: Mapping[str, Any] | str,
    *,
    required_sources: Sequence[str] = (),
    max_words: int | None = 1200,
) -> PreflightLintReceipt:
    """Stage A zero-token deterministic preflight for Research company/targeting briefs."""
    return run_preflight_lint(
        brief_payload,
        required_grounding_ids=required_sources,
        enforce_anti_ai_filter=True,
        forbid_prompt_injection=True,
        max_words=max_words,
    )


def evaluate_research_brief_v3(
    *,
    artifact_id: str,
    brief_payload: Mapping[str, Any],
    profile_token: str = "company_research_brief:company_brief_synthesis",
    author_model_family: str = "anthropic",
    llm_raw_response: Mapping[str, Any] | str | None = None,
    judge_model_id: str | None = None,
    required_sources: Sequence[str] = (),
    artifact_path: Path | None = None,
    verify_verbatim_in: str | None = None,
) -> tuple[PreflightLintReceipt, JudgeV3Scorecard]:
    """Execute Stage A preflight followed by Stage B Judge v3 sealing (or honest SKIPPED_NO_LLM)."""
    reg = JudgeRubricRegistryV3.load()
    bundle, profile, _prompt = build_v3_evaluation_bundle(
        profile_token=profile_token,
        artifact_id=artifact_id,
        raw_input=brief_payload,
        author_model_family=author_model_family,
        registry=reg,
        artifact_path=artifact_path,
    )
    preflight = run_research_brief_preflight(brief_payload, required_sources=required_sources)
    if not preflight.passed:
        return preflight, build_skipped_v3_scorecard(
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            preflight_receipt=preflight,
        )
    if llm_raw_response is None:
        return preflight, build_skipped_v3_scorecard(
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            reason="SKIPPED_NO_LLM",
        )
    resolved_model = judge_model_id or _default_research_judge_model_id()
    scorecard = parse_and_seal_v3_verdict(
        llm_raw_response,
        bundle=bundle,
        profile=profile,
        rubric_sha256=reg.rubric_sha256,
        judge_model_id=resolved_model,
        artifact_disk_path=artifact_path,
        verify_verbatim_in=verify_verbatim_in,
    )
    return preflight, scorecard


def run_research_brief_ide_cli_judge(
    *,
    artifact_id: str,
    brief_payload: Mapping[str, Any],
    profile_token: str = "company_research_brief:company_brief_synthesis",
    author_model_family: str = "openai",
    required_sources: Sequence[str] = (),
    artifact_path: Path | None = None,
    agy_bin: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[PreflightLintReceipt, JudgeV3Scorecard]:
    """Execute keyless Antigravity IDE CLI (`agy -p`) Judge v3 for company or targeting briefs."""
    from infrastructure.sdks_mcps.agy_cli_transport import (
        AGY_CLI_ENV_VAR,
        AgyTransportError,
        ide_cli_ready,
        run_agy,
    )

    reg = JudgeRubricRegistryV3.load()
    bundle, profile, prompt = build_v3_evaluation_bundle(
        profile_token=profile_token,
        artifact_id=artifact_id,
        raw_input=brief_payload,
        author_model_family=author_model_family,
        registry=reg,
        artifact_path=artifact_path,
    )
    preflight = run_research_brief_preflight(brief_payload, required_sources=required_sources)
    if not preflight.passed:
        return preflight, build_skipped_v3_scorecard(
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            preflight_receipt=preflight,
        )
    from infrastructure.config.env_loader import snapshot_process_env

    env = snapshot_process_env() if environ is None else environ
    bin_path = str(agy_bin or env.get(AGY_CLI_ENV_VAR) or "")
    ok, _why = ide_cli_ready(bin_path or None)
    if not ok:
        return preflight, build_skipped_v3_scorecard(
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            reason="BLOCKED_IDE_CLI_UNAVAILABLE",
        )
    model_slug = _default_research_judge_model_id()
    effort = str(
        get_judge_ide_router_v3().select_ide_reasoning_effort(
            profile.archetype,
            assurance_tier=profile.assurance_tier,
            profile_reasoning=profile.reasoning_effort,
        )
    )
    raw_t = str(env.get(RESEARCH_JUDGE_TIMEOUT_ENV) or "").strip()
    timeout_s = int(raw_t) if raw_t.isdigit() and int(raw_t) > 0 else DEFAULT_RESEARCH_JUDGE_TIMEOUT_S
    try:
        res = run_agy(
            prompt,
            model=model_slug,
            json_schema=build_v3_response_schema(profile),
            effort=effort,
            timeout_s=timeout_s,
            agy_bin=bin_path,
        )
        raw_obj = res.structured_output if isinstance(res.structured_output, dict) else res.response
        scorecard = parse_and_seal_v3_verdict(
            raw_obj,
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            judge_model_id=res.model_reported or model_slug,
            artifact_disk_path=artifact_path,
            verify_verbatim_in=json.dumps(bundle.payload, ensure_ascii=False),
            conversation_id=res.conversation_id,
            usage=res.usage,
        )
        return preflight, scorecard
    except (AgyTransportError, JudgeV3SchemaError, ValueError):
        return preflight, build_skipped_v3_scorecard(
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            reason="BLOCKED_IDE_CLI_CALL_FAILED",
        )


__all__ = [
    "RESEARCH_JUDGE_TRANSPORT_ENV",
    "evaluate_research_brief_v3",
    "run_research_brief_ide_cli_judge",
    "run_research_brief_preflight",
]
