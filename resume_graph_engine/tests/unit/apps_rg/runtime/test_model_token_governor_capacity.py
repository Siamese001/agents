from __future__ import annotations

from apps_rg.runtime.model_token_governor import (
    apps_rg_model_token_budget_policy,
    reserve_apps_rg_model_tokens,
)


def test_required_executive_summary_panel_fits_governed_run_capacity(tmp_path) -> None:
    """Regression for Retry 19: the tenth required call needed ~253k reserved tokens."""
    policy = apps_rg_model_token_budget_policy()
    assert policy.max_reserved_tokens_per_run == 300_000

    # Approximate the observed finite path: one generation call followed by
    # four complete Gemini/OpenAI judge rounds. Each judge reserves the governed
    # 8,192-token hard output ceiling.
    reservations = []
    for index in range(10):
        reservations.append(
            reserve_apps_rg_model_tokens(
                artifact_dir=tmp_path,
                provider="openai" if index % 2 else "gemini",
                model=f"required-model-{index}",
                request_digest=f"request-{index}",
                prompt_text="x" * 47_000,
                max_output_tokens=8_192 if index else 4_096,
                stage="X1D" if index else "L2",
                section_id="executive_summary",
                run_id="capacity-regression",
            )
        )

    assert all(row.allowed for row in reservations)
    assert reservations[-1].prior_reserved_total_tokens < 300_000
    assert (
        reservations[-1].prior_reserved_total_tokens
        + reservations[-1].reserved_total_tokens
        <= 300_000
    )
