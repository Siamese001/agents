"""App-local L2/L3 proof for requested L1 reasoning controls.

L1 only requests controls. This contract records L2/L3 observations of the
actual transport and selection run. It never treats an L1 request, a provider
profile, or an output artifact as proof that a reasoning control was applied.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_planning_capsule import (
    PlanningCapsuleIntegrityError,
    verify_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr
from apps_rg.runtime.reasoning.section_reasoning_intensity import (
    control_semantics_for_requested_controls,
)

REASONING_CONTROL_EXECUTION_RECEIPT_SCHEMA_VERSION: Final[str] = (
    "apps_rg.reasoning_control_execution_receipt.v1"
)
REASONING_CONTROL_EXECUTION_RECEIPT_AUTHORITY: Final[str] = (
    "L2_L3_EXECUTION_OBSERVATION_ONLY"
)
VALID_EMITTER_STAGES: Final[frozenset[str]] = frozenset({"L2", "L3"})
VALID_SUPPORT_STATUSES: Final[frozenset[str]] = frozenset(
    {"SUPPORTED", "UNSUPPORTED", "UNKNOWN"}
)
VALID_EXECUTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"APPLIED", "ADAPTED", "IGNORED", "BLOCKED"}
)
_APPLIED_STATUSES: Final[frozenset[str]] = frozenset({"APPLIED", "ADAPTED"})


class ReasoningControlExecutionReceiptError(ValueError):
    """Raised when an L2/L3 control-execution observation is untrustworthy."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return the stable digest excluding the self-referential digest field."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return "sha256:" + hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _required_string(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ReasoningControlExecutionReceiptError(f"{field} is required")
    return text


def _safe_ref(value: Any, *, field: str, required: bool = True) -> str:
    ref = str(value or "").strip().replace("\\", "/")
    if not ref:
        if required:
            raise ReasoningControlExecutionReceiptError(f"{field} is required")
        return ""
    candidate = Path(ref)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ReasoningControlExecutionReceiptError(f"{field} must be relative")
    return ref


def _unique_strings(value: Any, *, field: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReasoningControlExecutionReceiptError(f"{field} must be a sequence")
    rows = [str(item or "").strip() for item in value]
    if not allow_empty and not rows:
        raise ReasoningControlExecutionReceiptError(f"{field} must not be empty")
    if any(not item for item in rows) or len(set(rows)) != len(rows):
        raise ReasoningControlExecutionReceiptError(
            f"{field} must contain unique non-empty values"
        )
    return sorted(rows)


def _value_equal(left: Any, right: Any) -> bool:
    return _canonical_json(left) == _canonical_json(right)


def _cognition_row(capsule: Mapping[str, Any], unit_id: str) -> Mapping[str, Any]:
    rows = capsule.get("cognition_plan")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise ReasoningControlExecutionReceiptError("L1 cognition_plan is invalid")
    matches = [
        row
        for row in rows
        if isinstance(row, Mapping) and str(row.get("unit_id") or "") == unit_id
    ]
    if len(matches) != 1:
        raise ReasoningControlExecutionReceiptError(
            "L1 cognition_plan must contain exactly one requested control row per unit"
        )
    return matches[0]


def _control_semantics(cognition_row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    requested = cognition_row.get("requested_controls")
    if not isinstance(requested, Mapping) or not requested:
        raise ReasoningControlExecutionReceiptError("L1 requested_controls are invalid")
    expected = control_semantics_for_requested_controls(dict(requested))
    declared = cognition_row.get("control_semantics")
    if not isinstance(declared, Mapping):
        declared = expected
    if declared != expected:
        raise ReasoningControlExecutionReceiptError(
            "L1 control semantics do not match the fixed certification policy"
        )
    normalized: dict[str, dict[str, Any]] = {}
    for control_name in sorted(expected):
        item = declared.get(control_name)
        if not isinstance(item, Mapping):
            raise ReasoningControlExecutionReceiptError(
                "L1 control semantic row is invalid"
            )
        if item.get("requested") != requested[control_name]:
            raise ReasoningControlExecutionReceiptError(
                "L1 control semantic requested value is invalid"
            )
        if not isinstance(item.get("required_for_certification"), bool):
            raise ReasoningControlExecutionReceiptError(
                "L1 control semantic certification flag is invalid"
            )
        if item.get("transport_supported") != "L2_OR_L3_MUST_OBSERVE":
            raise ReasoningControlExecutionReceiptError(
                "L1 control semantics cannot claim transport support"
            )
        if item.get("receipt_required") is not True:
            raise ReasoningControlExecutionReceiptError(
                "L1 control semantics must require an execution receipt"
            )
        normalized[control_name] = {
            "requested": requested[control_name],
            "required_for_certification": expected[control_name][
                "required_for_certification"
            ],
            "receipt_required": True,
        }
    return normalized


def _normalize_control_observations(
    observations: Mapping[str, Any],
    *,
    semantics: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(observations, Mapping) or set(observations) != set(semantics):
        raise ReasoningControlExecutionReceiptError(
            "L2/L3 observations must cover requested controls exactly"
        )
    rows: list[dict[str, Any]] = []
    for control_name in sorted(semantics):
        raw = observations.get(control_name)
        if not isinstance(raw, Mapping):
            raise ReasoningControlExecutionReceiptError(
                "L2/L3 control observation must be a mapping"
            )
        support_status = (
            str(raw.get("support_status") or raw.get("transport_support_status") or "")
            .strip()
            .upper()
        )
        execution_status = str(raw.get("execution_status") or "").strip().upper()
        if support_status not in VALID_SUPPORT_STATUSES:
            raise ReasoningControlExecutionReceiptError(
                "control support_status is invalid"
            )
        if execution_status not in VALID_EXECUTION_STATUSES:
            raise ReasoningControlExecutionReceiptError(
                "control execution_status is invalid"
            )
        requested_value = semantics[control_name]["requested"]
        observed_value = raw.get("observed_value")
        evidence_ref = _safe_ref(raw.get("evidence_ref"), field="control evidence_ref")
        reason_code = _required_string(raw.get("reason_code"), field="reason_code")
        if execution_status in _APPLIED_STATUSES and support_status != "SUPPORTED":
            raise ReasoningControlExecutionReceiptError(
                "applied/adapted controls require transport support"
            )
        if execution_status == "APPLIED" and not _value_equal(
            observed_value, requested_value
        ):
            raise ReasoningControlExecutionReceiptError(
                "applied control must equal its requested value"
            )
        rows.append(
            {
                "control_name": control_name,
                "requested_value": requested_value,
                "required_for_certification": bool(
                    semantics[control_name]["required_for_certification"]
                ),
                "receipt_required": True,
                "transport_support_status": support_status,
                "execution_status": execution_status,
                "observed_value": observed_value,
                "evidence_ref": evidence_ref,
                "reason_code": reason_code,
            }
        )
    return rows


def build_reasoning_control_execution_receipt(
    *,
    plan_capsule: Mapping[str, Any],
    unit_id: str,
    emitter_stage: str,
    provider_profiles: Sequence[str],
    model_ids: Sequence[str],
    candidate_count: int,
    selection_method: str,
    execution_receipt_ref: str,
    observed_controls: Mapping[str, Any],
    c0_obligation_receipt_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Bind observed L2/L3 control states to one verified L1 plan unit."""

    try:
        verification = verify_apps_rg_l1_planning_capsule(plan_capsule)
    except PlanningCapsuleIntegrityError as exc:
        raise ReasoningControlExecutionReceiptError(
            f"invalid L1 planning capsule: {exc}"
        ) from exc
    normalized_unit_id = _required_string(unit_id, field="unit_id")
    stage = _required_string(emitter_stage, field="emitter_stage").upper()
    if stage not in VALID_EMITTER_STAGES:
        raise ReasoningControlExecutionReceiptError("emitter_stage must be L2 or L3")
    if not isinstance(candidate_count, int) or isinstance(candidate_count, bool):
        raise ReasoningControlExecutionReceiptError(
            "candidate_count must be an integer"
        )
    if candidate_count < 0:
        raise ReasoningControlExecutionReceiptError(
            "candidate_count must not be negative"
        )
    cognition_row = _cognition_row(plan_capsule, normalized_unit_id)
    semantics = _control_semantics(cognition_row)
    controls = _normalize_control_observations(observed_controls, semantics=semantics)
    required_failures = [
        row["control_name"]
        for row in controls
        if row["required_for_certification"]
        and row["execution_status"] not in _APPLIED_STATUSES
    ]
    receipt: dict[str, Any] = {
        "schema_version": REASONING_CONTROL_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "authority_class": REASONING_CONTROL_EXECUTION_RECEIPT_AUTHORITY,
        "emitter_stage": stage,
        "request_id": str(plan_capsule.get("request_id") or ""),
        "run_id": str(plan_capsule.get("run_id") or ""),
        "trace_id": str(plan_capsule.get("trace_id") or ""),
        "plan_capsule_digest": str(verification["capsule_digest"]),
        "unit_id": normalized_unit_id,
        "provider_configuration": {
            "provider_profiles": _unique_strings(
                provider_profiles, field="provider_profiles"
            ),
            "model_ids": _unique_strings(model_ids, field="model_ids"),
            "candidate_count": candidate_count,
            "selection_method": _required_string(
                selection_method, field="selection_method"
            ),
        },
        "execution_receipt_ref": _safe_ref(
            execution_receipt_ref, field="execution_receipt_ref"
        ),
        "c0_obligation_receipt_refs": [
            _safe_ref(ref, field="c0_obligation_receipt_ref")
            for ref in _unique_strings(
                c0_obligation_receipt_refs,
                field="c0_obligation_receipt_refs",
                allow_empty=True,
            )
        ],
        "control_observations": controls,
        "l2_l3_applied_controls": [
            row["control_name"]
            for row in controls
            if row["execution_status"] in _APPLIED_STATUSES
        ],
        "quality_certification": {
            "required_control_failures": required_failures,
            "eligible": not required_failures,
            "denied": bool(required_failures),
        },
        "authority_assertions": {
            "l1_requests_only": True,
            "controls_applied_emitted_by_l2_or_l3": True,
            "does_not_authorize_route_or_exit": True,
            "does_not_create_candidate_evidence": True,
        },
    }
    receipt["receipt_digest"] = receipt_digest(receipt)
    validate_reasoning_control_execution_receipt(receipt, plan_capsule=plan_capsule)
    return receipt


def validate_reasoning_control_execution_receipt(
    receipt: Mapping[str, Any],
    *,
    plan_capsule: Mapping[str, Any],
) -> None:
    """Fail closed unless L2/L3 observed every requested L1 control exactly."""

    if not isinstance(receipt, Mapping):
        raise ReasoningControlExecutionReceiptError("receipt must be a mapping")
    if (
        receipt.get("schema_version")
        != REASONING_CONTROL_EXECUTION_RECEIPT_SCHEMA_VERSION
    ):
        raise ReasoningControlExecutionReceiptError("receipt schema_version is invalid")
    if receipt.get("authority_class") != REASONING_CONTROL_EXECUTION_RECEIPT_AUTHORITY:
        raise ReasoningControlExecutionReceiptError(
            "receipt authority_class is invalid"
        )
    if str(receipt.get("emitter_stage") or "") not in VALID_EMITTER_STAGES:
        raise ReasoningControlExecutionReceiptError("receipt emitter_stage is invalid")
    if receipt.get("receipt_digest") != receipt_digest(receipt):
        raise ReasoningControlExecutionReceiptError("receipt digest mismatch")
    try:
        verification = verify_apps_rg_l1_planning_capsule(plan_capsule)
    except PlanningCapsuleIntegrityError as exc:
        raise ReasoningControlExecutionReceiptError(
            "receipt L1 capsule is invalid"
        ) from exc
    for field in ("request_id", "run_id", "trace_id"):
        if receipt.get(field) != plan_capsule.get(field):
            raise ReasoningControlExecutionReceiptError(
                "receipt identity is not L1-bound"
            )
    if receipt.get("plan_capsule_digest") != verification["capsule_digest"]:
        raise ReasoningControlExecutionReceiptError("receipt capsule digest is invalid")
    unit_id = _required_string(receipt.get("unit_id"), field="unit_id")
    cognition_row = _cognition_row(plan_capsule, unit_id)
    semantics = _control_semantics(cognition_row)
    configuration = receipt.get("provider_configuration")
    if not isinstance(configuration, Mapping):
        raise ReasoningControlExecutionReceiptError("provider_configuration is invalid")
    _unique_strings(configuration.get("provider_profiles"), field="provider_profiles")
    _unique_strings(configuration.get("model_ids"), field="model_ids")
    candidate_count = configuration.get("candidate_count")
    if not isinstance(candidate_count, int) or isinstance(candidate_count, bool):
        raise ReasoningControlExecutionReceiptError("candidate_count is invalid")
    if candidate_count < 0:
        raise ReasoningControlExecutionReceiptError("candidate_count is invalid")
    _required_string(configuration.get("selection_method"), field="selection_method")
    _safe_ref(receipt.get("execution_receipt_ref"), field="execution_receipt_ref")
    c0_refs = _unique_strings(
        receipt.get("c0_obligation_receipt_refs"),
        field="c0_obligation_receipt_refs",
        allow_empty=True,
    )
    for ref in c0_refs:
        _safe_ref(ref, field="c0_obligation_receipt_ref")
    observations = receipt.get("control_observations")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise ReasoningControlExecutionReceiptError("control_observations are invalid")
    by_control: dict[str, Mapping[str, Any]] = {}
    for row in observations:
        if not isinstance(row, Mapping):
            raise ReasoningControlExecutionReceiptError(
                "control observation is invalid"
            )
        name = str(row.get("control_name") or "")
        if not name or name in by_control:
            raise ReasoningControlExecutionReceiptError(
                "control observation coverage is invalid"
            )
        by_control[name] = row
    remapped = {name: by_control[name] for name in by_control}
    normalized = _normalize_control_observations(remapped, semantics=semantics)
    if list(observations) != normalized:
        raise ReasoningControlExecutionReceiptError(
            "control observations are not canonical"
        )
    applied = [
        row["control_name"]
        for row in normalized
        if row["execution_status"] in _APPLIED_STATUSES
    ]
    if receipt.get("l2_l3_applied_controls") != applied:
        raise ReasoningControlExecutionReceiptError(
            "applied control summary is invalid"
        )
    failures = [
        row["control_name"]
        for row in normalized
        if row["required_for_certification"]
        and row["execution_status"] not in _APPLIED_STATUSES
    ]
    quality = receipt.get("quality_certification")
    if not isinstance(quality, Mapping) or quality != {
        "required_control_failures": failures,
        "eligible": not failures,
        "denied": bool(failures),
    }:
        raise ReasoningControlExecutionReceiptError(
            "quality certification reconciliation is invalid"
        )
    assertions = receipt.get("authority_assertions")
    required_assertions = {
        "l1_requests_only",
        "controls_applied_emitted_by_l2_or_l3",
        "does_not_authorize_route_or_exit",
        "does_not_create_candidate_evidence",
    }
    if not isinstance(assertions, Mapping) or any(
        assertions.get(name) is not True for name in required_assertions
    ):
        raise ReasoningControlExecutionReceiptError(
            "receipt authority assertions are invalid"
        )


def l2_observations_from_lane_records(
    *,
    requested_controls: Mapping[str, Any],
    lane_records: Sequence[Mapping[str, Any]],
    lane_record_ref: str,
) -> dict[str, Any]:
    """Derive conservative L2 observations from section-provider call records.

    The phase-1 record proves temperature and self-consistency counts only. It
    deliberately records ToT/reflection as unsupported until a runner emits
    explicit L2/L3 evidence for those controls.
    """

    ref = _safe_ref(lane_record_ref, field="lane_record_ref")
    usable = [
        row
        for row in lane_records
        if isinstance(row, Mapping) and row.get("provider_call_attempted") is True
    ]
    provider_profiles = sorted(
        {str(row.get("provider_profile") or "NOT_OBSERVED") for row in usable}
    ) or ["NOT_OBSERVED"]
    model_ids = sorted(
        {str(row.get("model_id") or "NOT_OBSERVED") for row in usable}
    ) or ["NOT_OBSERVED"]
    observations: dict[str, dict[str, Any]] = {}
    for name, requested in sorted(requested_controls.items()):
        if name == "temperature":
            values = [row.get("temperature") for row in usable if "temperature" in row]
            if values:
                observations[name] = {
                    "support_status": "SUPPORTED",
                    "execution_status": "APPLIED"
                    if all(_value_equal(value, requested) for value in values)
                    else "ADAPTED",
                    "observed_value": values[0]
                    if len(set(map(str, values))) == 1
                    else values,
                    "evidence_ref": ref,
                    "reason_code": "L2_SECTION_PROVIDER_CALL_TEMPERATURE_OBSERVED",
                }
            else:
                observations[name] = {
                    "support_status": "UNKNOWN",
                    "execution_status": "BLOCKED",
                    "observed_value": None,
                    "evidence_ref": ref,
                    "reason_code": "L2_SECTION_PROVIDER_CALL_ABSENT",
                }
        elif name == "self_consistency_samples":
            values = [
                row.get("self_consistency_executed")
                for row in usable
                if isinstance(row.get("self_consistency_executed"), int)
            ]
            if values:
                observations[name] = {
                    "support_status": "SUPPORTED",
                    "execution_status": "APPLIED"
                    if len(values) == 1 and _value_equal(values[0], requested)
                    else "ADAPTED",
                    "observed_value": values[0] if len(values) == 1 else values,
                    "evidence_ref": ref,
                    "reason_code": "L2_SECTION_PROVIDER_CALL_SELF_CONSISTENCY_OBSERVED",
                }
            else:
                observations[name] = {
                    "support_status": "UNKNOWN",
                    "execution_status": "BLOCKED",
                    "observed_value": None,
                    "evidence_ref": ref,
                    "reason_code": "L2_SECTION_PROVIDER_CALL_ABSENT",
                }
        else:
            observations[name] = {
                "support_status": "UNSUPPORTED",
                "execution_status": "IGNORED",
                "observed_value": None,
                "evidence_ref": ref,
                "reason_code": "L2_LANE_RECORD_HAS_NO_TRANSPORT_CONTROL_OBSERVATION",
            }
    return {
        "emitter_stage": "L2",
        "provider_profiles": provider_profiles,
        "model_ids": model_ids,
        "candidate_count": sum(
            int(row.get("self_consistency_executed") or 0) for row in usable
        ),
        "selection_method": (
            "L2_SECTION_PROVIDER_CALLS"
            if usable
            else "L2_SECTION_PROVIDER_CALLS_NOT_OBSERVED"
        ),
        "observed_controls": observations,
    }


def write_reasoning_control_execution_receipt(
    *, output_path: Path, receipt: Mapping[str, Any], plan_capsule: Mapping[str, Any]
) -> Path:
    """Validate and write one caller-owned L2/L3 execution receipt."""

    validate_reasoning_control_execution_receipt(receipt, plan_capsule=plan_capsule)
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


__all__ = [
    "REASONING_CONTROL_EXECUTION_RECEIPT_AUTHORITY",
    "REASONING_CONTROL_EXECUTION_RECEIPT_SCHEMA_VERSION",
    "ReasoningControlExecutionReceiptError",
    "VALID_EMITTER_STAGES",
    "VALID_EXECUTION_STATUSES",
    "VALID_SUPPORT_STATUSES",
    "build_reasoning_control_execution_receipt",
    "l2_observations_from_lane_records",
    "receipt_digest",
    "validate_reasoning_control_execution_receipt",
    "write_reasoning_control_execution_receipt",
]
