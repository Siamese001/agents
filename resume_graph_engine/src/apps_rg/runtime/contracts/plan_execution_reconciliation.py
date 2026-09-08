"""W1 emission of exhaustive L1-plan execution observations.

This module projects plan-bound L1 work units over already-emitted execution
artifacts.  It does not dispatch work, retry it, choose a route, or authorize
an exit.  Missing evidence is deliberately represented as a terminal
non-completed outcome rather than being inferred as success.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.contracts.plan_execution_receipt import (
    PlanExecutionReceiptError,
    build_plan_execution_receipt,
    receipt_digest,
    validate_plan_execution_receipt,
)
from apps_rg.runtime.contracts.reasoning_control_execution_receipt import (
    ReasoningControlExecutionReceiptError,
    build_reasoning_control_execution_receipt,
    l2_observations_from_lane_records,
    receipt_digest as control_execution_receipt_digest,
    validate_reasoning_control_execution_receipt,
    write_reasoning_control_execution_receipt,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


PLAN_EXECUTION_RECONCILIATION_SCHEMA_VERSION: Final[str] = (
    "apps_rg.plan_execution_reconciliation.v2"
)
PLAN_EXECUTION_EMITTER: Final[str] = "apps_rg.runtime.contracts.plan_execution_reconciliation"

# L1 plans resume-visible units, while L2 emits the finer-grained lane
# artifacts.  These are the explicit, conservative mappings used to reconcile
# the two levels.  A completed aggregate requires every listed lane artifact.
_UNIT_LANES: Final[dict[str, tuple[str, ...]]] = {
    "headline": ("headline",),
    "executive_summary": ("executive_summary",),
    "competencies": ("competencies",),
    "skills": ("competencies",),
    "skills_block": ("competencies",),
    "experience": (
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "ey_bullets",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "ey_narrative",
    ),
    "experience_block": (
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "ey_bullets",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "ey_narrative",
    ),
}
_LOCKED_COPY_UNITS: Final[frozenset[str]] = frozenset(
    {"education", "education_block", "certifications", "certifications_block"}
)
_LOCKED_COPY_MANIFEST: Final[str] = "modular_r4/locked_copy/locked_copy_manifest.json"
_SECTION_CALLS: Final[str] = "modular_r4/section_provider_calls.json"
_RUNTIME_WITNESS: Final[str] = "runtime_execution_witness.json"
_CONTROL_RECEIPT_DIR: Final[str] = "reasoning_control_execution"
_C0_OBLIGATION_RECEIPT: Final[str] = "l1_evidence_obligation_receipt.json"


class PlanExecutionReconciliationError(ValueError):
    """Raised when W1 cannot emit or validate an exhaustive observation."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _relative_file_ref(artifact_dir: Path, value: Any) -> str:
    """Return a normalized receipt ref only for a file under this run."""

    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(artifact_dir.resolve())
        except ValueError:
            return ""
    absolute = artifact_dir / candidate
    if not absolute.is_file():
        return ""
    return candidate.as_posix()


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _detached_contract_value(value: Any) -> Any:
    """Return a serializable copy without mutating immutable ingress contracts."""

    if isinstance(value, Mapping):
        return {
            str(key): _detached_contract_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_detached_contract_value(item) for item in value]
    return copy.deepcopy(value)


def _control_receipt_ref(unit_id: str) -> str:
    safe_unit = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in unit_id
    ).strip("_")
    if not safe_unit:
        raise PlanExecutionReconciliationError("unit_id cannot form a receipt path")
    return f"{_CONTROL_RECEIPT_DIR}/{safe_unit}.json"


def _lane_records_by_lane(
    artifact_dir: Path,
) -> tuple[dict[str, list[Mapping[str, Any]]], str]:
    calls_ref = _relative_file_ref(artifact_dir, _SECTION_CALLS)
    if not calls_ref:
        return {}, "l2_section_provider_calls:absent"
    document = _read_json_mapping(artifact_dir / calls_ref)
    rows = document.get("records")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return {}, calls_ref
    by_lane: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        lane = str(row.get("section_lane") or row.get("lane") or "").strip()
        if lane:
            by_lane.setdefault(lane, []).append(row)
    return by_lane, calls_ref


def _c0_obligation_refs_by_unit(artifact_dir: Path) -> dict[str, list[str]]:
    receipt_ref = _relative_file_ref(artifact_dir, _C0_OBLIGATION_RECEIPT)
    if not receipt_ref:
        return {}
    receipt = _read_json_mapping(artifact_dir / receipt_ref)
    entries = receipt.get("obligation_dispositions")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        return {}
    refs_by_unit: dict[str, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        unit_id = str(entry.get("target_unit_id") or "").strip()
        if unit_id:
            refs_by_unit.setdefault(unit_id, []).append(receipt_ref)
    return {
        unit_id: sorted(set(refs)) for unit_id, refs in sorted(refs_by_unit.items())
    }


def _capsule_unit_maps(
    plan_capsule: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    units = plan_capsule.get("work_units") or ()
    evidence = plan_capsule.get("evidence_plan") or ()
    cognition = plan_capsule.get("cognition_plan") or ()
    if not all(isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)) for rows in (units, evidence, cognition)):
        raise PlanExecutionReconciliationError("L1 capsule plan surfaces must be sequences")

    def index(rows: Sequence[Any], name: str) -> dict[str, Mapping[str, Any]]:
        out: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise PlanExecutionReconciliationError(f"L1 {name} entries must be mappings")
            unit_id = str(row.get("unit_id") or "").strip()
            if not unit_id or unit_id in out:
                raise PlanExecutionReconciliationError(f"L1 {name} must have unique unit IDs")
            out[unit_id] = row
        return out

    by_unit = index(units, "work_units")
    evidence_by_unit = index(evidence, "evidence_plan")
    cognition_by_unit = index(cognition, "cognition_plan")
    if set(by_unit) != set(evidence_by_unit) or set(by_unit) != set(cognition_by_unit):
        raise PlanExecutionReconciliationError("L1 plan surfaces disagree on planned unit coverage")
    return by_unit, evidence_by_unit, cognition_by_unit


def _lane_output_refs(l2_result: Any, artifact_dir: Path) -> dict[str, str]:
    """Read the recipe's explicit lane-output references, never infer them."""

    source = _mapping(l2_result)
    if not source and l2_result is not None:
        source = _mapping(getattr(l2_result, "section_output_refs", None))
        if source:
            return {
                str(lane): ref
                for lane, value in source.items()
                if (ref := _relative_file_ref(artifact_dir, value))
            }
    outputs = source.get("section_output_refs") if isinstance(source, Mapping) else {}
    outputs = _mapping(outputs)
    return {
        str(lane): ref
        for lane, value in outputs.items()
        if (ref := _relative_file_ref(artifact_dir, value))
    }


def _required_lanes(unit_id: str, lane_refs: Mapping[str, str]) -> tuple[str, ...]:
    normalized = unit_id.strip().lower()
    if normalized in _LOCKED_COPY_UNITS:
        return ("locked_copy",)
    if normalized in _UNIT_LANES:
        return _UNIT_LANES[normalized]
    # Single-section plans use their section id as their L2 lane when it is a
    # known observed output.  Otherwise retain the explicit no-owner gap.
    if normalized in lane_refs:
        return (normalized,)
    return ()


def _artifact_refs_for_unit(
    *,
    unit_id: str,
    lane_refs: Mapping[str, str],
    artifact_dir: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    required = _required_lanes(unit_id, lane_refs)
    if required == ("locked_copy",):
        ref = _relative_file_ref(artifact_dir, _LOCKED_COPY_MANIFEST)
        return ((ref,) if ref else ()), required
    return tuple(lane_refs[lane] for lane in required if lane in lane_refs), required


def _control_execution_receipt_for_unit(
    *,
    plan_capsule: Mapping[str, Any],
    unit_id: str,
    required_lanes: Sequence[str],
    lane_records: Mapping[str, Sequence[Mapping[str, Any]]],
    lane_record_ref: str,
    c0_obligation_receipt_refs: Sequence[str],
    supplied_receipts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    supplied = supplied_receipts.get(unit_id)
    if supplied is not None:
        try:
            validate_reasoning_control_execution_receipt(
                supplied,
                plan_capsule=plan_capsule,
            )
        except ReasoningControlExecutionReceiptError as exc:
            raise PlanExecutionReconciliationError(
                f"W3 supplied control receipt is invalid for {unit_id}: {exc}"
            ) from exc
        return _detached_contract_value(dict(supplied))

    cognition_rows = plan_capsule.get("cognition_plan") or ()
    cognition = next(
        (
            row
            for row in cognition_rows
            if isinstance(row, Mapping) and str(row.get("unit_id") or "") == unit_id
        ),
        None,
    )
    if not isinstance(cognition, Mapping):
        raise PlanExecutionReconciliationError(
            f"W3 L1 cognition plan is missing unit {unit_id!r}"
        )
    requested_controls = _mapping(cognition.get("requested_controls"))
    if not requested_controls:
        raise PlanExecutionReconciliationError(
            f"W3 L1 requested controls are missing for {unit_id!r}"
        )
    unit_records = [
        record for lane in required_lanes for record in lane_records.get(str(lane), ())
    ]
    observed = l2_observations_from_lane_records(
        requested_controls=requested_controls,
        lane_records=unit_records,
        lane_record_ref=lane_record_ref,
    )
    try:
        return build_reasoning_control_execution_receipt(
            plan_capsule=plan_capsule,
            unit_id=unit_id,
            emitter_stage=str(observed["emitter_stage"]),
            provider_profiles=observed["provider_profiles"],
            model_ids=observed["model_ids"],
            candidate_count=int(observed["candidate_count"]),
            selection_method=str(observed["selection_method"]),
            execution_receipt_ref=_control_receipt_ref(unit_id),
            observed_controls=observed["observed_controls"],
            c0_obligation_receipt_refs=c0_obligation_receipt_refs,
        )
    except ReasoningControlExecutionReceiptError as exc:
        raise PlanExecutionReconciliationError(
            f"W3 control execution receipt could not be built for {unit_id}: {exc}"
        ) from exc


def _execution_state(execution_witness: Mapping[str, Any] | None) -> tuple[bool, str]:
    witness = _mapping(execution_witness)
    l2 = _mapping(witness.get("l2"))
    executed = l2.get("executed") is True
    fault = str(l2.get("fault") or "").strip()
    return executed, fault


def _outcome_for_observation(
    *,
    planning_status: str,
    l2_executed: bool,
    l2_fault: str,
    required_lanes: Sequence[str],
    artifact_refs: Sequence[str],
    quality_certification_eligible: bool,
) -> tuple[str, bool, str]:
    if planning_status != "READY":
        return "BLOCKED", False, "L1_PLAN_BLOCKED"
    if not l2_executed:
        return "SKIPPED", False, "POLICY_BLOCKED"
    if required_lanes and len(artifact_refs) == len(required_lanes):
        if not quality_certification_eligible:
            return "BLOCKED", True, "REQUIRED_CONTROL_EXECUTION_ABSENT"
        return "COMPLETED", True, ""
    if l2_fault:
        return "FAILED", True, "GENERATION_FAILED"
    return "BLOCKED", True, "REQUIRED_PROOF_ABSENT"


def _unit_observations(
    *,
    plan_capsule: Mapping[str, Any],
    artifact_dir: Path,
    execution_witness: Mapping[str, Any] | None,
    l2_result: Any,
    control_execution_receipts: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    units, evidence_by_unit, cognition_by_unit = _capsule_unit_maps(plan_capsule)
    planning_status = str(plan_capsule.get("planning_status") or "").strip().upper()
    l2_executed, l2_fault = _execution_state(execution_witness)
    lane_refs = _lane_output_refs(l2_result, artifact_dir)
    witness_ref = _relative_file_ref(artifact_dir, _RUNTIME_WITNESS)
    calls_ref = _relative_file_ref(artifact_dir, _SECTION_CALLS)
    lane_records, lane_record_ref = _lane_records_by_lane(artifact_dir)
    c0_refs_by_unit = _c0_obligation_refs_by_unit(artifact_dir)
    supplied_receipts = {
        str(unit_id): receipt
        for unit_id, receipt in (control_execution_receipts or {}).items()
        if isinstance(receipt, Mapping)
    }
    outcomes: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for unit_id, unit in units.items():
        artifact_refs, required_lanes = _artifact_refs_for_unit(
            unit_id=unit_id,
            lane_refs=lane_refs,
            artifact_dir=artifact_dir,
        )
        control_receipt = _control_execution_receipt_for_unit(
            plan_capsule=plan_capsule,
            unit_id=unit_id,
            required_lanes=required_lanes,
            lane_records=lane_records,
            lane_record_ref=lane_record_ref,
            c0_obligation_receipt_refs=c0_refs_by_unit.get(unit_id, ()),
            supplied_receipts=supplied_receipts,
        )
        quality = _mapping(control_receipt.get("quality_certification"))
        quality_eligible = quality.get("eligible") is True
        disposition, attempted, failure_code = _outcome_for_observation(
            planning_status=planning_status,
            l2_executed=l2_executed,
            l2_fault=l2_fault,
            required_lanes=required_lanes,
            artifact_refs=artifact_refs,
            quality_certification_eligible=quality_eligible,
        )
        actual_attempt_refs = (
            [ref for ref in (witness_ref, calls_ref) if ref] if l2_executed else []
        )
        outcomes.append(
            {
                "unit_id": unit_id,
                "disposition": disposition,
                "attempted": attempted,
                "failure_code": failure_code,
                "artifact_refs": list(artifact_refs),
                "control_receipt_refs": [str(control_receipt["execution_receipt_ref"])],
            }
        )
        observations.append(
            {
                "unit_id": unit_id,
                "planned_inputs": list(unit.get("required_inputs") or ()),
                "evidence_plan": _detached_contract_value(
                    dict(evidence_by_unit[unit_id])
                ),
                "requested_controls": _detached_contract_value(
                    _mapping(cognition_by_unit[unit_id]).get("requested_controls") or {}
                ),
                "reasoning_control_execution_receipt": control_receipt,
                "reasoning_control_execution_receipt_ref": str(
                    control_receipt["execution_receipt_ref"]
                ),
                "reasoning_control_execution_receipt_digest": str(
                    control_receipt["receipt_digest"]
                ),
                "l2_l3_applied_controls": list(
                    control_receipt["l2_l3_applied_controls"]
                ),
                "quality_certification_eligible": quality_eligible,
                "c0_obligation_receipt_refs": list(
                    control_receipt["c0_obligation_receipt_refs"]
                ),
                "required_execution_lanes": list(required_lanes),
                "observed_lane_artifacts": {
                    lane: lane_refs[lane]
                    for lane in required_lanes
                    if lane in lane_refs
                },
                "actual_attempt_refs": actual_attempt_refs,
                "artifact_refs": list(artifact_refs),
                "l2_fault": l2_fault if l2_executed else "",
                "disposition": disposition,
                "attempted": attempted,
            }
        )
    return outcomes, sorted(observations, key=lambda row: str(row["unit_id"]))


def build_plan_execution_reconciliation(
    *,
    request_id: str,
    run_id: str,
    plan_capsule: Mapping[str, Any],
    artifact_dir: Path,
    execution_witness: Mapping[str, Any] | None = None,
    l2_result: Any = None,
    control_execution_receipts: Mapping[str, Mapping[str, Any]] | None = None,
    terminal_reason: str = "",
) -> dict[str, Any]:
    """Build the W1 whole-run reconciliation without changing execution state."""

    artifact_dir = Path(artifact_dir)
    outcomes, observations = _unit_observations(
        plan_capsule=plan_capsule,
        artifact_dir=artifact_dir,
        execution_witness=execution_witness,
        l2_result=l2_result,
        control_execution_receipts=control_execution_receipts,
    )
    receipt = build_plan_execution_receipt(
        request_id=request_id,
        run_id=run_id,
        plan_capsule=plan_capsule,
        unit_outcomes=outcomes,
    )
    receipt["emission"] = {
        "schema_version": PLAN_EXECUTION_RECONCILIATION_SCHEMA_VERSION,
        "wave": "W1",
        "emitter": PLAN_EXECUTION_EMITTER,
        "terminal_reason": str(terminal_reason or "").strip(),
        "observation_only": True,
        "w3_control_reconciliation": True,
    }
    receipt["unit_observations"] = observations
    receipt["receipt_digest"] = receipt_digest(receipt)
    validate_plan_execution_reconciliation(receipt)
    return receipt


def validate_plan_execution_reconciliation(receipt: Mapping[str, Any]) -> None:
    """Validate both W0 receipt integrity and W1 per-unit observation coverage."""

    try:
        validate_plan_execution_receipt(receipt)
    except PlanExecutionReceiptError as exc:
        raise PlanExecutionReconciliationError(str(exc)) from exc
    emission = _mapping(receipt.get("emission"))
    if (
        emission.get("schema_version") != PLAN_EXECUTION_RECONCILIATION_SCHEMA_VERSION
        or emission.get("wave") != "W1"
        or emission.get("emitter") != PLAN_EXECUTION_EMITTER
        or emission.get("observation_only") is not True
        or emission.get("w3_control_reconciliation") is not True
    ):
        raise PlanExecutionReconciliationError("W1 emission metadata is invalid")
    observations = receipt.get("unit_observations")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise PlanExecutionReconciliationError(
            "W1 unit observations must be a sequence"
        )
    outcomes = {
        str(row.get("unit_id") or ""): row
        for row in receipt.get("unit_outcomes") or ()
        if isinstance(row, Mapping)
    }
    observed_ids: set[str] = set()
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise PlanExecutionReconciliationError(
                "W1 unit observation must be a mapping"
            )
        unit_id = str(observation.get("unit_id") or "").strip()
        if not unit_id or unit_id in observed_ids or unit_id not in outcomes:
            raise PlanExecutionReconciliationError(
                "W1 unit observation coverage is invalid"
            )
        observed_ids.add(unit_id)
        if not isinstance(observation.get("planned_inputs"), Sequence) or isinstance(
            observation.get("planned_inputs"), (str, bytes)
        ):
            raise PlanExecutionReconciliationError(
                "W1 planned_inputs must be a sequence"
            )
        evidence_plan = observation.get("evidence_plan")
        if (
            not isinstance(evidence_plan, Mapping)
            or evidence_plan.get("unit_id") != unit_id
        ):
            raise PlanExecutionReconciliationError(
                "W1 evidence plan binding is invalid"
            )
        if not isinstance(observation.get("requested_controls"), Mapping):
            raise PlanExecutionReconciliationError(
                "W1 requested controls must be a mapping"
            )
        control_receipt = observation.get("reasoning_control_execution_receipt")
        if not isinstance(control_receipt, Mapping):
            raise PlanExecutionReconciliationError("W3 control receipt is required")
        if control_receipt.get("receipt_digest") != control_execution_receipt_digest(
            control_receipt
        ):
            raise PlanExecutionReconciliationError(
                "W3 control receipt digest is invalid"
            )
        if (
            control_receipt.get("plan_capsule_digest")
            != receipt["plan"].get("capsule_digest")
            or control_receipt.get("unit_id") != unit_id
        ):
            raise PlanExecutionReconciliationError(
                "W3 control receipt is not plan-bound"
            )
        if observation.get(
            "reasoning_control_execution_receipt_ref"
        ) != control_receipt.get("execution_receipt_ref") or observation.get(
            "reasoning_control_execution_receipt_digest"
        ) != control_receipt.get("receipt_digest"):
            raise PlanExecutionReconciliationError(
                "W3 control receipt reference is invalid"
            )
        control_rows = control_receipt.get("control_observations")
        if not isinstance(control_rows, Sequence) or isinstance(
            control_rows, (str, bytes)
        ):
            raise PlanExecutionReconciliationError(
                "W3 control observations are invalid"
            )
        controls_by_name = {
            str(row.get("control_name") or ""): row
            for row in control_rows
            if isinstance(row, Mapping)
        }
        requested_controls = _mapping(observation.get("requested_controls"))
        if set(controls_by_name) != set(requested_controls) or any(
            controls_by_name[name].get("requested_value") != value
            for name, value in requested_controls.items()
        ):
            raise PlanExecutionReconciliationError(
                "W3 control receipt does not cover requested controls exactly"
            )
        applied_controls = [
            str(row.get("control_name") or "")
            for row in control_rows
            if isinstance(row, Mapping)
            and row.get("execution_status") in {"APPLIED", "ADAPTED"}
        ]
        if observation.get("l2_l3_applied_controls") != applied_controls:
            raise PlanExecutionReconciliationError(
                "W3 applied control summary is invalid"
            )
        quality = _mapping(control_receipt.get("quality_certification"))
        if observation.get("quality_certification_eligible") is not quality.get(
            "eligible"
        ):
            raise PlanExecutionReconciliationError(
                "W3 quality certification summary is invalid"
            )
        c0_refs = observation.get("c0_obligation_receipt_refs")
        if not isinstance(c0_refs, Sequence) or isinstance(c0_refs, (str, bytes)):
            raise PlanExecutionReconciliationError("W3 C0 receipt refs are invalid")
        if list(c0_refs) != list(
            control_receipt.get("c0_obligation_receipt_refs") or []
        ):
            raise PlanExecutionReconciliationError(
                "W3 C0 receipt refs do not reconcile"
            )
        for field in (
            "required_execution_lanes",
            "actual_attempt_refs",
            "artifact_refs",
        ):
            value = observation.get(field)
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                raise PlanExecutionReconciliationError(f"W1 {field} must be a sequence")
        if not isinstance(observation.get("l2_fault"), str):
            raise PlanExecutionReconciliationError("W1 l2_fault must be a string")
        expected = outcomes[unit_id]
        if (
            observation.get("disposition") != expected.get("disposition")
            or observation.get("attempted") is not expected.get("attempted")
            or list(observation.get("artifact_refs") or [])
            != list(expected.get("artifact_refs") or [])
        ):
            raise PlanExecutionReconciliationError(
                "W1 observation does not match its terminal outcome"
            )
        required = list(observation.get("required_execution_lanes") or [])
        observed = _mapping(observation.get("observed_lane_artifacts"))
        if any(
            str(lane) not in observed for lane in required if str(lane) != "locked_copy"
        ):
            if expected.get("disposition") == "COMPLETED":
                raise PlanExecutionReconciliationError(
                    "completed W1 unit is missing a required lane artifact"
                )
        if expected.get("disposition") == "COMPLETED" and not quality.get("eligible"):
            raise PlanExecutionReconciliationError(
                "completed W1 unit lacks required control execution proof"
            )
        if list(expected.get("control_receipt_refs") or []) != [
            str(control_receipt.get("execution_receipt_ref") or "")
        ]:
            raise PlanExecutionReconciliationError(
                "W3 control receipt outcome binding is invalid"
            )
    if observed_ids != set(outcomes):
        raise PlanExecutionReconciliationError(
            "W1 observations omit planned execution outcomes"
        )


def emit_plan_execution_reconciliation(**kwargs: Any) -> Path:
    """Build, validate, and write the canonical W1 receipt for a run."""

    artifact_dir = Path(kwargs["artifact_dir"])
    receipt = build_plan_execution_reconciliation(**kwargs)
    plan_capsule = kwargs["plan_capsule"]
    for observation in receipt["unit_observations"]:
        control_receipt = observation["reasoning_control_execution_receipt"]
        output_ref = str(control_receipt["execution_receipt_ref"])
        write_reasoning_control_execution_receipt(
            output_path=artifact_dir / output_ref,
            receipt=control_receipt,
            plan_capsule=plan_capsule,
        )
    path = artifact_dir / sr.FILENAME_PLAN_EXECUTION_RECEIPT
    sr.write_stage_receipt(path, receipt)
    return path


__all__ = [
    "PLAN_EXECUTION_RECONCILIATION_SCHEMA_VERSION",
    "PlanExecutionReconciliationError",
    "build_plan_execution_reconciliation",
    "emit_plan_execution_reconciliation",
    "validate_plan_execution_reconciliation",
]
