from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.bindings.l1_planning_capsule import (
    build_apps_rg_l1_planning_capsule,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.plan_execution_reconciliation import (
    PLAN_EXECUTION_RECONCILIATION_SCHEMA_VERSION,
    build_plan_execution_reconciliation,
    emit_plan_execution_reconciliation,
    validate_plan_execution_reconciliation,
)
from apps_rg.runtime.contracts.reasoning_control_execution_receipt import (
    build_reasoning_control_execution_receipt,
)
from apps_rg.runtime.dispatch.spine_stage_receipts import (
    FILENAME_PLAN_EXECUTION_RECEIPT,
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


def _full_resume_capsule() -> dict:
    return build_apps_rg_l1_planning_capsule(
        app_payload={
            "generation_mode": "strategic_tailor",
            "target_company": "ExampleCo",
            "target_role": "VP Product",
            "target_level": "VP",
            "source_resume_text": "Evidence-backed product experience.",
            "job_description_text": "Own product strategy and execution.",
        },
        request_id="w1-request",
        run_id="w1-run",
        trace_id="w1-trace",
        replay_key="w1-replay",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


def _execution_artifacts(root: Path, *, omit: set[str] | None = None) -> dict[str, str]:
    omit = omit or set()
    refs: dict[str, str] = {}
    for lane in _LANES:
        ref = f"modular_r4/sections/{lane}/l2_output.json"
        if lane not in omit:
            _write(root / ref)
            refs[lane] = ref
    _write(root / "modular_r4/locked_copy/locked_copy_manifest.json")
    _write(root / "modular_r4/section_provider_calls.json")
    _write(root / "runtime_execution_witness.json")
    return refs


def _witness(*, fault: str = "", executed: bool = True) -> dict:
    return {"l2": {"executed": executed, "fault": fault}}


def _control_execution_receipts(capsule: dict) -> dict[str, dict]:
    receipts: dict[str, dict] = {}
    for cognition in capsule["cognition_plan"]:
        unit_id = cognition["unit_id"]
        requested = dict(cognition["requested_controls"])
        receipts[unit_id] = build_reasoning_control_execution_receipt(
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
    return receipts


def test_w1_reconciles_each_planned_unit_to_observed_artifacts(tmp_path: Path) -> None:
    capsule = _full_resume_capsule()
    lane_refs = _execution_artifacts(tmp_path)
    control_receipts = _control_execution_receipts(capsule)

    receipt = build_plan_execution_reconciliation(
        request_id="w1-request",
        run_id="w1-run",
        plan_capsule=capsule,
        artifact_dir=tmp_path,
        execution_witness=_witness(),
        l2_result={"section_output_refs": lane_refs},
        control_execution_receipts=control_receipts,
    )

    assert receipt["emission"]["schema_version"] == PLAN_EXECUTION_RECONCILIATION_SCHEMA_VERSION
    assert receipt["emission"]["wave"] == "W1"
    assert receipt["summary"]["all_planned_units_reconciled"] is True
    assert {row["disposition"] for row in receipt["unit_outcomes"]} == {"COMPLETED"}
    observations = {row["unit_id"]: row for row in receipt["unit_observations"]}
    assert observations["experience_block"]["required_execution_lanes"] == [
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
        "ey_bullets",
        "unify_narrative",
        "ibm_narrative",
        "insurtech_narrative",
        "ey_narrative",
    ]
    assert observations["skills_block"]["requested_controls"]
    assert observations["education_block"]["artifact_refs"] == [
        "modular_r4/locked_copy/locked_copy_manifest.json"
    ]
    assert observations["headline"]["actual_attempt_refs"] == [
        "runtime_execution_witness.json",
        "modular_r4/section_provider_calls.json",
    ]
    assert observations["headline"]["quality_certification_eligible"] is True
    assert observations["headline"]["l2_l3_applied_controls"]
    assert observations["headline"]["reasoning_control_execution_receipt_ref"] == (
        "reasoning_control_execution/headline.json"
    )
    validate_plan_execution_reconciliation(receipt)


def test_w1_marks_missing_artifact_as_blocked_instead_of_silently_completing(
    tmp_path: Path,
) -> None:
    capsule = _full_resume_capsule()
    lane_refs = _execution_artifacts(tmp_path, omit={"headline"})
    control_receipts = _control_execution_receipts(capsule)

    receipt = build_plan_execution_reconciliation(
        request_id="w1-request",
        run_id="w1-run",
        plan_capsule=capsule,
        artifact_dir=tmp_path,
        execution_witness=_witness(),
        l2_result={"section_output_refs": lane_refs},
        control_execution_receipts=control_receipts,
    )

    outcomes = {row["unit_id"]: row for row in receipt["unit_outcomes"]}
    assert outcomes["headline"]["disposition"] == "BLOCKED"
    assert outcomes["headline"]["failure_code"] == "REQUIRED_PROOF_ABSENT"
    assert outcomes["headline"]["attempted"] is True
    assert outcomes["experience_block"]["disposition"] == "COMPLETED"


def test_w3_blocks_completed_output_without_required_control_execution_proof(
    tmp_path: Path,
) -> None:
    capsule = _full_resume_capsule()
    lane_refs = _execution_artifacts(tmp_path)
    (tmp_path / "l1_evidence_obligation_receipt.json").write_text(
        json.dumps(
            {
                "obligation_dispositions": [
                    {"target_unit_id": "executive_summary"},
                ]
            }
        ),
        encoding="utf-8",
    )

    receipt = build_plan_execution_reconciliation(
        request_id="w1-request",
        run_id="w1-run",
        plan_capsule=capsule,
        artifact_dir=tmp_path,
        execution_witness=_witness(),
        l2_result={"section_output_refs": lane_refs},
    )

    outcomes = {row["unit_id"]: row for row in receipt["unit_outcomes"]}
    assert outcomes["executive_summary"]["disposition"] == "BLOCKED"
    assert outcomes["executive_summary"]["failure_code"] == (
        "REQUIRED_CONTROL_EXECUTION_ABSENT"
    )
    summary = {row["unit_id"]: row for row in receipt["unit_observations"]}[
        "executive_summary"
    ]
    assert summary["quality_certification_eligible"] is False
    assert (
        "tot_branches"
        in summary["reasoning_control_execution_receipt"]["quality_certification"][
            "required_control_failures"
        ]
    )
    assert summary["c0_obligation_receipt_refs"] == [
        "l1_evidence_obligation_receipt.json"
    ]


def test_w1_pre_execution_termination_is_exhaustive_and_emits_receipt(
    tmp_path: Path,
) -> None:
    capsule = _full_resume_capsule()
    _write(tmp_path / "runtime_execution_witness.json")

    path = emit_plan_execution_reconciliation(
        request_id="w1-request",
        run_id="w1-run",
        plan_capsule=capsule,
        artifact_dir=tmp_path,
        execution_witness=_witness(executed=False),
        terminal_reason="E2E_FRESH_RUN_REQUIRES_CACHE_MISS",
    )

    assert path == tmp_path / FILENAME_PLAN_EXECUTION_RECEIPT
    assert (tmp_path / "reasoning_control_execution/headline.json").is_file()
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["emission"]["terminal_reason"] == "E2E_FRESH_RUN_REQUIRES_CACHE_MISS"
    assert {row["disposition"] for row in persisted["unit_outcomes"]} == {"SKIPPED"}
    assert {row["failure_code"] for row in persisted["unit_outcomes"]} == {"POLICY_BLOCKED"}
    validate_plan_execution_reconciliation(persisted)


def test_w1_blocked_l1_plan_is_recorded_without_an_execution_attempt(tmp_path: Path) -> None:
    capsule = build_apps_rg_l1_planning_capsule(
        app_payload={
            "generation_mode": "strategic_tailor",
            "target_company": "ExampleCo",
            "target_role": "VP Product",
            "source_resume_text": "Evidence-backed product experience.",
        },
        request_id="w1-request",
        run_id="w1-run",
        trace_id="w1-trace",
        replay_key="w1-replay",
        planning_profile_ref=l1_planning_profile_ref(),
        planning_profile_digest=l1_planning_profile_digest(allow_missing=False),
    )

    receipt = build_plan_execution_reconciliation(
        request_id="w1-request",
        run_id="w1-run",
        plan_capsule=capsule,
        artifact_dir=tmp_path,
    )

    assert capsule["planning_status"] == "BLOCKED"
    assert {row["disposition"] for row in receipt["unit_outcomes"]} == {"BLOCKED"}
    assert {row["failure_code"] for row in receipt["unit_outcomes"]} == {"L1_PLAN_BLOCKED"}
    assert {row["attempted"] for row in receipt["unit_outcomes"]} == {False}


def test_w1_l2_fault_is_recorded_as_generation_failure_when_no_output_is_observed(
    tmp_path: Path,
) -> None:
    capsule = _full_resume_capsule()
    _write(tmp_path / "runtime_execution_witness.json")

    receipt = build_plan_execution_reconciliation(
        request_id="w1-request",
        run_id="w1-run",
        plan_capsule=capsule,
        artifact_dir=tmp_path,
        execution_witness=_witness(fault="L2_EXECUTION_ERROR:RuntimeError:boom"),
    )

    assert {row["disposition"] for row in receipt["unit_outcomes"]} == {"FAILED"}
    assert {row["failure_code"] for row in receipt["unit_outcomes"]} == {"GENERATION_FAILED"}
