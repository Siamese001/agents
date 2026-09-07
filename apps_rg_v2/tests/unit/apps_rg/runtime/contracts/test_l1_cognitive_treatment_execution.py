"""Tests for Apps RG-local observed v2/v3 treatment receipts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from apps_rg.runtime.bindings.l1_cognitive_consumption import (
    build_l1_cognitive_consumer_advisory,
    build_l1_cognitive_revision_advisory,
    cognitive_revision_gap_requirements,
)
from apps_rg.runtime.bindings.l1_cognitive_planner_v3 import (
    build_l1_cognitive_plan_v3,
)
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1_COGNITIVE_V3_CANDIDATE_ARM,
    build_l1_cognitive_treatment,
)
from apps_rg.runtime.bindings.l1_planning_capsule_v2 import (
    build_apps_rg_l1_planning_capsule_v2,
)
from apps_rg.runtime.bindings.u0_profile_manifest import (
    l1_planning_profile_digest,
    l1_planning_profile_ref,
)
from apps_rg.runtime.contracts.l1_cognitive_c0_outcome_receipt import (
    build_l1_cognitive_c0_outcome_receipt,
    build_l1_cognitive_revision_from_c0_outcome,
)
from apps_rg.runtime.contracts.l1_cognitive_output_disposition import (
    L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT,
    L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT,
    apply_l1_cognitive_output_disposition_to_x3_mirror,
    apply_l1_cognitive_output_projection,
    emit_l1_cognitive_output_disposition,
    l1_cognitive_output_projection_digest,
)
from apps_rg.runtime.contracts.l1_cognitive_treatment_execution import (
    build_l1_cognitive_treatment_execution_receipt,
    emit_l1_cognitive_treatment_execution_receipt,
    validate_l1_cognitive_treatment_execution_receipt,
)
from apps_rg.runtime.contracts.l1_evidence_obligation_receipt import (
    build_l1_evidence_obligation_receipt,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


def _payload(
    *,
    user_constraints: dict[str, Any] | None = None,
    job_description_text: str = "Requirements\n- Must lead platform engineering.",
) -> dict[str, Any]:
    return {
        "target_company": "Acme",
        "target_role": "VP Engineering",
        "target_level": "EXECUTIVE",
        "job_description_text": job_description_text,
        "source_resume_text": "Led platform engineering.",
        "generation_mode": "strategic_tailor",
        "user_constraints": dict(user_constraints or {}),
    }


def _candidate_plan(
    *,
    user_constraints: dict[str, Any] | None = None,
    job_description_text: str = "Requirements\n- Must lead platform engineering.",
) -> tuple[SimpleNamespace, dict[str, Any], dict[str, Any]]:
    kwargs = {
        "app_payload": _payload(
            user_constraints=user_constraints,
            job_description_text=job_description_text,
        ),
        "request_id": "request",
        "run_id": "run",
        "trace_id": "trace",
        "replay_key": "replay",
        "planning_profile_ref": l1_planning_profile_ref(),
        "planning_profile_digest": l1_planning_profile_digest(allow_missing=False),
    }
    cognitive = dict(build_l1_cognitive_plan_v3(**kwargs))
    v2 = dict(build_apps_rg_l1_planning_capsule_v2(**kwargs))
    plan = SimpleNamespace(
        task_spec={
            "l1_cognitive_treatment": build_l1_cognitive_treatment(
                L1_COGNITIVE_V3_CANDIDATE_ARM,
                assignment_origin="U0_VALIDATED_INGRESS",
            ),
            "apps_rg_cognitive_v3_plan": cognitive,
            "apps_rg_cognitive_v3_plan_ref": cognitive["plan_digest"],
            "apps_rg_planning_v2_capsule": v2,
        }
    )
    return plan, cognitive, v2


def _write_candidate_artifacts(root: Path) -> SimpleNamespace:
    plan, cognitive, v2 = _candidate_plan()
    c0 = build_l1_evidence_obligation_receipt(
        capsule=v2,
        request_id="request",
        run_id="run",
        trace_id="trace",
        final_evidence_digest="sha256:" + "a" * 64,
        evidence_items=(),
    )
    outcome = build_l1_cognitive_c0_outcome_receipt(
        cognitive_plan=cognitive,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )
    revision = build_l1_cognitive_revision_from_c0_outcome(
        cognitive_plan=cognitive,
        outcome_receipt=outcome,
        outcome_receipt_ref=sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT,
        v2_capsule=v2,
        c0_obligation_receipt=c0,
    )
    advisory = build_l1_cognitive_consumer_advisory(plan)
    revision_advisory = build_l1_cognitive_revision_advisory(
        cognitive_plan=cognitive,
        revision=revision,
        c0_outcome_receipt_digest=outcome["receipt_digest"],
    )
    assert advisory is not None
    for filename, data in (
        (sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT, outcome),
        (sr.FILENAME_L1_COGNITIVE_REVISION, revision),
        (sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY, revision_advisory),
    ):
        (root / filename).write_text(json.dumps(data), encoding="utf-8")
    compiled = {
        "section_id": "ibm_bullets",
        "dispatch_sha256_prompt16": "a" * 16,
        "l1_cognitive_plan_digest": cognitive["plan_digest"],
        "l1_cognitive_advisory_digest": advisory["advisory_digest"],
        "l1_cognitive_c0_outcome_receipt_digest": outcome["receipt_digest"],
        "l1_cognitive_revision_ref": sr.FILENAME_L1_COGNITIVE_REVISION,
        "l1_cognitive_revision_digest": revision["revision_digest"],
        "l1_cognitive_revision_advisory_ref": sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY,
        "l1_cognitive_revision_advisory_digest": revision_advisory["advisory_digest"],
        "l1_cognitive_revision_outcome_ref": sr.FILENAME_L1_COGNITIVE_C0_OUTCOME_RECEIPT,
    }
    (root / "compiled_prompt_artifact.json").write_text(
        json.dumps(compiled), encoding="utf-8"
    )
    gap_requirements = cognitive_revision_gap_requirements(
        revision_advisory,
        section_id="ibm_bullets",
    )
    assert len(gap_requirements) == 1
    (root / "provider_request.json").write_text(
        json.dumps({"prompt_hash": compiled["dispatch_sha256_prompt16"]}),
        encoding="utf-8",
    )
    (root / "l2_output.json").write_text(
        json.dumps(
            {
                "gap_notes": [],
                "change_log": [],
            }
        ),
        encoding="utf-8",
    )
    projection = apply_l1_cognitive_output_projection(
        artifact_dir=root,
        section_id="ibm_bullets",
        runtime_payload={"l1_cognitive_revision_advisory": revision_advisory},
    )
    assert projection["status"] == "APPLIED"
    emit_l1_cognitive_output_disposition(
        artifact_dir=root,
        section_id="ibm_bullets",
        runtime_payload={"l1_cognitive_revision_advisory": revision_advisory},
    )
    return plan


def test_candidate_receipt_proves_c0_to_pa_consumption(tmp_path: Path) -> None:
    plan = _write_candidate_artifacts(tmp_path)

    receipt = build_l1_cognitive_treatment_execution_receipt(
        run_root=tmp_path,
        l1_plan=plan,
    )

    assert receipt["status"] == "PASS"
    assert receipt["summary"]["observed_consumption_count"] == 1
    record = receipt["records"][0]
    assert record["provider_request_observation"]["observed"] is True
    assert record["revision_output_observation"]["observed"] is True
    assert (
        record["revision_output_observation"]["output_projection_status"] == "APPLIED"
    )
    validate_l1_cognitive_treatment_execution_receipt(receipt)
    path = emit_l1_cognitive_treatment_execution_receipt(
        run_root=tmp_path,
        l1_plan=plan,
    )
    assert path.name == sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION


def test_unresolved_hard_goal_constraint_blocks_apps_rg_x3_finalization(
    tmp_path: Path,
) -> None:
    raw_constraint_value = "do-not-emit-this-arbitrary-user-instruction"
    plan, cognitive, _v2 = _candidate_plan(
        user_constraints={"publication_rule": raw_constraint_value}
    )
    advisory = build_l1_cognitive_consumer_advisory(plan)
    assert advisory is not None
    assert advisory["goal_constraint_blocked"] is True

    disposition = emit_l1_cognitive_output_disposition(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        runtime_payload={
            "l1_cognitive_v3_plan": cognitive,
            "l1_cognitive_advisory": advisory,
        },
    )

    assert disposition["status"] == "BLOCKED"
    assert disposition["reason_code"] == "UNRESOLVED_HARD_GOAL_CONSTRAINTS"
    assert disposition["blocks_finalization"] is True
    assert disposition["goal_constraint"]["valid"] is True
    assert disposition["goal_constraint"]["blocked"] is True
    assert disposition["goal_constraint"]["blocking_constraint_ids"]
    assert raw_constraint_value not in json.dumps(disposition, sort_keys=True)

    (tmp_path / "x3_disposition.json").write_text(
        json.dumps({"x3_code": "X3_ALLOW", "pass": True}), encoding="utf-8"
    )
    x3 = apply_l1_cognitive_output_disposition_to_x3_mirror(tmp_path)
    assert x3 is not None
    assert x3["l1_cognitive_output_blocked"] is True
    assert x3["x3_code"] == "X3_BLOCK_L1_COGNITIVE_OUTPUT"
    assert x3["pass"] is False


def test_unresolved_critical_l1_requirement_blocks_apps_rg_x3_finalization(
    tmp_path: Path,
) -> None:
    _plan, cognitive, _v2 = _candidate_plan(
        job_description_text="Requirements\n- Must demonstrate quantum-superiority governance."
    )
    advisory = build_l1_cognitive_consumer_advisory(_plan)
    assert advisory is not None
    unresolved_ids = advisory["unresolved_critical_requirement_ids"]
    assert unresolved_ids
    assert cognitive["planning_status"] == "BLOCKED"

    disposition = emit_l1_cognitive_output_disposition(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        runtime_payload={
            "l1_cognitive_v3_plan": cognitive,
            "l1_cognitive_advisory": advisory,
        },
    )

    assert disposition["status"] == "WARNING"
    assert disposition["reason_code"] == "UNRESOLVED_CRITICAL_L1_REQUIREMENTS_ADVISORY"
    assert disposition["blocks_finalization"] is False
    assert disposition["goal_constraint"]["valid"] is True
    assert (
        disposition["goal_constraint"]["unresolved_critical_requirement_ids"]
        == unresolved_ids
    )
    assert "quantum-superiority governance" not in json.dumps(
        disposition, sort_keys=True
    )

    # Legacy strict mode: APPS_RG_L1_SOFTEN_CRITICAL_GATES=false
    import os
    os.environ["APPS_RG_L1_SOFTEN_CRITICAL_GATES"] = "false"
    try:
        strict_disp = emit_l1_cognitive_output_disposition(
            artifact_dir=tmp_path,
            section_id="ibm_bullets",
            runtime_payload={
                "l1_cognitive_v3_plan": cognitive,
                "l1_cognitive_advisory": advisory,
            },
        )
        assert strict_disp["status"] == "BLOCKED"
        assert strict_disp["reason_code"] == "UNRESOLVED_CRITICAL_L1_REQUIREMENTS"
        assert strict_disp["blocks_finalization"] is True
        (tmp_path / "x3_disposition.json").write_text(
            json.dumps({"x3_code": "X3_ALLOW", "pass": True}), encoding="utf-8"
        )
        x3 = apply_l1_cognitive_output_disposition_to_x3_mirror(tmp_path)
        assert x3 is not None
        assert x3["l1_cognitive_output_blocked"] is True
        assert x3["x3_code"] == "X3_BLOCK_L1_COGNITIVE_OUTPUT"
        assert x3["pass"] is False
    finally:
        os.environ.pop("APPS_RG_L1_SOFTEN_CRITICAL_GATES", None)


def test_mapped_critical_l1_requirement_does_not_block_without_c0_revision(
    tmp_path: Path,
) -> None:
    plan, cognitive, _v2 = _candidate_plan()
    advisory = build_l1_cognitive_consumer_advisory(plan)
    assert advisory is not None
    assert advisory["unresolved_critical_requirement_ids"] == []

    disposition = emit_l1_cognitive_output_disposition(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        runtime_payload={
            "l1_cognitive_v3_plan": cognitive,
            "l1_cognitive_advisory": advisory,
        },
    )

    assert disposition["status"] == "NOT_APPLICABLE"
    assert disposition["blocks_finalization"] is False
    assert disposition["goal_constraint"]["valid"] is True
    assert disposition["goal_constraint"]["unresolved_critical_requirement_ids"] == []


def test_app_owned_c0_projection_preserves_provider_content_and_claims(
    tmp_path: Path,
) -> None:
    _write_candidate_artifacts(tmp_path)
    raw_provider_response = '{"content":"provider-authored output"}'
    (tmp_path / "provider_response.json").write_text(
        raw_provider_response,
        encoding="utf-8",
    )
    l2_path = tmp_path / "l2_output.json"
    l2_output = json.loads(l2_path.read_text(encoding="utf-8"))
    l2_output["claim_ledger"] = [
        {"claim_text": "grounded claim", "source_fact_ids": ["f1"]}
    ]
    l2_path.write_text(json.dumps(l2_output), encoding="utf-8")
    revision_advisory = json.loads(
        (tmp_path / sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY).read_text(
            encoding="utf-8"
        )
    )

    projection = apply_l1_cognitive_output_projection(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        runtime_payload={"l1_cognitive_revision_advisory": revision_advisory},
    )
    disposition = emit_l1_cognitive_output_disposition(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        runtime_payload={"l1_cognitive_revision_advisory": revision_advisory},
    )
    projected_output = json.loads(l2_path.read_text(encoding="utf-8"))

    assert projection["status"] == "APPLIED"
    assert projection["added_gap_note_count"] == 0
    assert projection["added_change_log_count"] == 0
    assert (tmp_path / "provider_response.json").read_text(
        encoding="utf-8"
    ) == raw_provider_response
    assert projected_output["claim_ledger"] == [
        {"claim_text": "grounded claim", "source_fact_ids": ["f1"]}
    ]
    assert any(
        isinstance(row, dict)
        and row.get("source") == "apps_rg_l1_cognitive_c0_outcome_projection"
        for row in projected_output["gap_notes"]
    )
    assert any(
        isinstance(row, dict)
        and row.get("source") == "apps_rg_l1_cognitive_c0_outcome_projection"
        for row in projected_output["change_log"]
    )
    assert disposition["status"] == "PASS"
    assert disposition["blocks_finalization"] is False


def test_control_receipt_rejects_v3_prompt_fields(tmp_path: Path) -> None:
    plan = SimpleNamespace(
        task_spec={
            "l1_cognitive_treatment": build_l1_cognitive_treatment(
                L1_COGNITIVE_V2_CONTROL_ARM,
                assignment_origin="U0_VALIDATED_INGRESS",
            ),
            "apps_rg_planning_v2_capsule": {"capsule_digest": "sha256:" + "a" * 64},
        }
    )
    (tmp_path / "compiled_prompt_artifact.json").write_text(
        json.dumps({"section_id": "headline", "l1_cognitive_plan_digest": "sha256:x"}),
        encoding="utf-8",
    )

    receipt = build_l1_cognitive_treatment_execution_receipt(
        run_root=tmp_path,
        l1_plan=plan,
    )

    assert receipt["status"] == "BLOCKED"
    assert "control_prompt_contains_v3_fields" in " ".join(receipt["errors"])


def test_candidate_receipt_rejects_missing_c0_gap_disposition(tmp_path: Path) -> None:
    plan = _write_candidate_artifacts(tmp_path)
    (tmp_path / "l2_output.json").write_text(
        json.dumps({"gap_notes": [], "change_log": []}), encoding="utf-8"
    )
    revision_advisory = json.loads(
        (tmp_path / sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY).read_text(
            encoding="utf-8"
        )
    )
    disposition = emit_l1_cognitive_output_disposition(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        runtime_payload={"l1_cognitive_revision_advisory": revision_advisory},
    )

    receipt = build_l1_cognitive_treatment_execution_receipt(
        run_root=tmp_path,
        l1_plan=plan,
    )

    assert receipt["status"] == "BLOCKED"
    assert "missing_required_gap_tag" in " ".join(receipt["errors"])
    assert "missing_required_change_log_tag" in " ".join(receipt["errors"])
    assert disposition["status"] == "BLOCKED"
    assert disposition["blocks_finalization"] is True
    assert (tmp_path / L1_COGNITIVE_OUTPUT_DISPOSITION_ARTIFACT).is_file()
    assert (tmp_path / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT).is_file()


def test_candidate_disposition_rejects_tags_without_app_owned_projection(
    tmp_path: Path,
) -> None:
    _write_candidate_artifacts(tmp_path)
    projection_path = tmp_path / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT
    projection_path.unlink()
    revision_advisory = json.loads(
        (tmp_path / sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY).read_text(
            encoding="utf-8"
        )
    )

    disposition = emit_l1_cognitive_output_disposition(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        runtime_payload={"l1_cognitive_revision_advisory": revision_advisory},
    )

    assert disposition["status"] == "BLOCKED"
    assert disposition["reason_code"] == "C0_OUTCOME_PROJECTION_INVALID"
    assert disposition["blocks_finalization"] is True


def test_candidate_disposition_fails_closed_on_malformed_projection(
    tmp_path: Path,
) -> None:
    _write_candidate_artifacts(tmp_path)
    projection_path = tmp_path / L1_COGNITIVE_OUTPUT_PROJECTION_ARTIFACT
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    projection["revision_advisory"] = "malformed"
    projection["projection_digest"] = l1_cognitive_output_projection_digest(projection)
    projection_path.write_text(json.dumps(projection), encoding="utf-8")
    revision_advisory = json.loads(
        (tmp_path / sr.FILENAME_L1_COGNITIVE_REVISION_ADVISORY).read_text(
            encoding="utf-8"
        )
    )

    disposition = emit_l1_cognitive_output_disposition(
        artifact_dir=tmp_path,
        section_id="ibm_bullets",
        runtime_payload={"l1_cognitive_revision_advisory": revision_advisory},
    )

    assert disposition["status"] == "BLOCKED"
    assert disposition["reason_code"] == "C0_OUTCOME_PROJECTION_INVALID"
    assert disposition["blocks_finalization"] is True
