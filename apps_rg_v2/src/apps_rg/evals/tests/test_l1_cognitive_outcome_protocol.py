"""Tests for the frozen L1 v2-control/v3-treatment outcome protocol."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from apps_rg.evals.l1_cognitive_outcome_protocol import (
    L1CognitiveOutcomeProtocolError,
    build_l1_cognitive_paired_shadow_receipt,
    load_l1_cognitive_outcome_protocol,
    paired_shadow_receipt_digest,
    validate_l1_cognitive_paired_shadow_receipt,
    write_l1_cognitive_paired_shadow_receipt,
)


def _digest(value: str) -> str:
    return "sha256:" + value * 64


def _pairs() -> list[dict[str, object]]:
    return [
        {
            "pair_id": "l1-cognitive-shadow-001",
            "frozen_input_digest": _digest("a"),
            "provider_model_config_digest": _digest("b"),
            "tool_config_digest": _digest("c"),
            "control": {
                "run_ref": "control/run_receipt.json",
                "run_id": "control-run-001",
                "l1_v2_capsule_digest": _digest("d"),
                "l1_cognitive_treatment_execution_digest": _digest("7"),
                "compiled_prompt_digest": _digest("e"),
                "output_digest": _digest("f"),
                "completion_status": "PASS",
            },
            "candidate": {
                "run_ref": "candidate/run_receipt.json",
                "run_id": "candidate-run-001",
                "l1_cognitive_plan_digest": _digest("1"),
                "l1_cognitive_advisory_digest": _digest("2"),
                "c0_outcome_set_digest": _digest("3"),
                "l1_cognitive_revision_set_digest": _digest("6"),
                "l1_cognitive_treatment_execution_digest": _digest("8"),
                "compiled_prompt_digest": _digest("4"),
                "output_digest": _digest("5"),
                "completion_status": "PASS",
            },
        }
    ]


def test_protocol_freezes_control_candidate_and_human_outcome_boundary() -> None:
    protocol = load_l1_cognitive_outcome_protocol()

    assert protocol["control"]["treatment_id"] == "l1_v2_control"
    assert protocol["candidate"]["treatment_id"] == "l1_cognitive_v3"
    assert protocol["paired_execution"]["automatic_promotion_forbidden"] is True
    assert protocol["human_review"]["human_labels_may_not_be_generated"] is True
    assert protocol["human_review"]["variant_assessment_fields"] == [
        "finished_resume_utility_score",
        "grounded_decision_ready",
        "unsupported_material_claim_count",
    ]
    assert protocol["human_review"]["adjudicated_measurements_required"] is True
    assert protocol["capability_review"]["source_bound"] is True
    assert protocol["capability_review"]["score_range"] == [0, 2]
    assert (
        protocol["capability_review"]["complete_protected_holdout_cohort_required"]
        is True
    )
    assert (
        protocol["capability_review"][
            "opaque_case_bindings_external_human_attestation_required"
        ]
        is True
    )
    assert protocol["capability_review"]["dimensions"] == [
        "goal_constraint_fidelity",
        "atomic_requirement_fidelity",
        "feasibility_plan_coherence",
        "critique_quality",
        "revision_quality",
    ]


def test_paired_shadow_receipt_preserves_attempts_without_claiming_outcomes(
    tmp_path: Path,
) -> None:
    protocol = load_l1_cognitive_outcome_protocol()
    pairs = _pairs()
    receipt = build_l1_cognitive_paired_shadow_receipt(
        protocol=protocol,
        pairs=pairs,
    )

    assert receipt["summary"] == {
        "attempt_count": 1,
        "completed_pair_count": 1,
        "all_attempts_preserved": True,
        "candidate_c0_outcome_before_pa_required": True,
        "run_bound_input_configuration_required": True,
    }
    assert receipt["outcomes"]["P1"]["status"] == "NOT_MEASURED"
    assert receipt["outcomes"]["P2"]["status"] == "NOT_MEASURED"
    assert receipt["authority"]["automatic_promotion"] is False
    path = write_l1_cognitive_paired_shadow_receipt(
        output_path=tmp_path / "paired_shadow.json",
        receipt=receipt,
        protocol=protocol,
        pairs=pairs,
    )
    assert json.loads(path.read_text(encoding="utf-8")) == receipt


def test_paired_shadow_receipt_rejects_redigested_or_human_labeled_rows() -> None:
    protocol = load_l1_cognitive_outcome_protocol()
    pairs = _pairs()
    receipt = build_l1_cognitive_paired_shadow_receipt(
        protocol=protocol,
        pairs=pairs,
    )
    tampered = copy.deepcopy(receipt)
    tampered["summary"]["completed_pair_count"] = 0
    tampered["receipt_digest"] = paired_shadow_receipt_digest(tampered)
    with pytest.raises(L1CognitiveOutcomeProtocolError, match="does not match"):
        validate_l1_cognitive_paired_shadow_receipt(
            tampered,
            protocol=protocol,
            pairs=pairs,
        )

    human_labeled = _pairs()
    human_labeled[0]["candidate"]["grade"] = "better"  # type: ignore[index]
    with pytest.raises(L1CognitiveOutcomeProtocolError, match="human judgment"):
        build_l1_cognitive_paired_shadow_receipt(
            protocol=protocol,
            pairs=human_labeled,
        )
