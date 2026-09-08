"""Apps RG binding for the source-controlled external-model token governor."""

from __future__ import annotations

from pathlib import Path

from apps_model_telemetry.token_budget_governor import (
    TokenBudgetPolicy,
    TokenBudgetReservation,
    reserve_token_budget,
)
from apps_rg.runtime.section_model_limits import runtime_limit_float, runtime_limit_int


def apps_rg_model_token_budget_policy() -> TokenBudgetPolicy:
    return TokenBudgetPolicy(
        chars_per_token_estimate=runtime_limit_int("model_token_governor.chars_per_token_estimate"),
        safety_multiplier=runtime_limit_float("model_token_governor.safety_multiplier"),
        max_input_tokens_per_attempt=runtime_limit_int(
            "model_token_governor.max_input_tokens_per_attempt"
        ),
        max_reserved_tokens_per_run=runtime_limit_int(
            "model_token_governor.max_reserved_tokens_per_run"
        ),
    )


def reserve_apps_rg_model_tokens(
    *,
    artifact_dir: Path | None,
    provider: str,
    model: str,
    request_digest: str,
    prompt_text: str,
    max_output_tokens: int,
    stage: str,
    section_id: str = "",
    run_id: str = "",
) -> TokenBudgetReservation:
    return reserve_token_budget(
        artifact_dir=artifact_dir,
        provider=provider,
        model=model,
        request_digest=request_digest,
        prompt_text=prompt_text,
        max_output_tokens=max_output_tokens,
        policy=apps_rg_model_token_budget_policy(),
        stage=stage,
        section_id=section_id,
        run_id=run_id,
    )


__all__ = ["apps_rg_model_token_budget_policy", "reserve_apps_rg_model_tokens"]
