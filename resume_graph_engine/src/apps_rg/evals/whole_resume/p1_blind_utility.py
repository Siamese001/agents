"""Fail-closed ledger validation for blinded P1 finished-resume review."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping, Sequence


LEDGER_VERSION = "apps_rg.p1_blind_review_ledger.v1"
SUMMARY_VERSION = "apps_rg.p1_blind_review_summary.v1"
EVALUATOR_VERSION = LEDGER_VERSION
DEFAULT_LEDGER_PATH = Path(__file__).with_name("p1_blind_review_ledger.v1.json")
REPO_ROOT = Path(__file__).resolve().parents[4]
LANE_CONTRACT_PATH = REPO_ROOT / "src/apps_eval/registries/apps_rg_lane_contract.json"
_DIGEST_PREFIX = "sha256:"
_DATA_SPLITS = {"calibration", "holdout"}
P1_DIMENSIONS = (
    "authenticity",
    "grounding",
    "ats",
    "readability",
    "concision",
    "target_relevance",
)
P1_SLICE_KEYS = ("role_family", "target_company", "document_format")


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _DIGEST_PREFIX + hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len(_DIGEST_PREFIX) + 64
        and value.startswith(_DIGEST_PREFIX)
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def runtime_lanes() -> tuple[str, ...]:
    contract = json.loads(LANE_CONTRACT_PATH.read_text(encoding="utf-8"))
    lanes = contract.get("generated_lanes") if isinstance(contract, Mapping) else None
    if (
        not isinstance(lanes, list)
        or not lanes
        or any(not isinstance(lane, str) or not lane for lane in lanes)
    ):
        raise ValueError("runtime lane contract is invalid")
    return tuple(lanes)


def current_source_identity() -> dict[str, str]:
    return {
        "lane_contract_digest": file_sha256(LANE_CONTRACT_PATH),
        "evaluator_version": EVALUATOR_VERSION,
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("P1 review ledger must be a JSON object")
    return value


def _record_digest_matches(value: Mapping[str, Any]) -> bool:
    return _valid_digest(value.get("record_digest")) and value.get(
        "record_digest"
    ) == canonical_digest(
        {key: item for key, item in value.items() if key != "record_digest"}
    )


def _cohort_errors(value: Any, *, has_pairs: bool) -> tuple[list[str], tuple[str, ...]]:
    if not isinstance(value, Mapping):
        return ["P1_COHORT_INVALID"], ()
    status = value.get("status")
    cohort_id = value.get("cohort_id")
    data_split = value.get("data_split")
    pair_ids = value.get("frozen_pair_ids")
    pair_ids_digest = value.get("frozen_pair_ids_digest")
    baseline_policy_digest = value.get("baseline_policy_digest")
    blind_mapping_receipt_digest = value.get("blind_mapping_receipt_digest")
    if not isinstance(pair_ids, list) or any(
        not isinstance(pair_id, str) or not pair_id for pair_id in pair_ids
    ) or len(pair_ids) != len(set(pair_ids)):
        return ["P1_COHORT_PAIR_IDS_INVALID"], ()
    if status == "PENDING":
        if (
            has_pairs
            or cohort_id not in (None, "")
            or data_split is not None
            or pair_ids
            or pair_ids_digest is not None
            or baseline_policy_digest is not None
            or blind_mapping_receipt_digest is not None
        ):
            return ["P1_PENDING_COHORT_STATE_INVALID"], ()
        return [], ()
    if status != "FROZEN":
        return ["P1_COHORT_STATUS_INVALID"], ()
    if (
        not isinstance(cohort_id, str)
        or not cohort_id
        or data_split not in _DATA_SPLITS
        or not pair_ids
        or pair_ids_digest != canonical_digest(pair_ids)
        or not _valid_digest(baseline_policy_digest)
        or not _valid_digest(blind_mapping_receipt_digest)
    ):
        return ["P1_FROZEN_COHORT_IDENTITY_INVALID"], ()
    if not has_pairs:
        return ["P1_FROZEN_COHORT_HAS_NO_PAIRS"], tuple(pair_ids)
    return [], tuple(pair_ids)


def _source_identity_errors(value: Any, *, has_pairs: bool) -> list[str]:
    if not isinstance(value, Mapping):
        return ["P1_SOURCE_IDENTITY_INVALID"]
    if value.get("evaluator_version") != EVALUATOR_VERSION:
        return ["P1_EVALUATOR_VERSION_INVALID"]
    if has_pairs and value.get("lane_contract_digest") != file_sha256(
        LANE_CONTRACT_PATH
    ):
        return ["P1_RUNTIME_LANE_CONTRACT_STALE"]
    return []


def _slice_errors(value: Any) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != set(P1_SLICE_KEYS):
        return ["P1_PAIR_SLICE_VALUES_INVALID"]
    if any(not isinstance(item, str) or not item for item in value.values()):
        return ["P1_PAIR_SLICE_VALUE_INVALID"]
    return []


def _review_errors(
    value: Any, *, packet_digest: str
) -> tuple[list[str], str, str, str]:
    if not isinstance(value, Mapping):
        return ["P1_PRIMARY_REVIEW_INVALID"], "", "", ""
    expected_fields = {
        "review_id",
        "reviewer_identity_digest",
        "submitted_at",
        "review_packet_digest",
        "blind_preference",
        "rationale",
        "source_locator",
        "independent_review",
        "record_digest",
    }
    errors: list[str] = []
    if set(value) != expected_fields:
        errors.append("P1_PRIMARY_REVIEW_FIELDS_INVALID")
    review_id = value.get("review_id")
    reviewer_digest = value.get("reviewer_identity_digest")
    review_digest = value.get("record_digest")
    if not isinstance(review_id, str) or not review_id:
        errors.append("P1_PRIMARY_REVIEW_ID_INVALID")
    if not _valid_digest(reviewer_digest):
        errors.append("P1_PRIMARY_REVIEWER_IDENTITY_INVALID")
    if not _valid_timestamp(value.get("submitted_at")):
        errors.append("P1_PRIMARY_REVIEW_TIMESTAMP_INVALID")
    if value.get("review_packet_digest") != packet_digest:
        errors.append("P1_PRIMARY_REVIEW_PACKET_MISMATCH")
    if value.get("blind_preference") not in {"A", "B", "TIE"}:
        errors.append("P1_PRIMARY_REVIEW_BLIND_PREFERENCE_INVALID")
    if not isinstance(value.get("rationale"), str) or not value["rationale"]:
        errors.append("P1_PRIMARY_REVIEW_RATIONALE_REQUIRED")
    if not isinstance(value.get("source_locator"), str) or not value["source_locator"]:
        errors.append("P1_PRIMARY_REVIEW_LOCATOR_REQUIRED")
    if value.get("independent_review") is not True:
        errors.append("P1_PRIMARY_REVIEW_INDEPENDENCE_REQUIRED")
    if not _record_digest_matches(value):
        errors.append("P1_PRIMARY_REVIEW_RECORD_DIGEST_INVALID")
    return (
        errors,
        review_id if isinstance(review_id, str) else "",
        reviewer_digest if isinstance(reviewer_digest, str) else "",
        review_digest if isinstance(review_digest, str) else "",
    )


def _adjudication_errors(
    value: Any,
    *,
    packet_digest: str,
    review_ids: set[str],
    review_digests: set[str],
    reviewer_digests: set[str],
) -> tuple[list[str], str, bool, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return ["P1_ADJUDICATION_INVALID"], "", False, {}
    expected_fields = {
        "adjudication_id",
        "adjudicator_identity_digest",
        "submitted_at",
        "review_packet_digest",
        "primary_review_ids",
        "primary_review_record_digests",
        "resolved_preference",
        "candidate_material_regression",
        "dimension_deltas",
        "rationale",
        "source_locator",
        "record_digest",
    }
    errors: list[str] = []
    if set(value) != expected_fields:
        errors.append("P1_ADJUDICATION_FIELDS_INVALID")
    adjudication_id = value.get("adjudication_id")
    adjudicator_digest = value.get("adjudicator_identity_digest")
    if not isinstance(adjudication_id, str) or not adjudication_id:
        errors.append("P1_ADJUDICATION_ID_INVALID")
    if not _valid_digest(adjudicator_digest) or adjudicator_digest in reviewer_digests:
        errors.append("P1_ADJUDICATOR_INDEPENDENCE_INVALID")
    if not _valid_timestamp(value.get("submitted_at")):
        errors.append("P1_ADJUDICATION_TIMESTAMP_INVALID")
    if value.get("review_packet_digest") != packet_digest:
        errors.append("P1_ADJUDICATION_PACKET_MISMATCH")
    if {str(item) for item in value.get("primary_review_ids") or []} != review_ids:
        errors.append("P1_ADJUDICATION_REVIEW_IDS_INVALID")
    if {
        str(item) for item in value.get("primary_review_record_digests") or []
    } != review_digests:
        errors.append("P1_ADJUDICATION_REVIEW_DIGESTS_INVALID")
    preference = value.get("resolved_preference")
    if preference not in {"CANDIDATE", "BASELINE", "TIE"}:
        errors.append("P1_ADJUDICATION_PREFERENCE_INVALID")
    regression = value.get("candidate_material_regression")
    if not isinstance(regression, bool):
        errors.append("P1_ADJUDICATION_REGRESSION_FLAG_INVALID")
    dimensions = value.get("dimension_deltas")
    if not isinstance(dimensions, Mapping) or set(dimensions) != set(P1_DIMENSIONS):
        errors.append("P1_ADJUDICATION_DIMENSIONS_INVALID")
        dimensions = {}
    elif any(
        not isinstance(delta, (int, float))
        or isinstance(delta, bool)
        or not math.isfinite(float(delta))
        for delta in dimensions.values()
    ):
        errors.append("P1_ADJUDICATION_DIMENSION_VALUE_INVALID")
    if not isinstance(value.get("rationale"), str) or not value["rationale"]:
        errors.append("P1_ADJUDICATION_RATIONALE_REQUIRED")
    if not isinstance(value.get("source_locator"), str) or not value["source_locator"]:
        errors.append("P1_ADJUDICATION_LOCATOR_REQUIRED")
    if not _record_digest_matches(value):
        errors.append("P1_ADJUDICATION_RECORD_DIGEST_INVALID")
    return (
        errors,
        preference if isinstance(preference, str) else "",
        regression if isinstance(regression, bool) else False,
        dimensions,
    )


def _pair_result(pair: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(pair, Mapping):
        return {"pair_id": "", "status": "BLOCKED"}, ["P1_PAIR_INVALID"]
    expected_fields = {
        "pair_id",
        "source_attempt_id",
        "source_attempt_record_digest",
        "input_digest",
        "baseline_output_digest",
        "candidate_output_digest",
        "review_packet_digest",
        "slice_values",
        "primary_reviews",
        "adjudication",
    }
    errors: list[str] = []
    if set(pair) != expected_fields:
        errors.append("P1_PAIR_FIELDS_INVALID")
    pair_id = pair.get("pair_id")
    source_attempt_id = pair.get("source_attempt_id")
    for field in ("source_attempt_id",):
        if not isinstance(pair.get(field), str) or not pair[field]:
            errors.append("P1_PAIR_SOURCE_ATTEMPT_INVALID")
    for field in (
        "source_attempt_record_digest",
        "input_digest",
        "baseline_output_digest",
        "candidate_output_digest",
        "review_packet_digest",
    ):
        if not _valid_digest(pair.get(field)):
            errors.append("P1_PAIR_DIGEST_INVALID")
            break
    if pair.get("baseline_output_digest") == pair.get("candidate_output_digest"):
        errors.append("P1_PAIR_VARIANTS_NOT_DISTINCT")
    errors.extend(_slice_errors(pair.get("slice_values")))
    reviews = pair.get("primary_reviews")
    review_ids: set[str] = set()
    reviewer_digests: set[str] = set()
    review_digests: set[str] = set()
    if not isinstance(reviews, list) or len(reviews) != 2:
        errors.append("P1_PRIMARY_REVIEW_QUORUM_INVALID")
        reviews = []
    for review in reviews:
        review_errors, review_id, reviewer_digest, review_digest = _review_errors(
            review, packet_digest=str(pair.get("review_packet_digest") or "")
        )
        errors.extend(review_errors)
        if not review_id or review_id in review_ids:
            errors.append("P1_PRIMARY_REVIEW_IDS_INVALID")
        review_ids.add(review_id)
        if not reviewer_digest or reviewer_digest in reviewer_digests:
            errors.append("P1_PRIMARY_REVIEWER_INDEPENDENCE_INVALID")
        reviewer_digests.add(reviewer_digest)
        if not review_digest or review_digest in review_digests:
            errors.append("P1_PRIMARY_REVIEW_RECORDS_INVALID")
        review_digests.add(review_digest)
    adjudication_errors, preference, regression, dimensions = _adjudication_errors(
        pair.get("adjudication"),
        packet_digest=str(pair.get("review_packet_digest") or ""),
        review_ids=review_ids,
        review_digests=review_digests,
        reviewer_digests=reviewer_digests,
    )
    errors.extend(adjudication_errors)
    result = {
        "pair_id": pair_id if isinstance(pair_id, str) else "",
        "source_attempt_id": source_attempt_id
        if isinstance(source_attempt_id, str)
        else "",
        "status": "BLOCKED" if errors else "PASS",
        "resolved_preference": preference,
        "candidate_material_regression": regression,
        "dimension_deltas": dict(dimensions),
    }
    return result, errors


def validate_p1_blind_review_ledger(
    path: Path = DEFAULT_LEDGER_PATH,
) -> dict[str, Any]:
    """Validate P1 review records without granting human or release authority."""

    try:
        ledger = _load_json(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        ledger = {}
        blocking = ["P1_LEDGER_UNREADABLE"]
    else:
        blocking: list[str] = []
    if ledger.get("schema_version") != LEDGER_VERSION:
        blocking.append("P1_LEDGER_SCHEMA_INVALID")
    if not isinstance(ledger.get("evaluation_id"), str) or not ledger[
        "evaluation_id"
    ]:
        blocking.append("P1_LEDGER_ID_INVALID")
    if ledger.get("synthetic_grades_created") is not False:
        blocking.append("P1_SYNTHETIC_GRADES_FORBIDDEN")
    pairs = ledger.get("pairs")
    if not isinstance(pairs, list):
        blocking.append("P1_PAIRS_INVALID")
        pairs = []
    blocking.extend(
        _source_identity_errors(
            ledger.get("source_identity"), has_pairs=bool(pairs)
        )
    )
    cohort_errors, frozen_pair_ids = _cohort_errors(
        ledger.get("cohort"), has_pairs=bool(pairs)
    )
    blocking.extend(cohort_errors)
    not_measured = ["P1_BLINDED_REVIEW_PAIRS_PENDING"] if not pairs else []
    results: list[dict[str, Any]] = []
    seen_pair_ids: set[str] = set()
    seen_attempt_ids: set[str] = set()
    for pair in pairs:
        result, pair_errors = _pair_result(pair)
        results.append(result)
        blocking.extend(pair_errors)
        pair_id = result["pair_id"]
        attempt_id = result["source_attempt_id"]
        if not pair_id or pair_id in seen_pair_ids:
            blocking.append("P1_PAIR_ID_DUPLICATE_OR_INVALID")
        elif frozen_pair_ids and pair_id not in frozen_pair_ids:
            blocking.append("P1_PAIR_OUTSIDE_FROZEN_COHORT")
        seen_pair_ids.add(pair_id)
        if not attempt_id or attempt_id in seen_attempt_ids:
            blocking.append("P1_SOURCE_ATTEMPT_DUPLICATE_OR_INVALID")
        seen_attempt_ids.add(attempt_id)
    if frozen_pair_ids and seen_pair_ids != set(frozen_pair_ids):
        blocking.append("P1_FROZEN_COHORT_MEMBERSHIP_INCOMPLETE")
    completed = [result for result in results if result["status"] == "PASS"]
    candidate_preference_count = sum(
        result["resolved_preference"] == "CANDIDATE"
        and result["candidate_material_regression"] is False
        for result in completed
    )
    baseline_preference_count = sum(
        result["resolved_preference"] == "BASELINE" for result in completed
    )
    tie_count = sum(result["resolved_preference"] == "TIE" for result in completed)
    regression_count = sum(
        result["candidate_material_regression"] is True for result in completed
    )
    dimension_values: dict[str, list[float]] = {
        dimension: [] for dimension in P1_DIMENSIONS
    }
    for result in completed:
        dimensions = result["dimension_deltas"]
        if not isinstance(dimensions, Mapping):
            continue
        for dimension in P1_DIMENSIONS:
            value = dimensions.get(dimension)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                dimension_values[dimension].append(float(value))
    status = "BLOCKED" if blocking else "NOT_MEASURED" if not_measured else "PASS"
    summary: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "evaluation_id": str(ledger.get("evaluation_id") or path.stem),
        "status": status,
        "source_identity": ledger.get("source_identity"),
        "cohort": {
            "status": ledger.get("cohort", {}).get("status")
            if isinstance(ledger.get("cohort"), Mapping)
            else None,
            "cohort_id": ledger.get("cohort", {}).get("cohort_id")
            if isinstance(ledger.get("cohort"), Mapping)
            else None,
            "data_split": ledger.get("cohort", {}).get("data_split")
            if isinstance(ledger.get("cohort"), Mapping)
            else None,
            "frozen_pair_count": len(frozen_pair_ids),
        },
        "pair_count": len(completed),
        "primary_review_count": len(completed) * 2,
        "adjudication_count": len(completed),
        "candidate_preference_count": candidate_preference_count,
        "baseline_preference_count": baseline_preference_count,
        "tie_count": tie_count,
        "candidate_material_regression_count": regression_count,
        "candidate_preference_margin": (
            (candidate_preference_count - baseline_preference_count) / len(completed)
            if completed
            else None
        ),
        "dimension_mean_deltas": {
            dimension: fmean(values) if values else None
            for dimension, values in dimension_values.items()
        },
        "pair_results": results,
        "authority": {
            "technical_validation": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
        },
        "blocking_reasons": sorted(set(blocking)),
        "not_measured_reasons": sorted(set(not_measured)),
    }
    summary["record_digest"] = canonical_digest(summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Apps RG blinded P1 review")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER_PATH)
    args = parser.parse_args(argv)
    result = validate_p1_blind_review_ledger(args.ledger)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2
