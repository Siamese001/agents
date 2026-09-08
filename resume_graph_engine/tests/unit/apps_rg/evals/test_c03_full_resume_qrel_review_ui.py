"""Owner UI ledger tests use only explicit human grades and rationales."""

from __future__ import annotations

import pytest

from apps_rg.evals.owner_solo.c03_full_resume_qrel_review_ui import (
    FullResumeQrelReviewError,
    active_judgments,
    append_batch_judgments,
    canonical_sha256,
    render_batch_html,
    selected_rationale,
    ungraded_candidates,
)


PACKET_DIGEST = "a" * 64


def _candidate() -> dict[str, str]:
    return {
        "item_ref": "item-a",
        "candidate_ref": "candidate-a",
        "target_context": "Target role description: Senior AI leader",
        "resume_section": "Core Competencies",
        "section_prompt": "How useful is this evidence?",
        "evidence_cluster_text": "Action: Built an agentic AI platform. Scope: Enterprise. Evidence: Source-backed delivery.",
    }


def test_batch_appends_only_explicit_owner_grade_and_rationale(tmp_path) -> None:
    ledger = tmp_path / "owner-events.jsonl"
    candidate = _candidate()
    events = append_batch_judgments(
        ledger,
        [candidate],
        [
            {
                "item_ref": candidate["item_ref"],
                "candidate_ref": candidate["candidate_ref"],
                "grade": 2,
                "rationale": "Relevant source material for this section",
            }
        ],
        packet_manifest_sha256=PACKET_DIGEST,
    )

    assert events[0]["relevance_grade"] == 2
    assert events[0]["raw_human_rationale"] == "Relevant source material for this section"
    assert events[0]["qrel_finalized"] is False
    assert events[0]["event_digest"]


def test_duplicate_candidate_return_fails_closed(tmp_path) -> None:
    ledger = tmp_path / "owner-events.jsonl"
    candidate = _candidate()
    return_row = {
        "item_ref": candidate["item_ref"],
        "candidate_ref": candidate["candidate_ref"],
        "grade": 1,
        "rationale": "Transferable, but indirect or too generic for this section",
    }
    append_batch_judgments(
        ledger, [candidate], [return_row], packet_manifest_sha256=PACKET_DIGEST
    )
    with pytest.raises(FullResumeQrelReviewError, match="already graded"):
        append_batch_judgments(
            ledger, [candidate], [return_row], packet_manifest_sha256=PACKET_DIGEST
        )


def test_other_rationale_requires_a_human_note() -> None:
    with pytest.raises(FullResumeQrelReviewError, match="requires your note"):
        selected_rationale("Other — I added my own note", "")
    assert selected_rationale("Other — I added my own note", "Needs company specificity") == (
        "Other — I added my own note\nHuman note: Needs company specificity"
    )


def test_correction_requires_exact_prior_event_reference() -> None:
    initial_unsigned = {
        "schema_version": "apps_rg.owner_solo_full_resume_qrel_review_event.v1",
        "event_id": "event-1",
        "event_type": "OWNER_EXPLICIT_QREL_GRADE",
        "recorded_at_utc": "2026-08-04T00:00:00Z",
        "owner_identity_ref": "human-reviewer://amit-owner",
        "packet_manifest_sha256": PACKET_DIGEST,
        "item_ref": "item-a",
        "candidate_ref": "candidate-a",
        "relevance_grade": 1,
        "raw_human_rationale": "Transferable, but indirect or too generic for this section",
        "prior_event_id": None,
        "reviewer_visible_packet_only": True,
        "qrel_finalized": False,
        "release_authorizing": False,
    }
    initial = {**initial_unsigned, "event_digest": canonical_sha256(initial_unsigned)}
    correction_unsigned = {
        **initial_unsigned,
        "event_id": "event-2",
        "event_type": "OWNER_QREL_CORRECTION",
        "relevance_grade": 3,
        "raw_human_rationale": "Direct, core source material for this target and section",
        "prior_event_id": "event-1",
    }
    correction = {
        **correction_unsigned,
        "event_digest": canonical_sha256(correction_unsigned),
    }
    active = active_judgments(
        [initial, correction],
        allowed_keys={("item-a", "candidate-a")},
        packet_manifest_sha256=PACKET_DIGEST,
    )
    assert active[("item-a", "candidate-a")]["relevance_grade"] == 3


def test_rendered_page_never_exposes_server_side_references() -> None:
    page = render_batch_html([_candidate()], completed=0, total=600)
    assert "item-a" not in page
    assert "candidate-a" not in page
    assert "frozen_rank" not in page
    assert "similarity" not in page
    assert len(ungraded_candidates([_candidate()], [], packet_manifest_sha256=PACKET_DIGEST)) == 1
