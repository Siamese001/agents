from __future__ import annotations

import pytest

from apps_rg.evals.owner_solo.final_competency_review_ui import (
    FinalCompetencyReviewError,
    append_reviews,
    render_html,
    selected_rationale,
    write_selection_receipt,
)


def _candidate() -> dict[str, object]:
    return {
        "bundle_id": "bundle-a",
        "resume_line": "Engineering Leadership & Operating Model: executive operating cadence",
    }


def test_final_competency_event_preserves_explicit_rating(tmp_path) -> None:
    events = append_reviews(tmp_path / "events.jsonl", [_candidate()], [{"bundle_id": "bundle-a", "grade": 3, "rationale": "Core competency for this target role"}])
    assert events[0]["grade"] == 3
    assert events[0]["retrieval_qrel"] is False


def test_final_competency_rejects_empty_or_unknown_rationale() -> None:
    with pytest.raises(FinalCompetencyReviewError):
        selected_rationale("", "")


def test_final_competency_ui_does_not_show_evidence_fields() -> None:
    page = render_html([_candidate()], completed=0, total=12)
    assert "Action:" not in page
    assert "Scope:" not in page
    assert "Evidence:" not in page
    assert "Engineering Leadership &amp; Operating Model: executive operating cadence" in page


def test_selection_receipt_requires_the_complete_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "apps_rg.evals.owner_solo.final_competency_review_ui.load_final_competencies",
        lambda _root: [_candidate()],
    )
    ledger = tmp_path / "events.jsonl"
    append_reviews(
        ledger,
        [_candidate()],
        [{"bundle_id": "bundle-a", "grade": 3, "rationale": "Core competency for this target role"}],
    )
    receipt = write_selection_receipt(tmp_path, ledger, tmp_path / "selection.json")
    assert receipt["selected_competency_count"] == 1
    assert receipt["retrieval_qrels_created"] is False
