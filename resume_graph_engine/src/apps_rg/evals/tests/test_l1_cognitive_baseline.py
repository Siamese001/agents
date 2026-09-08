"""Tests for the source-bound W0 v1/v2 L1 cognition baseline."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps_rg.evals.l1_cognitive_baseline import (
    L1CognitiveBaselineError,
    build_l1_cognitive_development_baseline_receipt,
    development_baseline_digest,
    validate_l1_cognitive_development_baseline_receipt,
    write_l1_cognitive_development_baseline_receipt,
)
from apps_rg.evals.l1_cognitive_qa import load_development_corpus


def test_w0_baseline_runs_v1_and_v2_once_and_names_the_priority_slice(
    tmp_path: Path,
) -> None:
    corpus = load_development_corpus()
    receipt = build_l1_cognitive_development_baseline_receipt(corpus=corpus)

    assert receipt["summary"]["fixture_count"] == 4
    assert receipt["summary"]["baseline_runs_by_version"] == {"v1": 4, "v2": 4}
    assert (
        receipt["summary"]["dominant_failure_slice"]
        == "COMPOUND_AND_RELATION_DECOMPOSITION"
    )
    compound_case = next(
        row
        for row in receipt["cases"]
        if row["fixture_id"] == "l1-cognitive-atomic-and-v1"
    )
    assert compound_case["expected_relation"] == "AND"
    assert {row["code"] for row in compound_case["observations"]} >= {
        "V1_OBLIGATION_COALESCES_EXPECTED_ATOMS",
        "V2_PARENT_COALESCES_EXPECTED_ATOMS",
        "V1_V2_NO_EXPLICIT_RELATION_LEDGER",
        "V1_BROAD_MULTI_UNIT_TARGETING",
        "V1_V2_NO_PREEXECUTION_CRITIQUE_LEDGER",
        "V1_V2_NO_OBSERVED_OUTCOME_REVISION_LEDGER",
    }
    assert compound_case["source_span_digests"]
    assert receipt["authority"]["human_qualified"] is False
    assert receipt["assertions"]["does_not_measure_candidate_quality"] is True
    rendered = json.dumps(receipt, sort_keys=True)
    assert "Must lead AI strategy" not in rendered
    validate_l1_cognitive_development_baseline_receipt(receipt, corpus=corpus)

    path = write_l1_cognitive_development_baseline_receipt(
        output_path=tmp_path / "w0_baseline.json",
        receipt=receipt,
        corpus=corpus,
    )
    assert json.loads(path.read_text(encoding="utf-8")) == receipt


def test_w0_baseline_rejects_a_redigested_observation_change() -> None:
    corpus = load_development_corpus()
    receipt = build_l1_cognitive_development_baseline_receipt(corpus=corpus)
    tampered = copy.deepcopy(receipt)
    tampered["cases"][0]["priority_failure_slice"] = "BROAD_TARGETING"
    tampered["receipt_digest"] = development_baseline_digest(tampered)

    with pytest.raises(L1CognitiveBaselineError, match="does not match"):
        validate_l1_cognitive_development_baseline_receipt(
            tampered,
            corpus=corpus,
        )


def test_w0_baseline_rejects_an_unvalidated_in_memory_corpus() -> None:
    corpus = copy.deepcopy(load_development_corpus())
    corpus["cases"][0]["app_payload"]["target_role"] = "CTO"

    with pytest.raises(L1CognitiveBaselineError, match="development corpus is invalid"):
        build_l1_cognitive_development_baseline_receipt(corpus=corpus)
