"""Clean-Slate Judge v3 Runner for `agent_trace_and_calibration:agent_trajectory_governance` (`<= 190L`).

Separates Stage A deterministic trajectory preflight (unresolved errors, prompt injection,
empty trace) from Stage B atomic binary evaluation (`YES` / `NO` + verbatim `evidence_span`
on `NO`) over `RunTrace` tool-evidence packets via keyless Antigravity IDE CLI (`agy -p`).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping
import yaml

from apps_eval.contracts.schemas import RunTrace
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

TRAJECTORY_PROFILE_ID = "agent_trace_and_calibration:agent_trajectory_governance"
TRAJECTORY_JUDGE_TRANSPORT_ENV = "AGENTS_TRAJECTORY_JUDGE_TRANSPORT"


def _default_trajectory_judge_model_id(repo_root: Path | None = None) -> str:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    cfg_path = root / "config" / "provider_profiles.yaml"
    if cfg_path.is_file():
        doc = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        pin = str(((doc.get("judge_models") or {}).get("enhanced") or {}).get("gemini_pro") or "").strip()
        if pin:
            return pin
    return "antigravity-argon-high"


def build_trajectory_judge_packet(trace: RunTrace | Mapping[str, Any]) -> dict[str, Any]:
    """Project `RunTrace` into a cold-reader packet stripped of deterministic gate scores."""
    raw = trace.to_dict() if isinstance(trace, RunTrace) else dict(trace)
    return {
        "trace_id": str(raw.get("trace_id") or ""),
        "app_id": str(raw.get("app_id") or ""),
        "terminal_status": str(raw.get("terminal_status") or ""),
        "input_redacted": dict(raw.get("input_redacted") or {}),
        "output_summary": dict(raw.get("output_summary") or {}),
        "trajectory_steps": list(raw.get("trajectory_steps") or []),
    }


def run_trajectory_preflight(trace: RunTrace | Mapping[str, Any]) -> PreflightLintReceipt:
    """Stage A zero-token deterministic preflight for agent execution trajectories."""
    packet = build_trajectory_judge_packet(trace)
    return run_preflight_lint(
        json.dumps(packet, ensure_ascii=False, sort_keys=True),
        required_keys=("trace_id", "app_id", "terminal_status"),
        enforce_anti_ai_filter=False,
        forbid_prompt_injection=True,
    )


def evaluate_trajectory_governance_v3(
    trace: RunTrace | Mapping[str, Any],
    *,
    author_model_family: str = "anthropic",
    llm_raw_response: Mapping[str, Any] | str | None = None,
    judge_model_id: str | None = None,
    artifact_path: Path | None = None,
    verify_verbatim_in: str | None = None,
    repo_root: Path | None = None,
) -> tuple[PreflightLintReceipt, JudgeV3Scorecard]:
    """Execute Stage A preflight followed by Stage B Judge v3 sealing for `agent_trajectory_governance`."""
    packet = build_trajectory_judge_packet(trace)
    artifact_id = packet["trace_id"] or "trace-unknown"
    reg = JudgeRubricRegistryV3.load()
    bundle, profile, _prompt = build_v3_evaluation_bundle(
        profile_token=TRAJECTORY_PROFILE_ID,
        artifact_id=artifact_id,
        raw_input=packet,
        author_model_family=author_model_family,
        registry=reg,
        artifact_path=artifact_path,
        repo_root=repo_root,
    )
    preflight = run_trajectory_preflight(trace)
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
    resolved_model = judge_model_id or _default_trajectory_judge_model_id(repo_root)
    corpus = verify_verbatim_in if verify_verbatim_in is not None else json.dumps(bundle.payload, ensure_ascii=False)
    scorecard = parse_and_seal_v3_verdict(
        llm_raw_response,
        bundle=bundle,
        profile=profile,
        rubric_sha256=reg.rubric_sha256,
        judge_model_id=resolved_model,
        artifact_disk_path=artifact_path,
        verify_verbatim_in=corpus,
    )
    return preflight, scorecard


def run_trajectory_ide_cli_judge(
    trace: RunTrace | Mapping[str, Any],
    *,
    author_model_family: str = "anthropic",
    agy_bin: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> tuple[PreflightLintReceipt, JudgeV3Scorecard]:
    """Execute keyless `agy -p` Judge v3 evaluation for `agent_trajectory_governance`."""
    from infrastructure.sdks_mcps.agy_cli_transport import (
        AGY_CLI_ENV_VAR,
        AgyTransportError,
        ide_cli_ready,
        run_agy,
    )

    packet = build_trajectory_judge_packet(trace)
    reg = JudgeRubricRegistryV3.load()
    bundle, profile, prompt = build_v3_evaluation_bundle(
        profile_token=TRAJECTORY_PROFILE_ID,
        artifact_id=packet["trace_id"] or "trace-unknown",
        raw_input=packet,
        author_model_family=author_model_family,
        registry=reg,
        repo_root=repo_root,
    )
    preflight = run_trajectory_preflight(trace)
    if not preflight.passed:
        return preflight, build_skipped_v3_scorecard(
            bundle=bundle, profile=profile, rubric_sha256=reg.rubric_sha256, preflight_receipt=preflight
        )
    from infrastructure.config.env_loader import snapshot_process_env

    env = snapshot_process_env() if environ is None else environ
    bin_path = str(agy_bin or env.get(AGY_CLI_ENV_VAR) or "")
    ok, _ = ide_cli_ready(bin_path or None)
    if not ok:
        return preflight, build_skipped_v3_scorecard(
            bundle=bundle, profile=profile, rubric_sha256=reg.rubric_sha256, reason="BLOCKED_IDE_CLI_UNAVAILABLE"
        )
    model_slug = _default_trajectory_judge_model_id(repo_root)
    effort = str(
        get_judge_ide_router_v3().select_ide_reasoning_effort(
            profile.archetype, assurance_tier=profile.assurance_tier, profile_reasoning=profile.reasoning_effort
        )
    )
    try:
        res = run_agy(prompt, model=model_slug, json_schema=build_v3_response_schema(profile), effort=effort, timeout_s=240, agy_bin=bin_path)
        raw_obj = res.structured_output if isinstance(res.structured_output, dict) else res.response
        card = parse_and_seal_v3_verdict(
            raw_obj,
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            judge_model_id=res.model_reported or model_slug,
            verify_verbatim_in=json.dumps(bundle.payload, ensure_ascii=False),
            conversation_id=res.conversation_id,
            usage=res.usage,
        )
        return preflight, card
    except (AgyTransportError, JudgeV3SchemaError, ValueError):
        return preflight, build_skipped_v3_scorecard(
            bundle=bundle, profile=profile, rubric_sha256=reg.rubric_sha256, reason="BLOCKED_IDE_CLI_CALL_FAILED"
        )


__all__ = [
    "TRAJECTORY_JUDGE_TRANSPORT_ENV",
    "TRAJECTORY_PROFILE_ID",
    "build_trajectory_judge_packet",
    "evaluate_trajectory_governance_v3",
    "run_trajectory_ide_cli_judge",
    "run_trajectory_preflight",
]
