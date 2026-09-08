from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from apps_rg.evals.whole_resume.p1_blind_utility import (
    LEDGER_VERSION,
    P1_DIMENSIONS,
    canonical_digest,
    current_source_identity,
    validate_p1_blind_review_ledger,
)


WHOLE_RESUME_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = WHOLE_RESUME_ROOT / "schemas" / "p1_blind_review_ledger.v1.schema.json"
DEFAULT_LEDGER_PATH = WHOLE_RESUME_ROOT / "p1_blind_review_ledger.v1.json"


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sealed_record(payload: dict[str, object]) -> dict[str, object]:
    payload["record_digest"] = canonical_digest(payload)
    return payload


def _review(pair_id: str, reviewer: str, choice: str) -> dict[str, object]:
    return _sealed_record(
        {
            "review_id": f"review-{pair_id}-{reviewer}",
            "reviewer_identity_digest": _digest(f"reviewer-{reviewer}"),
            "submitted_at": "2026-08-11T12:00:00+00:00",
            "review_packet_digest": _digest(f"packet-{pair_id}"),
            "blind_preference": choice,
            "rationale": "Reviewer recorded a reasoned blinded comparison.",
            "source_locator": f"packet://{pair_id}/rubric",
            "independent_review": True,
        }
    )


def _pair(pair_id: str, preference: str) -> dict[str, object]:
    first = _review(pair_id, "one", "A")
    second = _review(pair_id, "two", "B")
    review_ids = [first["review_id"], second["review_id"]]
    review_digests = [first["record_digest"], second["record_digest"]]
    adjudication = _sealed_record(
        {
            "adjudication_id": f"adjudication-{pair_id}",
            "adjudicator_identity_digest": _digest(f"adjudicator-{pair_id}"),
            "submitted_at": "2026-08-11T13:00:00+00:00",
            "review_packet_digest": _digest(f"packet-{pair_id}"),
            "primary_review_ids": review_ids,
            "primary_review_record_digests": review_digests,
            "resolved_preference": preference,
            "candidate_material_regression": False,
            "dimension_deltas": {dimension: 0.1 for dimension in P1_DIMENSIONS},
            "rationale": "Independent adjudication resolved the blinded pair.",
            "source_locator": f"packet://{pair_id}/adjudication",
        }
    )
    return {
        "pair_id": pair_id,
        "source_attempt_id": f"attempt-{pair_id}",
        "source_attempt_record_digest": _digest(f"attempt-record-{pair_id}"),
        "input_digest": _digest(f"input-{pair_id}"),
        "baseline_output_digest": _digest(f"baseline-{pair_id}"),
        "candidate_output_digest": _digest(f"candidate-{pair_id}"),
        "review_packet_digest": _digest(f"packet-{pair_id}"),
        "slice_values": {
            "role_family": "strategy",
            "target_company": "target",
            "document_format": "pdf-docx",
        },
        "primary_reviews": [first, second],
        "adjudication": adjudication,
    }


def _ledger(pair_ids: list[str]) -> dict[str, object]:
    return {
        "schema_version": LEDGER_VERSION,
        "evaluation_id": "p1-blind-ledger-test",
        "source_identity": current_source_identity(),
        "cohort": {
            "status": "FROZEN",
            "cohort_id": "p1-calibration",
            "data_split": "calibration",
            "frozen_pair_ids": pair_ids,
            "frozen_pair_ids_digest": canonical_digest(pair_ids),
            "baseline_policy_digest": _digest("baseline-policy"),
            "blind_mapping_receipt_digest": _digest("sealed-blind-map"),
        },
        "synthetic_grades_created": False,
        "pairs": [],
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_schema_and_tracked_p1_ledger_remain_pending_without_authority() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    tracked = json.loads(DEFAULT_LEDGER_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(tracked)

    result = validate_p1_blind_review_ledger()

    assert result["status"] == "NOT_MEASURED"
    assert result["cohort"]["status"] == "PENDING"
    assert result["authority"]["human_qualified"] is False
    assert result["authority"]["release_authorizing"] is False


def test_frozen_blinded_pairs_require_two_reviews_and_one_adjudication(
    tmp_path: Path,
) -> None:
    ledger = _ledger(["pair-one", "pair-two"])
    pairs = ledger["pairs"]
    assert isinstance(pairs, list)
    pairs.extend([_pair("pair-one", "CANDIDATE"), _pair("pair-two", "BASELINE")])
    path = tmp_path / "ledger.json"
    _write(path, ledger)

    result = validate_p1_blind_review_ledger(path)

    assert result["status"] == "PASS"
    assert result["pair_count"] == 2
    assert result["primary_review_count"] == 4
    assert result["adjudication_count"] == 2
    assert result["candidate_preference_count"] == 1
    assert result["baseline_preference_count"] == 1
    assert result["candidate_preference_margin"] == 0.0
    assert result["authority"]["human_qualified"] is False


def test_duplicate_reviewer_or_missing_rationale_blocks_blinded_review(
    tmp_path: Path,
) -> None:
    ledger = _ledger(["pair-one"])
    pairs = ledger["pairs"]
    assert isinstance(pairs, list)
    pair = _pair("pair-one", "CANDIDATE")
    reviews = pair["primary_reviews"]
    assert isinstance(reviews, list)
    second = reviews[1]
    assert isinstance(second, dict)
    first = reviews[0]
    assert isinstance(first, dict)
    second["reviewer_identity_digest"] = first["reviewer_identity_digest"]
    second["rationale"] = ""
    second["record_digest"] = canonical_digest(
        {key: value for key, value in second.items() if key != "record_digest"}
    )
    pairs.append(pair)
    path = tmp_path / "invalid-review.json"
    _write(path, ledger)

    result = validate_p1_blind_review_ledger(path)

    assert result["status"] == "BLOCKED"
    assert "P1_PRIMARY_REVIEWER_INDEPENDENCE_INVALID" in result["blocking_reasons"]
    assert "P1_PRIMARY_REVIEW_RATIONALE_REQUIRED" in result["blocking_reasons"]


def test_stale_lane_contract_or_missing_frozen_pair_blocks_p1_ledger(
    tmp_path: Path,
) -> None:
    stale = _ledger(["pair-one"])
    source_identity = stale["source_identity"]
    assert isinstance(source_identity, dict)
    source_identity["lane_contract_digest"] = _digest("stale-lanes")
    stale_pairs = stale["pairs"]
    assert isinstance(stale_pairs, list)
    stale_pairs.append(_pair("pair-one", "CANDIDATE"))
    stale_path = tmp_path / "stale.json"
    _write(stale_path, stale)

    stale_result = validate_p1_blind_review_ledger(stale_path)
    assert stale_result["status"] == "BLOCKED"
    assert "P1_RUNTIME_LANE_CONTRACT_STALE" in stale_result["blocking_reasons"]

    missing = copy.deepcopy(_ledger(["pair-one", "pair-two"]))
    missing_pairs = missing["pairs"]
    assert isinstance(missing_pairs, list)
    missing_pairs.append(_pair("pair-one", "CANDIDATE"))
    missing_path = tmp_path / "missing-pair.json"
    _write(missing_path, missing)

    missing_result = validate_p1_blind_review_ledger(missing_path)
    assert missing_result["status"] == "BLOCKED"
    assert "P1_FROZEN_COHORT_MEMBERSHIP_INCOMPLETE" in missing_result[
        "blocking_reasons"
    ]
