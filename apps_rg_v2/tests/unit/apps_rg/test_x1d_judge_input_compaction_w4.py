"""W4 regression coverage for lossless X1D judge-input compaction."""

from __future__ import annotations

from apps_rg.runtime.judges.executive_summary_x1d import (
    JUDGE_COMPACT_OUTPUT,
    JUDGE_SCORE_SCHEMA,
    JUDGE_USER_PROMPT_RUBRIC,
    _build_judge_user_prompt,
    build_x1d_judge_system_prompt,
)
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import (
    EXEC_SUMMARY_RUBRIC_DIMENSION_IDS,
)


def test_x1d_output_contract_is_supplied_once_across_system_and_user_prompts() -> None:
    """W4 removes only a byte-for-byte duplicate, not an evaluation control."""
    system_prompt = build_x1d_judge_system_prompt(compact=True)
    user_prompt = _build_judge_user_prompt("S1. Evidence-backed summary.", [{"fact_id": "f1"}])
    combined_prompt = f"{system_prompt}\n\n{user_prompt}"

    assert JUDGE_COMPACT_OUTPUT in system_prompt
    assert JUDGE_COMPACT_OUTPUT not in user_prompt
    assert combined_prompt.count(JUDGE_COMPACT_OUTPUT) == 1

    # The user message still contains its complete evidence-evaluation rubric;
    # the score contract is supplied once by the system instruction.
    assert JUDGE_USER_PROMPT_RUBRIC in user_prompt
    assert JUDGE_SCORE_SCHEMA in system_prompt
    assert "RESUME_DISPLAY_TEXT:\nS1. Evidence-backed summary." in user_prompt
    assert 'CLAIM_LEDGER:\n[{"fact_id":"f1"}]' in user_prompt
    for dimension_id in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS:
        assert dimension_id in user_prompt
