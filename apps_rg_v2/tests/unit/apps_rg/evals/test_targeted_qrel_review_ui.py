from __future__ import annotations

import json

import pytest

from apps_rg.evals.owner_solo.targeted_qrel_review_ui import (
    TargetedReviewError,
    active_judgments,
    append_batch_judgments,
    canonical_sha256,
    prior_confirmed_candidate_keys,
    render_batch_html,
    selected_rationale,
)


def _candidate() -> dict[str, str]:
    return {"item_ref": "item-a", "candidate_ref": "candidate-a", "action": "Led strategy", "scope": "Enterprise", "evidence": "Measured result", "evidence_cluster_text": "ignored"}


def test_batch_appends_only_explicit_human_grades(tmp_path) -> None:
    ledger = tmp_path / "events.jsonl"
    events = append_batch_judgments(ledger, [_candidate()], [{**_candidate(), "grade": 2, "rationale": "Relevant enterprise strategy evidence"}])
    assert events[0]["relevance_grade"] == 2
    assert events[0]["raw_human_rationale"] == "Relevant enterprise strategy evidence"
    assert "event_digest" in events[0]


def test_duplicate_targeted_candidate_fails_closed(tmp_path) -> None:
    ledger = tmp_path / "events.jsonl"
    submission = [{**_candidate(), "grade": 1, "rationale": "Some context"}]
    append_batch_judgments(ledger, [_candidate()], submission)
    with pytest.raises(TargetedReviewError, match="already graded"):
        append_batch_judgments(ledger, [_candidate()], submission)


def test_invalid_ledger_digest_fails_closed() -> None:
    event = {"schema_version": "apps_rg.owner_solo_targeted_qrel_event.v1", "event_id": "a", "event_type": "OWNER_EXPLICIT_QREL_GRADE", "owner_identity_ref": "human-reviewer://amit-owner", "item_ref": "item-a", "candidate_ref": "candidate-a", "relevance_grade": 0, "raw_human_rationale": "No fit", "event_digest": "bad"}
    with pytest.raises(TargetedReviewError, match="invalid digest"):
        active_judgments([event], {("item-a", "candidate-a")})


def test_rendered_ui_does_not_leak_internal_candidate_ref() -> None:
    page = render_batch_html([_candidate()], completed=3, total=22)
    assert "candidate-a" not in page
    assert "item-a" not in page
    assert "frozen rank" not in page.lower()


def test_selected_rationale_is_explicit_human_input() -> None:
    assert selected_rationale("Generic; does not distinguish this candidate", "") == "Generic; does not distinguish this candidate"
    assert selected_rationale("Only contextual or transferable", "Useful technology context") == "Only contextual or transferable\nHuman note: Useful technology context"


def test_prior_owner_confirmation_removes_candidate_from_queue(tmp_path) -> None:
    unsigned = {
        "schema_version": "apps_rg.owner_solo_prior_label_link_event.v1",
        "event_type": "OWNER_CONFIRMED_SAME_UNDERLYING_EVIDENCE",
        "owner_identity_ref": "human-reviewer://amit-owner",
        "grade_reused_verbatim": True,
        "qrel_created": False,
        "prior_label": {"grade": 2, "rationale": "Relevant evidence"},
        "frozen_candidate": {"candidate_ref": "candidate-a"},
    }
    ledger = tmp_path / "prior.jsonl"
    ledger.write_text(json.dumps({**unsigned, "event_digest": canonical_sha256(unsigned)}) + "\n", encoding="utf-8")
    assert prior_confirmed_candidate_keys(ledger, [_candidate()]) == {("item-a", "candidate-a")}
