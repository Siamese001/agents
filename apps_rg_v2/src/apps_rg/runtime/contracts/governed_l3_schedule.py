"""Receipt-bound L3 scheduling for the advisory apps_rg L1 v2 work DAG.

L1 supplies a verified graph, never an execution order.  This module lets the
apps_rg L3 owner derive a deterministic serial schedule from that graph and
current C0/W1/W3 receipts.  It does not dispatch a unit, retrieve evidence,
assemble a prompt, choose a route, or authorize an Exit decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    L1PlanningV2IntegrityError,
    verify_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    L1EvidenceObligationReceiptError,
    receipt_digest as c0_obligation_receipt_digest,
    validate_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    PlanExecutionReconciliationError,
    receipt_digest as plan_execution_receipt_digest,
    validate_plan_execution_reconciliation,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


GOVERNED_L3_SCHEDULE_SCHEMA_VERSION: Final[str] = (
    "apps_rg.governed_l3_schedule.v1"
)
GOVERNED_L3_SCHEDULE_AUTHORITY: Final[str] = "L3_SCHEDULING_ONLY"
L3_SCHEDULING_POLICY_ID: Final[str] = "apps_rg.l3.serial_topological.v1"
_VALID_ENTRY_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"SATISFIED", "SELECTED", "DEFERRED", "BLOCKED", "SKIPPED"}
)
_ROOT_NODE_IDS: Final[frozenset[str]] = frozenset(
    {"u0:validated_jd", "u0:validated_resume"}
)


class GovernedL3ScheduleError(ValueError):
    """Raised when an L3 schedule cannot be bound to authoritative receipts."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    """Return the stable digest excluding this receipt's self-reference."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return _sha256(body)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _require_relative_ref(value: Any, *, field: str, allow_empty: bool = False) -> str:
    ref = str(value or "").strip().replace("\\", "/")
    if not ref:
        if allow_empty:
            return ""
        raise GovernedL3ScheduleError(f"{field} is required")
    candidate = Path(ref)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise GovernedL3ScheduleError(f"{field} must be a relative artifact reference")
    return ref


def _identity(capsule: Mapping[str, Any]) -> dict[str, str]:
    identity = {
        field: str(capsule.get(field) or "").strip()
        for field in ("request_id", "run_id", "trace_id")
    }
    if any(not value for value in identity.values()):
        raise GovernedL3ScheduleError("L1 v2 identity is incomplete")
    return identity


def _verified_graph(capsule: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str], dict[str, str], list[dict[str, str]]]:
    try:
        verification = verify_apps_rg_l1_planning_capsule_v2(capsule)
    except L1PlanningV2IntegrityError as exc:
        raise GovernedL3ScheduleError("L1 v2 capsule is invalid") from exc
    dag = capsule.get("work_dag")
    if not isinstance(dag, Mapping):
        raise GovernedL3ScheduleError("L1 v2 work DAG is invalid")
    nodes = dag.get("nodes")
    edges = dag.get("edges")
    if not isinstance(nodes, Sequence) or not isinstance(edges, Sequence):
        raise GovernedL3ScheduleError("L1 v2 work DAG is incomplete")
    node_types = {
        str(node.get("node_id") or ""): str(node.get("node_type") or "")
        for node in nodes
        if isinstance(node, Mapping)
    }
    if len(node_types) != len(nodes) or not node_types:
        raise GovernedL3ScheduleError("L1 v2 work DAG node coverage is invalid")
    normalized_edges: list[dict[str, str]] = []
    for edge in edges:
        if not isinstance(edge, Mapping):
            raise GovernedL3ScheduleError("L1 v2 work DAG edge is invalid")
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        relation = str(edge.get("relation") or "")
        if source not in node_types or target not in node_types or not relation:
            raise GovernedL3ScheduleError("L1 v2 work DAG edge is invalid")
        normalized_edges.append({"from": source, "to": target, "relation": relation})
    return (
        {"capsule_digest": str(verification["capsule_digest"]), "dag_digest": str(verification["work_dag_digest"])},
        _identity(capsule),
        node_types,
        sorted(normalized_edges, key=lambda edge: (edge["from"], edge["to"], edge["relation"])),
    )


def _topological_order(node_types: Mapping[str, str], edges: Sequence[Mapping[str, str]]) -> list[str]:
    incoming = {node_id: 0 for node_id in node_types}
    children = {node_id: [] for node_id in node_types}
    for edge in edges:
        source = str(edge["from"])
        target = str(edge["to"])
        incoming[target] += 1
        children[source].append(target)
    order: list[str] = []
    ready = sorted(node_id for node_id, count in incoming.items() if count == 0)
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for child in sorted(children[node_id]):
            incoming[child] -= 1
            if incoming[child] == 0:
                ready.append(child)
        ready.sort()
    if len(order) != len(node_types):
        raise GovernedL3ScheduleError("L1 v2 work DAG is not schedulable")
    return order


def _validate_c0_receipt(
    *, capsule: Mapping[str, Any], receipt: Mapping[str, Any], identity: Mapping[str, str]
) -> dict[str, Any]:
    try:
        validate_l1_evidence_obligation_receipt(receipt, capsule=capsule)
    except L1EvidenceObligationReceiptError as exc:
        raise GovernedL3ScheduleError("C0 obligation receipt is invalid") from exc
    receipt_identity = _mapping(receipt.get("identity"))
    if any(str(receipt_identity.get(field) or "") != identity[field] for field in identity):
        raise GovernedL3ScheduleError("C0 obligation receipt identity is not L1-bound")
    return {
        "receipt_digest": c0_obligation_receipt_digest(receipt),
        "disposition_count": len(receipt.get("obligation_dispositions") or ()),
    }


def _execution_observations(
    *,
    receipt: Mapping[str, Any] | None,
    receipt_ref: str,
    identity: Mapping[str, str],
    work_unit_ids: frozenset[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if receipt is None:
        if receipt_ref:
            raise GovernedL3ScheduleError(
                "plan_execution_reconciliation_ref requires a receipt"
            )
        return {}, {"observed": False, "ref": "", "receipt_digest": ""}
    ref = _require_relative_ref(
        receipt_ref, field="plan_execution_reconciliation_ref"
    )
    try:
        validate_plan_execution_reconciliation(receipt)
    except PlanExecutionReconciliationError as exc:
        raise GovernedL3ScheduleError("W1 execution reconciliation is invalid") from exc
    if any(str(receipt.get(field) or "") != identity[field] for field in ("request_id", "run_id")):
        raise GovernedL3ScheduleError("W1 execution reconciliation identity is invalid")
    outcomes = {
        str(row.get("unit_id") or ""): dict(row)
        for row in receipt.get("unit_outcomes") or ()
        if isinstance(row, Mapping)
    }
    observations = {
        str(row.get("unit_id") or ""): dict(row)
        for row in receipt.get("unit_observations") or ()
        if isinstance(row, Mapping)
    }
    if set(outcomes) != work_unit_ids or set(observations) != work_unit_ids:
        raise GovernedL3ScheduleError(
            "W1 execution reconciliation does not cover the L1 v2 work units"
        )
    return (
        {
            unit_id: {"outcome": outcomes[unit_id], "observation": observations[unit_id]}
            for unit_id in sorted(work_unit_ids)
        },
        {
            "observed": True,
            "ref": ref,
            "receipt_digest": plan_execution_receipt_digest(receipt),
        },
    )


def _entry(
    *,
    node_id: str,
    node_type: str,
    disposition: str,
    reason_code: str,
    predecessor_states: Sequence[Mapping[str, str]],
    receipt_refs: Sequence[str],
) -> dict[str, Any]:
    if disposition not in _VALID_ENTRY_DISPOSITIONS:
        raise GovernedL3ScheduleError("L3 schedule disposition is invalid")
    return {
        "node_id": node_id,
        "node_type": node_type,
        "disposition": disposition,
        "reason_code": reason_code,
        "predecessor_states": [dict(row) for row in predecessor_states],
        "receipt_refs": sorted(set(str(ref) for ref in receipt_refs if str(ref))),
    }


def _schedule_entries(
    *,
    node_types: Mapping[str, str],
    edges: Sequence[Mapping[str, str]],
    topological_order: Sequence[str],
    c0_ref: str,
    execution_by_unit: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    predecessors: dict[str, list[dict[str, str]]] = {node_id: [] for node_id in node_types}
    for edge in edges:
        predecessors[str(edge["to"])].append(dict(edge))
    entries: dict[str, dict[str, Any]] = {}
    selected: list[str] = []

    for node_id in topological_order:
        node_type = node_types[node_id]
        prior = [
            {
                "from": str(edge["from"]),
                "relation": str(edge["relation"]),
                "disposition": str(entries[str(edge["from"])]["disposition"]),
            }
            for edge in sorted(
                predecessors[node_id], key=lambda edge: (edge["from"], edge["relation"])
            )
        ]
        if node_id in _ROOT_NODE_IDS:
            entries[node_id] = _entry(
                node_id=node_id,
                node_type=node_type,
                disposition="SATISFIED",
                reason_code="U0_VALIDATED_INPUT_BOUND",
                predecessor_states=prior,
                receipt_refs=(),
            )
            continue
        if node_type == "REQUIREMENT":
            entries[node_id] = _entry(
                node_id=node_id,
                node_type=node_type,
                disposition="SATISFIED",
                reason_code="L1_ADVISORY_TARGETING_BOUND",
                predecessor_states=prior,
                receipt_refs=(),
            )
            continue
        if node_type == "WORK_UNIT":
            unit_id = node_id.removeprefix("unit:")
            execution = execution_by_unit.get(unit_id)
            if execution is None:
                disposition, reason, refs = "SELECTED", "C0_RECEIPT_READY_FOR_L3", [c0_ref]
                selected.append(node_id)
            else:
                outcome = _mapping(execution.get("outcome"))
                if outcome.get("disposition") == "COMPLETED":
                    disposition, reason, refs = "SATISFIED", "W1_UNIT_COMPLETED", [c0_ref]
                elif outcome.get("disposition") == "SKIPPED":
                    disposition, reason, refs = "SKIPPED", str(outcome.get("failure_code") or "W1_SKIPPED"), [c0_ref]
                else:
                    disposition, reason, refs = "BLOCKED", str(outcome.get("failure_code") or "W1_UNIT_NOT_COMPLETED"), [c0_ref]
            entries[node_id] = _entry(
                node_id=node_id,
                node_type=node_type,
                disposition=disposition,
                reason_code=reason,
                predecessor_states=prior,
                receipt_refs=refs,
            )
            continue
        if node_type == "VALIDATION":
            unit_node = next(
                (str(edge["from"]) for edge in predecessors[node_id] if edge["relation"] == "REQUIRES_VALIDATION"),
                "",
            )
            unit_entry = entries.get(unit_node, {})
            unit_id = unit_node.removeprefix("unit:")
            execution = execution_by_unit.get(unit_id, {})
            observation = _mapping(execution.get("observation"))
            control_ref = str(observation.get("reasoning_control_execution_receipt_ref") or "")
            if unit_entry.get("disposition") == "SATISFIED" and observation.get("quality_certification_eligible") is True:
                disposition, reason, refs = "SATISFIED", "W3_CONTROL_QUALITY_ELIGIBLE", [control_ref]
            elif unit_entry.get("disposition") in {"BLOCKED", "SKIPPED"}:
                disposition, reason, refs = str(unit_entry["disposition"]), "UNIT_PREDECESSOR_NOT_SATISFIED", [control_ref]
            else:
                disposition, reason, refs = "DEFERRED", "AWAITING_UNIT_COMPLETION_AND_W3_RECEIPT", []
            entries[node_id] = _entry(
                node_id=node_id,
                node_type=node_type,
                disposition=disposition,
                reason_code=reason,
                predecessor_states=prior,
                receipt_refs=refs,
            )
            continue
        if node_type == "MERGE":
            validation_entries = [entries[str(edge["from"])] for edge in predecessors[node_id] if edge["relation"] == "MERGE_AFTER"]
            validation_dispositions = {str(entry["disposition"]) for entry in validation_entries}
            refs = [ref for entry in validation_entries for ref in entry["receipt_refs"]]
            if validation_entries and validation_dispositions == {"SATISFIED"}:
                disposition, reason = "SELECTED", "MERGE_AFTER_VALIDATION_SATISFIED"
                selected.append(node_id)
            elif validation_dispositions & {"BLOCKED", "SKIPPED"}:
                disposition, reason = "BLOCKED", "MERGE_AFTER_VALIDATION_BLOCKED"
            else:
                disposition, reason = "DEFERRED", "AWAITING_MERGE_AFTER_VALIDATION"
            entries[node_id] = _entry(
                node_id=node_id,
                node_type=node_type,
                disposition=disposition,
                reason_code=reason,
                predecessor_states=prior,
                receipt_refs=refs,
            )
            continue
        raise GovernedL3ScheduleError(f"L1 v2 node type is unschedulable: {node_type}")

    merge_entries = [entry for entry in entries.values() if entry["node_type"] == "MERGE"]
    merge_check = {
        "merge_node_ids": sorted(entry["node_id"] for entry in merge_entries),
        "status": (
            "NOT_APPLICABLE"
            if not merge_entries
            else str(merge_entries[0]["disposition"])
        ),
        "required_validation_node_ids": sorted(
            str(edge["from"])
            for edge in edges
            if edge["relation"] == "MERGE_AFTER"
        ),
        "control_receipt_refs": sorted(
            {
                ref
                for entry in merge_entries
                for ref in entry["receipt_refs"]
            }
        ),
    }
    return [entries[node_id] for node_id in topological_order], selected, merge_check


def _receipt_body(
    *,
    l1_v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
    c0_obligation_receipt_ref: str,
    plan_execution_reconciliation: Mapping[str, Any] | None,
    plan_execution_reconciliation_ref: str,
) -> dict[str, Any]:
    plan, identity, node_types, edges = _verified_graph(l1_v2_capsule)
    c0_ref = _require_relative_ref(
        c0_obligation_receipt_ref, field="c0_obligation_receipt_ref"
    )
    c0 = _validate_c0_receipt(
        capsule=l1_v2_capsule,
        receipt=c0_obligation_receipt,
        identity=identity,
    )
    work_unit_ids = frozenset(
        node_id.removeprefix("unit:")
        for node_id, node_type in node_types.items()
        if node_type == "WORK_UNIT"
    )
    execution_by_unit, execution = _execution_observations(
        receipt=plan_execution_reconciliation,
        receipt_ref=plan_execution_reconciliation_ref,
        identity=identity,
        work_unit_ids=work_unit_ids,
    )
    topological = _topological_order(node_types, edges)
    entries, selected, merge_check = _schedule_entries(
        node_types=node_types,
        edges=edges,
        topological_order=topological,
        c0_ref=c0_ref,
        execution_by_unit=execution_by_unit,
    )
    return {
        "schema_version": GOVERNED_L3_SCHEDULE_SCHEMA_VERSION,
        "authority_class": GOVERNED_L3_SCHEDULE_AUTHORITY,
        "identity": identity,
        "l1_v2": plan,
        "input_receipts": {
            "c0_obligation_receipt_ref": c0_ref,
            "c0_obligation_receipt_digest": c0["receipt_digest"],
            "c0_obligation_disposition_count": c0["disposition_count"],
            "plan_execution_reconciliation_ref": execution["ref"],
            "plan_execution_reconciliation_digest": execution["receipt_digest"],
            "plan_execution_reconciliation_observed": execution["observed"],
        },
        "l3_policy": {
            "policy_id": L3_SCHEDULING_POLICY_ID,
            "max_parallelism": 1,
            "selection_method": "TOPOLOGICAL_LEXICAL_SERIAL",
            "l1_supplies_graph_but_not_execution_order": True,
        },
        "schedule": {
            "topological_node_order": topological,
            "entries": entries,
            "selected_node_ids": selected,
            "parallel_batches": [[node_id] for node_id in selected],
            "observed_parallelism": 1 if selected else 0,
        },
        "merge_check": merge_check,
        "authority_assertions": {
            "l3_chose_execution_order": True,
            "does_not_execute_work_units": True,
            "does_not_retrieve_evidence": True,
            "does_not_assemble_prompts": True,
            "does_not_select_route_or_authorize_exit": True,
            "c0_remains_evidence_authority": True,
        },
    }


def build_governed_l3_schedule_receipt(
    *,
    l1_v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
    c0_obligation_receipt_ref: str,
    plan_execution_reconciliation: Mapping[str, Any] | None = None,
    plan_execution_reconciliation_ref: str = "",
) -> dict[str, Any]:
    """Have L3 select serial eligible nodes from verified downstream state."""

    receipt = _receipt_body(
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        c0_obligation_receipt_ref=c0_obligation_receipt_ref,
        plan_execution_reconciliation=plan_execution_reconciliation,
        plan_execution_reconciliation_ref=plan_execution_reconciliation_ref,
    )
    receipt["receipt_digest"] = receipt_digest(receipt)
    validate_governed_l3_schedule_receipt(
        receipt,
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        plan_execution_reconciliation=plan_execution_reconciliation,
    )
    return receipt


def validate_governed_l3_schedule_receipt(
    receipt: Mapping[str, Any],
    *,
    l1_v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
    plan_execution_reconciliation: Mapping[str, Any] | None = None,
) -> None:
    """Fail closed unless the receipt is an exact L3-derived schedule."""

    if not isinstance(receipt, Mapping):
        raise GovernedL3ScheduleError("L3 schedule receipt must be a mapping")
    if receipt.get("schema_version") != GOVERNED_L3_SCHEDULE_SCHEMA_VERSION:
        raise GovernedL3ScheduleError("L3 schedule receipt schema_version is invalid")
    if receipt.get("authority_class") != GOVERNED_L3_SCHEDULE_AUTHORITY:
        raise GovernedL3ScheduleError("L3 schedule receipt authority is invalid")
    if receipt.get("receipt_digest") != receipt_digest(receipt):
        raise GovernedL3ScheduleError("L3 schedule receipt digest mismatch")
    input_receipts = _mapping(receipt.get("input_receipts"))
    expected = _receipt_body(
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        c0_obligation_receipt_ref=str(
            input_receipts.get("c0_obligation_receipt_ref") or ""
        ),
        plan_execution_reconciliation=plan_execution_reconciliation,
        plan_execution_reconciliation_ref=str(
            input_receipts.get("plan_execution_reconciliation_ref") or ""
        ),
    )
    expected["receipt_digest"] = receipt_digest(expected)
    if dict(receipt) != expected:
        raise GovernedL3ScheduleError("L3 schedule receipt does not reconcile")


def write_governed_l3_schedule_receipt(
    *,
    output_path: Path,
    receipt: Mapping[str, Any],
    l1_v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
    plan_execution_reconciliation: Mapping[str, Any] | None = None,
) -> Path:
    """Validate and write one caller-owned L3 schedule sidecar."""

    validate_governed_l3_schedule_receipt(
        receipt,
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        plan_execution_reconciliation=plan_execution_reconciliation,
    )
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


def emit_governed_l3_schedule_receipt(
    *,
    artifact_dir: Path,
    receipt: Mapping[str, Any],
    l1_v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
    plan_execution_reconciliation: Mapping[str, Any] | None = None,
) -> Path:
    """Persist the canonical schedule receipt beneath the run artifact root."""

    return write_governed_l3_schedule_receipt(
        output_path=Path(artifact_dir) / sr.FILENAME_GOVERNED_L3_SCHEDULE_RECEIPT,
        receipt=receipt,
        l1_v2_capsule=l1_v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
        plan_execution_reconciliation=plan_execution_reconciliation,
    )


__all__ = [
    "GOVERNED_L3_SCHEDULE_AUTHORITY",
    "GOVERNED_L3_SCHEDULE_SCHEMA_VERSION",
    "GovernedL3ScheduleError",
    "L3_SCHEDULING_POLICY_ID",
    "build_governed_l3_schedule_receipt",
    "emit_governed_l3_schedule_receipt",
    "receipt_digest",
    "validate_governed_l3_schedule_receipt",
    "write_governed_l3_schedule_receipt",
]
