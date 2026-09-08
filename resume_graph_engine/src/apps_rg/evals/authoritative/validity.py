"""G6 criterion validation against an authorized human pilot."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .artifacts import (
    load_human_authority_receipt,
    seal_record,
    validate_authorized_reviewer,
    validate_label_review_coverage,
    validate_pinned_record,
)

MACHINE_SCHEMA = "apps_rg.evaluator_validity_receipt.v1"
AUTOMATED_RESULTS_SCHEMA = "apps_rg.authoritative_automated_grader_results.v1"
HUMAN_PILOT_SCHEMA = "apps_rg.authoritative_human_grader_pilot.v1"
POLICY_SCHEMA = "apps_rg.authoritative_validity_policy.v1"
RECEIPT_SCHEMA = "apps_rg.authoritative_evaluator_validity_receipt.v1"


def _wilson_upper(errors: int, total: int, *, z: float = 1.959963984540054) -> float:
    proportion = errors / total
    denominator = 1 + z * z / total
    center = proportion + z * z / (2 * total)
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
    return (center + margin) / denominator


def _rows(value: Any, label: str, reasons: list[str]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        reasons.append(f"{label}_EMPTY")
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for row in value:
        if not isinstance(row, Mapping):
            reasons.append(f"{label}_ROW_INVALID")
            continue
        item_id = str(row.get("item_id") or "")
        if not item_id or item_id in result or row.get("status") not in {"PASS", "FAIL"}:
            reasons.append(f"{label}_ROW_INVALID")
            continue
        result[item_id] = row
    return result


def evaluate_authoritative_validity(
    *,
    machine_receipt: Any,
    expected_machine_receipt_digest: str,
    automated_results: Any,
    expected_automated_results_digest: str,
    human_pilot: Any,
    expected_human_pilot_digest: str,
    policy: Any,
    expected_policy_digest: str,
    authority_receipt_path: Any,
    expected_authority_file_sha256: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    for value, expected, schema in (
        (machine_receipt, expected_machine_receipt_digest, MACHINE_SCHEMA),
        (automated_results, expected_automated_results_digest, AUTOMATED_RESULTS_SCHEMA),
        (human_pilot, expected_human_pilot_digest, HUMAN_PILOT_SCHEMA),
        (policy, expected_policy_digest, POLICY_SCHEMA),
    ):
        reasons.extend(validate_pinned_record(value, expected_digest=expected, schema_version=schema))
    authority, roster, authority_reasons = load_human_authority_receipt(
        authority_receipt_path,
        expected_file_sha256=expected_authority_file_sha256,
    )
    reasons.extend(authority_reasons)
    if not all(
        isinstance(value, Mapping)
        for value in (machine_receipt, automated_results, human_pilot, policy)
    ):
        return seal_record(
            {
                "schema_version": RECEIPT_SCHEMA,
                "gate_id": "G6",
                "score_groups": ["evaluator_validity"],
                "status": "UNKNOWN",
                "metrics": {},
                "failure_codes": [],
                "unknown_reasons": sorted(set(reasons)),
                "authority": {
                    "machine_critical_grader_validation_complete": False,
                    "human_agreement_pilot_complete": False,
                    "release_authorizing": False,
                },
            }
        )
    if human_pilot.get("authority_receipt_file_sha256") != expected_authority_file_sha256:
        reasons.append("HUMAN_PILOT_AUTHORITY_BINDING_MISMATCH")
    reviewers = human_pilot.get("reviewer_identity_refs")
    if (
        not isinstance(reviewers, list)
        or any(not isinstance(reviewer, str) or not reviewer for reviewer in reviewers)
        or len(set(reviewers)) < 2
    ):
        reasons.append("HUMAN_PILOT_TWO_REVIEWERS_REQUIRED")
        reviewers = []
    for reviewer in reviewers:
        reasons.extend(
            validate_authorized_reviewer(
                identity_ref=str(reviewer),
                qualification_ref=None,
                cohort="proof",
                role="primary",
                roster=roster,
            )
        )
    adjudicator = str(human_pilot.get("adjudicator_identity_ref") or "")
    reasons.extend(
        validate_authorized_reviewer(
            identity_ref=adjudicator,
            qualification_ref=None,
            cohort="proof",
            role="adjudicator",
            roster=roster,
        )
    )
    automated = _rows(automated_results.get("results"), "AUTOMATED_RESULTS", reasons)
    human = _rows(human_pilot.get("labels"), "HUMAN_PILOT", reasons)
    for label in human.values():
        reasons.extend(
            validate_label_review_coverage(
                label,
                reviewer_identity_refs=[str(reviewer) for reviewer in reviewers],
                adjudicator_identity_ref=adjudicator,
            )
        )
    if set(automated) != set(human):
        reasons.append("HUMAN_PILOT_DENOMINATOR_MISMATCH")
    sample_size = len(set(automated) & set(human))
    minimum_sample = policy.get("minimum_sample_size")
    if not isinstance(minimum_sample, int) or isinstance(minimum_sample, bool) or minimum_sample <= 0:
        reasons.append("VALIDITY_POLICY_SAMPLE_SIZE_INVALID")
    elif sample_size < minimum_sample:
        reasons.append("HUMAN_PILOT_SAMPLE_TOO_SMALL")
    human_pass_count = sum(
        human[item]["status"] == "PASS" for item in set(automated) & set(human)
    )
    human_fail_count = sample_size - human_pass_count
    for field, observed in (
        ("minimum_positive_sample_size", human_pass_count),
        ("minimum_negative_sample_size", human_fail_count),
    ):
        minimum = policy.get(field)
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum <= 0:
            reasons.append(f"VALIDITY_POLICY_{field.upper()}_INVALID")
        elif observed < minimum:
            reasons.append(f"HUMAN_PILOT_{field.upper()}_NOT_MET")
    for field in (
        "minimum_exact_agreement",
        "maximum_false_positive_upper_95",
        "maximum_false_negative_upper_95",
    ):
        threshold = policy.get(field)
        if (
            not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not math.isfinite(float(threshold))
            or not 0 <= float(threshold) <= 1
        ):
            reasons.append(f"VALIDITY_POLICY_{field.upper()}_INVALID")
    if reasons:
        return seal_record(
            {
                "schema_version": RECEIPT_SCHEMA,
                "gate_id": "G6",
                "score_groups": ["evaluator_validity"],
                "status": "UNKNOWN",
                "metrics": {},
                "failure_codes": [],
                "unknown_reasons": sorted(set(reasons)),
                "authority": {
                    "machine_critical_grader_validation_complete": False,
                    "human_agreement_pilot_complete": False,
                    "release_authorizing": False,
                },
            }
        )
    agreements = sum(automated[item]["status"] == human[item]["status"] for item in automated)
    human_pass = [item for item in human if human[item]["status"] == "PASS"]
    false_positives = sum(automated[item]["status"] == "FAIL" for item in human_pass)
    human_fail = [item for item in human if human[item]["status"] == "FAIL"]
    false_negatives = sum(automated[item]["status"] == "PASS" for item in human_fail)
    agreement = agreements / sample_size
    fpr = false_positives / len(human_pass) if human_pass else 0.0
    fnr = false_negatives / len(human_fail) if human_fail else 0.0
    fpr_upper = _wilson_upper(false_positives, len(human_pass)) if human_pass else 0.0
    fnr_upper = _wilson_upper(false_negatives, len(human_fail)) if human_fail else 0.0
    failures: list[str] = []
    if machine_receipt.get("status") != "PASS":
        failures.append("MACHINE_MUTATION_VALIDITY_NONPASS")
    minimum_agreement = policy.get("minimum_exact_agreement")
    maximum_fpr_upper = policy.get("maximum_false_positive_upper_95")
    maximum_fnr_upper = policy.get("maximum_false_negative_upper_95")
    if agreement < float(minimum_agreement):
        failures.append("HUMAN_EXACT_AGREEMENT_BELOW_POLICY")
    if fpr_upper > float(maximum_fpr_upper):
        failures.append("HUMAN_FALSE_POSITIVE_UPPER_BOUND_EXCEEDED")
    if fnr_upper > float(maximum_fnr_upper):
        failures.append("HUMAN_FALSE_NEGATIVE_UPPER_BOUND_EXCEEDED")
    machine_metrics = machine_receipt.get("metrics")
    return seal_record(
        {
            "schema_version": RECEIPT_SCHEMA,
            "gate_id": "G6",
            "score_groups": ["evaluator_validity"],
            "status": "FAIL" if failures else "PASS",
            "metrics": {
                **(dict(machine_metrics) if isinstance(machine_metrics, Mapping) else {}),
                "human_grader_agreement": agreement,
                "human_false_positive_rate": fpr,
                "human_false_negative_rate": fnr,
                "human_false_positive_rate_upper_95": fpr_upper,
                "human_false_negative_rate_upper_95": fnr_upper,
                "human_pilot_sample_size": sample_size,
                "human_positive_sample_size": len(human_pass),
                "human_negative_sample_size": len(human_fail),
            },
            "failure_codes": failures,
            "unknown_reasons": [],
            "authority": {
                "authority_receipt_digest": authority.get("receipt_digest"),
                "authority_receipt_file_sha256": expected_authority_file_sha256,
                "machine_critical_grader_validation_complete": machine_receipt.get("status") == "PASS",
                "human_agreement_pilot_complete": True,
                "release_authorizing": False,
            },
        }
    )


__all__ = [
    "AUTOMATED_RESULTS_SCHEMA",
    "HUMAN_PILOT_SCHEMA",
    "POLICY_SCHEMA",
    "RECEIPT_SCHEMA",
    "evaluate_authoritative_validity",
]
