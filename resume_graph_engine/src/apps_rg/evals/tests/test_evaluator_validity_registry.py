from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.evaluator_validity_registry import (
    REQUIRED_GRADERS,
    validate_evaluator_registry,
    wilson_upper_bound,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "evaluator_validity_registry.v1.schema.json"
REGISTRY_PATH = EVALS_ROOT / "evaluator_validity_registry.v1.json"


def _registry() -> dict[str, object]:
    return deepcopy(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _validated_card(card: dict[str, object]) -> None:
    card["validation_status"] = "VALIDATED"
    card["mutation_suite"] = {"status": "COMPLETE", "version": "mutation.v1"}
    card["human_pilot"] = {
        "status": "COMPLETE",
        "receipt_digest": "sha256:external-pilot",
        "sample_count": 400,
        "false_pass_count": 0,
        "false_fail_count": 0,
        "synthetic_human_labels_created": False,
    }
    card["thresholds"] = {
        "critical_false_pass_upper_bound_max": 0.02,
        "false_fail_upper_bound_max": 0.02,
        "confidence_level": 0.95,
    }


def test_schema_and_tracked_registry_keep_every_unvalidated_grader_not_measured() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_registry())

    summary = validate_evaluator_registry()

    assert summary["status"] == "NOT_MEASURED"
    assert [row["grader_id"] for row in summary["grader_results"]] == list(
        REQUIRED_GRADERS
    )
    assert all(row["status"] == "NOT_MEASURED" for row in summary["grader_results"])
    assert summary["authority"]["release_authorizing"] is False


def test_validated_cards_compute_wilson_bounds_but_remain_non_authorizing(
    tmp_path: Path,
) -> None:
    registry = _registry()
    cards = registry["cards"]
    assert isinstance(cards, list)
    for card in cards:
        assert isinstance(card, dict)
        _validated_card(card)
    path = tmp_path / "validated.json"
    _write(path, registry)

    summary = validate_evaluator_registry(path)

    assert summary["status"] == "PASS"
    assert summary["authority"] == {
        "human_qualified": False,
        "release_authorizing": False,
        "production_authorizing": False,
    }
    assert all(
        row["metrics"]["critical_false_pass_upper_bound"]
        <= 0.02
        for row in summary["grader_results"]
    )


def test_false_pass_bound_and_synthetic_labels_fail_closed(tmp_path: Path) -> None:
    registry = _registry()
    cards = registry["cards"]
    assert isinstance(cards, list) and isinstance(cards[0], dict)
    _validated_card(cards[0])
    pilot = cards[0]["human_pilot"]
    assert isinstance(pilot, dict)
    pilot["false_pass_count"] = 3
    path = tmp_path / "false-pass.json"
    _write(path, registry)
    false_pass = validate_evaluator_registry(path)
    assert false_pass["status"] == "FAIL"
    assert "EVALUATOR_FALSE_PASS_BOUND_FAILED_G1_RETRIEVAL" in false_pass[
        "failure_reasons"
    ]

    synthetic = _registry()
    synthetic_cards = synthetic["cards"]
    assert isinstance(synthetic_cards, list) and isinstance(synthetic_cards[0], dict)
    synthetic_pilot = synthetic_cards[0]["human_pilot"]
    assert isinstance(synthetic_pilot, dict)
    synthetic_pilot["synthetic_human_labels_created"] = True
    synthetic_path = tmp_path / "synthetic.json"
    _write(synthetic_path, synthetic)
    synthetic_result = validate_evaluator_registry(synthetic_path)
    assert synthetic_result["status"] == "BLOCKED"
    assert "EVALUATOR_SYNTHETIC_HUMAN_LABELS_FORBIDDEN" in synthetic_result[
        "blocking_reasons"
    ]


def test_p1_and_p2_assemblers_cannot_escape_evaluator_validity_coverage(
    tmp_path: Path,
) -> None:
    registry = _registry()
    cards = registry["cards"]
    assert isinstance(cards, list)
    registry["cards"] = [
        card
        for card in cards
        if isinstance(card, dict)
        and card.get("grader_id") != "P2_PIPELINE_ATTEMPT_LEDGER"
    ]
    path = tmp_path / "missing-p2-assembler.json"
    _write(path, registry)

    result = validate_evaluator_registry(path)

    assert result["status"] == "BLOCKED"
    assert "EVALUATOR_REGISTRY_COVERAGE_INVALID" in result["blocking_reasons"]


def test_wilson_bound_is_conservative_for_zero_observed_false_passes() -> None:
    assert wilson_upper_bound(errors=0, observations=400, confidence_level=0.95) > 0
