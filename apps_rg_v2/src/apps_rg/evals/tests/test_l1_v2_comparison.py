from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from apps_rg.evals.l1_v2_comparison import (
    L1V2ComparisonError,
    build_l1_v2_comparison,
    build_l1_v2_promotion_readiness,
    build_l1_v2_review_packet,
    comparison_digest,
    load_development_corpus,
    load_protected_holdout_commitment,
    promotion_readiness_digest,
    review_packet_digest,
    validate_external_protected_holdout,
    validate_l1_v2_comparison,
    validate_l1_v2_promotion_readiness,
    validate_l1_v2_review_packet,
    write_l1_v2_comparison,
    write_l1_v2_promotion_readiness,
    write_l1_v2_review_packet,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


def _keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return {
            str(key).lower()
            for key in value
        } | set().union(*(_keys(item) for item in value.values()))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return set().union(*(_keys(item) for item in value)) if value else set()
    return set()


def test_frozen_development_corpus_and_opaque_holdout_are_bound() -> None:
    corpus = load_development_corpus()
    holdout = load_protected_holdout_commitment()

    assert {case["scenario"] for case in corpus["cases"]} == {
        "STRAIGHTFORWARD",
        "COMPOUND",
        "CROSS_CUTTING",
        "UNKNOWN",
    }
    assert holdout["development_access"] == "DENIED"
    assert {row["scenario"] for row in holdout["commitments"]} == {
        "STALE_BRIEF",
        "CONFLICTING_CONSTRAINT",
        "ABSENT_CANDIDATE_EVIDENCE",
    }
    assert all(
        "app_payload" not in row
        and "fixture_conditions" not in row
        and "c0_evidence_items" not in row
        for row in holdout["commitments"]
    )

    with pytest.raises(L1V2ComparisonError, match="does not match commitment"):
        validate_external_protected_holdout([], commitment=holdout)


def test_comparison_is_source_bound_and_non_promoting() -> None:
    corpus = load_development_corpus()
    comparison = build_l1_v2_comparison(corpus)

    assert comparison["development_corpus"]["fixture_count"] == 4
    assert comparison["protected_holdout"]["results_present"] is False
    assert (
        comparison["metrics"]["requirement_extraction_and_typing"]
        ["measurement_status"]
        == "SOURCE_BOUND_DETERMINISTIC_FIXTURE_ASSERTIONS"
    )
    assert (
        comparison["metrics"]["requirement_extraction_and_typing"]
        ["all_fixture_assertions_match"]
        is True
    )
    assert comparison["metrics"]["c0_obligation_reconciliation"]["rate"] == 1.0
    assert (
        comparison["metrics"]["false_broad_mapping"]["measurement_status"]
        == "PROXY_ONLY_HUMAN_GROUND_TRUTH_REQUIRED"
    )
    assert comparison["promotion_authority"]["production_promotion_authorized"] is False
    rendered = json.dumps(comparison, sort_keys=True)
    assert "Synthetic product leadership evidence." not in rendered
    assert "quantum-superiority governance" not in rendered
    validate_l1_v2_comparison(comparison, corpus=corpus)


def test_review_intake_has_no_prefilled_human_judgments_and_readiness_is_blocked() -> None:
    comparison = build_l1_v2_comparison()
    packet = build_l1_v2_review_packet(comparison)
    readiness = build_l1_v2_promotion_readiness(comparison, packet)

    assert packet["review_items"]
    assert not {"grade", "label", "score", "verdict", "adjudication", "approval"} & _keys(
        packet["review_items"]
    )
    assert packet["human_review_authority"]["human_grades_present"] is False
    assert readiness["status"] == "NOT_AUTHORIZED"
    assert readiness["promotion_authority"]["production_promotion_authorized"] is False
    assert readiness["promotion_authority"]["critical_requirement_fail_closed_enforcement_enabled"] is False
    validate_l1_v2_review_packet(packet, comparison=comparison)
    validate_l1_v2_promotion_readiness(
        readiness, comparison=comparison, review_packet=packet
    )


def test_tampering_is_rejected_even_if_self_digest_is_recomputed() -> None:
    comparison = build_l1_v2_comparison()
    altered_comparison = copy.deepcopy(comparison)
    altered_comparison["technical_thresholds_met"] = not bool(
        altered_comparison["technical_thresholds_met"]
    )
    altered_comparison["comparison_digest"] = comparison_digest(altered_comparison)
    with pytest.raises(L1V2ComparisonError, match="does not match frozen corpus"):
        validate_l1_v2_comparison(altered_comparison)

    packet = build_l1_v2_review_packet(comparison)
    altered_packet = copy.deepcopy(packet)
    altered_packet["review_items"][0]["label"] = "approved"
    altered_packet["packet_digest"] = review_packet_digest(altered_packet)
    with pytest.raises(L1V2ComparisonError, match="does not match comparison receipt"):
        validate_l1_v2_review_packet(altered_packet, comparison=comparison)


def test_validated_receipts_write_to_caller_owned_paths(tmp_path: Path) -> None:
    corpus = load_development_corpus()
    comparison = build_l1_v2_comparison(corpus)
    packet = build_l1_v2_review_packet(comparison)
    readiness = build_l1_v2_promotion_readiness(comparison, packet)

    comparison_path = write_l1_v2_comparison(
        output_path=tmp_path / sr.FILENAME_L1_V2_COMPARISON,
        receipt=comparison,
        corpus=corpus,
    )
    packet_path = write_l1_v2_review_packet(
        output_path=tmp_path / sr.FILENAME_L1_V2_REVIEW_PACKET,
        packet=packet,
        comparison=comparison,
    )
    readiness_path = write_l1_v2_promotion_readiness(
        output_path=tmp_path / sr.FILENAME_L1_V2_PROMOTION_READINESS,
        receipt=readiness,
        comparison=comparison,
        review_packet=packet,
    )

    assert json.loads(comparison_path.read_text(encoding="utf-8")) == comparison
    assert json.loads(packet_path.read_text(encoding="utf-8")) == packet
    assert json.loads(readiness_path.read_text(encoding="utf-8")) == readiness
    assert readiness["readiness_digest"] == promotion_readiness_digest(readiness)
