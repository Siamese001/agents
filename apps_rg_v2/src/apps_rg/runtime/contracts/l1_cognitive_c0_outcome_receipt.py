"""C0-owned outcomes for atomic L1 v3 cognitive requirements.

This receipt translates already-authoritative C0 v2 obligation dispositions to
their v3 atomic children.  It does not create evidence, alter C0's result, or
authorise a retry.  The resulting failure rows are the only C0 inputs eligible
for a bounded L1 v3 revision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import (
    L1CognitivePlanError,
    _build_l1_cognitive_revision_from_validated_c0_outcomes,
    validate_l1_cognitive_plan_v3,
    validate_l1_cognitive_revision_v3,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    L1EvidenceObligationReceiptError,
    validate_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


L1_COGNITIVE_C0_OUTCOME_SCHEMA_VERSION: Final[str] = (
    "apps_rg.l1_cognitive_c0_outcome.v1"
)
L1_COGNITIVE_C0_OUTCOME_AUTHORITY: Final[str] = "C0_EVIDENCE_RECONCILIATION_ONLY"
L1_COGNITIVE_C0_OUTCOME_APP_SCOPE: Final[str] = "APPS_RG_V2_ONLY"
_FAILURE_CODES: Final[frozenset[str]] = frozenset(
    {"C0_CONTRADICTED", "C0_INSUFFICIENT"}
)


class L1CognitiveC0OutcomeError(ValueError):
    """Raised when C0 outcomes cannot be reconciled to a v3 cognitive plan."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return (
        "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    )


def cognitive_c0_outcome_digest(receipt: Mapping[str, Any]) -> str:
    """Return the canonical digest excluding only ``receipt_digest``."""

    body = dict(receipt)
    body.pop("receipt_digest", None)
    return _sha256(body)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _validated_inputs(
    *,
    cognitive_plan: Mapping[str, Any],
    v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
) -> None:
    try:
        validate_l1_cognitive_plan_v3(cognitive_plan)
    except L1CognitivePlanError as exc:
        raise L1CognitiveC0OutcomeError("L1 v3 cognitive plan is invalid") from exc
    try:
        validate_l1_evidence_obligation_receipt(
            c0_obligation_receipt, capsule=v2_capsule
        )
    except L1EvidenceObligationReceiptError as exc:
        raise L1CognitiveC0OutcomeError("C0 obligation receipt is invalid") from exc


def _outcome_rows(
    cognitive_plan: Mapping[str, Any], c0_obligation_receipt: Mapping[str, Any]
) -> list[dict[str, Any]]:
    entries_by_parent: dict[str, list[Mapping[str, Any]]] = {}
    entries = c0_obligation_receipt.get("obligation_dispositions")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise L1CognitiveC0OutcomeError("C0 obligation dispositions are invalid")
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise L1CognitiveC0OutcomeError("C0 obligation disposition is invalid")
        parent_id = str(entry.get("requirement_id") or "").strip()
        if not parent_id:
            raise L1CognitiveC0OutcomeError("C0 obligation requirement ID is invalid")
        entries_by_parent.setdefault(parent_id, []).append(entry)

    graph = _mapping(cognitive_plan.get("atomic_requirement_graph"))
    requirements = graph.get("requirements")
    if not isinstance(requirements, Sequence) or isinstance(requirements, (str, bytes)):
        raise L1CognitiveC0OutcomeError("L1 v3 requirement graph is invalid")
    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            raise L1CognitiveC0OutcomeError("L1 v3 requirement is invalid")
        requirement_id = str(requirement.get("requirement_id") or "").strip()
        parent_requirement_id = str(
            requirement.get("parent_requirement_id") or ""
        ).strip()
        coverage_status = str(requirement.get("coverage_status") or "").strip()
        if not requirement_id or not parent_requirement_id:
            raise L1CognitiveC0OutcomeError("L1 v3 requirement identity is invalid")
        parent_entries = entries_by_parent.get(parent_requirement_id, [])
        if coverage_status != "MAPPED":
            outcome = (
                "L1_ESCALATED" if coverage_status == "ESCALATED" else "L1_UNMAPPED"
            )
            rows.append(
                {
                    "requirement_id": requirement_id,
                    "parent_requirement_id": parent_requirement_id,
                    "outcome": outcome,
                    "c0_obligation_ids": [],
                    "c0_evidence_refs": [],
                    "c0_parent_obligation_eligible": bool(
                        requirement.get("parent_c0_obligation_eligible")
                    ),
                    "reason_code": "L1_REQUIREMENT_NOT_MAPPED",
                    "revision_eligible": False,
                }
            )
            continue
        if not parent_entries:
            # V3 may split a compound or otherwise unbound V2 parent into a
            # semantically targetable atom.  That does *not* create C0
            # evidence.  Treat the observed absence of a parent obligation as
            # C0 insufficiency so downstream handling is an explicit safe
            # revision/gate, rather than an untraceable planner crash or an
            # unsupported claim.  Older plans without this explicit marker
            # remain fail-closed.
            if requirement.get("parent_c0_obligation_eligible") is False:
                rows.append(
                    {
                        "requirement_id": requirement_id,
                        "parent_requirement_id": parent_requirement_id,
                        "outcome": "C0_INSUFFICIENT",
                        "c0_obligation_ids": [],
                        "c0_evidence_refs": [],
                        "c0_parent_obligation_eligible": False,
                        "reason_code": "C0_PARENT_OBLIGATION_MISSING",
                        "revision_eligible": True,
                    }
                )
                continue
            raise L1CognitiveC0OutcomeError(
                "mapped L1 v3 requirement has no C0 parent obligation"
            )
        dispositions = {
            str(entry.get("support_disposition") or "").strip()
            for entry in parent_entries
        }
        if "CONTRADICTED" in dispositions:
            outcome = "C0_CONTRADICTED"
        elif dispositions == {"SUPPORTED"}:
            outcome = "C0_SUPPORTED"
        else:
            outcome = "C0_INSUFFICIENT"
        rows.append(
            {
                "requirement_id": requirement_id,
                "parent_requirement_id": parent_requirement_id,
                "outcome": outcome,
                "c0_obligation_ids": sorted(
                    str(entry.get("obligation_id") or "") for entry in parent_entries
                ),
                "c0_evidence_refs": sorted(
                    {
                        str(ref)
                        for entry in parent_entries
                        for ref in (entry.get("evidence_refs") or ())
                        if str(ref).strip()
                    }
                ),
                "c0_parent_obligation_eligible": bool(
                    requirement.get("parent_c0_obligation_eligible", True)
                ),
                "reason_code": (
                    "C0_REQUIREMENT_CONTRADICTED"
                    if outcome == "C0_CONTRADICTED"
                    else "C0_REQUIREMENT_SUPPORTED"
                    if outcome == "C0_SUPPORTED"
                    else "C0_REQUIREMENT_INSUFFICIENT"
                ),
                "revision_eligible": outcome in _FAILURE_CODES,
            }
        )
    return sorted(rows, key=lambda row: str(row["requirement_id"]))


def build_l1_cognitive_c0_outcome_receipt(
    *,
    cognitive_plan: Mapping[str, Any],
    v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind C0 evidence dispositions to every atomic L1 v3 requirement."""

    _validated_inputs(
        cognitive_plan=cognitive_plan,
        v2_capsule=v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
    )
    identity = _mapping(c0_obligation_receipt.get("identity"))
    rows = _outcome_rows(cognitive_plan, c0_obligation_receipt)
    receipt = {
        "schema_version": L1_COGNITIVE_C0_OUTCOME_SCHEMA_VERSION,
        "authority_class": L1_COGNITIVE_C0_OUTCOME_AUTHORITY,
        "app_scope": L1_COGNITIVE_C0_OUTCOME_APP_SCOPE,
        "identity": identity,
        "l1_cognitive": {
            "plan_digest": str(cognitive_plan["plan_digest"]),
            "atomic_requirement_graph_digest": str(
                _mapping(cognitive_plan.get("atomic_requirement_graph")).get(
                    "graph_digest"
                )
                or ""
            ),
        },
        "c0_obligation_receipt_digest": str(
            c0_obligation_receipt.get("receipt_digest") or ""
        ),
        "requirement_outcomes": rows,
        "summary": {
            "requirement_count": len(rows),
            "revision_eligible_count": sum(
                1 for row in rows if row["revision_eligible"]
            ),
            "all_requirements_observed_or_escalated": True,
            "c0_remains_evidence_authority": True,
            "does_not_authorize_execution": True,
        },
    }
    receipt["receipt_digest"] = cognitive_c0_outcome_digest(receipt)
    validate_l1_cognitive_c0_outcome_receipt(
        receipt,
        cognitive_plan=cognitive_plan,
        v2_capsule=v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
    )
    return receipt


def validate_l1_cognitive_c0_outcome_receipt(
    receipt: Mapping[str, Any],
    *,
    cognitive_plan: Mapping[str, Any],
    v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
) -> None:
    """Fail closed unless outcomes exactly preserve authoritative C0 results."""

    _validated_inputs(
        cognitive_plan=cognitive_plan,
        v2_capsule=v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
    )
    if not isinstance(receipt, Mapping):
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcome receipt is invalid")
    if receipt.get("schema_version") != L1_COGNITIVE_C0_OUTCOME_SCHEMA_VERSION:
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcome receipt schema is invalid")
    if receipt.get("authority_class") != L1_COGNITIVE_C0_OUTCOME_AUTHORITY:
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcome authority is invalid")
    if receipt.get("app_scope") != L1_COGNITIVE_C0_OUTCOME_APP_SCOPE:
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcome scope is invalid")
    if receipt.get("receipt_digest") != cognitive_c0_outcome_digest(receipt):
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcome digest is invalid")
    expected = build_l1_cognitive_c0_outcome_receipt_unchecked(
        cognitive_plan=cognitive_plan,
        c0_obligation_receipt=c0_obligation_receipt,
    )
    if dict(receipt) != expected:
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcome receipt is not source-bound")


def build_l1_cognitive_c0_outcome_receipt_unchecked(
    *, cognitive_plan: Mapping[str, Any], c0_obligation_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the expected canonical receipt after all source inputs validate."""

    rows = _outcome_rows(cognitive_plan, c0_obligation_receipt)
    receipt = {
        "schema_version": L1_COGNITIVE_C0_OUTCOME_SCHEMA_VERSION,
        "authority_class": L1_COGNITIVE_C0_OUTCOME_AUTHORITY,
        "app_scope": L1_COGNITIVE_C0_OUTCOME_APP_SCOPE,
        "identity": _mapping(c0_obligation_receipt.get("identity")),
        "l1_cognitive": {
            "plan_digest": str(cognitive_plan["plan_digest"]),
            "atomic_requirement_graph_digest": str(
                _mapping(cognitive_plan.get("atomic_requirement_graph")).get(
                    "graph_digest"
                )
                or ""
            ),
        },
        "c0_obligation_receipt_digest": str(
            c0_obligation_receipt.get("receipt_digest") or ""
        ),
        "requirement_outcomes": rows,
        "summary": {
            "requirement_count": len(rows),
            "revision_eligible_count": sum(
                1 for row in rows if row["revision_eligible"]
            ),
            "all_requirements_observed_or_escalated": True,
            "c0_remains_evidence_authority": True,
            "does_not_authorize_execution": True,
        },
    }
    receipt["receipt_digest"] = cognitive_c0_outcome_digest(receipt)
    return receipt


def build_l1_cognitive_revision_from_c0_outcome(
    *,
    cognitive_plan: Mapping[str, Any],
    outcome_receipt: Mapping[str, Any],
    outcome_receipt_ref: str,
    v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one bounded L1 revision from source-bound C0 failure outcomes."""

    validate_l1_cognitive_c0_outcome_receipt(
        outcome_receipt,
        cognitive_plan=cognitive_plan,
        v2_capsule=v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
    )
    reference = str(outcome_receipt_ref or "").strip()
    if not reference or Path(reference).is_absolute() or ".." in Path(reference).parts:
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcome reference is invalid")
    if outcome_receipt.get("l1_cognitive", {}).get("plan_digest") != cognitive_plan.get(
        "plan_digest"
    ):
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcome plan binding is invalid")
    rows = outcome_receipt.get("requirement_outcomes")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise L1CognitiveC0OutcomeError("L1 v3 C0 outcomes are invalid")
    observed = [
        {
            "requirement_id": str(row["requirement_id"]),
            "code": str(row["outcome"]),
            "observation_ref": f"{reference}#{row['requirement_id']}",
        }
        for row in rows
        if isinstance(row, Mapping) and row.get("outcome") in _FAILURE_CODES
    ]
    try:
        revision = dict(
            _build_l1_cognitive_revision_from_validated_c0_outcomes(
                plan=cognitive_plan,
                observed_outcomes=observed,
                c0_outcome_receipt_digest=str(outcome_receipt["receipt_digest"]),
            )
        )
        validate_l1_cognitive_revision_v3(revision, plan=cognitive_plan)
    except L1CognitivePlanError as exc:
        raise L1CognitiveC0OutcomeError("L1 v3 cognitive revision is invalid") from exc
    return revision


def write_l1_cognitive_c0_outcome_receipt(
    *,
    output_path: Path,
    receipt: Mapping[str, Any],
    cognitive_plan: Mapping[str, Any],
    v2_capsule: Mapping[str, Any],
    c0_obligation_receipt: Mapping[str, Any],
) -> Path:
    """Validate and write a C0-owned v3 outcome receipt to one caller path."""

    validate_l1_cognitive_c0_outcome_receipt(
        receipt,
        cognitive_plan=cognitive_plan,
        v2_capsule=v2_capsule,
        c0_obligation_receipt=c0_obligation_receipt,
    )
    path = Path(output_path)
    sr.write_stage_receipt(path, receipt)
    return path


__all__ = [
    "L1CognitiveC0OutcomeError",
    "L1_COGNITIVE_C0_OUTCOME_APP_SCOPE",
    "L1_COGNITIVE_C0_OUTCOME_AUTHORITY",
    "L1_COGNITIVE_C0_OUTCOME_SCHEMA_VERSION",
    "build_l1_cognitive_c0_outcome_receipt",
    "build_l1_cognitive_revision_from_c0_outcome",
    "cognitive_c0_outcome_digest",
    "validate_l1_cognitive_c0_outcome_receipt",
    "write_l1_cognitive_c0_outcome_receipt",
]
