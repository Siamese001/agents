from __future__ import annotations

from apps_rg.runtime.judges.headline_x1d import HEADLINE_RUBRIC


def test_headline_rubric_includes_adversarial_review_lens() -> None:
    rubric = HEADLINE_RUBRIC.lower()
    assert "head of talent acquisition" in rubric
    assert "ai-authenticity" in rubric
    assert "buzzword soup" in rubric
    assert "adversarial review lens" in rubric


def test_headline_rubric_accepts_every_explicit_active_packet_id_prefix() -> None:
    rubric = HEADLINE_RUBRIC.lower()
    assert "reb_*" in rubric
    assert "skill_*" in rubric
    assert "never use an id prefix as a reason to reject evidence" in rubric
