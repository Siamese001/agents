from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps_rg.evals.l1_cognitive_qa import (
    L1CognitiveQaError,
    load_development_corpus,
    run_l1_cognitive_technical_qa,
)


def test_cognitive_technical_qa_passes_without_claiming_human_qualification() -> None:
    corpus = load_development_corpus()
    receipt = run_l1_cognitive_technical_qa(corpus)

    assert receipt["technical_status"] == "PASS"
    assert receipt["semantic_qualification_status"] == "HUMAN_REVIEW_REQUIRED"
    assert receipt["promotion_authorized"] is False
    assert receipt["assertions"] == {
        "does_not_create_human_labels": True,
        "does_not_access_protected_holdout": True,
        "does_not_authorize_product_promotion": True,
    }
    assert {row["fixture_id"] for row in receipt["results"]} == {
        "l1-cognitive-atomic-and-v1",
        "l1-cognitive-unknown-v1",
        "l1-cognitive-alternative-or-v1",
        "l1-cognitive-constraint-conflict-v1",
    }
    assert all(row["passed"] for row in receipt["results"])
    rendered = json.dumps(receipt, sort_keys=True)
    assert "Must lead AI strategy" not in rendered
    assert "quantum-superiority governance" not in rendered


def test_cognitive_qa_rejects_tampered_fixture_input(tmp_path: Path) -> None:
    corpus = copy.deepcopy(load_development_corpus())
    corpus["cases"][0]["app_payload"]["target_role"] = "CTO"
    path = tmp_path / "tampered-corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")

    with pytest.raises(L1CognitiveQaError, match="source digest mismatch"):
        load_development_corpus(path)


def test_cognitive_qa_rejects_prefilled_human_judgment(tmp_path: Path) -> None:
    corpus = copy.deepcopy(load_development_corpus())
    corpus["cases"][0]["human_label"] = "approved"
    path = tmp_path / "human-labeled-corpus.json"
    path.write_text(json.dumps(corpus), encoding="utf-8")

    with pytest.raises(L1CognitiveQaError, match="cannot prefill human judgment"):
        load_development_corpus(path)
