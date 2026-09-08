"""Immutable W0 contract for reconciling an L1 plan with execution outcomes.

This module defines the contract only.  It does not execute work units, retry
them, choose a route, retrieve evidence, or authorize an outcome.  Later waves
may emit this receipt from the orchestration boundary and use the declared
failure taxonomy to choose a governed replan.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml

from apps_rg.runtime.bindings.l1_planning_capsule import (
    PlanningCapsuleIntegrityError,
    verify_apps_rg_l1_planning_capsule,
)
from apps_rg.repository_layout import repository_root, resolve_apps_rg_path


PLAN_EXECUTION_RECEIPT_SCHEMA_VERSION: Final[str] = (
    "apps_rg.plan_execution_receipt.v1"
)
PLAN_EXECUTION_RECEIPT_CONTRACT_TYPE: Final[str] = "PlanExecutionReceipt"
FAILURE_TAXONOMY_RELPATH: Final[Path] = Path(
    "apps_rg/runtime/contracts/plan_execution_failure_taxonomy.yaml"
)

VALID_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"COMPLETED", "BLOCKED", "SKIPPED", "FAILED"}
)
_FAILURE_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"BLOCKED", "SKIPPED", "FAILED"}
)


class PlanExecutionReceiptError(ValueError):
    """Raised when a receipt is incomplete, inconsistent, or digest-invalid."""


def failure_taxonomy_path() -> Path:
    """Return the app-owned W0 failure-taxonomy location."""

    return resolve_apps_rg_path(
        repository_root(Path(__file__)),
        "runtime",
        "contracts",
        FAILURE_TAXONOMY_RELPATH.name,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return the stable digest of a receipt, excluding its own digest field."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return "sha256:" + hashlib.sha256(
        _canonical_json(body).encode("utf-8")
    ).hexdigest()


def load_failure_taxonomy(path: Path | None = None) -> dict[str, Any]:
    """Load and minimally validate the declarative W0 failure taxonomy."""

    taxonomy_path = path or failure_taxonomy_path()
    try:
        data = yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlanExecutionReceiptError(
            f"cannot read plan-execution failure taxonomy: {taxonomy_path}"
        ) from exc
    except yaml.YAMLError as exc:
        raise PlanExecutionReceiptError(
            f"invalid plan-execution failure taxonomy: {taxonomy_path}"
        ) from exc
    if not isinstance(data, dict):
        raise PlanExecutionReceiptError("plan-execution failure taxonomy must be a mapping")
    if data.get("schema_version") != "apps_rg.plan_execution_failure_taxonomy.v1":
        raise PlanExecutionReceiptError("unsupported plan-execution failure taxonomy")
    codes = data.get("failure_codes")
    if not isinstance(codes, Sequence) or isinstance(codes, (str, bytes)):
        raise PlanExecutionReceiptError("failure taxonomy must contain failure_codes")
    for row in codes:
        if not isinstance(row, Mapping):
            raise PlanExecutionReceiptError("failure taxonomy entries must be mappings")
        code = str(row.get("code") or "").strip()
        failure_class = str(row.get("failure_class") or "").strip()
        dispositions = row.get("allowed_dispositions")
        if not code or not failure_class:
            raise PlanExecutionReceiptError("failure taxonomy entries need code and class")
        if (
            not isinstance(dispositions, Sequence)
            or isinstance(dispositions, (str, bytes))
            or not dispositions
            or not set(str(value) for value in dispositions) <= _FAILURE_DISPOSITIONS
        ):
            raise PlanExecutionReceiptError(
                f"failure taxonomy {code!r} has invalid allowed_dispositions"
            )
    return data


def failure_taxonomy_by_code(
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Mapping[str, Any]]:
    """Return the taxonomy indexed by its stable failure code."""

    data = taxonomy or load_failure_taxonomy()
    rows = data.get("failure_codes") or ()
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        code = str(row.get("code") or "").strip()
        if not code or code in out:
            raise PlanExecutionReceiptError(
                f"plan-execution failure taxonomy has duplicate/blank code: {code!r}"
            )
        out[code] = row
    if not out:
        raise PlanExecutionReceiptError("plan-execution failure taxonomy is empty")
    return out


def _normalize_refs(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PlanExecutionReceiptError(f"{field_name} must be a sequence of references")
    refs = [str(ref).strip() for ref in value]
    if not all(refs) or len(set(refs)) != len(refs):
        raise PlanExecutionReceiptError(
            f"{field_name} must contain unique non-empty references"
        )
    return refs


def _planned_units(capsule: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    units = capsule.get("work_units")
    if not isinstance(units, Sequence) or isinstance(units, (str, bytes)):
        raise PlanExecutionReceiptError("verified L1 capsule must contain work_units")
    normalized: list[Mapping[str, Any]] = []
    unit_ids: list[str] = []
    for unit in units:
        if not isinstance(unit, Mapping):
            raise PlanExecutionReceiptError("L1 work_units entries must be mappings")
        unit_id = str(unit.get("unit_id") or "").strip()
        if not unit_id:
            raise PlanExecutionReceiptError("L1 work_units entries need unit_id")
        unit_ids.append(unit_id)
        normalized.append(unit)
    if not unit_ids or len(set(unit_ids)) != len(unit_ids):
        raise PlanExecutionReceiptError("L1 work_units must have unique non-empty IDs")
    return normalized


def _plan_binding(capsule: Mapping[str, Any]) -> dict[str, Any]:
    verified = verify_apps_rg_l1_planning_capsule(capsule)
    prior = capsule["planning_prior_refs"][0]
    if not isinstance(prior, Mapping):  # defensive; verifier already checks this.
        raise PlanExecutionReceiptError("L1 planning-prior binding is invalid")
    return {
        "capsule_digest": str(verified["capsule_digest"]),
        "planning_status": str(verified["planning_status"]),
        "planning_profile_ref": str(prior["ref"]),
        "planning_profile_digest": str(prior["digest"]),
    }


def _normalize_unit_outcomes(
    outcomes: Sequence[Mapping[str, Any]],
    *,
    planned_unit_ids: set[str],
    taxonomy_by_code: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
        raise PlanExecutionReceiptError("unit_outcomes must be a sequence")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in outcomes:
        if not isinstance(raw, Mapping):
            raise PlanExecutionReceiptError("unit outcome entries must be mappings")
        unit_id = str(raw.get("unit_id") or "").strip()
        disposition = str(raw.get("disposition") or "").strip().upper()
        if not unit_id or unit_id not in planned_unit_ids:
            raise PlanExecutionReceiptError(f"unit outcome is not in the L1 plan: {unit_id!r}")
        if unit_id in seen:
            raise PlanExecutionReceiptError(f"duplicate execution outcome for unit: {unit_id}")
        if disposition not in VALID_DISPOSITIONS:
            raise PlanExecutionReceiptError(
                f"unit {unit_id!r} has unsupported disposition {disposition!r}"
            )
        attempted = raw.get("attempted")
        if not isinstance(attempted, bool):
            raise PlanExecutionReceiptError(f"unit {unit_id!r} must declare attempted")
        if disposition == "COMPLETED" and not attempted:
            raise PlanExecutionReceiptError(
                f"completed unit {unit_id!r} must have attempted=true"
            )
        failure_code = str(raw.get("failure_code") or "").strip()
        if disposition == "COMPLETED" and failure_code:
            raise PlanExecutionReceiptError(
                f"completed unit {unit_id!r} cannot carry a failure_code"
            )
        if disposition in _FAILURE_DISPOSITIONS and not failure_code:
            raise PlanExecutionReceiptError(
                f"{disposition.lower()} unit {unit_id!r} requires a failure_code"
            )
        failure_class = ""
        next_action = ""
        if failure_code:
            taxon = taxonomy_by_code.get(failure_code)
            if taxon is None:
                raise PlanExecutionReceiptError(
                    f"unit {unit_id!r} uses unclassified failure_code {failure_code!r}"
                )
            allowed = {str(value) for value in taxon["allowed_dispositions"]}
            if disposition not in allowed:
                raise PlanExecutionReceiptError(
                    f"failure_code {failure_code!r} cannot use disposition {disposition!r}"
                )
            failure_class = str(taxon["failure_class"])
            next_action = str(taxon.get("w2_replan_hint") or "")
        artifact_refs = _normalize_refs(raw.get("artifact_refs"), field_name="artifact_refs")
        control_receipt_refs = _normalize_refs(
            raw.get("control_receipt_refs"), field_name="control_receipt_refs"
        )
        if disposition == "COMPLETED" and not artifact_refs:
            raise PlanExecutionReceiptError(
                f"completed unit {unit_id!r} requires an artifact reference"
            )
        normalized.append(
            {
                "unit_id": unit_id,
                "disposition": disposition,
                "attempted": attempted,
                "failure_code": failure_code,
                "failure_class": failure_class,
                "w2_replan_hint": next_action,
                "artifact_refs": artifact_refs,
                "control_receipt_refs": control_receipt_refs,
            }
        )
        seen.add(unit_id)
    missing = sorted(planned_unit_ids - seen)
    if missing:
        raise PlanExecutionReceiptError(
            f"plan execution receipt has no outcome for planned units: {missing}"
        )
    return sorted(normalized, key=lambda row: row["unit_id"])


def _summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_disposition = {disposition: 0 for disposition in sorted(VALID_DISPOSITIONS)}
    failure_codes: dict[str, int] = {}
    for row in rows:
        by_disposition[str(row["disposition"])] += 1
        failure_code = str(row.get("failure_code") or "")
        if failure_code:
            failure_codes[failure_code] = failure_codes.get(failure_code, 0) + 1
    return {
        "planned_unit_count": len(rows),
        "reconciled_unit_count": len(rows),
        "all_planned_units_reconciled": True,
        "by_disposition": by_disposition,
        "failure_code_counts": dict(sorted(failure_codes.items())),
    }


def build_plan_execution_receipt(
    *,
    request_id: str,
    run_id: str,
    plan_capsule: Mapping[str, Any],
    unit_outcomes: Sequence[Mapping[str, Any]],
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a digest-bound, exhaustive reconciliation receipt for one L1 plan.

    W0 is deliberately side-effect free.  Callers provide observed outcomes; this
    function validates their relationship to a verified L1 planning capsule.
    """

    request = str(request_id or "").strip()
    run = str(run_id or "").strip()
    if not request or not run:
        raise PlanExecutionReceiptError("request_id and run_id are required")
    try:
        plan = _plan_binding(plan_capsule)
    except PlanningCapsuleIntegrityError as exc:
        raise PlanExecutionReceiptError(f"invalid L1 plan capsule: {exc}") from exc
    units = _planned_units(plan_capsule)
    taxonomy_document = taxonomy or load_failure_taxonomy()
    taxonomy_rows = failure_taxonomy_by_code(taxonomy_document)
    outcomes = _normalize_unit_outcomes(
        unit_outcomes,
        planned_unit_ids={str(unit["unit_id"]) for unit in units},
        taxonomy_by_code=taxonomy_rows,
    )
    receipt: dict[str, Any] = {
        "schema_version": PLAN_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "contract_type": PLAN_EXECUTION_RECEIPT_CONTRACT_TYPE,
        "authority_class": "OBSERVABILITY_ONLY_W0",
        "request_id": request,
        "run_id": run,
        "plan": plan,
        "taxonomy_ref": FAILURE_TAXONOMY_RELPATH.as_posix(),
        "taxonomy_digest": "sha256:"
        + hashlib.sha256(_canonical_json(taxonomy_document).encode("utf-8")).hexdigest(),
        "unit_outcomes": outcomes,
        "summary": _summary(outcomes),
        "execution_authority_assertions": {
            "does_not_execute_work_units": True,
            "does_not_select_retries": True,
            "does_not_authorize_route_or_exit": True,
        },
    }
    receipt["receipt_digest"] = receipt_digest(receipt)
    validate_plan_execution_receipt(receipt, taxonomy=taxonomy)
    return receipt


def validate_plan_execution_receipt(
    receipt: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed unless a receipt is complete, taxonomy-bound, and digest-valid."""

    if not isinstance(receipt, Mapping):
        raise PlanExecutionReceiptError("plan execution receipt must be a mapping")
    if receipt.get("schema_version") != PLAN_EXECUTION_RECEIPT_SCHEMA_VERSION:
        raise PlanExecutionReceiptError("unsupported plan execution receipt schema_version")
    if receipt.get("contract_type") != PLAN_EXECUTION_RECEIPT_CONTRACT_TYPE:
        raise PlanExecutionReceiptError("invalid plan execution receipt contract_type")
    if receipt.get("authority_class") != "OBSERVABILITY_ONLY_W0":
        raise PlanExecutionReceiptError("W0 receipt authority_class is invalid")
    if not str(receipt.get("request_id") or "").strip() or not str(
        receipt.get("run_id") or ""
    ).strip():
        raise PlanExecutionReceiptError("receipt request_id and run_id are required")
    declared_digest = str(receipt.get("receipt_digest") or "").strip()
    if not declared_digest or declared_digest != receipt_digest(receipt):
        raise PlanExecutionReceiptError("plan execution receipt digest mismatch")
    plan = receipt.get("plan")
    if not isinstance(plan, Mapping):
        raise PlanExecutionReceiptError("receipt plan binding is required")
    required_plan_fields = {
        "capsule_digest",
        "planning_status",
        "planning_profile_ref",
        "planning_profile_digest",
    }
    if any(not str(plan.get(field) or "").strip() for field in required_plan_fields):
        raise PlanExecutionReceiptError("receipt plan binding is incomplete")
    outcomes = receipt.get("unit_outcomes")
    if not isinstance(outcomes, Sequence) or isinstance(outcomes, (str, bytes)):
        raise PlanExecutionReceiptError("receipt unit_outcomes must be a sequence")
    taxonomy_document = taxonomy or load_failure_taxonomy()
    if receipt.get("taxonomy_ref") != FAILURE_TAXONOMY_RELPATH.as_posix():
        raise PlanExecutionReceiptError("receipt taxonomy_ref is invalid")
    expected_taxonomy_digest = "sha256:" + hashlib.sha256(
        _canonical_json(taxonomy_document).encode("utf-8")
    ).hexdigest()
    if receipt.get("taxonomy_digest") != expected_taxonomy_digest:
        raise PlanExecutionReceiptError("receipt taxonomy digest mismatch")
    taxonomy_rows = failure_taxonomy_by_code(taxonomy_document)
    seen: set[str] = set()
    for raw in outcomes:
        if not isinstance(raw, Mapping):
            raise PlanExecutionReceiptError("receipt unit outcomes must be mappings")
        unit_id = str(raw.get("unit_id") or "").strip()
        disposition = str(raw.get("disposition") or "").strip().upper()
        if not unit_id or unit_id in seen or disposition not in VALID_DISPOSITIONS:
            raise PlanExecutionReceiptError("receipt unit outcome IDs/dispositions are invalid")
        seen.add(unit_id)
        attempted = raw.get("attempted")
        if not isinstance(attempted, bool):
            raise PlanExecutionReceiptError("receipt unit outcome attempted must be boolean")
        failure_code = str(raw.get("failure_code") or "").strip()
        if disposition == "COMPLETED":
            if not attempted or failure_code or not raw.get("artifact_refs"):
                raise PlanExecutionReceiptError(
                    "completed receipt outcome lacks attempt/artifact integrity"
                )
        else:
            taxon = taxonomy_rows.get(failure_code)
            if taxon is None:
                raise PlanExecutionReceiptError(
                    "non-completed receipt outcome has unclassified failure code"
                )
            if disposition not in {str(value) for value in taxon["allowed_dispositions"]}:
                raise PlanExecutionReceiptError(
                    "receipt failure code/disposition combination is invalid"
                )
            if raw.get("failure_class") != taxon.get("failure_class"):
                raise PlanExecutionReceiptError("receipt failure class does not match taxonomy")
            if raw.get("w2_replan_hint") != str(taxon.get("w2_replan_hint") or ""):
                raise PlanExecutionReceiptError("receipt W2 replan hint does not match taxonomy")
        _normalize_refs(raw.get("artifact_refs"), field_name="artifact_refs")
        _normalize_refs(
            raw.get("control_receipt_refs"), field_name="control_receipt_refs"
        )
    summary = receipt.get("summary")
    if not isinstance(summary, Mapping) or summary != _summary(outcomes):
        raise PlanExecutionReceiptError("receipt summary does not reconcile unit outcomes")
    assertions = receipt.get("execution_authority_assertions")
    if not isinstance(assertions, Mapping) or any(
        assertions.get(key) is not True
        for key in (
            "does_not_execute_work_units",
            "does_not_select_retries",
            "does_not_authorize_route_or_exit",
        )
    ):
        raise PlanExecutionReceiptError("W0 execution authority assertions are incomplete")


__all__ = [
    "FAILURE_TAXONOMY_RELPATH",
    "PLAN_EXECUTION_RECEIPT_CONTRACT_TYPE",
    "PLAN_EXECUTION_RECEIPT_SCHEMA_VERSION",
    "PlanExecutionReceiptError",
    "VALID_DISPOSITIONS",
    "build_plan_execution_receipt",
    "failure_taxonomy_by_code",
    "failure_taxonomy_path",
    "load_failure_taxonomy",
    "receipt_digest",
    "validate_plan_execution_receipt",
]
