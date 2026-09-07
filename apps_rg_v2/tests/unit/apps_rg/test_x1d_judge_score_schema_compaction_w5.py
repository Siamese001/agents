"""W5 regression coverage for lossless X1D score-schema compaction."""

from __future__ import annotations

from apps_rg.runtime.judges.executive_summary_x1d import (
    JUDGE_INPUT_PROMPT_VERSION,
    JUDGE_SCORE_SCHEMA,
    JUDGE_USER_PROMPT_RUBRIC,
    RUBRIC,
    _build_judge_user_prompt,
    build_x1d_judge_system_prompt,
)


def test_x1d_score_contract_is_system_owned_and_occurs_once_per_request() -> None:
    """The canonical rubric remains complete while the transmitted request is compact."""
    system_prompt = build_x1d_judge_system_prompt(compact=True)
    user_prompt = _build_judge_user_prompt("S1. Evidence-backed summary.", [])
    combined_prompt = f"{system_prompt}\n\n{user_prompt}"

    assert JUDGE_SCORE_SCHEMA in RUBRIC
    assert JUDGE_SCORE_SCHEMA not in JUDGE_USER_PROMPT_RUBRIC
    assert JUDGE_SCORE_SCHEMA in system_prompt
    assert JUDGE_SCORE_SCHEMA not in user_prompt
    assert combined_prompt.count(JUDGE_SCORE_SCHEMA) == 1
    assert JUDGE_INPUT_PROMPT_VERSION.endswith("_v2")
