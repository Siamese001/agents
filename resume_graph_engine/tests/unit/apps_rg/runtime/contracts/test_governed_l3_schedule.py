"""W4 tests for receipt-bound apps_rg L3 scheduling and merge checks."""

from __future__ import annotations

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
from apps_rg.runtime.bindings.l3_binding import l3_schedule_apps_rg
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.governed_l3_schedule import (
    GovernedL3ScheduleError,
    build_governed_l3_schedule_receipt,
    emit_governed_l3_schedule_receipt,
    receipt_digest,
    validate_governed_l3_schedule_receipt,
    write_governed_l3_schedule_receipt,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    build_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    build_plan_execution_reconciliation,
)
from apps_rg.runtime.contracts.reasoning_control_execution_receipt import (
    build_reasoning_control_execution_receipt,
)


_LANES = (
    "headline",
    "executive_summary",
    "competencies",
    "unify_bullets",
    "ibm_bullets",
    "insurtech_bullets",
    "ey_bullets",
    "unify_narrative",
    "ibm_narrative",
    "insurtech_narrative",
    "ey_narrative",
)


def _payload() -> dict[str, Any]:
    return {
        "generation_mode": "strategic_tailor",
        "target_company": "ExampleCo",
        "target_role": "VP Product",
        "target_level": "VP",
        "source_resume_text": "Evidence-backed product experience.",
        "job_description_text": "Requirements\n- Must lead product strategy.",
    }


def _capsules() -> tuple[dict[str, Any], dict[str, Any]]:
    kwargs = {
        "app_payload": _payload(),
        "request_id": "w4-request",
        "run_id": "w4-run",
        "trace_id": "w4-trace",
        "replay_key": "w4-replay",
        "planning_profile_ref": l1_planning_profile_ref(),
        "planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
    }
    return (
        build_apps_rg_l1_planning_capsule(**kwargs),
        build_apps_rg_l1_planning_capsule_v2(**kwargs),
    )


def _c0_receipt(capsule: dict[str, Any]) -> dict[str, Any]:
    return build_l1_evidence_obligation_receipt(
        capsule=capsule,
        request_id="w4-request",
        run_id="w4-run",
        trace_id="w4-trace",
        final_evidence_digest="sha256:" + "c" * 64,
        evidence_items=(),
    )


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def _completed_w1(
    root: Path, capsule: dict[str, Any], *, prove_controls: bool
) -> dict[str, Any]:
    lane_refs: dict[str, str] = {}
    for lane in _LANES:
        ref = f"modular_r4/sections/{lane}/l2_output.json"
        _write(root / ref)
        lane_refs[lane] = ref
    _write(root / "modular_r4/locked_copy/locked_copy_manifest.json")
    _write(root / "modular_r4/section_provider_calls.json")
    _write(root / "runtime_execution_witness.json")
    controls: dict[str, dict[str, Any]] | None = None
    if prove_controls:
        controls = {}
        for cognition in capsule["cognition_plan"]:
            unit_id = cognition["unit_id"]
            requested = dict(cognition["requested_controls"])
            controls[unit_id] = build_reasoning_control_execution_receipt(
                plan_capsule=capsule,
                unit_id=unit_id,
                emitter_stage="L2",
                provider_profiles=["test_l2_lane"],
                model_ids=["test-model"],
                candidate_count=1,
                selection_method="TEST_L2_SELECTOR",
                execution_receipt_ref=f"reasoning_control_execution/{unit_id}.json",
                observed_controls={
                    name: {
                        "support_status": "SUPPORTED",
                        "execution_status": "APPLIED",
                        "observed_value": value,
                        "evidence_ref": "modular_r4/section_provider_calls.json",
                        "reason_code": "TEST_L2_OBSERVED",
                    }
                    for name, value in requested.items()
                },
            )
    return build_plan_execution_reconciliation(
        request_id="w4-request",
        run_id="w4-run",
        plan_capsule=capsule,
        artifact_dir=root,
        execution_witness={"l2": {"executed": True, "fault": ""}},
        l2_result={"section_output_refs": lane_refs},
        control_execution_receipts=controls,
    )


def _entry_by_node(receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["node_id"]: row for row in receipt["schedule"]["entries"]}


def test_l3_selects_only_ready_work_units_from_the_advisory_graph() -> None:
    _v1, v2 = _capsules()
    c0 = _c0_receipt(v2)

    receipt = build_governed_l3_schedule_receipt(
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        c0_obligation_receipt_ref="l1_evidence_obligation_receipt.json",
    )

    work_nodes = {
        row["node_id"]
        for row in receipt["schedule"]["entries"]
        if row["node_type"] == "WORK_UNIT"
    }
    entries = _entry_by_node(receipt)
    assert set(receipt["schedule"]["selected_node_ids"]) == work_nodes
    assert entries["merge:final_resume"]["disposition"] == "DEFERRED"
    assert all(
        row["disposition"] == "DEFERRED"
        for row in receipt["schedule"]["entries"]
        if row["node_type"] == "VALIDATION"
    )
    assert receipt["l3_policy"]["l1_supplies_graph_but_not_execution_order"] is True
    assert receipt["authority_assertions"]["l3_chose_execution_order"] is True
    assert receipt["schedule"]["parallel_batches"] == [
        [node_id] for node_id in receipt["schedule"]["selected_node_ids"]
    ]


def test_l3_allows_merge_only_after_w1_and_w3_prove_every_predecessor(
    tmp_path: Path,
) -> None:
    v1, v2 = _capsules()
    c0 = _c0_receipt(v2)
    w1 = _completed_w1(tmp_path, v1, prove_controls=True)

    receipt = l3_schedule_apps_rg(
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        c0_obligation_receipt_ref="l1_evidence_obligation_receipt.json",
        plan_execution_reconciliation=w1,
        plan_execution_reconciliation_ref="plan_execution_receipt.json",
    )

    entries = _entry_by_node(receipt)
    assert entries["merge:final_resume"]["disposition"] == "SELECTED"
    assert receipt["schedule"]["selected_node_ids"] == ["merge:final_resume"]
    assert receipt["merge_check"]["status"] == "SELECTED"
    assert len(receipt["merge_check"]["required_validation_node_ids"]) == len(
        v2["work_unit_ids"]
    )
    assert len(receipt["merge_check"]["control_receipt_refs"]) == len(
        v2["work_unit_ids"]
    )
    validate_governed_l3_schedule_receipt(
        receipt,
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        plan_execution_reconciliation=w1,
    )
    path = write_governed_l3_schedule_receipt(
        output_path=tmp_path / "governed_l3_schedule_receipt.json",
        receipt=receipt,
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        plan_execution_reconciliation=w1,
    )
    persisted = json.loads(path.read_text(encoding="utf-8"))
    validate_governed_l3_schedule_receipt(
        persisted,
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        plan_execution_reconciliation=w1,
    )
    emitted = emit_governed_l3_schedule_receipt(
        artifact_dir=tmp_path,
        receipt=receipt,
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        plan_execution_reconciliation=w1,
    )
    assert emitted == tmp_path / "governed_l3_schedule_receipt.json"


def test_l3_blocks_merge_when_w3_control_proof_is_absent(tmp_path: Path) -> None:
    v1, v2 = _capsules()
    c0 = _c0_receipt(v2)
    w1 = _completed_w1(tmp_path, v1, prove_controls=False)

    receipt = build_governed_l3_schedule_receipt(
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        c0_obligation_receipt_ref="l1_evidence_obligation_receipt.json",
        plan_execution_reconciliation=w1,
        plan_execution_reconciliation_ref="plan_execution_receipt.json",
    )

    assert receipt["merge_check"]["status"] == "BLOCKED"
    assert "merge:final_resume" not in receipt["schedule"]["selected_node_ids"]


def test_l3_rejects_path_escape_and_tampered_schedule() -> None:
    _v1, v2 = _capsules()
    c0 = _c0_receipt(v2)
    with pytest.raises(GovernedL3ScheduleError, match="relative artifact"):
        build_governed_l3_schedule_receipt(
            l1_v2_capsule=v2,
            c0_obligation_receipt=c0,
            c0_obligation_receipt_ref="../l1_evidence_obligation_receipt.json",
        )

    receipt = build_governed_l3_schedule_receipt(
        l1_v2_capsule=v2,
        c0_obligation_receipt=c0,
        c0_obligation_receipt_ref="l1_evidence_obligation_receipt.json",
    )
    receipt["schedule"]["selected_node_ids"] = []
    receipt["receipt_digest"] = receipt_digest(receipt)
    with pytest.raises(GovernedL3ScheduleError, match="does not reconcile"):
        validate_governed_l3_schedule_receipt(
            receipt,
            l1_v2_capsule=v2,
            c0_obligation_receipt=c0,
        )
