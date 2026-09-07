from __future__ import annotations

import json
import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.finished_resume_outcome import (
    OUTCOME_VERSION,
    GUARDRAIL_DIMENSIONS,
    runtime_lanes,
    validate_finished_resume_outcome,
)
from apps_rg.evals.whole_resume.p1_blind_utility import (
    LEDGER_VERSION,
    P1_DIMENSIONS,
    canonical_digest as review_canonical_digest,
    current_source_identity,
    file_sha256 as review_file_sha256,
    validate_p1_blind_review_ledger,
)


EVALS_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = EVALS_ROOT / "schemas" / "finished_resume_outcome.v1.schema.json"


def _outcome() -> dict[str, object]:
    return {
        "schema_version": OUTCOME_VERSION,
        "outcome_id": "P1",
        "required_lanes": list(runtime_lanes()),
        "review_protocol": {
            "blinded": True,
            "independent_primary_reviewers_per_pair": 2,
            "independent_adjudicators_per_pair": 1,
            "frozen_baseline_required": True,
            "candidate_preference_required": True,
            "utility_superiority_required": True,
        },
        "noninferiority_margins": {
            dimension: 0.1 for dimension in GUARDRAIL_DIMENSIONS
        },
        "p1_evidence": {
            "status": "COMPLETE",
            "pair_count": 12,
            "primary_review_count": 24,
            "adjudication_count": 12,
            "external_authority_receipt_sha256": "sha256:external-authority",
            "completed_review_receipt_digest": "sha256:completed-review",
            "utility_effect": 0.25,
            "utility_ci_lower": 0.03,
            "candidate_preference_count": 8,
            "baseline_preference_count": 3,
            "dimension_ci_lowers": {
                dimension: -0.05 for dimension in GUARDRAIL_DIMENSIONS
            },
            "blind_review_ledger_path": "",
            "blind_review_ledger_file_sha256": "",
            "synthetic_grades_created": False,
        },
        "owner_solo_status": "PRESENT_COMPLEMENTARY",
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sealed_review(payload: dict[str, object]) -> dict[str, object]:
    payload["record_digest"] = review_canonical_digest(payload)
    return payload


def _review_ledger_pair(pair_id: str, preference: str) -> dict[str, object]:
    packet_digest = _digest(f"packet-{pair_id}")
    reviews = [
        _sealed_review(
            {
                "review_id": f"{pair_id}-review-a",
                "reviewer_identity_digest": _digest(f"reviewer-a-{pair_id}"),
                "submitted_at": "2026-08-11T12:00:00+00:00",
                "review_packet_digest": packet_digest,
                "blind_preference": "A",
                "rationale": "Independent blinded review rationale.",
                "source_locator": f"packet://{pair_id}/review-a",
                "independent_review": True,
            }
        ),
        _sealed_review(
            {
                "review_id": f"{pair_id}-review-b",
                "reviewer_identity_digest": _digest(f"reviewer-b-{pair_id}"),
                "submitted_at": "2026-08-11T12:05:00+00:00",
                "review_packet_digest": packet_digest,
                "blind_preference": "B",
                "rationale": "Independent blinded review rationale.",
                "source_locator": f"packet://{pair_id}/review-b",
                "independent_review": True,
            }
        ),
    ]
    adjudication = _sealed_review(
        {
            "adjudication_id": f"{pair_id}-adjudication",
            "adjudicator_identity_digest": _digest(f"adjudicator-{pair_id}"),
            "submitted_at": "2026-08-11T13:00:00+00:00",
            "review_packet_digest": packet_digest,
            "primary_review_ids": [review["review_id"] for review in reviews],
            "primary_review_record_digests": [
                review["record_digest"] for review in reviews
            ],
            "resolved_preference": preference,
            "candidate_material_regression": False,
            "dimension_deltas": {dimension: 0.1 for dimension in P1_DIMENSIONS},
            "rationale": "Independent adjudication rationale.",
            "source_locator": f"packet://{pair_id}/adjudication",
        }
    )
    return {
        "pair_id": pair_id,
        "source_attempt_id": f"attempt-{pair_id}",
        "source_attempt_record_digest": _digest(f"attempt-{pair_id}"),
        "input_digest": _digest(f"input-{pair_id}"),
        "baseline_output_digest": _digest(f"baseline-{pair_id}"),
        "candidate_output_digest": _digest(f"candidate-{pair_id}"),
        "review_packet_digest": packet_digest,
        "slice_values": {
            "role_family": "strategy",
            "target_company": "target",
            "document_format": "pdf-docx",
        },
        "primary_reviews": reviews,
        "adjudication": adjudication,
    }


def _complete_outcome(
    tmp_path: Path, preferences: tuple[str, ...] = ("CANDIDATE", "CANDIDATE", "BASELINE")
) -> dict[str, object]:
    pair_ids = [f"pair-{index}" for index in range(len(preferences))]
    ledger = {
        "schema_version": LEDGER_VERSION,
        "evaluation_id": "p1-outcome-test-ledger",
        "source_identity": current_source_identity(),
        "cohort": {
            "status": "FROZEN",
            "cohort_id": "p1-test-cohort",
            "data_split": "calibration",
            "frozen_pair_ids": pair_ids,
            "frozen_pair_ids_digest": review_canonical_digest(pair_ids),
            "baseline_policy_digest": _digest("baseline-policy"),
            "blind_mapping_receipt_digest": _digest("blind-map"),
        },
        "synthetic_grades_created": False,
        "pairs": [
            _review_ledger_pair(pair_id, preference)
            for pair_id, preference in zip(pair_ids, preferences)
        ],
    }
    ledger_path = tmp_path / "review-ledger.json"
    _write(ledger_path, ledger)
    ledger_summary = validate_p1_blind_review_ledger(ledger_path)
    assert ledger_summary["status"] == "PASS"
    outcome = _outcome()
    evidence = outcome["p1_evidence"]
    assert isinstance(evidence, dict)
    evidence["pair_count"] = ledger_summary["pair_count"]
    evidence["primary_review_count"] = ledger_summary["primary_review_count"]
    evidence["adjudication_count"] = ledger_summary["adjudication_count"]
    evidence["external_authority_receipt_sha256"] = _digest("human-authority")
    evidence["completed_review_receipt_digest"] = ledger_summary["record_digest"]
    evidence["utility_effect"] = ledger_summary["candidate_preference_margin"]
    evidence["utility_ci_lower"] = 0.01
    evidence["candidate_preference_count"] = ledger_summary[
        "candidate_preference_count"
    ]
    evidence["baseline_preference_count"] = ledger_summary[
        "baseline_preference_count"
    ]
    evidence["blind_review_ledger_path"] = ledger_path.name
    evidence["blind_review_ledger_file_sha256"] = review_file_sha256(ledger_path)
    return outcome


def test_schema_is_valid_and_tracked_p1_outcome_is_not_measured() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_outcome())

    result = validate_finished_resume_outcome()

    assert result["status"] == "NOT_MEASURED"
    assert result["authority"]["human_qualified"] is False
    assert "P1_HUMAN_REVIEW_PENDING" in result["not_measured_reasons"]
    assert "P1_NONINFERIORITY_MARGINS_NOT_PREREGISTERED" in result[
        "not_measured_reasons"
    ]


def test_complete_summary_must_cover_all_lanes_and_strictly_pass_p1(tmp_path: Path) -> None:
    path = tmp_path / "p1.json"
    _write(path, _complete_outcome(tmp_path))

    result = validate_finished_resume_outcome(path)

    assert result["status"] == "PASS"
    assert result["required_lanes"] == list(runtime_lanes())
    assert result["owner_solo_status"] == "PRESENT_COMPLEMENTARY"
    assert result["authority"]["release_authorizing"] is False


def test_tie_and_noninferiority_regression_fail_p1_without_becoming_authority(
    tmp_path: Path,
) -> None:
    tie = _complete_outcome(tmp_path, ("CANDIDATE", "BASELINE", "TIE"))
    evidence = tie["p1_evidence"]
    assert isinstance(evidence, dict)
    path = tmp_path / "tie.json"
    _write(path, tie)

    tie_result = validate_finished_resume_outcome(path)
    assert tie_result["status"] == "FAIL"
    assert "P1_TIE_OR_BASELINE_PREFERENCE_CANNOT_ESTABLISH_SUPERIORITY" in tie_result[
        "failure_reasons"
    ]

    regression = _complete_outcome(tmp_path)
    regression_evidence = regression["p1_evidence"]
    assert isinstance(regression_evidence, dict)
    dimensions = regression_evidence["dimension_ci_lowers"]
    assert isinstance(dimensions, dict)
    dimensions["grounding"] = -0.2
    regression_path = tmp_path / "regression.json"
    _write(regression_path, regression)
    regression_result = validate_finished_resume_outcome(regression_path)
    assert regression_result["status"] == "FAIL"
    assert "P1_NONINFERIORITY_GUARDRAIL_FAILED_grounding" in regression_result[
        "failure_reasons"
    ]


def test_synthetic_grades_or_wrong_lane_coverage_block_w4(tmp_path: Path) -> None:
    synthetic = _complete_outcome(tmp_path)
    evidence = synthetic["p1_evidence"]
    assert isinstance(evidence, dict)
    evidence["synthetic_grades_created"] = True
    synthetic_path = tmp_path / "synthetic.json"
    _write(synthetic_path, synthetic)
    synthetic_result = validate_finished_resume_outcome(synthetic_path)
    assert synthetic_result["status"] == "BLOCKED"
    assert "P1_SYNTHETIC_GRADES_FORBIDDEN" in synthetic_result["blocking_reasons"]

    incomplete = _complete_outcome(tmp_path)
    lanes = incomplete["required_lanes"]
    assert isinstance(lanes, list)
    lanes.pop()
    incomplete_path = tmp_path / "incomplete.json"
    _write(incomplete_path, incomplete)
    incomplete_result = validate_finished_resume_outcome(incomplete_path)
    assert incomplete_result["status"] == "BLOCKED"
    assert "P1_ALL_RUNTIME_LANES_REQUIRED" in incomplete_result["blocking_reasons"]


def test_aggregate_p1_counts_must_match_the_source_bound_blind_review_ledger(
    tmp_path: Path,
) -> None:
    outcome = _complete_outcome(tmp_path)
    evidence = outcome["p1_evidence"]
    assert isinstance(evidence, dict)
    evidence["candidate_preference_count"] = 99
    path = tmp_path / "mismatched-ledger.json"
    _write(path, outcome)

    result = validate_finished_resume_outcome(path)

    assert result["status"] == "BLOCKED"
    assert "P1_CANDIDATE_PREFERENCE_LEDGER_MISMATCH" in result[
        "blocking_reasons"
    ]
