"""Tests for L1 v3 development calibration and holdout separation."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from apps_rg.evals.l1_cognitive_baseline import (
    build_l1_cognitive_development_baseline_receipt,
    development_baseline_digest,
)
from apps_rg.evals.l1_cognitive_calibration import (
    L1CognitiveCalibrationError,
    build_l1_cognitive_development_calibration_receipt,
    development_calibration_digest,
    holdout_commitment_path,
    validate_l1_cognitive_development_calibration_receipt,
    write_l1_cognitive_development_calibration_receipt,
)
from apps_rg.evals.l1_cognitive_qa import (
    fixture_input_digest,
    load_development_corpus,
    run_l1_cognitive_technical_qa,
)


def _holdout() -> dict[str, object]:
    return json.loads(holdout_commitment_path().read_text(encoding="utf-8"))


def _digest(value: object) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_development_calibration_is_technically_ready_but_not_human_qualified(
    tmp_path: Path,
) -> None:
    corpus = load_development_corpus()
    technical_qa = run_l1_cognitive_technical_qa(corpus)
    holdout = _holdout()
    receipt = build_l1_cognitive_development_calibration_receipt(
        corpus=corpus,
        technical_qa=technical_qa,
        holdout_commitment=holdout,
    )

    assert receipt["development"]["technical_status"] == "PASS"
    assert receipt["development"]["v1_v2_baseline_runs_by_version"] == {
        "v1": 4,
        "v2": 4,
    }
    assert (
        receipt["development"]["w1_priority_failure_slice"]
        == "COMPOUND_AND_RELATION_DECOMPOSITION"
    )
    assert receipt["protected_holdout"]["development_access"] == "DENIED"
    assert receipt["protected_holdout"]["input_digest_overlap_count"] == 0
    assert receipt["human_outcome_calibration"]["status"] == "NOT_MEASURED"
    assert receipt["authority"]["automatic_promotion"] is False
    rendered = json.dumps(receipt, sort_keys=True)
    assert "Must lead AI strategy" not in rendered

    path = write_l1_cognitive_development_calibration_receipt(
        output_path=tmp_path / "development_calibration.json",
        receipt=receipt,
        corpus=corpus,
        technical_qa=technical_qa,
        holdout_commitment=holdout,
    )
    assert json.loads(path.read_text(encoding="utf-8")) == receipt


def test_calibration_rejects_redigested_source_mismatch() -> None:
    corpus = load_development_corpus()
    technical_qa = run_l1_cognitive_technical_qa(corpus)
    holdout = _holdout()
    receipt = build_l1_cognitive_development_calibration_receipt(
        corpus=corpus,
        technical_qa=technical_qa,
        holdout_commitment=holdout,
    )
    tampered = copy.deepcopy(receipt)
    tampered["development"]["fixture_count"] = 99
    tampered["receipt_digest"] = development_calibration_digest(tampered)
    with pytest.raises(L1CognitiveCalibrationError, match="does not match"):
        validate_l1_cognitive_development_calibration_receipt(
            tampered,
            corpus=corpus,
            technical_qa=technical_qa,
            holdout_commitment=holdout,
        )


def test_calibration_fails_closed_when_development_input_overlaps_holdout() -> None:
    corpus = load_development_corpus()
    technical_qa = run_l1_cognitive_technical_qa(corpus)
    holdout = _holdout()
    commitments = holdout["commitments"]
    assert isinstance(commitments, list)
    first_case = corpus["cases"][0]
    assert isinstance(first_case, dict)
    first_commitment = commitments[0]
    assert isinstance(first_commitment, dict)
    first_commitment["source_input_digest"] = fixture_input_digest(first_case)
    holdout["commitment_digest"] = _digest(
        {key: value for key, value in holdout.items() if key != "commitment_digest"}
    )

    with pytest.raises(L1CognitiveCalibrationError, match="overlaps"):
        build_l1_cognitive_development_calibration_receipt(
            corpus=corpus,
            technical_qa=technical_qa,
            holdout_commitment=holdout,
        )


def test_calibration_rejects_a_redigested_w0_baseline_change() -> None:
    corpus = load_development_corpus()
    technical_qa = run_l1_cognitive_technical_qa(corpus)
    holdout = _holdout()
    baseline = build_l1_cognitive_development_baseline_receipt(corpus=corpus)
    baseline["summary"]["dominant_failure_slice"] = "BROAD_TARGETING"
    baseline["receipt_digest"] = development_baseline_digest(baseline)

    with pytest.raises(L1CognitiveCalibrationError, match="baseline receipt"):
        build_l1_cognitive_development_calibration_receipt(
            corpus=corpus,
            technical_qa=technical_qa,
            holdout_commitment=holdout,
            baseline_receipt=baseline,
        )
