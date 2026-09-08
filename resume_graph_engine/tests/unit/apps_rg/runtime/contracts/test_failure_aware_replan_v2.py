"""W5 receipt-bound failure diagnostics and bounded advisory replans."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.bindings.l1_planning_capsule import (
    build_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    build_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.failure_aware_replan import (
    FAILURE_AWARE_REPLAN_V2_SCHEMA_VERSION,
    PLAN_EXECUTION_FAILURE_DIAGNOSTIC_SCHEMA_VERSION,
    FailureAwareReplanError,
    build_failure_aware_replan_v2,
    build_plan_execution_failure_diagnostic,
    emit_failure_aware_replan_v2,
    failure_aware_replan_v2_digest,
    validate_failure_aware_replan_v2,
    validate_plan_execution_failure_diagnostic,
)
from apps_rg.runtime.contracts.governed_l3_schedule import (
    build_governed_l3_schedule_receipt,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    build_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    build_plan_execution_reconciliation,
)
from apps_rg.runtime.contracts.plan_execution_receipt import load_failure_taxonomy
from apps_rg.runtime.dispatch.spine_stage_receipts import (
    FILENAME_FAILURE_AWARE_REPLAN_V2,
    FILENAME_PLAN_EXECUTION_FAILURE_DIAGNOSTIC,
)


def _payload(*, include_jd: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generation_mode": "strategic_tailor",
        "target_company": "ExampleCo",
        "target_role": "VP Product",
        "target_level": "VP",
        "source_resume_text": "Evidence-backed product experience.",
    }
    if include_jd:
        payload["job_description_text"] = (
            "Requirements\n"
            "- Must lead product strategy.\n"
            "- Must own product execution."
        )
    return payload


def _capsules(*, include_jd: bool = True) -> tuple[dict[str, Any], dict[str, Any]]:
    kwargs = {
        "app_payload": _payload(include_jd=include_jd),
        "request_id": "w5-request",
        "run_id": "w5-run",
        "trace_id": "w5-trace",
        "replay_key": "w5-replay",
        "planning_profile_ref": l1_planning_profile_ref(),
        "planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
    }
    return (
        build_apps_rg_l1_planning_capsule(**kwargs),
        build_apps_rg_l1_planning_capsule_v2(**kwargs),
    )


def _source_receipts(
    root: Path, *, include_jd: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    v1, v2 = _capsules(include_jd=include_jd)
    c0 = build_l1_evidence_obligation_receipt(
        capsule=v2,
        request_id="w5-request",
        run_id="w5-run",
        trace_id="w5-trace",
        final_evidence_digest="sha256:" + "c" * 64,
        evidence_items=(),
    )
    w1 = build_plan_execution_reconciliation(
        request_id="w5-request",
        run_id="w5-run",
        plan_capsule=v1,
        artifact_dir=root,
        execution_witness={
            "l2": {
                "executed": include_jd,
                "fault": "PROVIDER_TIMEOUT: upstream unavailable" if include_jd else "",
            }
        },
    )
    l3 = build_governed_l3_schedule_receipt(
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        c0_obligation_receipt_ref="l1_evidence_obligation_receipt.json",
        plan_execution_reconciliation=w1,
        plan_execution_reconciliation_ref="plan_execution_receipt.json",
    )
    return v1, v2, c0, w1, l3


def _diagnostic(
    root: Path, *, include_jd: bool = True
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    _v1, v2, c0, w1, l3 = _source_receipts(root, include_jd=include_jd)
    diagnostic = build_plan_execution_failure_diagnostic(
        l1_v2_capsule=v2,
        parent_plan_ref="l1_planning_capsule_v2.json",
        c0_obligation_receipt=c0,
        c0_obligation_receipt_ref="l1_evidence_obligation_receipt.json",
        plan_execution_reconciliation=w1,
        plan_execution_reconciliation_ref="plan_execution_receipt.json",
        governed_l3_schedule=l3,
        governed_l3_schedule_ref="governed_l3_schedule_receipt.json",
    )
    return v2, c0, w1, l3, diagnostic


def test_w5_diagnostic_receipt_cites_observed_causes_and_bounds_delta_to_requirements(
    tmp_path: Path,
) -> None:
    v2, c0, w1, l3, diagnostic = _diagnostic(tmp_path)

    assert diagnostic["schema_version"] == PLAN_EXECUTION_FAILURE_DIAGNOSTIC_SCHEMA_VERSION
    codes = {row["code"] for row in diagnostic["diagnostics"]}
    assert {
        "C0_OBLIGATION_RECEIPT_UNBOUND",
        "C0_OBLIGATION_UNRESOLVED",
        "REQUIRED_CONTROL_EXECUTION_ABSENT",
        "PROVIDER_OR_TRANSPORT_FAULT",
        "GRAPH_PREDECESSOR_UNMET",
    } <= codes
    assert all(row["receipt_refs"] for row in diagnostic["diagnostics"])
    validate_plan_execution_failure_diagnostic(
        diagnostic,
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        plan_execution_reconciliation=w1,
        governed_l3_schedule=l3,
    )

    decision = build_failure_aware_replan_v2(
        l1_v2_capsule=v2,
        parent_plan_ref="l1_planning_capsule_v2.json",
        diagnostic_receipt=diagnostic,
        diagnostic_receipt_ref="plan_execution_failure_diagnostic.json",
    )

    expected_requirement_ids = {
        row["requirement_id"] for row in v2["requirements"] if row["target_unit_ids"]
    }
    assert decision["schema_version"] == FAILURE_AWARE_REPLAN_V2_SCHEMA_VERSION
    assert decision["replan_status"] == "REPLAN_PROPOSED"
    assert decision["replan_delta"]["schema_version"] == "apps_rg.l1_replan_delta.v2"
    assert all(
        set(action["affected_requirement_ids"]) <= expected_requirement_ids
        and action["affected_requirement_ids"]
        for action in decision["replan_actions"]
    )
    assert all(action["automatic_execution"] is False for action in decision["replan_actions"])
    assert decision["authority_assertions"]["does_not_select_retries"] is True
    validate_failure_aware_replan_v2(
        decision,
        l1_v2_capsule=v2,
        diagnostic_receipt=diagnostic,
    )


def test_w5_unchanged_diagnostic_escalates_instead_of_creating_a_retry_loop(
    tmp_path: Path,
) -> None:
    v2, _c0, _w1, _l3, diagnostic = _diagnostic(tmp_path)
    first = build_failure_aware_replan_v2(
        l1_v2_capsule=v2,
        parent_plan_ref="l1_planning_capsule_v2.json",
        diagnostic_receipt=diagnostic,
        diagnostic_receipt_ref="plan_execution_failure_diagnostic.json",
    )

    repeated = build_failure_aware_replan_v2(
        l1_v2_capsule=v2,
        parent_plan_ref="l1_planning_capsule_v2.json",
        diagnostic_receipt=diagnostic,
        diagnostic_receipt_ref="plan_execution_failure_diagnostic.json",
        prior_replan_decisions=[first],
    )

    assert repeated["replan_status"] == "ESCALATED_UNCHANGED_DIAGNOSTIC"
    assert repeated["replan_actions"] == []
    assert repeated["replan_delta"] is None
    assert "UNCHANGED_DIAGNOSTIC_FINGERPRINT" in {
        row["reason_code"] for row in repeated["escalation"]
    }
    validate_failure_aware_replan_v2(
        repeated,
        l1_v2_capsule=v2,
        diagnostic_receipt=diagnostic,
        prior_replan_decisions=[first],
    )


def test_w5_records_u0_uncertainty_without_unscoped_auto_replan(tmp_path: Path) -> None:
    v2, _c0, _w1, _l3, diagnostic = _diagnostic(tmp_path, include_jd=False)
    uncertainty = next(
        row for row in diagnostic["diagnostics"] if row["code"] == "U0_UNCERTAINTY_OPEN"
    )

    assert uncertainty["observed_facts"]["u0_uncertainty_id"].startswith("u0dec-")
    assert uncertainty["designated_resolver"] == "U0"
    decision = build_failure_aware_replan_v2(
        l1_v2_capsule=v2,
        parent_plan_ref="l1_planning_capsule_v2.json",
        diagnostic_receipt=diagnostic,
        diagnostic_receipt_ref="plan_execution_failure_diagnostic.json",
    )
    assert decision["replan_status"] == "ESCALATED_NO_NEW_EVIDENCE_OR_INPUT"
    assert decision["replan_actions"] == []
    assert decision["replan_delta"] is None
    assert {row["designated_resolver"] for row in decision["escalation"]} >= {"U0"}


def test_w5_writer_and_validator_reject_a_redigested_wider_action(tmp_path: Path) -> None:
    v2, c0, w1, l3, diagnostic = _diagnostic(tmp_path)
    decision = build_failure_aware_replan_v2(
        l1_v2_capsule=v2,
        parent_plan_ref="l1_planning_capsule_v2.json",
        diagnostic_receipt=diagnostic,
        diagnostic_receipt_ref="plan_execution_failure_diagnostic.json",
    )
    diagnostic_path, decision_path = emit_failure_aware_replan_v2(
        artifact_dir=tmp_path,
        l1_v2_capsule=v2,
        parent_plan_ref="l1_planning_capsule_v2.json",
        c0_obligation_receipt=c0,
        c0_obligation_receipt_ref="l1_evidence_obligation_receipt.json",
        plan_execution_reconciliation=w1,
        plan_execution_reconciliation_ref="plan_execution_receipt.json",
        governed_l3_schedule=l3,
        governed_l3_schedule_ref="governed_l3_schedule_receipt.json",
    )

    assert diagnostic_path == tmp_path / FILENAME_PLAN_EXECUTION_FAILURE_DIAGNOSTIC
    assert decision_path == tmp_path / FILENAME_FAILURE_AWARE_REPLAN_V2
    assert json.loads(diagnostic_path.read_text(encoding="utf-8"))["receipt_digest"] == diagnostic[
        "receipt_digest"
    ]
    assert json.loads(decision_path.read_text(encoding="utf-8"))["decision_digest"] == decision[
        "decision_digest"
    ]
    tampered = copy.deepcopy(decision)
    tampered["replan_actions"][0]["affected_requirement_ids"] = ["l1req-unplanned"]
    tampered["decision_digest"] = failure_aware_replan_v2_digest(tampered)
    with pytest.raises(FailureAwareReplanError, match="does not match"):
        validate_failure_aware_replan_v2(
            tampered,
            l1_v2_capsule=v2,
            diagnostic_receipt=diagnostic,
        )


def test_w5_taxonomy_declares_a_bounded_diagnostic_policy() -> None:
    policy = load_failure_taxonomy()["w5_diagnostic_policy"]

    assert policy["max_advisory_revision_depth"] == 2
    assert policy["repeated_diagnostic_disposition"] == "ESCALATE_TO_DESIGNATED_RESOLVER"
    assert policy["diagnostic_codes"]["PROVIDER_OR_TRANSPORT_FAULT"]["actionable"] is True
