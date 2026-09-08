"""Bounded L2 projection for the assembled product artifact.

Lane ``l2_output.json`` files are complete execution evidence and remain authoritative on disk.
The final resume needs the materialized content, claim/evidence bindings, and graph allocation
identity, but it must not duplicate megabytes of traversal diagnostics from every lane.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


L2_SNAPSHOT_PROJECTION_SCHEMA = "apps_rg.final_resume_l2_projection.v1"

# These selected-fact-plan fields are diagnostic exhaust.  They stay in the source L2 and its
# digest-bound lane artifacts; omitting them from the product projection does not remove evidence
# authority or change any selected fact, graph id, claim, allocation, or materialized output.
VERBOSE_SELECTED_FACT_PLAN_KEYS: frozenset[str] = frozenset(
    {
        "allocation_source_traversal_evidence",
        "graph_candidate_decision_ledger",
        "graph_traversal_receipt",
        "graph_evidence_depth_comparison_report",
        "graph_evidence_depth_post_report",
        "graph_evidence_depth_pre_report",
        "graph_evidence_depth_report",
        "skew_diagnostics",
    }
)


def project_l2_output_for_final_resume(
    l2_output: dict[str, Any],
    *,
    graph_claim_binding_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the deterministic product projection of an authoritative lane L2 document.

    Lane L2 stores only the graph-binding digest/ref envelope.  When that
    envelope is active, the final product projection must hydrate the exact
    rows from the digest-bound sidecar.  Missing or mismatched sidecars fail
    closed here instead of producing an evidence-empty final snapshot.
    """

    projected = dict(l2_output)
    if l2_output.get("resume_graph_claim_binding_active") is True:
        contract = graph_claim_binding_contract
        if not isinstance(contract, Mapping):
            raise ValueError("active graph claim binding sidecar missing")
        expected_digest = str(
            l2_output.get("graph_claim_binding_contract_digest") or ""
        ).strip()
        observed_digest = str(contract.get("contract_digest") or "").strip()
        if not expected_digest or observed_digest != expected_digest:
            raise ValueError("graph claim binding sidecar digest mismatch")
        if contract.get("active") is not True:
            raise ValueError("graph claim binding sidecar is not active")
        if bool(contract.get("pass")) != bool(
            l2_output.get("resume_graph_claim_binding_pass")
        ):
            raise ValueError("graph claim binding sidecar pass mismatch")
        bindings = contract.get("bindings")
        if not isinstance(bindings, list):
            raise ValueError("graph claim binding sidecar rows missing")
        projected["graph_claim_bindings"] = [
            dict(row) for row in bindings if isinstance(row, Mapping)
        ]
    plan = l2_output.get("selected_fact_plan")
    if isinstance(plan, dict):
        projected["selected_fact_plan"] = {
            key: value
            for key, value in plan.items()
            if key not in VERBOSE_SELECTED_FACT_PLAN_KEYS
        }
    return projected


def omitted_l2_projection_paths(l2_output: dict[str, Any]) -> list[str]:
    """List diagnostic paths omitted from the projection, for explicit assembly telemetry."""

    plan = l2_output.get("selected_fact_plan")
    if not isinstance(plan, dict):
        return []
    return [
        f"selected_fact_plan.{key}"
        for key in sorted(VERBOSE_SELECTED_FACT_PLAN_KEYS)
        if key in plan
    ]


__all__ = [
    "L2_SNAPSHOT_PROJECTION_SCHEMA",
    "VERBOSE_SELECTED_FACT_PLAN_KEYS",
    "omitted_l2_projection_paths",
    "project_l2_output_for_final_resume",
]
