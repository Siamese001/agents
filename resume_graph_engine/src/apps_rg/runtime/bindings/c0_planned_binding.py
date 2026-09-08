"""Verified L1-plan boundary for apps_rg C0 retrieval.

Canonical product callers use this wrapper rather than calling the compatibility
C0 binding without an L1 plan. C0 remains the evidence authority; this module
only verifies and threads the planning support intent.
"""

from __future__ import annotations

from typing import Any

from apps_rg.runtime.spine_contracts import ValidatedRequest
from apps_rg.runtime.spine_contracts import FinalEvidenceContract
from apps_rg.runtime.spine_contracts import L1PlanContract
from apps_rg.runtime.bindings.c0_binding import C0EvidenceGapError, c0_retrieve_apps_rg
from apps_rg.runtime.bindings.l1_planning_capsule import (
    extract_verified_planning_capsule,
)
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    extract_verified_planning_capsule_v2,
)
from apps_rg.runtime.bindings.l1_cognitive_consumption import (
    extract_l1_cognitive_plan,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    build_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.contracts.l1_cognitive_c0_outcome_receipt import (
    build_l1_cognitive_c0_outcome_receipt,
)


def c0_retrieve_apps_rg_planned(
    route: Any,
    validated_request: ValidatedRequest,
    *,
    l1_plan: L1PlanContract,
    **kwargs: Any,
) -> FinalEvidenceContract:
    """Verify L1 integrity, execute C0, and require capsule lineage on the FEC."""

    if not isinstance(l1_plan, L1PlanContract):
        raise TypeError(
            "c0_retrieve_apps_rg_planned requires an L1PlanContract; "
            f"got {type(l1_plan).__name__}"
        )
    capsule, _verification = extract_verified_planning_capsule(l1_plan, required=True)
    fec = c0_retrieve_apps_rg(
        route,
        validated_request,
        l1_plan=l1_plan,
        **kwargs,
    )
    capsule_digest = str(capsule.get("capsule_digest") or "")
    retrieval_plan_ref = str(getattr(fec, "retrieval_plan_ref", "") or "")
    audit_refs = tuple(str(ref) for ref in (getattr(fec, "audit_refs", None) or ()))
    if not retrieval_plan_ref or capsule_digest[:24] not in retrieval_plan_ref:
        raise C0EvidenceGapError(
            "C0 completed without binding FinalEvidenceContract.retrieval_plan_ref "
            "to the verified L1 planning capsule"
        )
    if not any(
        ref.startswith("l1_capsule_digest:") and capsule_digest[:24] in ref
        for ref in audit_refs
    ):
        raise C0EvidenceGapError(
            "C0 completed without an L1 capsule audit reference on FinalEvidenceContract"
        )
    v2_capsule, _v2_verification = extract_verified_planning_capsule_v2(
        l1_plan, required=False
    )
    if v2_capsule:
        obligation_receipt = build_l1_evidence_obligation_receipt(
            capsule=v2_capsule,
            request_id=str(getattr(fec, "request_id", "") or ""),
            run_id=str(getattr(fec, "run_id", "") or ""),
            trace_id=str(getattr(fec, "trace_id", "") or ""),
            final_evidence_digest=str(getattr(fec, "final_evidence_digest", "") or ""),
            evidence_items=tuple(getattr(fec, "evidence_items", None) or ()),
        )
        ledger_digest = str(v2_capsule["evidence_obligation_ledger"]["ledger_digest"])
        if "l1_v2_evidence_obligation_ledger:" + ledger_digest not in audit_refs:
            raise C0EvidenceGapError(
                "C0 completed without the verified L1 v2 evidence-obligation ledger audit reference"
            )
        if (
            "l1_evidence_obligation_receipt_digest:"
            + str(obligation_receipt["receipt_digest"])
            not in audit_refs
        ):
            raise C0EvidenceGapError(
                "C0 completed without exact L1 v2 evidence-obligation reconciliation"
            )
        cognitive_plan = extract_l1_cognitive_plan(l1_plan, required=False)
        if cognitive_plan is not None:
            cognitive_outcome = build_l1_cognitive_c0_outcome_receipt(
                cognitive_plan=cognitive_plan,
                v2_capsule=v2_capsule,
                c0_obligation_receipt=obligation_receipt,
            )
            if (
                "l1_cognitive_c0_outcome_receipt_digest:"
                + str(cognitive_outcome["receipt_digest"])
                not in audit_refs
            ):
                raise C0EvidenceGapError(
                    "C0 completed without exact L1 v3 cognitive outcome reconciliation"
                )
    return fec


__all__ = ["c0_retrieve_apps_rg_planned"]
