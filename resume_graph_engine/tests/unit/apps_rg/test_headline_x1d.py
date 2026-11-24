"""Contract tests for Clean-Slate Judge v3 headline rubric (`resume_sections:headline`)."""
from __future__ import annotations

from apps_rg.runtime.judges.headline_x1d import HEADLINE_RUBRIC, JUDGE_RUBRIC_VERSION
from apps_rg.runtime.judges.v3_section_judge import DEFAULT_THRESHOLD


def test_headline_rubric_v3_atomic_checks_and_word_budget() -> None:
    rubric = HEADLINE_RUBRIC.lower()
    assert JUDGE_RUBRIC_VERSION == "headline_judge_v3"
    assert DEFAULT_THRESHOLD == 0.80
    assert "source_fact_grounding" in rubric
    assert "no_target_as_experience" in rubric
    assert "target_mandate_alignment" in rubric
    assert "natural_executive_clarity" in rubric
    assert len(HEADLINE_RUBRIC.split()) <= 300


def test_headline_rubric_v3_forbids_title_inflation_and_buzzword_stuffing() -> None:
    rubric = HEADLINE_RUBRIC.lower()
    assert "title inflation" in rubric
    assert "buzzword stuffing" in rubric or "keyword stuffing" in rubric
