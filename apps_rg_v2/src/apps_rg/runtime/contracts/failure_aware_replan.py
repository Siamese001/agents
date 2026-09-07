"""W2 failure-aware, non-executing replans over W1 observations.

The replan decision is an immutable advisory revision.  It links a verified
parent L1 capsule to the exact W1 receipt that triggered it, and it proposes
only the next governed owner.  It never retries work, changes a route,
retrieves evidence, calls a model, or authorizes an exit.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_planning_capsule import (
    PlanningCapsuleIntegrityError,
    verify_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    L1PlanningV2IntegrityError,
    verify_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.contracts.governed_l3_schedule import (
    GovernedL3ScheduleError,
    receipt_digest as governed_l3_schedule_receipt_digest,
    validate_governed_l3_schedule_receipt,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    L1EvidenceObligationReceiptError,
    receipt_digest as c0_obligation_receipt_digest,
    validate_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    PlanExecutionReconciliationError,
    receipt_digest as plan_execution_reconciliation_digest,
    validate_plan_execution_reconciliation,
)
from apps_rg.runtime.contracts.plan_execution_receipt import load_failure_taxonomy
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


FAILURE_AWARE_REPLAN_SCHEMA_VERSION: Final[str] = "apps_rg.failure_aware_replan.v1"
L1_REPLAN_REVISION_SCHEMA_VERSION: Final[str] = "apps_rg.l1_replan_revision.v1"
FAILURE_AWARE_REPLAN_CONTRACT_TYPE: Final[str] = "FailureAwareReplanDecision"
_EMITTER: Final[str] = "apps_rg.runtime.contracts.failure_aware_replan"

_ACTIONABLE_HINTS: Final[dict[str, tuple[str, str]]] = {
    "CLARIFY_OR_REPAIR_INPUT": ("CLARIFY_OR_REPAIR_INPUT", "U0"),
    "REPLAN_EVIDENCE": ("REPLAN_EVIDENCE", "C0"),
    "REPLAN_RETRIEVAL": ("REPLAN_RETRIEVAL", "C0"),
    "REPAIR_OR_RETRY_GENERATION": ("REPAIR_OR_RETRY_GENERATION", "L2"),
}
_TERMINAL_HINT: Final[str] = "TERMINAL_BLOCK"


class FailureAwareReplanError(ValueError):
    """Raised when a W2 decision lacks a trustworthy parent or trigger."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Mapping[str, Any], *, field: str) -> str:
    body = dict(value)
    body.pop(field, None)
    return "sha256:" + hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _normalised_ref(value: Any, *, field_name: str) -> str:
    ref = str(value or "").strip().replace("\\", "/")
    if not ref:
        raise FailureAwareReplanError(f"{field_name} is required")
    if Path(ref).is_absolute() or ".." in Path(ref).parts:
        raise FailureAwareReplanError(f"{field_name} must be a relative artifact reference")
    return ref


def _verified_parent_binding(
    plan_capsule: Mapping[str, Any], *, parent_plan_ref: str
) -> dict[str, str]:
    try:
        verified = verify_apps_rg_l1_planning_capsule(plan_capsule)
    except PlanningCapsuleIntegrityError as exc:
        raise FailureAwareReplanError(f"invalid parent L1 capsule: {exc}") from exc
    prior = (plan_capsule.get("planning_prior_refs") or [None])[0]
    if not isinstance(prior, Mapping):
        raise FailureAwareReplanError("parent L1 capsule has no planning-prior binding")
    return {
        "capsule_ref": _normalised_ref(parent_plan_ref, field_name="parent_plan_ref"),
        "capsule_digest": str(verified["capsule_digest"]),
        "planning_status": str(verified["planning_status"]),
        "planning_profile_ref": str(prior.get("ref") or ""),
        "planning_profile_digest": str(prior.get("digest") or ""),
    }


def _validate_trigger_receipt(receipt: Mapping[str, Any]) -> None:
    try:
        validate_plan_execution_reconciliation(receipt)
    except (PlanExecutionReconciliationError, ValueError) as exc:
        raise FailureAwareReplanError(f"invalid W1 trigger receipt: {exc}") from exc


def _outcomes_by_unit(receipt: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = receipt.get("unit_outcomes")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise FailureAwareReplanError("W1 trigger receipt has no unit outcomes")
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FailureAwareReplanError("W1 trigger outcome must be a mapping")
        unit_id = str(row.get("unit_id") or "").strip()
        if not unit_id or unit_id in out:
            raise FailureAwareReplanError("W1 trigger outcome coverage is invalid")
        out[unit_id] = row
    return out


def _observations_by_unit(receipt: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = receipt.get("unit_observations")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise FailureAwareReplanError("W1 trigger receipt has no unit observations")
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise FailureAwareReplanError("W1 trigger observation must be a mapping")
        unit_id = str(row.get("unit_id") or "").strip()
        if not unit_id or unit_id in out:
            raise FailureAwareReplanError("W1 trigger observation coverage is invalid")
        out[unit_id] = row
    return out


def _classification_rows(receipt: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for unit_id, outcome in _outcomes_by_unit(receipt).items():
        disposition = str(outcome.get("disposition") or "").upper()
        hint = str(outcome.get("w2_replan_hint") or "")
        failure_code = str(outcome.get("failure_code") or "")
        if disposition == "COMPLETED":
            status = "NO_REPLAN_REQUIRED"
        elif hint in _ACTIONABLE_HINTS:
            status = "REPLAN_PROPOSED"
        elif hint == _TERMINAL_HINT:
            status = "TERMINAL_BLOCKED"
        else:
            raise FailureAwareReplanError(
                f"W1 outcome {unit_id!r} has unsupported W2 replan hint {hint!r}"
            )
        rows.append(
            {
                "unit_id": unit_id,
                "source_disposition": disposition,
                "failure_code": failure_code,
                "failure_class": str(outcome.get("failure_class") or ""),
                "replan_hint": hint,
                "classification": status,
            }
        )
    return sorted(rows, key=lambda row: row["unit_id"])


def _action_rows(
    classifications: Sequence[Mapping[str, Any]],
    observations: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for row in classifications:
        hint = str(row.get("replan_hint") or "")
        if hint not in _ACTIONABLE_HINTS:
            continue
        unit_id = str(row["unit_id"])
        observation = observations.get(unit_id)
        if observation is None:
            raise FailureAwareReplanError(
                f"W1 observation is missing for replan unit {unit_id!r}"
            )
        strategy, next_owner = _ACTIONABLE_HINTS[hint]
        evidence_only = strategy in {"REPLAN_EVIDENCE", "REPLAN_RETRIEVAL"}
        actions.append(
            {
                "unit_id": unit_id,
                "failure_code": str(row["failure_code"]),
                "failure_class": str(row["failure_class"]),
                "strategy": strategy,
                "next_governed_owner": next_owner,
                "parent_evidence_plan": copy.deepcopy(
                    _mapping(observation.get("evidence_plan"))
                ),
                "requested_controls": copy.deepcopy(
                    _mapping(observation.get("requested_controls"))
                ),
                "generation_retry_prohibited": evidence_only,
                "requires_new_governed_generation": (
                    strategy == "REPAIR_OR_RETRY_GENERATION"
                ),
                "automatic_execution": False,
                "automatic_retry": False,
                "automatic_route_change": False,
                "automatic_exit_authorization": False,
            }
        )
    return sorted(actions, key=lambda row: row["unit_id"])


def _revision(
    *,
    parent: Mapping[str, str],
    trigger: Mapping[str, str],
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not actions:
        return None
    deltas = [
        {
            "unit_id": str(action["unit_id"]),
            "strategy": str(action["strategy"]),
            "next_governed_owner": str(action["next_governed_owner"]),
            "parent_evidence_plan": copy.deepcopy(action["parent_evidence_plan"]),
            "requested_controls": copy.deepcopy(action["requested_controls"]),
            "generation_retry_prohibited": bool(action["generation_retry_prohibited"]),
            "requires_new_governed_generation": bool(
                action["requires_new_governed_generation"]
            ),
        }
        for action in actions
    ]
    seed = {
        "schema_version": L1_REPLAN_REVISION_SCHEMA_VERSION,
        "parent_plan_capsule_digest": parent["capsule_digest"],
        "trigger_receipt_digest": trigger["receipt_digest"],
        "revision_number": 1,
        "plan_deltas": deltas,
    }
    revision_id = "l1r-" + hashlib.sha256(_canonical_json(seed).encode("utf-8")).hexdigest()[:16]
    revision: dict[str, Any] = {
        **seed,
        "revision_id": revision_id,
        "authority_class": "PLANNING_ADVISORY_ONLY",
        "execution_authority_assertions": {
            "does_not_execute_work_units": True,
            "does_not_select_retries": True,
            "does_not_change_route": True,
            "does_not_authorize_exit": True,
        },
    }
    revision["revision_digest"] = _digest(revision, field="revision_digest")
    return revision


def _decision_digest(decision: Mapping[str, Any]) -> str:
    return _digest(decision, field="decision_digest")


def build_failure_aware_replan(
    *,
    plan_capsule: Mapping[str, Any],
    parent_plan_ref: str,
    plan_execution_receipt: Mapping[str, Any],
    trigger_receipt_ref: str,
) -> dict[str, Any]:
    """Classify W1 outcomes and produce an optional digest-bound plan revision."""

    parent = _verified_parent_binding(plan_capsule, parent_plan_ref=parent_plan_ref)
    _validate_trigger_receipt(plan_execution_receipt)
    ref = _normalised_ref(trigger_receipt_ref, field_name="trigger_receipt_ref")
    if (
        str(plan_execution_receipt.get("request_id") or "")
        != str(plan_capsule.get("request_id") or "")
        or str(plan_execution_receipt.get("run_id") or "")
        != str(plan_capsule.get("run_id") or "")
    ):
        raise FailureAwareReplanError("W1 trigger receipt identity does not match parent L1 plan")
    trigger_plan = _mapping(plan_execution_receipt.get("plan"))
    if trigger_plan.get("capsule_digest") != parent["capsule_digest"]:
        raise FailureAwareReplanError("W1 trigger receipt is bound to a different L1 plan")

    classifications = _classification_rows(plan_execution_receipt)
    observations = _observations_by_unit(plan_execution_receipt)
    if set(observations) != {str(row["unit_id"]) for row in classifications}:
        raise FailureAwareReplanError("W1 trigger observations do not cover all classified units")
    actions = _action_rows(classifications, observations)
    trigger = {
        "receipt_ref": ref,
        "receipt_digest": str(plan_execution_receipt.get("receipt_digest") or ""),
        "schema_version": str(plan_execution_receipt.get("schema_version") or ""),
    }
    decision: dict[str, Any] = {
        "schema_version": FAILURE_AWARE_REPLAN_SCHEMA_VERSION,
        "contract_type": FAILURE_AWARE_REPLAN_CONTRACT_TYPE,
        "authority_class": "PLANNING_ADVISORY_ONLY",
        "request_id": str(plan_capsule.get("request_id") or ""),
        "run_id": str(plan_capsule.get("run_id") or ""),
        "parent_plan": parent,
        "trigger_receipt": trigger,
        "failure_classifications": classifications,
        "replan_actions": actions,
        "replan_status": "REPLAN_PROPOSED" if actions else "NO_ACTIONABLE_REPLAN",
        "replan_revision": _revision(parent=parent, trigger=trigger, actions=actions),
        "execution_authority_assertions": {
            "does_not_execute_work_units": True,
            "does_not_select_retries": True,
            "does_not_change_route": True,
            "does_not_authorize_exit": True,
        },
        "emitter": _EMITTER,
    }
    decision["decision_digest"] = _decision_digest(decision)
    validate_failure_aware_replan(
        decision,
        plan_capsule=plan_capsule,
        plan_execution_receipt=plan_execution_receipt,
    )
    return decision


def validate_failure_aware_replan(
    decision: Mapping[str, Any],
    *,
    plan_capsule: Mapping[str, Any],
    plan_execution_receipt: Mapping[str, Any],
) -> None:
    """Fail closed unless W2's revision exactly follows its parent and trigger."""

    if not isinstance(decision, Mapping):
        raise FailureAwareReplanError("W2 decision must be a mapping")
    if decision.get("schema_version") != FAILURE_AWARE_REPLAN_SCHEMA_VERSION:
        raise FailureAwareReplanError("unsupported W2 decision schema_version")
    if decision.get("contract_type") != FAILURE_AWARE_REPLAN_CONTRACT_TYPE:
        raise FailureAwareReplanError("invalid W2 decision contract_type")
    if decision.get("authority_class") != "PLANNING_ADVISORY_ONLY":
        raise FailureAwareReplanError("W2 decision authority_class is invalid")
    if decision.get("emitter") != _EMITTER:
        raise FailureAwareReplanError("W2 decision emitter is invalid")
    if decision.get("decision_digest") != _decision_digest(decision):
        raise FailureAwareReplanError("W2 decision digest mismatch")

    parent_ref = _mapping(decision.get("parent_plan")).get("capsule_ref")
    parent = _verified_parent_binding(plan_capsule, parent_plan_ref=str(parent_ref or ""))
    _validate_trigger_receipt(plan_execution_receipt)
    if decision.get("parent_plan") != parent:
        raise FailureAwareReplanError("W2 parent-plan binding is invalid")
    if (
        decision.get("request_id") != str(plan_capsule.get("request_id") or "")
        or decision.get("run_id") != str(plan_capsule.get("run_id") or "")
    ):
        raise FailureAwareReplanError("W2 decision identity is invalid")
    trigger = _mapping(decision.get("trigger_receipt"))
    expected_trigger = {
        "receipt_ref": _normalised_ref(
            trigger.get("receipt_ref"), field_name="trigger_receipt.receipt_ref"
        ),
        "receipt_digest": str(plan_execution_receipt.get("receipt_digest") or ""),
        "schema_version": str(plan_execution_receipt.get("schema_version") or ""),
    }
    if trigger != expected_trigger:
        raise FailureAwareReplanError("W2 trigger receipt binding is invalid")

    classifications = _classification_rows(plan_execution_receipt)
    if decision.get("failure_classifications") != classifications:
        raise FailureAwareReplanError("W2 failure classifications do not match W1 outcomes")
    observations = _observations_by_unit(plan_execution_receipt)
    actions = _action_rows(classifications, observations)
    if decision.get("replan_actions") != actions:
        raise FailureAwareReplanError("W2 replan actions do not match failure classifications")
    expected_status = "REPLAN_PROPOSED" if actions else "NO_ACTIONABLE_REPLAN"
    if decision.get("replan_status") != expected_status:
        raise FailureAwareReplanError("W2 replan status is invalid")
    expected_revision = _revision(parent=parent, trigger=expected_trigger, actions=actions)
    if decision.get("replan_revision") != expected_revision:
        raise FailureAwareReplanError("W2 replan revision does not match parent and trigger")
    assertions = _mapping(decision.get("execution_authority_assertions"))
    if any(
        assertions.get(key) is not True
        for key in (
            "does_not_execute_work_units",
            "does_not_select_retries",
            "does_not_change_route",
            "does_not_authorize_exit",
        )
    ):
        raise FailureAwareReplanError("W2 execution authority assertions are incomplete")


def emit_failure_aware_replan(
    *,
    parent_plan_capsule_path: Path,
    plan_execution_receipt_path: Path,
    artifact_dir: Path,
) -> Path:
    """Load the canonical W1 receipt and write its W2 advisory decision."""

    artifact_dir = Path(artifact_dir)
    parent_source = Path(parent_plan_capsule_path)
    source = Path(plan_execution_receipt_path)
    try:
        plan_capsule = json.loads(parent_source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FailureAwareReplanError(f"cannot read parent L1 capsule: {parent_source}") from exc
    if not isinstance(plan_capsule, Mapping):
        raise FailureAwareReplanError("parent L1 capsule must decode to a mapping")
    try:
        receipt = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FailureAwareReplanError(f"cannot read W1 trigger receipt: {source}") from exc
    if not isinstance(receipt, Mapping):
        raise FailureAwareReplanError("W1 trigger receipt must decode to a mapping")
    try:
        parent_ref = parent_source.resolve().relative_to(artifact_dir.resolve()).as_posix()
        trigger_ref = source.resolve().relative_to(artifact_dir.resolve()).as_posix()
    except ValueError as exc:
        raise FailureAwareReplanError("W1 trigger receipt must be inside the run artifact directory") from exc
    decision = build_failure_aware_replan(
        plan_capsule=plan_capsule,
        parent_plan_ref=parent_ref,
        plan_execution_receipt=receipt,
        trigger_receipt_ref=trigger_ref,
    )
    path = artifact_dir / sr.FILENAME_PLAN_REPLAN_DECISION
    sr.write_stage_receipt(path, decision)
    return path


PLAN_EXECUTION_FAILURE_DIAGNOSTIC_SCHEMA_VERSION: Final[str] = (
    "apps_rg.plan_execution_failure_diagnostic.v1"
)
FAILURE_AWARE_REPLAN_V2_SCHEMA_VERSION: Final[str] = (
    "apps_rg.failure_aware_replan.v2"
)
L1_REPLAN_DELTA_V2_SCHEMA_VERSION: Final[str] = "apps_rg.l1_replan_delta.v2"
FAILURE_AWARE_REPLAN_V2_CONTRACT_TYPE: Final[str] = "FailureAwareReplanDecisionV2"
_W5_DIAGNOSTIC_AUTHORITY: Final[str] = "OBSERVABILITY_AND_PLANNING_ADVISORY_ONLY"
_W5_REPLAN_AUTHORITY: Final[str] = "PLANNING_ADVISORY_ONLY"
_W5_EMITTER: Final[str] = "apps_rg.runtime.contracts.failure_aware_replan"
_W5_POLICY_SCHEMA_VERSION: Final[str] = (
    "apps_rg.plan_execution_failure_diagnostic_policy.v1"
)
_APPLIED_CONTROL_STATUSES: Final[frozenset[str]] = frozenset(
    {"APPLIED", "ADAPTED"}
)


def failure_diagnostic_receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return the W5 diagnostic digest excluding only its self digest."""

    return _digest(receipt, field="receipt_digest")


def failure_aware_replan_v2_digest(decision: Mapping[str, Any]) -> str:
    """Return the W5 decision digest excluding only its self digest."""

    return _digest(decision, field="decision_digest")


def _w5_policy() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    try:
        taxonomy = load_failure_taxonomy()
    except ValueError as exc:
        raise FailureAwareReplanError("W5 failure taxonomy is invalid") from exc
    raw_policy = taxonomy.get("w5_diagnostic_policy")
    if not isinstance(raw_policy, Mapping):
        raise FailureAwareReplanError("W5 failure taxonomy policy is missing")
    policy = dict(raw_policy)
    if policy.get("schema_version") != _W5_POLICY_SCHEMA_VERSION:
        raise FailureAwareReplanError("W5 failure taxonomy policy schema is invalid")
    max_depth = policy.get("max_advisory_revision_depth")
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 1:
        raise FailureAwareReplanError("W5 maximum advisory revision depth is invalid")
    if (
        policy.get("repeated_diagnostic_disposition")
        != "ESCALATE_TO_DESIGNATED_RESOLVER"
    ):
        raise FailureAwareReplanError("W5 repeated-diagnostic policy is invalid")
    raw_codes = policy.get("diagnostic_codes")
    if not isinstance(raw_codes, Mapping) or not raw_codes:
        raise FailureAwareReplanError("W5 diagnostic codes are missing")
    codes: dict[str, dict[str, Any]] = {}
    for code, raw in raw_codes.items():
        normalized_code = str(code or "").strip()
        if not normalized_code or not isinstance(raw, Mapping):
            raise FailureAwareReplanError("W5 diagnostic code is invalid")
        row = dict(raw)
        for field in ("strategy", "next_governed_owner", "designated_resolver"):
            if not str(row.get(field) or "").strip():
                raise FailureAwareReplanError("W5 diagnostic action policy is invalid")
        if not isinstance(row.get("actionable"), bool):
            raise FailureAwareReplanError("W5 diagnostic actionable policy is invalid")
        codes[normalized_code] = row
    return policy, codes


def _relative_refs(values: Sequence[Any], *, field_name: str) -> list[str]:
    refs = [
        _normalised_ref(value, field_name=field_name)
        for value in values
        if str(value or "").strip()
    ]
    return sorted(set(refs))


def _identity_v2(capsule: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    try:
        verified = verify_apps_rg_l1_planning_capsule_v2(capsule)
    except L1PlanningV2IntegrityError as exc:
        raise FailureAwareReplanError("W5 parent L1 v2 capsule is invalid") from exc
    identity = {
        field: str(capsule.get(field) or "").strip()
        for field in ("request_id", "run_id", "trace_id")
    }
    if any(not value for value in identity.values()):
        raise FailureAwareReplanError("W5 L1 v2 identity is incomplete")
    return identity, {"capsule_digest": str(verified["capsule_digest"])}


def _w5_source_bindings(
    *,
    l1_v2_capsule: Mapping[str, Any],
    parent_plan_ref: str,
    c0_obligation_receipt: Mapping[str, Any],
    c0_obligation_receipt_ref: str,
    plan_execution_reconciliation: Mapping[str, Any],
    plan_execution_reconciliation_ref: str,
    governed_l3_schedule: Mapping[str, Any],
    governed_l3_schedule_ref: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    identity, l1_binding = _identity_v2(l1_v2_capsule)
    parent_ref = _normalised_ref(parent_plan_ref, field_name="parent_plan_ref")
    c0_ref = _normalised_ref(
        c0_obligation_receipt_ref, field_name="c0_obligation_receipt_ref"
    )
    w1_ref = _normalised_ref(
        plan_execution_reconciliation_ref,
        field_name="plan_execution_reconciliation_ref",
    )
    l3_ref = _normalised_ref(
        governed_l3_schedule_ref, field_name="governed_l3_schedule_ref"
    )
    try:
        validate_l1_evidence_obligation_receipt(
            c0_obligation_receipt, capsule=l1_v2_capsule
        )
    except L1EvidenceObligationReceiptError as exc:
        raise FailureAwareReplanError("W5 C0 obligation receipt is invalid") from exc
    try:
        validate_plan_execution_reconciliation(plan_execution_reconciliation)
    except PlanExecutionReconciliationError as exc:
        raise FailureAwareReplanError("W5 W1 execution reconciliation is invalid") from exc
    try:
        validate_governed_l3_schedule_receipt(
            governed_l3_schedule,
            l1_v2_capsule=l1_v2_capsule,
            c0_obligation_receipt=c0_obligation_receipt,
            plan_execution_reconciliation=plan_execution_reconciliation,
        )
    except GovernedL3ScheduleError as exc:
        raise FailureAwareReplanError("W5 governed L3 schedule is invalid") from exc
    if any(
        str(plan_execution_reconciliation.get(field) or "") != identity[field]
        for field in ("request_id", "run_id")
    ):
        raise FailureAwareReplanError("W5 W1 identity does not match L1 v2")
    c0_identity = _mapping(c0_obligation_receipt.get("identity"))
    if any(str(c0_identity.get(field) or "") != identity[field] for field in identity):
        raise FailureAwareReplanError("W5 C0 identity does not match L1 v2")
    schedule_identity = _mapping(governed_l3_schedule.get("identity"))
    if any(
        str(schedule_identity.get(field) or "") != identity[field]
        for field in identity
    ):
        raise FailureAwareReplanError("W5 L3 identity does not match L1 v2")
    schedule_inputs = _mapping(governed_l3_schedule.get("input_receipts"))
    if (
        schedule_inputs.get("c0_obligation_receipt_ref") != c0_ref
        or schedule_inputs.get("c0_obligation_receipt_digest")
        != c0_obligation_receipt_digest(c0_obligation_receipt)
        or schedule_inputs.get("plan_execution_reconciliation_ref") != w1_ref
        or schedule_inputs.get("plan_execution_reconciliation_digest")
        != plan_execution_reconciliation_digest(plan_execution_reconciliation)
    ):
        raise FailureAwareReplanError("W5 L3 schedule receipt inputs do not match")
    schedule_l1 = _mapping(governed_l3_schedule.get("l1_v2"))
    if schedule_l1.get("capsule_digest") != l1_binding["capsule_digest"]:
        raise FailureAwareReplanError("W5 L3 schedule parent capsule is invalid")
    return identity, {
        "parent_l1_v2": {
            "capsule_ref": parent_ref,
            "capsule_digest": l1_binding["capsule_digest"],
        },
        "c0_obligation_receipt": {
            "receipt_ref": c0_ref,
            "receipt_digest": c0_obligation_receipt_digest(c0_obligation_receipt),
        },
        "plan_execution_reconciliation": {
            "receipt_ref": w1_ref,
            "receipt_digest": plan_execution_reconciliation_digest(
                plan_execution_reconciliation
            ),
        },
        "governed_l3_schedule": {
            "receipt_ref": l3_ref,
            "receipt_digest": governed_l3_schedule_receipt_digest(
                governed_l3_schedule
            ),
        },
    }


def _requirement_targets(
    capsule: Mapping[str, Any],
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    by_unit: dict[str, list[str]] = {}
    units_by_requirement: dict[str, tuple[str, ...]] = {}
    requirements = capsule.get("requirements")
    if not isinstance(requirements, Sequence) or isinstance(requirements, (str, bytes)):
        raise FailureAwareReplanError("W5 L1 v2 requirements are invalid")
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            raise FailureAwareReplanError("W5 L1 v2 requirement is invalid")
        requirement_id = str(requirement.get("requirement_id") or "").strip()
        target_units = requirement.get("target_unit_ids")
        if not requirement_id or not isinstance(target_units, Sequence) or isinstance(
            target_units, (str, bytes)
        ):
            raise FailureAwareReplanError("W5 L1 v2 requirement target is invalid")
        targets = tuple(sorted(str(unit) for unit in target_units if str(unit)))
        units_by_requirement[requirement_id] = targets
        for unit_id in targets:
            by_unit.setdefault(unit_id, []).append(requirement_id)
    return (
        {unit_id: tuple(sorted(requirement_ids)) for unit_id, requirement_ids in by_unit.items()},
        units_by_requirement,
    )


def _diagnostic_row(
    *,
    code: str,
    affected_unit_ids: Sequence[str],
    affected_requirement_ids: Sequence[str],
    receipt_refs: Sequence[Any],
    observed_facts: Mapping[str, Any],
    designated_resolver: str,
) -> dict[str, Any]:
    body = {
        "code": str(code),
        "affected_unit_ids": sorted(
            set(str(unit_id) for unit_id in affected_unit_ids if str(unit_id))
        ),
        "affected_requirement_ids": sorted(
            set(
                str(requirement_id)
                for requirement_id in affected_requirement_ids
                if str(requirement_id)
            )
        ),
        "receipt_refs": _relative_refs(receipt_refs, field_name="diagnostic receipt_ref"),
        "observed_facts": copy.deepcopy(dict(observed_facts)),
        "designated_resolver": str(designated_resolver or "").strip(),
    }
    if not body["code"] or not body["designated_resolver"]:
        raise FailureAwareReplanError("W5 diagnostic row is incomplete")
    diagnostic_id = "w5diag-" + hashlib.sha256(
        _canonical_json(body).encode("utf-8")
    ).hexdigest()[:16]
    return {"diagnostic_id": diagnostic_id, **body}


def _diagnostic_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    projection = [
        {
            "code": str(row.get("code") or ""),
            "affected_unit_ids": list(row.get("affected_unit_ids") or ()),
            "affected_requirement_ids": list(
                row.get("affected_requirement_ids") or ()
            ),
            "observed_facts": copy.deepcopy(_mapping(row.get("observed_facts"))),
            "designated_resolver": str(row.get("designated_resolver") or ""),
        }
        for row in rows
    ]
    return "sha256:" + hashlib.sha256(
        _canonical_json(projection).encode("utf-8")
    ).hexdigest()


def _diagnostic_rows(
    *,
    l1_v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
    plan_execution_reconciliation: Mapping[str, Any],
    governed_l3_schedule: Mapping[str, Any],
    source_bindings: Mapping[str, Any],
    policy_codes: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    requirements_by_unit, units_by_requirement = _requirement_targets(l1_v2_capsule)
    c0_ref = str(_mapping(source_bindings.get("c0_obligation_receipt")).get("receipt_ref") or "")
    w1_ref = str(
        _mapping(source_bindings.get("plan_execution_reconciliation")).get("receipt_ref")
        or ""
    )
    l3_ref = str(
        _mapping(source_bindings.get("governed_l3_schedule")).get("receipt_ref")
        or ""
    )
    outcomes = {
        str(row.get("unit_id") or ""): row
        for row in plan_execution_reconciliation.get("unit_outcomes") or ()
        if isinstance(row, Mapping)
    }
    observations = {
        str(row.get("unit_id") or ""): row
        for row in plan_execution_reconciliation.get("unit_observations") or ()
        if isinstance(row, Mapping)
    }
    if set(outcomes) != set(observations) or not outcomes:
        raise FailureAwareReplanError("W5 W1 outcome and observation coverage is invalid")
    c0_by_unit: dict[str, list[Mapping[str, Any]]] = {}
    for row in c0_obligation_receipt.get("obligation_dispositions") or ():
        if isinstance(row, Mapping):
            unit_id = str(row.get("target_unit_id") or "").strip()
            if unit_id:
                c0_by_unit.setdefault(unit_id, []).append(row)
    schedule_entries = {
        str(row.get("node_id") or ""): row
        for row in _mapping(governed_l3_schedule.get("schedule")).get("entries") or ()
        if isinstance(row, Mapping)
    }
    rows: list[dict[str, Any]] = []
    failed_unit_ids = {
        unit_id
        for unit_id, outcome in outcomes.items()
        if str(outcome.get("disposition") or "") != "COMPLETED"
    }
    for unit_id in sorted(failed_unit_ids):
        observation = observations[unit_id]
        requirement_ids = requirements_by_unit.get(unit_id, ())
        c0_consumed = observation.get("c0_obligation_receipt_refs") or ()
        if requirement_ids and c0_ref not in c0_consumed:
            rows.append(
                _diagnostic_row(
                    code="C0_OBLIGATION_RECEIPT_UNBOUND",
                    affected_unit_ids=(unit_id,),
                    affected_requirement_ids=requirement_ids,
                    receipt_refs=(w1_ref, c0_ref),
                    observed_facts={
                        "observed_c0_obligation_receipt_refs": list(c0_consumed),
                        "required_c0_obligation_receipt_ref": c0_ref,
                    },
                    designated_resolver=str(
                        policy_codes["C0_OBLIGATION_RECEIPT_UNBOUND"][
                            "designated_resolver"
                        ]
                    ),
                )
            )
        for disposition in sorted(
            c0_by_unit.get(unit_id, ()), key=lambda row: str(row.get("obligation_id") or "")
        ):
            requirement_id = str(disposition.get("requirement_id") or "")
            support_disposition = str(disposition.get("support_disposition") or "")
            if (
                requirement_id in requirement_ids
                and support_disposition in {"INSUFFICIENT", "CONTRADICTED"}
            ):
                rows.append(
                    _diagnostic_row(
                        code="C0_OBLIGATION_UNRESOLVED",
                        affected_unit_ids=(unit_id,),
                        affected_requirement_ids=(requirement_id,),
                        receipt_refs=(c0_ref, *list(disposition.get("evidence_refs") or ())),
                        observed_facts={
                            "obligation_id": str(disposition.get("obligation_id") or ""),
                            "support_disposition": support_disposition,
                            "reason_code": str(disposition.get("reason_code") or ""),
                        },
                        designated_resolver=str(
                            policy_codes["C0_OBLIGATION_UNRESOLVED"][
                                "designated_resolver"
                            ]
                        ),
                    )
                )
        control_receipt = _mapping(
            observation.get("reasoning_control_execution_receipt")
        )
        missing_controls = [
            {
                "control_name": str(control.get("control_name") or ""),
                "transport_support_status": str(
                    control.get("transport_support_status") or ""
                ),
                "execution_status": str(control.get("execution_status") or ""),
                "reason_code": str(control.get("reason_code") or ""),
            }
            for control in control_receipt.get("control_observations") or ()
            if isinstance(control, Mapping)
            and control.get("required_for_certification") is True
            and str(control.get("execution_status") or "")
            not in _APPLIED_CONTROL_STATUSES
        ]
        if missing_controls:
            rows.append(
                _diagnostic_row(
                    code="REQUIRED_CONTROL_EXECUTION_ABSENT",
                    affected_unit_ids=(unit_id,),
                    affected_requirement_ids=requirement_ids,
                    receipt_refs=(
                        w1_ref,
                        str(
                            observation.get(
                                "reasoning_control_execution_receipt_ref"
                            )
                            or ""
                        ),
                    ),
                    observed_facts={"controls": missing_controls},
                    designated_resolver=str(
                        policy_codes["REQUIRED_CONTROL_EXECUTION_ABSENT"][
                            "designated_resolver"
                        ]
                    ),
                )
            )
        l2_fault = str(observation.get("l2_fault") or "").strip()
        if l2_fault:
            rows.append(
                _diagnostic_row(
                    code="PROVIDER_OR_TRANSPORT_FAULT",
                    affected_unit_ids=(unit_id,),
                    affected_requirement_ids=requirement_ids,
                    receipt_refs=(w1_ref, *list(observation.get("actual_attempt_refs") or ())),
                    observed_facts={"observed_l2_fault": l2_fault},
                    designated_resolver=str(
                        policy_codes["PROVIDER_OR_TRANSPORT_FAULT"][
                            "designated_resolver"
                        ]
                    ),
                )
            )
        validation = _mapping(schedule_entries.get(f"validation:{unit_id}"))
        validation_disposition = str(validation.get("disposition") or "")
        if validation_disposition in {"BLOCKED", "SKIPPED"}:
            rows.append(
                _diagnostic_row(
                    code="GRAPH_PREDECESSOR_UNMET",
                    affected_unit_ids=(unit_id,),
                    affected_requirement_ids=requirement_ids,
                    receipt_refs=(l3_ref, *list(validation.get("receipt_refs") or ())),
                    observed_facts={
                        "validation_node_id": f"validation:{unit_id}",
                        "validation_disposition": validation_disposition,
                        "predecessor_states": copy.deepcopy(
                            list(validation.get("predecessor_states") or ())
                        ),
                    },
                    designated_resolver=str(
                        policy_codes["GRAPH_PREDECESSOR_UNMET"][
                            "designated_resolver"
                        ]
                    ),
                )
            )
    decision_ledger = _mapping(l1_v2_capsule.get("decision_ledger"))
    decisions = decision_ledger.get("decisions") or ()
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes)):
        raise FailureAwareReplanError("W5 L1 v2 decision ledger is invalid")
    for decision in decisions:
        if not isinstance(decision, Mapping) or decision.get("status") != "OPEN":
            continue
        requirement_ids = tuple(
            sorted(str(value) for value in decision.get("affected_requirement_ids") or () if str(value))
        )
        affected_units = tuple(
            sorted(
                {
                    unit_id
                    for requirement_id in requirement_ids
                    for unit_id in units_by_requirement.get(requirement_id, ())
                }
            )
        )
        if requirement_ids and not set(affected_units) & failed_unit_ids:
            continue
        resolver = str(decision.get("permitted_resolver") or "").strip() or str(
            policy_codes["U0_UNCERTAINTY_OPEN"]["designated_resolver"]
        )
        decision_digest = str(decision.get("decision_digest") or "")
        rows.append(
            _diagnostic_row(
                code="U0_UNCERTAINTY_OPEN",
                affected_unit_ids=affected_units,
                affected_requirement_ids=requirement_ids,
                receipt_refs=(
                    str(
                        _mapping(source_bindings.get("parent_l1_v2")).get(
                            "capsule_ref"
                        )
                        or ""
                    ),
                ),
                observed_facts={
                    "u0_uncertainty_id": "u0dec-"
                    + decision_digest.removeprefix("sha256:")[:16],
                    "decision_code": str(decision.get("code") or ""),
                    "blocking_policy": str(decision.get("blocking_policy") or ""),
                },
                designated_resolver=resolver,
            )
        )
    return sorted(
        rows,
        key=lambda row: (
            str(row["code"]),
            tuple(row["affected_unit_ids"]),
            tuple(row["affected_requirement_ids"]),
            str(row["diagnostic_id"]),
        ),
    )


def _failure_diagnostic_body(
    *,
    l1_v2_capsule: Mapping[str, Any],
    parent_plan_ref: str,
    c0_obligation_receipt: Mapping[str, Any],
    c0_obligation_receipt_ref: str,
    plan_execution_reconciliation: Mapping[str, Any],
    plan_execution_reconciliation_ref: str,
    governed_l3_schedule: Mapping[str, Any],
    governed_l3_schedule_ref: str,
) -> dict[str, Any]:
    policy, policy_codes = _w5_policy()
    identity, source_bindings = _w5_source_bindings(
        l1_v2_capsule=l1_v2_capsule,
        parent_plan_ref=parent_plan_ref,
        c0_obligation_receipt=c0_obligation_receipt,
        c0_obligation_receipt_ref=c0_obligation_receipt_ref,
        plan_execution_reconciliation=plan_execution_reconciliation,
        plan_execution_reconciliation_ref=plan_execution_reconciliation_ref,
        governed_l3_schedule=governed_l3_schedule,
        governed_l3_schedule_ref=governed_l3_schedule_ref,
    )
    diagnostics = _diagnostic_rows(
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        plan_execution_reconciliation=plan_execution_reconciliation,
        governed_l3_schedule=governed_l3_schedule,
        source_bindings=source_bindings,
        policy_codes=policy_codes,
    )
    by_code = {
        code: sum(1 for row in diagnostics if row["code"] == code)
        for code in sorted({str(row["code"]) for row in diagnostics})
    }
    return {
        "schema_version": PLAN_EXECUTION_FAILURE_DIAGNOSTIC_SCHEMA_VERSION,
        "contract_type": "PlanExecutionFailureDiagnostic",
        "authority_class": _W5_DIAGNOSTIC_AUTHORITY,
        "identity": identity,
        "source_bindings": source_bindings,
        "taxonomy": {
            "taxonomy_ref": str(
                plan_execution_reconciliation.get("taxonomy_ref") or ""
            ),
            "taxonomy_digest": str(
                plan_execution_reconciliation.get("taxonomy_digest") or ""
            ),
            "w5_policy_schema_version": str(policy["schema_version"]),
        },
        "diagnostics": diagnostics,
        "diagnostic_fingerprint": _diagnostic_fingerprint(diagnostics),
        "summary": {
            "diagnostic_count": len(diagnostics),
            "by_code": by_code,
            "affected_unit_ids": sorted(
                {
                    unit_id
                    for row in diagnostics
                    for unit_id in row["affected_unit_ids"]
                }
            ),
            "affected_requirement_ids": sorted(
                {
                    requirement_id
                    for row in diagnostics
                    for requirement_id in row["affected_requirement_ids"]
                }
            ),
        },
        "authority_assertions": {
            "diagnoses_observed_receipts_only": True,
            "does_not_execute_work_units": True,
            "does_not_select_retries": True,
            "does_not_change_route": True,
            "does_not_authorize_exit_or_release": True,
            "c0_remains_evidence_authority": True,
        },
        "emitter": _W5_EMITTER,
    }


def build_plan_execution_failure_diagnostic(
    *,
    l1_v2_capsule: Mapping[str, Any],
    parent_plan_ref: str,
    c0_obligation_receipt: Mapping[str, Any],
    c0_obligation_receipt_ref: str,
    plan_execution_reconciliation: Mapping[str, Any],
    plan_execution_reconciliation_ref: str,
    governed_l3_schedule: Mapping[str, Any],
    governed_l3_schedule_ref: str,
) -> dict[str, Any]:
    """Emit a receipt-bound W5 diagnostic ledger without changing execution."""

    receipt = _failure_diagnostic_body(
        l1_v2_capsule=l1_v2_capsule,
        parent_plan_ref=parent_plan_ref,
        c0_obligation_receipt=c0_obligation_receipt,
        c0_obligation_receipt_ref=c0_obligation_receipt_ref,
        plan_execution_reconciliation=plan_execution_reconciliation,
        plan_execution_reconciliation_ref=plan_execution_reconciliation_ref,
        governed_l3_schedule=governed_l3_schedule,
        governed_l3_schedule_ref=governed_l3_schedule_ref,
    )
    receipt["receipt_digest"] = failure_diagnostic_receipt_digest(receipt)
    validate_plan_execution_failure_diagnostic(
        receipt,
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        plan_execution_reconciliation=plan_execution_reconciliation,
        governed_l3_schedule=governed_l3_schedule,
    )
    return receipt


def validate_plan_execution_failure_diagnostic(
    receipt: Mapping[str, Any],
    *,
    l1_v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
    plan_execution_reconciliation: Mapping[str, Any],
    governed_l3_schedule: Mapping[str, Any],
) -> None:
    """Fail closed unless the W5 ledger exactly follows the observed receipts."""

    if not isinstance(receipt, Mapping):
        raise FailureAwareReplanError("W5 diagnostic receipt must be a mapping")
    if receipt.get("schema_version") != PLAN_EXECUTION_FAILURE_DIAGNOSTIC_SCHEMA_VERSION:
        raise FailureAwareReplanError("W5 diagnostic receipt schema_version is invalid")
    if receipt.get("contract_type") != "PlanExecutionFailureDiagnostic":
        raise FailureAwareReplanError("W5 diagnostic receipt contract_type is invalid")
    if receipt.get("authority_class") != _W5_DIAGNOSTIC_AUTHORITY:
        raise FailureAwareReplanError("W5 diagnostic receipt authority is invalid")
    if receipt.get("emitter") != _W5_EMITTER:
        raise FailureAwareReplanError("W5 diagnostic receipt emitter is invalid")
    if receipt.get("receipt_digest") != failure_diagnostic_receipt_digest(receipt):
        raise FailureAwareReplanError("W5 diagnostic receipt digest mismatch")
    bindings = _mapping(receipt.get("source_bindings"))
    expected = _failure_diagnostic_body(
        l1_v2_capsule=l1_v2_capsule,
        parent_plan_ref=str(
            _mapping(bindings.get("parent_l1_v2")).get("capsule_ref") or ""
        ),
        c0_obligation_receipt=c0_obligation_receipt,
        c0_obligation_receipt_ref=str(
            _mapping(bindings.get("c0_obligation_receipt")).get("receipt_ref") or ""
        ),
        plan_execution_reconciliation=plan_execution_reconciliation,
        plan_execution_reconciliation_ref=str(
            _mapping(bindings.get("plan_execution_reconciliation")).get(
                "receipt_ref"
            )
            or ""
        ),
        governed_l3_schedule=governed_l3_schedule,
        governed_l3_schedule_ref=str(
            _mapping(bindings.get("governed_l3_schedule")).get("receipt_ref")
            or ""
        ),
    )
    body = dict(receipt)
    body.pop("receipt_digest", None)
    if body != expected:
        raise FailureAwareReplanError(
            "W5 diagnostic receipt does not reconcile observed source receipts"
        )


def _prior_replan_metadata(
    values: Sequence[Mapping[str, Any]], *, parent_capsule_digest: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping):
            raise FailureAwareReplanError("W5 prior replan decision must be a mapping")
        if value.get("schema_version") != FAILURE_AWARE_REPLAN_V2_SCHEMA_VERSION:
            raise FailureAwareReplanError("W5 prior replan schema_version is invalid")
        declared_digest = str(value.get("decision_digest") or "")
        if not declared_digest or declared_digest != failure_aware_replan_v2_digest(value):
            raise FailureAwareReplanError("W5 prior replan digest is invalid")
        parent = _mapping(value.get("parent_l1_v2"))
        if parent.get("capsule_digest") != parent_capsule_digest:
            raise FailureAwareReplanError("W5 prior replan has a different parent plan")
        diagnostic = _mapping(value.get("diagnostic_receipt"))
        fingerprint = str(diagnostic.get("diagnostic_fingerprint") or "")
        depth = value.get("revision_depth")
        if not fingerprint or not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            raise FailureAwareReplanError("W5 prior replan diagnostic binding is invalid")
        if declared_digest in seen:
            raise FailureAwareReplanError("W5 prior replan decisions must be unique")
        seen.add(declared_digest)
        rows.append(
            {
                "decision_digest": declared_digest,
                "diagnostic_fingerprint": fingerprint,
                "revision_depth": depth,
            }
        )
    return sorted(rows, key=lambda row: row["decision_digest"])


def _w5_replan_actions(
    diagnostics: Sequence[Mapping[str, Any]],
    *,
    policy_codes: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, tuple[str, ...]], list[Mapping[str, Any]]] = {}
    unscoped: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        code = str(diagnostic.get("code") or "")
        policy = policy_codes.get(code)
        if policy is None:
            raise FailureAwareReplanError("W5 diagnostic code is not governed")
        requirement_ids = tuple(diagnostic.get("affected_requirement_ids") or ())
        unit_ids = tuple(diagnostic.get("affected_unit_ids") or ())
        if not policy["actionable"]:
            continue
        if not requirement_ids or not unit_ids:
            unscoped.append(
                {
                    "diagnostic_id": str(diagnostic.get("diagnostic_id") or ""),
                    "reason_code": "NO_AFFECTED_REQUIREMENT_SCOPE",
                    "designated_resolver": str(
                        diagnostic.get("designated_resolver") or policy["designated_resolver"]
                    ),
                }
            )
            continue
        key = (
            str(policy["strategy"]),
            str(policy["next_governed_owner"]),
            tuple(sorted(str(unit_id) for unit_id in unit_ids)),
        )
        grouped.setdefault(key, []).append(diagnostic)
    actions: list[dict[str, Any]] = []
    for (strategy, owner, unit_ids), group in sorted(grouped.items()):
        diagnostic_ids = sorted(str(row["diagnostic_id"]) for row in group)
        requirement_ids = sorted(
            {
                str(requirement_id)
                for row in group
                for requirement_id in row.get("affected_requirement_ids") or ()
            }
        )
        body = {
            "diagnostic_ids": diagnostic_ids,
            "affected_requirement_ids": requirement_ids,
            "affected_unit_ids": list(unit_ids),
            "strategy": strategy,
            "next_governed_owner": owner,
            "automatic_execution": False,
            "automatic_retry": False,
            "automatic_route_change": False,
            "automatic_exit_authorization": False,
        }
        action_id = "w5act-" + hashlib.sha256(
            _canonical_json(body).encode("utf-8")
        ).hexdigest()[:16]
        actions.append({"action_id": action_id, **body})
    return actions, sorted(unscoped, key=lambda row: row["diagnostic_id"])


def _replan_delta_v2(
    *,
    parent_capsule_digest: str,
    diagnostic_receipt_digest: str,
    revision_depth: int,
    actions: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not actions:
        return None
    body = {
        "schema_version": L1_REPLAN_DELTA_V2_SCHEMA_VERSION,
        "parent_plan_capsule_digest": parent_capsule_digest,
        "diagnostic_receipt_digest": diagnostic_receipt_digest,
        "revision_depth": revision_depth,
        "plan_deltas": [
            {
                "action_id": str(action["action_id"]),
                "affected_requirement_ids": list(action["affected_requirement_ids"]),
                "affected_unit_ids": list(action["affected_unit_ids"]),
                "strategy": str(action["strategy"]),
                "next_governed_owner": str(action["next_governed_owner"]),
            }
            for action in actions
        ],
        "authority_class": _W5_REPLAN_AUTHORITY,
        "authority_assertions": {
            "does_not_execute_work_units": True,
            "does_not_select_retries": True,
            "does_not_change_route": True,
            "does_not_authorize_exit": True,
        },
    }
    delta_id = "l1d-" + hashlib.sha256(
        _canonical_json(body).encode("utf-8")
    ).hexdigest()[:16]
    delta = {"delta_id": delta_id, **body}
    delta["delta_digest"] = _digest(delta, field="delta_digest")
    return delta


def _failure_aware_replan_v2_body(
    *,
    l1_v2_capsule: Mapping[str, Any],
    parent_plan_ref: str,
    diagnostic_receipt: Mapping[str, Any],
    diagnostic_receipt_ref: str,
    prior_replan_decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    policy, policy_codes = _w5_policy()
    identity, l1_binding = _identity_v2(l1_v2_capsule)
    parent_ref = _normalised_ref(parent_plan_ref, field_name="parent_plan_ref")
    diagnostic_ref = _normalised_ref(
        diagnostic_receipt_ref, field_name="diagnostic_receipt_ref"
    )
    if (
        diagnostic_receipt.get("schema_version")
        != PLAN_EXECUTION_FAILURE_DIAGNOSTIC_SCHEMA_VERSION
        or diagnostic_receipt.get("authority_class") != _W5_DIAGNOSTIC_AUTHORITY
        or diagnostic_receipt.get("receipt_digest")
        != failure_diagnostic_receipt_digest(diagnostic_receipt)
    ):
        raise FailureAwareReplanError("W5 diagnostic receipt is invalid for replan")
    diagnostic_identity = _mapping(diagnostic_receipt.get("identity"))
    if any(
        str(diagnostic_identity.get(field) or "") != identity[field]
        for field in identity
    ):
        raise FailureAwareReplanError("W5 diagnostic identity does not match L1 v2")
    diagnostic_parent = _mapping(
        _mapping(diagnostic_receipt.get("source_bindings")).get("parent_l1_v2")
    )
    if (
        diagnostic_parent.get("capsule_ref") != parent_ref
        or diagnostic_parent.get("capsule_digest") != l1_binding["capsule_digest"]
    ):
        raise FailureAwareReplanError("W5 diagnostic parent binding is invalid")
    diagnostics = diagnostic_receipt.get("diagnostics")
    if not isinstance(diagnostics, Sequence) or isinstance(diagnostics, (str, bytes)):
        raise FailureAwareReplanError("W5 diagnostic rows are invalid")
    expected_fingerprint = _diagnostic_fingerprint(
        [row for row in diagnostics if isinstance(row, Mapping)]
    )
    if (
        len(diagnostics) != len([row for row in diagnostics if isinstance(row, Mapping)])
        or diagnostic_receipt.get("diagnostic_fingerprint") != expected_fingerprint
    ):
        raise FailureAwareReplanError("W5 diagnostic fingerprint is invalid")
    prior = _prior_replan_metadata(
        prior_replan_decisions, parent_capsule_digest=l1_binding["capsule_digest"]
    )
    next_depth = max((int(row["revision_depth"]) for row in prior), default=0) + 1
    actions, unscoped = _w5_replan_actions(
        [dict(row) for row in diagnostics], policy_codes=policy_codes
    )
    fingerprint_seen = expected_fingerprint in {
        str(row["diagnostic_fingerprint"]) for row in prior
    }
    escalation: list[dict[str, Any]] = list(unscoped)
    if fingerprint_seen:
        status = "ESCALATED_UNCHANGED_DIAGNOSTIC"
        escalation.append(
            {
                "reason_code": "UNCHANGED_DIAGNOSTIC_FINGERPRINT",
                "designated_resolvers": sorted(
                    {
                        str(row.get("designated_resolver") or "")
                        for row in diagnostics
                        if str(row.get("designated_resolver") or "")
                    }
                ),
            }
        )
        actions = []
    elif next_depth > int(policy["max_advisory_revision_depth"]):
        status = "ESCALATED_REVISION_DEPTH_LIMIT"
        escalation.append(
            {
                "reason_code": "MAX_ADVISORY_REVISION_DEPTH_REACHED",
                "designated_resolvers": sorted(
                    {
                        str(row.get("designated_resolver") or "")
                        for row in diagnostics
                        if str(row.get("designated_resolver") or "")
                    }
                ),
            }
        )
        actions = []
    elif actions:
        status = "REPLAN_PROPOSED"
    elif diagnostics:
        status = "ESCALATED_NO_NEW_EVIDENCE_OR_INPUT"
    else:
        status = "NO_ACTIONABLE_REPLAN"
    diagnostic_binding = {
        "receipt_ref": diagnostic_ref,
        "receipt_digest": str(diagnostic_receipt["receipt_digest"]),
        "diagnostic_fingerprint": expected_fingerprint,
    }
    delta = _replan_delta_v2(
        parent_capsule_digest=l1_binding["capsule_digest"],
        diagnostic_receipt_digest=diagnostic_binding["receipt_digest"],
        revision_depth=next_depth,
        actions=actions,
    )
    return {
        "schema_version": FAILURE_AWARE_REPLAN_V2_SCHEMA_VERSION,
        "contract_type": FAILURE_AWARE_REPLAN_V2_CONTRACT_TYPE,
        "authority_class": _W5_REPLAN_AUTHORITY,
        "identity": identity,
        "parent_l1_v2": {
            "capsule_ref": parent_ref,
            "capsule_digest": l1_binding["capsule_digest"],
        },
        "diagnostic_receipt": diagnostic_binding,
        "prior_replan_decision_digests": [row["decision_digest"] for row in prior],
        "revision_depth": next_depth,
        "max_advisory_revision_depth": int(policy["max_advisory_revision_depth"]),
        "replan_status": status,
        "replan_actions": actions,
        "replan_delta": delta,
        "escalation": escalation,
        "authority_assertions": {
            "does_not_execute_work_units": True,
            "does_not_select_retries": True,
            "does_not_change_route": True,
            "does_not_authorize_exit_or_release": True,
            "replan_is_advisory_only": True,
        },
        "emitter": _W5_EMITTER,
    }


def build_failure_aware_replan_v2(
    *,
    l1_v2_capsule: Mapping[str, Any],
    parent_plan_ref: str,
    diagnostic_receipt: Mapping[str, Any],
    diagnostic_receipt_ref: str,
    prior_replan_decisions: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Propose a bounded, requirement-scoped W5 advisory replan delta."""

    decision = _failure_aware_replan_v2_body(
        l1_v2_capsule=l1_v2_capsule,
        parent_plan_ref=parent_plan_ref,
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_receipt_ref=diagnostic_receipt_ref,
        prior_replan_decisions=prior_replan_decisions,
    )
    decision["decision_digest"] = failure_aware_replan_v2_digest(decision)
    validate_failure_aware_replan_v2(
        decision,
        l1_v2_capsule=l1_v2_capsule,
        diagnostic_receipt=diagnostic_receipt,
        prior_replan_decisions=prior_replan_decisions,
    )
    return decision


def validate_failure_aware_replan_v2(
    decision: Mapping[str, Any],
    *,
    l1_v2_capsule: Mapping[str, Any],
    diagnostic_receipt: Mapping[str, Any],
    prior_replan_decisions: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Reject a W5 delta that is wider, stronger, or newer than its evidence."""

    if not isinstance(decision, Mapping):
        raise FailureAwareReplanError("W5 replan decision must be a mapping")
    if decision.get("schema_version") != FAILURE_AWARE_REPLAN_V2_SCHEMA_VERSION:
        raise FailureAwareReplanError("W5 replan schema_version is invalid")
    if decision.get("contract_type") != FAILURE_AWARE_REPLAN_V2_CONTRACT_TYPE:
        raise FailureAwareReplanError("W5 replan contract_type is invalid")
    if decision.get("authority_class") != _W5_REPLAN_AUTHORITY:
        raise FailureAwareReplanError("W5 replan authority is invalid")
    if decision.get("emitter") != _W5_EMITTER:
        raise FailureAwareReplanError("W5 replan emitter is invalid")
    if decision.get("decision_digest") != failure_aware_replan_v2_digest(decision):
        raise FailureAwareReplanError("W5 replan decision digest mismatch")
    parent = _mapping(decision.get("parent_l1_v2"))
    diagnostic = _mapping(decision.get("diagnostic_receipt"))
    expected = _failure_aware_replan_v2_body(
        l1_v2_capsule=l1_v2_capsule,
        parent_plan_ref=str(parent.get("capsule_ref") or ""),
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_receipt_ref=str(diagnostic.get("receipt_ref") or ""),
        prior_replan_decisions=prior_replan_decisions,
    )
    body = dict(decision)
    body.pop("decision_digest", None)
    if body != expected:
        raise FailureAwareReplanError(
            "W5 replan decision does not match diagnostic scope and policy"
        )


def write_plan_execution_failure_diagnostic(
    *,
    output_path: Path,
    receipt: Mapping[str, Any],
    l1_v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
    plan_execution_reconciliation: Mapping[str, Any],
    governed_l3_schedule: Mapping[str, Any],
) -> Path:
    """Validate and persist one caller-owned W5 diagnostic artifact."""

    validate_plan_execution_failure_diagnostic(
        receipt,
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        plan_execution_reconciliation=plan_execution_reconciliation,
        governed_l3_schedule=governed_l3_schedule,
    )
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


def write_failure_aware_replan_v2(
    *,
    output_path: Path,
    decision: Mapping[str, Any],
    l1_v2_capsule: Mapping[str, Any],
    diagnostic_receipt: Mapping[str, Any],
    prior_replan_decisions: Sequence[Mapping[str, Any]] = (),
) -> Path:
    """Validate and persist one caller-owned W5 advisory replan artifact."""

    validate_failure_aware_replan_v2(
        decision,
        l1_v2_capsule=l1_v2_capsule,
        diagnostic_receipt=diagnostic_receipt,
        prior_replan_decisions=prior_replan_decisions,
    )
    path = Path(output_path)
    sr.write_stage_receipt(path, decision)
    return path


def emit_failure_aware_replan_v2(
    *,
    artifact_dir: Path,
    l1_v2_capsule: Mapping[str, Any],
    parent_plan_ref: str,
    c0_obligation_receipt: Mapping[str, Any],
    c0_obligation_receipt_ref: str,
    plan_execution_reconciliation: Mapping[str, Any],
    plan_execution_reconciliation_ref: str,
    governed_l3_schedule: Mapping[str, Any],
    governed_l3_schedule_ref: str,
    prior_replan_decisions: Sequence[Mapping[str, Any]] = (),
) -> tuple[Path, Path]:
    """Build and persist the paired W5 diagnostic and advisory delta receipts."""

    artifact_dir = Path(artifact_dir)
    diagnostic = build_plan_execution_failure_diagnostic(
        l1_v2_capsule=l1_v2_capsule,
        parent_plan_ref=parent_plan_ref,
        c0_obligation_receipt=c0_obligation_receipt,
        c0_obligation_receipt_ref=c0_obligation_receipt_ref,
        plan_execution_reconciliation=plan_execution_reconciliation,
        plan_execution_reconciliation_ref=plan_execution_reconciliation_ref,
        governed_l3_schedule=governed_l3_schedule,
        governed_l3_schedule_ref=governed_l3_schedule_ref,
    )
    diagnostic_path = write_plan_execution_failure_diagnostic(
        output_path=artifact_dir / sr.FILENAME_PLAN_EXECUTION_FAILURE_DIAGNOSTIC,
        receipt=diagnostic,
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        plan_execution_reconciliation=plan_execution_reconciliation,
        governed_l3_schedule=governed_l3_schedule,
    )
    decision = build_failure_aware_replan_v2(
        l1_v2_capsule=l1_v2_capsule,
        parent_plan_ref=parent_plan_ref,
        diagnostic_receipt=diagnostic,
        diagnostic_receipt_ref=sr.FILENAME_PLAN_EXECUTION_FAILURE_DIAGNOSTIC,
        prior_replan_decisions=prior_replan_decisions,
    )
    decision_path = write_failure_aware_replan_v2(
        output_path=artifact_dir / sr.FILENAME_FAILURE_AWARE_REPLAN_V2,
        decision=decision,
        l1_v2_capsule=l1_v2_capsule,
        diagnostic_receipt=diagnostic,
        prior_replan_decisions=prior_replan_decisions,
    )
    return diagnostic_path, decision_path


__all__ = [
    "FAILURE_AWARE_REPLAN_SCHEMA_VERSION",
    "FAILURE_AWARE_REPLAN_V2_SCHEMA_VERSION",
    "L1_REPLAN_REVISION_SCHEMA_VERSION",
    "L1_REPLAN_DELTA_V2_SCHEMA_VERSION",
    "PLAN_EXECUTION_FAILURE_DIAGNOSTIC_SCHEMA_VERSION",
    "FailureAwareReplanError",
    "build_failure_aware_replan",
    "build_failure_aware_replan_v2",
    "build_plan_execution_failure_diagnostic",
    "emit_failure_aware_replan",
    "emit_failure_aware_replan_v2",
    "failure_aware_replan_v2_digest",
    "failure_diagnostic_receipt_digest",
    "validate_failure_aware_replan",
    "validate_failure_aware_replan_v2",
    "validate_plan_execution_failure_diagnostic",
    "write_failure_aware_replan_v2",
    "write_plan_execution_failure_diagnostic",
]
