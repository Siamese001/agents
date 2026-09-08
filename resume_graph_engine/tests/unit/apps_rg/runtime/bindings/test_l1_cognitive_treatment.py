"""Regression tests for Apps RG-local v2/v3 experiment assignment."""

from __future__ import annotations

import pytest

from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1CognitiveTreatmentError,
    build_l1_cognitive_treatment,
    treatment_from_task_spec,
)


def test_invalid_ingress_arm_is_rejected_before_l1_planning() -> None:
    with pytest.raises(L1CognitiveTreatmentError, match="must be one of"):
        build_l1_cognitive_treatment(
            "not-a-treatment",
            assignment_origin="U0_VALIDATED_INGRESS",
        )


def test_tampered_assignment_digest_is_rejected() -> None:
    treatment = build_l1_cognitive_treatment(
        L1_COGNITIVE_V2_CONTROL_ARM,
        assignment_origin="U0_VALIDATED_INGRESS",
    )
    treatment["arm"] = "l1_cognitive_v3"

    with pytest.raises(L1CognitiveTreatmentError, match="conflicts with arm"):
        treatment_from_task_spec({"l1_cognitive_treatment": treatment})


def test_missing_assignment_defaults_to_legacy_control_not_candidate() -> None:
    treatment = treatment_from_task_spec({})

    assert treatment["arm"] == L1_COGNITIVE_V2_CONTROL_ARM
    assert treatment["assignment_origin"] == "LEGACY_L1_DEFAULT"
    assert treatment["v3_cognitive_plan_enabled"] is False


def test_whole_run_ingress_binds_the_selected_arm_without_core_changes() -> None:
    from apps_rg.__main__ import _build_parser
    from apps_rg.runtime.orchestration.r3r4_whole_run_orchestration import (
        _build_cli_ingress_envelope,
    )

    default_parsed = _build_parser().parse_args([])
    assert default_parsed.l1_cognitive_treatment_arm == L1_COGNITIVE_V2_CONTROL_ARM

    parsed = _build_parser().parse_args(
        ["--l1-cognitive-treatment-arm", L1_COGNITIVE_V2_CONTROL_ARM]
    )
    assert parsed.l1_cognitive_treatment_arm == L1_COGNITIVE_V2_CONTROL_ARM

    envelope = _build_cli_ingress_envelope(
        target_company="Co",
        target_role="Role",
        target_level="",
        jd="Must lead platform engineering.",
        job_description_ref="",
        job_description_text="",
        manual_brief="brief.txt",
        resume_path="resume.json",
        source_resume_text="Led platform engineering.",
        generation_mode="strategic_tailor",
        l1_cognitive_treatment_arm=L1_COGNITIVE_V2_CONTROL_ARM,
        auto_research_internal=False,
        research_via=None,
    )

    assert envelope.app_payload["user_constraints"] == {
        "_l1_cognitive_treatment_arm": L1_COGNITIVE_V2_CONTROL_ARM
    }
