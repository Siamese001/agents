"""Unit tests for multi-touch sequence planner."""

from apps_lic.pipeline.touch_sequence import TouchSequencePlanner


def test_touch_sequence_planner_generates_3_touch_cadence(sample_candidate, sample_opportunity):
    planner = TouchSequencePlanner()
    seq = planner.plan_sequence(sample_candidate, sample_opportunity)

    assert len(seq.touches) == 3
    assert seq.touches[0].day_offset == 0
    assert seq.touches[1].day_offset == 4
    assert seq.touches[2].day_offset == 10

    # Ensure Day 1 and Day 4 use grounded facts
    assert len(seq.touches[0].draft.grounded_facts_used) == 1
    assert len(seq.touches[1].draft.grounded_facts_used) == 1

    # Ensure all drafts conclude with questions
    for t in seq.touches:
        assert t.draft.body.strip().endswith("?")
