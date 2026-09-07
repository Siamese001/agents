"""Fail-closed source-bound measurement records for Apps RG pipeline attempts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from apps_rg.evals.pipeline_measurement_coverage import (
    DEFAULT_CONTRACT_PATH,
    DIAGNOSTIC_GATES,
    GUARDRAILS,
    canonical_digest,
    load_pipeline_measurement_coverage,
    runtime_lanes,
    source_contract_digests,
)


MANIFEST_VERSION = "apps_rg.pipeline_attempt_evaluation.v1"
SUMMARY_VERSION = "apps_rg.pipeline_attempt_evaluation_summary.v1"
EVALUATOR_VERSION = MANIFEST_VERSION
DEFAULT_MANIFEST_PATH = Path(__file__).with_name(
    "pipeline_attempt_evaluation.v1.json"
)
_DIGEST_PREFIX = "sha256:"
_PIPELINE_STAGES = (
    "apps_research",
    "U0",
    "L1",
    "L0",
    "C0",
    "PA",
    "L2",
    "X2",
    "X1D",
    "X3",
    "EXIT",
    "UWG",
    "L6",
    "PACKAGE",
    "REGRESSION",
)
_PIPELINE_STAGE_INDEX = {
    stage_id: index for index, stage_id in enumerate(_PIPELINE_STAGES)
}
_EVIDENCE_STATUSES = {"PASS", "FAIL", "ABSTAINED", "NOT_RUN", "UNKNOWN"}
_TERMINAL_STATUSES = {"COMPLETE", "FAILED", "ABSTAINED", "NOT_STARTED"}
_CACHE_MODES = {"COLD", "WARM"}
_COHORT_SPLITS = {"calibration", "holdout"}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("pipeline attempt manifest must be a JSON object")
    return value


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len(_DIGEST_PREFIX) + 64
        and value.startswith(_DIGEST_PREFIX)
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def current_source_identity() -> dict[str, Any]:
    """Return the immutable control-plane identity required for populated runs."""

    contract = load_pipeline_measurement_coverage(DEFAULT_CONTRACT_PATH)
    return {
        "coverage_contract_digest": canonical_digest(contract),
        "source_contract_digests": source_contract_digests(),
        "evaluator_version": EVALUATOR_VERSION,
    }


def expected_element_evidence(
    contract: Mapping[str, Any],
) -> dict[tuple[str, str | None], Mapping[str, Any]]:
    """Expand lane-scoped coverage into one expected row for every runtime lane."""

    rows = contract.get("coverage")
    if not isinstance(rows, list):
        raise ValueError("coverage contract has no rows")
    expected: dict[tuple[str, str | None], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("coverage contract contains a non-object row")
        element_id = row.get("element_id")
        scope = row.get("scope")
        if not isinstance(element_id, str) or not element_id:
            raise ValueError("coverage row has no element_id")
        lane_ids = runtime_lanes() if scope == "lane" else (None,)
        for lane_id in lane_ids:
            key = (element_id, lane_id)
            if key in expected:
                raise ValueError("coverage contract expands duplicate evidence rows")
            expected[key] = row
    return expected


def required_slice_keys(contract: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the explicit slice dimensions declared by the coverage contract."""

    rows = contract.get("coverage")
    if not isinstance(rows, list):
        raise ValueError("coverage contract has no rows")
    keys: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("coverage contract contains a non-object row")
        row_keys = row.get("slice_keys")
        if not isinstance(row_keys, list) or any(
            not isinstance(key, str) or not key for key in row_keys
        ):
            raise ValueError("coverage contract has invalid slice keys")
        keys.update(row_keys)
    return tuple(sorted(keys))


def measurement_authority_requirements(
    contract: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Derive required gate and guardrail authority from the live coverage map."""

    rows = contract.get("coverage")
    if not isinstance(rows, list):
        raise ValueError("coverage contract has no rows")
    diagnostic_requirements: dict[str, set[str]] = {
        metric_id: set() for metric_id in DIAGNOSTIC_GATES
    }
    guardrail_requirements: dict[str, set[str]] = {
        metric_id: set() for metric_id in GUARDRAILS
    }
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("coverage contract contains a non-object row")
        links = row.get("metric_links")
        if not isinstance(links, list):
            raise ValueError("coverage contract has invalid metric links")
        for link in links:
            if not isinstance(link, Mapping):
                raise ValueError("coverage contract contains a non-object metric link")
            metric_id = link.get("metric_id")
            authority = link.get("authority_required")
            if metric_id in diagnostic_requirements:
                diagnostic_requirements[metric_id].add(str(authority))
            elif metric_id in guardrail_requirements:
                guardrail_requirements[metric_id].add(str(authority))
    invalid = [
        metric_id
        for requirements in (diagnostic_requirements, guardrail_requirements)
        for metric_id, authorities in requirements.items()
        if len(authorities) != 1
    ]
    if invalid:
        raise ValueError("coverage contract has ambiguous measurement authority")
    return (
        {
            metric_id: next(iter(authorities))
            for metric_id, authorities in diagnostic_requirements.items()
        },
        {
            metric_id: next(iter(authorities))
            for metric_id, authorities in guardrail_requirements.items()
        },
    )


def _handoff_is_pass(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("observed") is True
        and value.get("valid") is True
        and value.get("status") == "PASS"
        and _valid_digest(value.get("receipt_digest"))
    )


def _evidence_errors(
    value: Any,
    *,
    expected: Mapping[tuple[str, str | None], Mapping[str, Any]],
) -> tuple[list[str], dict[tuple[str, str | None], str]]:
    errors: list[str] = []
    statuses: dict[tuple[str, str | None], str] = {}
    if not isinstance(value, list):
        return ["ATTEMPT_ELEMENT_EVIDENCE_INVALID"], statuses
    for record in value:
        if not isinstance(record, Mapping):
            errors.append("ATTEMPT_ELEMENT_EVIDENCE_ROW_INVALID")
            continue
        element_id = record.get("element_id")
        lane_id = record.get("lane_id")
        key = (element_id, lane_id)
        if not isinstance(element_id, str) or key not in expected:
            errors.append("ATTEMPT_ELEMENT_EVIDENCE_UNEXPECTED")
            continue
        if key in statuses:
            errors.append("ATTEMPT_ELEMENT_EVIDENCE_DUPLICATE")
            continue
        contract_row = expected[key]
        if record.get("scope") != contract_row.get("scope") or record.get(
            "stage_id"
        ) != contract_row.get("stage_id"):
            errors.append("ATTEMPT_ELEMENT_EVIDENCE_STAGE_MISMATCH")
        expected_lane = contract_row.get("scope") == "lane"
        if expected_lane != isinstance(lane_id, str):
            errors.append("ATTEMPT_ELEMENT_EVIDENCE_LANE_SCOPE_INVALID")
        if (
            isinstance(lane_id, str)
            and lane_id not in runtime_lanes()
        ):
            errors.append("ATTEMPT_ELEMENT_EVIDENCE_LANE_INVALID")
        status = record.get("status")
        if status not in _EVIDENCE_STATUSES:
            errors.append("ATTEMPT_ELEMENT_EVIDENCE_STATUS_INVALID")
            continue
        statuses[key] = str(status)
        artifact_digests = record.get("artifact_digests")
        if not isinstance(artifact_digests, Mapping):
            errors.append("ATTEMPT_ELEMENT_ARTIFACT_DIGESTS_INVALID")
            artifact_digests = {}
        expected_roles = set(contract_row.get("artifact_roles") or [])
        actual_roles = set(artifact_digests)
        if not actual_roles.issubset(expected_roles):
            errors.append("ATTEMPT_ELEMENT_ARTIFACT_ROLE_UNEXPECTED")
        if status == "PASS":
            if actual_roles != expected_roles or not all(
                _valid_digest(digest) for digest in artifact_digests.values()
            ):
                errors.append("ATTEMPT_ELEMENT_PASS_ARTIFACTS_INVALID")
        elif artifact_digests and not all(
            _valid_digest(digest) for digest in artifact_digests.values()
        ):
            errors.append("ATTEMPT_ELEMENT_ARTIFACT_DIGEST_INVALID")
        if status == "NOT_RUN" and artifact_digests:
            errors.append("ATTEMPT_ELEMENT_NOT_RUN_ARTIFACTS_INVALID")
        reasons = record.get("reason_codes")
        if not isinstance(reasons, list) or any(
            not isinstance(reason, str) or not reason for reason in reasons
        ) or len(reasons) != len(set(reasons)):
            errors.append("ATTEMPT_ELEMENT_REASON_CODES_INVALID")
        elif status == "PASS" and reasons:
            errors.append("ATTEMPT_ELEMENT_PASS_REASON_CODES_INVALID")
        elif status != "PASS" and not reasons:
            errors.append("ATTEMPT_ELEMENT_NONPASS_REASON_REQUIRED")
    if set(expected) != set(statuses):
        errors.append("ATTEMPT_ELEMENT_EVIDENCE_MISSING")
    return errors, statuses


def _diagnostic_errors(
    value: Any, *, required_authorities: Mapping[str, str]
) -> tuple[list[str], dict[str, str]]:
    errors: list[str] = []
    statuses: dict[str, str] = {}
    if not isinstance(value, Mapping) or set(value) != set(DIAGNOSTIC_GATES):
        return ["ATTEMPT_DIAGNOSTIC_RECEIPTS_INVALID"], statuses
    for gate in DIAGNOSTIC_GATES:
        receipt = value.get(gate)
        if not isinstance(receipt, Mapping):
            errors.append("ATTEMPT_DIAGNOSTIC_RECEIPT_INVALID")
            continue
        status = receipt.get("status")
        if status not in {"PASS", "FAIL", "NOT_MEASURED", "UNKNOWN"}:
            errors.append("ATTEMPT_DIAGNOSTIC_STATUS_INVALID")
            continue
        tier = receipt.get("authority_tier")
        if tier != required_authorities.get(gate):
            errors.append("ATTEMPT_DIAGNOSTIC_AUTHORITY_INVALID")
        record_digest = receipt.get("record_digest")
        if status == "NOT_MEASURED":
            if record_digest not in ("", None):
                errors.append("ATTEMPT_DIAGNOSTIC_UNMEASURED_DIGEST_INVALID")
        elif not _valid_digest(record_digest):
            errors.append("ATTEMPT_DIAGNOSTIC_RECORD_DIGEST_INVALID")
        statuses[gate] = str(status)
    return errors, statuses


def _guardrail_errors(
    value: Any, *, required_authorities: Mapping[str, str]
) -> tuple[list[str], dict[str, int | None]]:
    errors: list[str] = []
    counts: dict[str, int | None] = {}
    if not isinstance(value, Mapping) or set(value) != set(GUARDRAILS):
        return ["ATTEMPT_GUARDRAILS_INVALID"], counts
    for guardrail in GUARDRAILS:
        receipt = value.get(guardrail)
        if not isinstance(receipt, Mapping):
            errors.append("ATTEMPT_GUARDRAIL_RECEIPT_INVALID")
            continue
        status = receipt.get("status")
        count = receipt.get("count")
        digest = receipt.get("record_digest")
        authority = receipt.get("authority_tier")
        if status not in {"PASS", "FAIL", "NOT_MEASURED", "UNKNOWN"}:
            errors.append("ATTEMPT_GUARDRAIL_STATUS_INVALID")
            continue
        if authority != required_authorities.get(guardrail):
            errors.append("ATTEMPT_GUARDRAIL_AUTHORITY_INVALID")
        if status == "NOT_MEASURED":
            if count is not None or digest not in ("", None):
                errors.append("ATTEMPT_GUARDRAIL_UNMEASURED_VALUE_INVALID")
        elif (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or not _valid_digest(digest)
        ):
            errors.append("ATTEMPT_GUARDRAIL_VALUE_INVALID")
        elif status == "PASS" and count != 0:
            errors.append("ATTEMPT_GUARDRAIL_PASS_COUNT_INVALID")
        elif status == "FAIL" and count == 0:
            errors.append("ATTEMPT_GUARDRAIL_FAIL_COUNT_INVALID")
        counts[guardrail] = count if isinstance(count, int) else None
    return errors, counts


def _runtime_errors(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return ["ATTEMPT_RUNTIME_IDENTITY_INVALID"]
    if (
        not isinstance(value.get("provider"), str)
        or not value["provider"]
        or not isinstance(value.get("model"), str)
        or not value["model"]
        or not _valid_digest(value.get("configuration_digest"))
        or value.get("cache_mode") not in _CACHE_MODES
    ):
        return ["ATTEMPT_RUNTIME_IDENTITY_INVALID"]
    return []


def _slice_errors(value: Any, *, required_keys: tuple[str, ...]) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != set(required_keys):
        return ["ATTEMPT_SLICE_VALUES_INVALID"]
    if any(not isinstance(item, str) or not item for item in value.values()):
        return ["ATTEMPT_SLICE_VALUE_INVALID"]
    return []


def _slice_binding_errors(
    value: Any,
    *,
    cohort_data_split: str | None,
    population_status: Any,
    runtime: Any,
) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    errors: list[str] = []
    if value.get("data_split") != cohort_data_split:
        errors.append("ATTEMPT_SLICE_DATA_SPLIT_MISMATCH")
    runtime_slice_keys = ("provider", "model", "cache_mode", "runtime_configuration")
    if population_status == "ELIGIBLE" and isinstance(runtime, Mapping):
        expected = {
            "provider": runtime.get("provider"),
            "model": runtime.get("model"),
            "cache_mode": runtime.get("cache_mode"),
            "runtime_configuration": runtime.get("configuration_digest"),
        }
        if any(value.get(key) != expected_value for key, expected_value in expected.items()):
            errors.append("ATTEMPT_SLICE_RUNTIME_MISMATCH")
    elif population_status == "EXCLUDED" and any(
        value.get(key) != "NOT_APPLICABLE" for key in runtime_slice_keys
    ):
        errors.append("EXCLUDED_ATTEMPT_RUNTIME_SLICE_INVALID")
    return errors


def _cohort_errors(value: Any, *, has_attempts: bool) -> tuple[list[str], tuple[str, ...]]:
    if not isinstance(value, Mapping):
        return ["PIPELINE_COHORT_INVALID"], ()
    status = value.get("status")
    cohort_id = value.get("cohort_id")
    data_split = value.get("data_split")
    members = value.get("frozen_member_ids")
    member_digest = value.get("frozen_member_ids_digest")
    if not isinstance(members, list) or any(
        not isinstance(member, str) or not member for member in members
    ) or len(members) != len(set(members)):
        return ["PIPELINE_COHORT_MEMBERS_INVALID"], ()
    if status == "PENDING":
        if (
            has_attempts
            or cohort_id not in (None, "")
            or data_split is not None
            or members
            or member_digest is not None
        ):
            return ["PIPELINE_PENDING_COHORT_STATE_INVALID"], ()
        return [], ()
    if status != "FROZEN":
        return ["PIPELINE_COHORT_STATUS_INVALID"], ()
    if (
        not isinstance(cohort_id, str)
        or not cohort_id
        or data_split not in _COHORT_SPLITS
        or not members
        or member_digest != canonical_digest(members)
    ):
        return ["PIPELINE_FROZEN_COHORT_IDENTITY_INVALID"], ()
    if not has_attempts:
        return ["PIPELINE_FROZEN_COHORT_HAS_NO_ATTEMPTS"], tuple(members)
    return [], tuple(members)


def _terminal_evidence_matches(
    statuses: Mapping[tuple[str, str | None], str],
    expected: Mapping[tuple[str, str | None], Mapping[str, Any]],
    *,
    terminal_stage: str,
    terminal_status: str,
) -> bool:
    return any(
        expected[key].get("stage_id") == terminal_stage and status == terminal_status
        for key, status in statuses.items()
    )


def _preterminal_evidence_errors(
    statuses: Mapping[tuple[str, str | None], str],
    expected: Mapping[tuple[str, str | None], Mapping[str, Any]],
    *,
    terminal_stage: str,
) -> list[str]:
    terminal_index = _PIPELINE_STAGE_INDEX[terminal_stage]
    for key, status in statuses.items():
        row = expected[key]
        stage_id = row.get("stage_id")
        if (
            row.get("required") is True
            and isinstance(stage_id, str)
            and _PIPELINE_STAGE_INDEX[stage_id] < terminal_index
            and status != "PASS"
        ):
            return ["INCOMPLETE_ATTEMPT_PRETERMINAL_EVIDENCE_INVALID"]
    return []


def _attempt_result(
    attempt: Any,
    *,
    expected: Mapping[tuple[str, str | None], Mapping[str, Any]],
    slice_keys: tuple[str, ...],
    diagnostic_authorities: Mapping[str, str],
    guardrail_authorities: Mapping[str, str],
    cohort_data_split: str | None,
) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    blocking: list[str] = []
    failures: list[str] = []
    not_measured: list[str] = []
    if not isinstance(attempt, Mapping):
        return (
            {"attempt_id": "", "status": "BLOCKED"},
            ["ATTEMPT_NOT_OBJECT"],
            failures,
            not_measured,
        )
    attempt_id = attempt.get("attempt_id")
    result = {
        "attempt_id": attempt_id if isinstance(attempt_id, str) else "",
        "cohort_member_id": attempt.get("cohort_member_id"),
        "population_status": attempt.get("population_status"),
        "terminal_status": attempt.get("terminal_status"),
        "status": "BLOCKED",
    }
    if not isinstance(attempt_id, str) or not attempt_id:
        blocking.append("ATTEMPT_ID_INVALID")
    if not _valid_digest(attempt.get("input_digest")):
        blocking.append("ATTEMPT_INPUT_DIGEST_INVALID")
    if not isinstance(attempt.get("cohort_member_id"), str) or not attempt[
        "cohort_member_id"
    ]:
        blocking.append("ATTEMPT_COHORT_MEMBER_ID_INVALID")
    population_status = attempt.get("population_status")
    terminal_status = attempt.get("terminal_status")
    if population_status not in {"ELIGIBLE", "EXCLUDED"}:
        blocking.append("ATTEMPT_POPULATION_STATUS_INVALID")
    if terminal_status not in _TERMINAL_STATUSES:
        blocking.append("ATTEMPT_TERMINAL_STATUS_INVALID")
    handoff_pass = _handoff_is_pass(attempt.get("apps_research_to_u0"))
    evidence_errors, evidence_statuses = _evidence_errors(
        attempt.get("element_evidence"), expected=expected
    )
    blocking.extend(evidence_errors)
    diagnostic_errors, diagnostic_statuses = _diagnostic_errors(
        attempt.get("diagnostic_receipts"),
        required_authorities=diagnostic_authorities,
    )
    blocking.extend(diagnostic_errors)
    guardrail_errors, guardrail_counts = _guardrail_errors(
        attempt.get("guardrails"), required_authorities=guardrail_authorities
    )
    blocking.extend(guardrail_errors)
    blocking.extend(_slice_errors(attempt.get("slice_values"), required_keys=slice_keys))
    exclusion_reason = attempt.get("exclusion_reason")
    terminal_stage = attempt.get("terminal_stage")
    terminal_reason = attempt.get("terminal_reason")
    runtime = attempt.get("runtime")
    blocking.extend(
        _slice_binding_errors(
            attempt.get("slice_values"),
            cohort_data_split=cohort_data_split,
            population_status=population_status,
            runtime=runtime,
        )
    )
    if population_status == "EXCLUDED":
        if handoff_pass:
            blocking.append("EXCLUDED_ATTEMPT_HANDOFF_MUST_NOT_PASS")
        if not isinstance(exclusion_reason, str) or not exclusion_reason:
            blocking.append("EXCLUDED_ATTEMPT_REASON_REQUIRED")
        if terminal_status != "NOT_STARTED" or terminal_stage not in (None, "") or terminal_reason not in (None, ""):
            blocking.append("EXCLUDED_ATTEMPT_TERMINAL_STATE_INVALID")
        if runtime is not None:
            blocking.append("EXCLUDED_ATTEMPT_RUNTIME_MUST_BE_EMPTY")
        for key, status in evidence_statuses.items():
            scope = expected[key].get("scope")
            if scope == "prerequisite":
                if status not in {"FAIL", "UNKNOWN"}:
                    blocking.append("EXCLUDED_PREREQUISITE_STATUS_INVALID")
            elif status != "NOT_RUN":
                blocking.append("EXCLUDED_ATTEMPT_NONPREREQUISITE_RAN")
        if any(status not in {"NOT_MEASURED", "UNKNOWN"} for status in diagnostic_statuses.values()):
            blocking.append("EXCLUDED_ATTEMPT_DIAGNOSTICS_INVALID")
        if any(count is not None for count in guardrail_counts.values()):
            blocking.append("EXCLUDED_ATTEMPT_GUARDRAILS_INVALID")
        result["status"] = "EXCLUDED" if not blocking else "BLOCKED"
        return result, blocking, failures, not_measured
    if population_status == "ELIGIBLE":
        if not handoff_pass:
            blocking.append("ELIGIBLE_ATTEMPT_HANDOFF_NOT_PASS")
        if evidence_statuses.get(("apps_research_to_u0", None)) != "PASS":
            blocking.append("ELIGIBLE_ATTEMPT_PREREQUISITE_EVIDENCE_INVALID")
        blocking.extend(_runtime_errors(runtime))
        if exclusion_reason not in (None, ""):
            blocking.append("ELIGIBLE_ATTEMPT_EXCLUSION_REASON_INVALID")
        if terminal_status == "COMPLETE":
            if terminal_stage != "EXIT" or terminal_reason not in (None, ""):
                blocking.append("COMPLETE_ATTEMPT_TERMINAL_STATE_INVALID")
            if any(
                status != "PASS"
                for key, status in evidence_statuses.items()
                if expected[key].get("required") is True
            ):
                blocking.append("COMPLETE_ATTEMPT_EVIDENCE_NOT_PASS")
        elif terminal_status in {"FAILED", "ABSTAINED"}:
            if terminal_stage not in _PIPELINE_STAGES or not isinstance(
                terminal_reason, str
            ) or not terminal_reason:
                blocking.append("INCOMPLETE_ATTEMPT_TERMINAL_CAUSE_INVALID")
            expected_terminal_evidence = (
                "FAIL" if terminal_status == "FAILED" else "ABSTAINED"
            )
            if terminal_stage in _PIPELINE_STAGES:
                if not _terminal_evidence_matches(
                    evidence_statuses,
                    expected,
                    terminal_stage=terminal_stage,
                    terminal_status=expected_terminal_evidence,
                ):
                    blocking.append("INCOMPLETE_ATTEMPT_TERMINAL_EVIDENCE_MISSING")
                blocking.extend(
                    _preterminal_evidence_errors(
                        evidence_statuses,
                        expected,
                        terminal_stage=terminal_stage,
                    )
                )
            if any(
                status == "UNKNOWN"
                for key, status in evidence_statuses.items()
                if expected[key].get("required") is True
            ):
                blocking.append("ELIGIBLE_ATTEMPT_UNKNOWN_EVIDENCE")
        elif terminal_status == "NOT_STARTED":
            blocking.append("ELIGIBLE_ATTEMPT_NOT_STARTED_INVALID")
        if "UNKNOWN" in diagnostic_statuses.values():
            blocking.append("ELIGIBLE_ATTEMPT_UNKNOWN_DIAGNOSTIC")
        if any(status == "FAIL" for status in diagnostic_statuses.values()):
            failures.append("ELIGIBLE_ATTEMPT_DIAGNOSTIC_FAILED")
        if any(status == "NOT_MEASURED" for status in diagnostic_statuses.values()):
            not_measured.append("ELIGIBLE_ATTEMPT_DIAGNOSTICS_NOT_MEASURED")
        if any(count not in (None, 0) for count in guardrail_counts.values()):
            failures.append("ELIGIBLE_ATTEMPT_CRITICAL_GUARDRAIL_FAILED")
        if any(count is None for count in guardrail_counts.values()):
            not_measured.append("ELIGIBLE_ATTEMPT_GUARDRAILS_NOT_MEASURED")
        result["status"] = (
            "BLOCKED"
            if blocking
            else "FAIL"
            if failures
            else "NOT_MEASURED"
            if not_measured
            else terminal_status
        )
    return result, blocking, failures, not_measured


def _source_identity_errors(value: Any, *, has_attempts: bool) -> list[str]:
    if not isinstance(value, Mapping):
        return ["PIPELINE_SOURCE_IDENTITY_INVALID"]
    if value.get("evaluator_version") != EVALUATOR_VERSION:
        return ["PIPELINE_EVALUATOR_VERSION_INVALID"]
    if not has_attempts:
        return []
    expected = current_source_identity()
    errors: list[str] = []
    if value.get("coverage_contract_digest") != expected["coverage_contract_digest"]:
        errors.append("PIPELINE_COVERAGE_CONTRACT_STALE")
    if value.get("source_contract_digests") != expected["source_contract_digests"]:
        errors.append("PIPELINE_SOURCE_CONTRACTS_STALE")
    return errors


def validate_pipeline_attempt_evaluation(
    path: Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Validate measurement completeness without executing or mutating Apps RG."""

    try:
        manifest = _load_json(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        manifest = {}
        blocking = ["PIPELINE_MANIFEST_UNREADABLE"]
    else:
        blocking: list[str] = []
    failures: list[str] = []
    not_measured: list[str] = []
    if manifest.get("schema_version") != MANIFEST_VERSION:
        blocking.append("PIPELINE_MANIFEST_SCHEMA_INVALID")
    if not isinstance(manifest.get("evaluation_id"), str) or not manifest[
        "evaluation_id"
    ]:
        blocking.append("PIPELINE_EVALUATION_ID_INVALID")
    attempts = manifest.get("attempts")
    if not isinstance(attempts, list):
        blocking.append("PIPELINE_ATTEMPTS_INVALID")
        attempts = []
    try:
        contract = load_pipeline_measurement_coverage(DEFAULT_CONTRACT_PATH)
        expected = expected_element_evidence(contract)
        slice_keys = required_slice_keys(contract)
        diagnostic_authorities, guardrail_authorities = (
            measurement_authority_requirements(contract)
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        contract = {}
        expected = {}
        slice_keys = ()
        diagnostic_authorities = {}
        guardrail_authorities = {}
        blocking.append("PIPELINE_COVERAGE_CONTRACT_INVALID")
    blocking.extend(
        _source_identity_errors(
            manifest.get("source_identity"), has_attempts=bool(attempts)
        )
    )
    if not attempts:
        not_measured.append("PIPELINE_NO_SOURCE_BOUND_ATTEMPTS")
    cohort_errors, frozen_member_ids = _cohort_errors(
        manifest.get("cohort"), has_attempts=bool(attempts)
    )
    blocking.extend(cohort_errors)
    cohort_data_split = (
        manifest["cohort"].get("data_split")
        if isinstance(manifest.get("cohort"), Mapping)
        else None
    )
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_member_ids: set[str] = set()
    eligible = 0
    excluded = 0
    complete = 0
    failed = 0
    abstained = 0
    for attempt in attempts:
        result, attempt_blocking, attempt_failures, attempt_not_measured = (
            _attempt_result(
                attempt,
                expected=expected,
                slice_keys=slice_keys,
                diagnostic_authorities=diagnostic_authorities,
                guardrail_authorities=guardrail_authorities,
                cohort_data_split=cohort_data_split,
            )
        )
        results.append(result)
        blocking.extend(attempt_blocking)
        failures.extend(attempt_failures)
        not_measured.extend(attempt_not_measured)
        attempt_id = result["attempt_id"]
        if not attempt_id or attempt_id in seen_ids:
            blocking.append("PIPELINE_ATTEMPT_ID_DUPLICATE")
        seen_ids.add(attempt_id)
        member_id = result["cohort_member_id"]
        if not isinstance(member_id, str) or not member_id or member_id in seen_member_ids:
            blocking.append("PIPELINE_COHORT_MEMBER_DUPLICATE_OR_INVALID")
        elif frozen_member_ids and member_id not in frozen_member_ids:
            blocking.append("PIPELINE_COHORT_MEMBER_OUTSIDE_FROZEN_POPULATION")
        seen_member_ids.add(member_id)
        if result["population_status"] == "ELIGIBLE":
            eligible += 1
            if result["terminal_status"] == "COMPLETE":
                complete += 1
            elif result["terminal_status"] == "FAILED":
                failed += 1
            elif result["terminal_status"] == "ABSTAINED":
                abstained += 1
        elif result["population_status"] == "EXCLUDED":
            excluded += 1
    if eligible != complete + failed + abstained:
        blocking.append("PIPELINE_ELIGIBLE_DENOMINATOR_CONSERVATION_FAILED")
    if frozen_member_ids and seen_member_ids != set(frozen_member_ids):
        blocking.append("PIPELINE_FROZEN_COHORT_MEMBERSHIP_INCOMPLETE")
    attempt_slice_values: dict[str, set[str]] = {
        key: set() for key in slice_keys
    }
    for attempt in attempts:
        if not isinstance(attempt, Mapping) or attempt.get("population_status") != "ELIGIBLE":
            continue
        values = attempt.get("slice_values")
        if not isinstance(values, Mapping):
            continue
        for key in slice_keys:
            value = values.get(key)
            if isinstance(value, str) and value:
                attempt_slice_values[key].add(value)
    status = (
        "BLOCKED"
        if blocking
        else "FAIL"
        if failures
        else "NOT_MEASURED"
        if not_measured
        else "PASS"
    )
    result: dict[str, Any] = {
        "schema_version": SUMMARY_VERSION,
        "evaluation_id": str(manifest.get("evaluation_id") or path.stem),
        "status": status,
        "coverage_contract_digest": canonical_digest(contract),
        "population_metrics": {
            "eligible_attempt_count": eligible,
            "excluded_attempt_count": excluded,
            "complete_attempt_count": complete,
            "failed_attempt_count": failed,
            "abstained_attempt_count": abstained,
            "grounded_decision_ready_completion_rate": complete / eligible
            if eligible
            else None,
        },
        "cohort": {
            "status": manifest.get("cohort", {}).get("status")
            if isinstance(manifest.get("cohort"), Mapping)
            else None,
            "cohort_id": manifest.get("cohort", {}).get("cohort_id")
            if isinstance(manifest.get("cohort"), Mapping)
            else None,
            "data_split": manifest.get("cohort", {}).get("data_split")
            if isinstance(manifest.get("cohort"), Mapping)
            else None,
            "frozen_member_count": len(frozen_member_ids),
            "frozen_member_ids_digest": manifest.get("cohort", {}).get(
                "frozen_member_ids_digest"
            )
            if isinstance(manifest.get("cohort"), Mapping)
            else None,
        },
        "slice_coverage": {
            "required_slice_keys": list(slice_keys),
            "eligible_values": {
                key: sorted(values) for key, values in attempt_slice_values.items()
            },
        },
        "outcomes": {
            "P1": {
                "status": "NOT_MEASURED",
                "reason_codes": ["P1_BLINDED_HUMAN_OUTCOME_NOT_LINKED"],
            },
            "P2": {
                "status": "NOT_MEASURED",
                "reason_codes": ["P2_HUMAN_QUALIFIED_OUTCOME_NOT_LINKED"],
            },
        },
        "attempt_results": results,
        "authority": {
            "technical_validation": True,
            "human_qualified": False,
            "release_authorizing": False,
            "production_authorizing": False,
        },
        "blocking_reasons": sorted(set(blocking)),
        "failure_reasons": sorted(set(failures)),
        "not_measured_reasons": sorted(set(not_measured)),
    }
    result["record_digest"] = canonical_digest(result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Apps RG source-bound pipeline attempt measurement"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args(argv)
    result = validate_pipeline_attempt_evaluation(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2
