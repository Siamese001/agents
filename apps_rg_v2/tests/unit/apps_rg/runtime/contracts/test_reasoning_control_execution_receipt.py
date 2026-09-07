"""Contract tests for L2/L3-owned reasoning-control execution evidence."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.bindings.l1_planning_capsule import (
    build_apps_rg_l1_planning_capsule,
    stable_capsule_digest,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.reasoning_control_execution_receipt import (
    ReasoningControlExecutionReceiptError,
    build_reasoning_control_execution_receipt,
    l2_observations_from_lane_records,
    validate_reasoning_control_execution_receipt,
    write_reasoning_control_execution_receipt,
)


def _capsule() -> dict[str, Any]:
    return build_apps_rg_l1_planning_capsule(
        app_payload={
            "generation_mode": "strategic_tailor",
            "target_company": "ExampleCo",
            "target_role": "VP Product",
            "target_level": "VP",
            "source_resume_text": "Evidence-backed product experience.",
            "job_description_text": "Own product strategy and execution.",
        },
        request_id="w3-request",
        run_id="w3-run",
        trace_id="w3-trace",
        replay_key="w3-replay",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )


def _requested(capsule: dict[str, Any], unit_id: str) -> dict[str, Any]:
    row = next(row for row in capsule["cognition_plan"] if row["unit_id"] == unit_id)
    return dict(row["requested_controls"])


def _applied_controls(requested: dict[str, Any]) -> dict[str, Any]:
    return {
        name: {
            "support_status": "SUPPORTED",
            "execution_status": "APPLIED",
            "observed_value": value,
            "evidence_ref": "modular_r4/section_provider_calls.json",
            "reason_code": "L2_TEST_OBSERVED",
        }
        for name, value in requested.items()
    }


def _receipt(
    capsule: dict[str, Any],
    *,
    observed_controls: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unit_id = "executive_summary"
    requested = _requested(capsule, unit_id)
    return build_reasoning_control_execution_receipt(
        plan_capsule=capsule,
        unit_id=unit_id,
        emitter_stage="L2",
        provider_profiles=["external_claude_section_lane"],
        model_ids=["claude-test"],
        candidate_count=5,
        selection_method="L2_TEST_SELECTOR",
        execution_receipt_ref="reasoning_control_execution/executive_summary.json",
        observed_controls=observed_controls or _applied_controls(requested),
        c0_obligation_receipt_refs=["l1_evidence_obligation_receipt.json"],
    )


def test_l2_receipt_proves_applied_controls_without_changing_l1_authority() -> None:
    capsule = _capsule()
    receipt = _receipt(capsule)

    l1_row = next(
        row
        for row in capsule["cognition_plan"]
        if row["unit_id"] == "executive_summary"
    )
    assert l1_row["controls_applied"] is False
    assert l1_row["execution_provability"] == "ADVISORY_ONLY_UNTIL_L2_RECEIPT"
    assert receipt["emitter_stage"] == "L2"
    assert receipt["quality_certification"] == {
        "required_control_failures": [],
        "eligible": True,
        "denied": False,
    }
    assert set(receipt["l2_l3_applied_controls"]) == set(
        _requested(capsule, "executive_summary")
    )
    validate_reasoning_control_execution_receipt(receipt, plan_capsule=capsule)


def test_required_ignored_control_denies_quality_certification() -> None:
    capsule = _capsule()
    controls = _applied_controls(_requested(capsule, "executive_summary"))
    controls["tot_branches"] = {
        "support_status": "UNSUPPORTED",
        "execution_status": "IGNORED",
        "observed_value": None,
        "evidence_ref": "modular_r4/section_provider_calls.json",
        "reason_code": "L2_TRANSPORT_HAS_NO_TOT_OBSERVATION",
    }

    receipt = _receipt(capsule, observed_controls=controls)

    assert receipt["quality_certification"] == {
        "required_control_failures": ["tot_branches"],
        "eligible": False,
        "denied": True,
    }
    assert "tot_branches" not in receipt["l2_l3_applied_controls"]


def test_l1_cannot_lower_the_fixed_control_certification_policy() -> None:
    capsule = json.loads(json.dumps(_capsule()))
    cognition = next(
        row
        for row in capsule["cognition_plan"]
        if row["unit_id"] == "executive_summary"
    )
    cognition["control_semantics"]["tot_branches"]["required_for_certification"] = (
        False
    )
    capsule["capsule_digest"] = stable_capsule_digest(capsule)

    with pytest.raises(
        ReasoningControlExecutionReceiptError,
        match="fixed certification policy",
    ):
        _receipt(capsule)


def test_receipt_rejects_missing_or_falsely_applied_controls() -> None:
    capsule = _capsule()
    controls = _applied_controls(_requested(capsule, "executive_summary"))
    controls.pop("reflexion_loops")
    with pytest.raises(
        ReasoningControlExecutionReceiptError, match="cover requested controls exactly"
    ):
        _receipt(capsule, observed_controls=controls)

    false_applied = _applied_controls(_requested(capsule, "executive_summary"))
    false_applied["self_consistency_samples"]["observed_value"] = 1
    with pytest.raises(
        ReasoningControlExecutionReceiptError, match="must equal its requested value"
    ):
        _receipt(capsule, observed_controls=false_applied)


def test_l2_lane_adapter_keeps_unobserved_tot_and_reflection_honest() -> None:
    capsule = _capsule()
    requested = _requested(capsule, "executive_summary")
    observation = l2_observations_from_lane_records(
        requested_controls=requested,
        lane_records=(
            {
                "provider_call_attempted": True,
                "provider_profile": "external_claude_section_lane",
                "model_id": "claude-test",
                "temperature": requested["temperature"],
                "self_consistency_executed": int(requested["self_consistency_samples"]),
            },
        ),
        lane_record_ref="modular_r4/section_provider_calls.json",
    )
    receipt = _receipt(capsule, observed_controls=observation["observed_controls"])

    rows = {row["control_name"]: row for row in receipt["control_observations"]}
    assert rows["temperature"]["execution_status"] == "APPLIED"
    assert rows["self_consistency_samples"]["execution_status"] == "ADAPTED"
    assert rows["tot_branches"]["execution_status"] == "IGNORED"
    assert rows["reflexion_loops"]["execution_status"] == "IGNORED"
    assert receipt["quality_certification"]["denied"] is True


def test_receipt_writer_and_validator_reject_tampering(tmp_path: Path) -> None:
    capsule = _capsule()
    receipt = _receipt(capsule)
    path = write_reasoning_control_execution_receipt(
        output_path=tmp_path / "reasoning_control_execution" / "executive_summary.json",
        receipt=receipt,
        plan_capsule=capsule,
    )

    assert path.is_file()
    tampered = copy.deepcopy(receipt)
    tampered["emitter_stage"] = "L1"
    with pytest.raises(ReasoningControlExecutionReceiptError, match="emitter_stage"):
        validate_reasoning_control_execution_receipt(tampered, plan_capsule=capsule)
