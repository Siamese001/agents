"""Tests that Apps RG captures paired attempts, including failed output attempts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.evals.l1_cognitive_paired_shadow_capture import (
    L1CognitivePairedShadowCaptureError,
    L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME,
    build_l1_cognitive_pair_config_receipt,
    build_l1_cognitive_pair_input_receipt,
    build_l1_cognitive_shadow_run_binding,
    capture_l1_cognitive_paired_shadow,
)
from apps_rg.runtime.bindings.l1_cognitive_treatment import (
    L1_COGNITIVE_V2_CONTROL_ARM,
    L1_COGNITIVE_V3_CANDIDATE_ARM,
)
from apps_rg.runtime.contracts.l1_cognitive_treatment_execution import (
    treatment_execution_digest,
)
from apps_rg.runtime.dispatch import spine_stage_receipts as sr


def _write_run(root: Path, *, arm: str, jd_payload_digest: str) -> None:
    lineage = {
        "l1_v2_capsule_digest": "sha256:" + "a" * 64,
        "l1_cognitive_plan_digest": "",
        "l1_cognitive_advisory_digest": "",
        "c0_outcome_set_digest": "sha256:" + "b" * 64,
        "l1_cognitive_revision_set_digest": "sha256:" + "c" * 64,
    }
    if arm == L1_COGNITIVE_V3_CANDIDATE_ARM:
        lineage["l1_cognitive_plan_digest"] = "sha256:" + "d" * 64
        lineage["l1_cognitive_advisory_digest"] = "sha256:" + "e" * 64
    receipt = {
        "schema_version": "apps_rg.l1_cognitive_treatment_execution.v4",
        "authority_class": "TECHNICAL_EXECUTION_OBSERVATION_ONLY",
        "app_scope": "APPS_RG_V2_ONLY",
        "treatment": {
            "arm": arm,
            "treatment_digest": "sha256:" + "f" * 64,
            "assignment_origin": "U0_VALIDATED_INGRESS",
        },
        "lineage": lineage,
        "status": "PASS",
        "records": [],
        "summary": {
            "compiled_prompt_artifact_count": 0,
            "observed_consumption_count": 0,
            "error_count": 0,
            "all_observed_records_source_bound": True,
        },
        "errors": [],
        "authority": {
            "does_not_dispatch": True,
            "does_not_score_resume_quality": True,
            "does_not_authorize_promotion": True,
            "human_qualified": False,
        },
        "receipt_digest": "",
    }
    receipt["receipt_digest"] = treatment_execution_digest(receipt)
    (root / sr.FILENAME_L1_COGNITIVE_TREATMENT_EXECUTION).write_text(
        json.dumps(receipt), encoding="utf-8"
    )
    (root / sr.FILENAME_L1_PLANNING_V2_CAPSULE).write_text(
        json.dumps(
            {
                "source_binding": {
                    "source_class": "U0_VALIDATED_JD_PAYLOAD",
                    "jd_hash": "a" * 64,
                    "inline_jd_available": True,
                    "inline_jd_digest": jd_payload_digest,
                }
            }
        ),
        encoding="utf-8",
    )
    (root / sr.FILENAME_SPINE_MANIFEST).write_text("{}", encoding="utf-8")


def _write_run_binding(
    root: Path, *, frozen: dict[str, object], config: dict[str, object]
) -> None:
    binding = build_l1_cognitive_shadow_run_binding(
        frozen_input_receipt=frozen,
        config_receipt=config,
    )
    (root / L1_COGNITIVE_SHADOW_RUN_BINDING_FILENAME).write_text(
        json.dumps(binding), encoding="utf-8"
    )


def test_capture_preserves_pair_when_both_final_outputs_are_not_complete(
    tmp_path: Path,
) -> None:
    campaign = tmp_path / "campaign"
    control = campaign / "control"
    candidate = campaign / "candidate"
    control.mkdir(parents=True)
    candidate.mkdir()
    jd = tmp_path / "jd.txt"
    brief = tmp_path / "brief.txt"
    resume = tmp_path / "resume.json"
    jd.write_text("Required platform leadership", encoding="utf-8")
    brief.write_text("Targeting brief", encoding="utf-8")
    resume.write_text("{}", encoding="utf-8")
    frozen = build_l1_cognitive_pair_input_receipt(
        target_company="Acme",
        target_role="VP Engineering",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
    )
    config = build_l1_cognitive_pair_config_receipt(
        generation_mode="strategic_tailor",
        auto_research_internal=False,
    )
    jd_payload_digest = frozen["inputs"]["job_description"]["u0_payload_digest"]
    _write_run(
        control,
        arm=L1_COGNITIVE_V2_CONTROL_ARM,
        jd_payload_digest=jd_payload_digest,
    )
    _write_run(
        candidate,
        arm=L1_COGNITIVE_V3_CANDIDATE_ARM,
        jd_payload_digest=jd_payload_digest,
    )
    _write_run_binding(control, frozen=frozen, config=config)
    _write_run_binding(candidate, frozen=frozen, config=config)

    paired = capture_l1_cognitive_paired_shadow(
        campaign_root=campaign,
        pair_id="pair-001",
        control_run_root=control,
        candidate_run_root=candidate,
        frozen_input_receipt=frozen,
        config_receipt=config,
    )

    assert paired["summary"]["attempt_count"] == 1
    assert paired["summary"]["completed_pair_count"] == 0
    assert paired["pairs"][0]["control"]["completion_status"] == "FAIL"
    assert paired["pairs"][0]["candidate"]["completion_status"] == "FAIL"
    assert (campaign / "l1_cognitive_paired_shadow_receipt.json").is_file()


def test_capture_rejects_an_arm_with_different_frozen_configuration(
    tmp_path: Path,
) -> None:
    campaign = tmp_path / "campaign"
    control = campaign / "control"
    candidate = campaign / "candidate"
    control.mkdir(parents=True)
    candidate.mkdir()
    jd = tmp_path / "jd.txt"
    brief = tmp_path / "brief.txt"
    resume = tmp_path / "resume.json"
    jd.write_text("Required platform leadership", encoding="utf-8")
    brief.write_text("Targeting brief", encoding="utf-8")
    resume.write_text("{}", encoding="utf-8")
    frozen = build_l1_cognitive_pair_input_receipt(
        target_company="Acme",
        target_role="VP Engineering",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
    )
    config = build_l1_cognitive_pair_config_receipt(
        generation_mode="strategic_tailor", auto_research_internal=False
    )
    jd_payload_digest = frozen["inputs"]["job_description"]["u0_payload_digest"]
    _write_run(
        control, arm=L1_COGNITIVE_V2_CONTROL_ARM, jd_payload_digest=jd_payload_digest
    )
    _write_run(
        candidate,
        arm=L1_COGNITIVE_V3_CANDIDATE_ARM,
        jd_payload_digest=jd_payload_digest,
    )
    _write_run_binding(control, frozen=frozen, config=config)
    candidate_config = build_l1_cognitive_pair_config_receipt(
        generation_mode="strategic_tailor",
        auto_research_internal=False,
        lane_provider="different-provider",
    )
    _write_run_binding(candidate, frozen=frozen, config=candidate_config)

    with pytest.raises(
        L1CognitivePairedShadowCaptureError,
        match="candidate run does not bind the supplied configuration receipt",
    ):
        capture_l1_cognitive_paired_shadow(
            campaign_root=campaign,
            pair_id="pair-configuration-mismatch",
            control_run_root=control,
            candidate_run_root=candidate,
            frozen_input_receipt=frozen,
            config_receipt=config,
        )


def test_capture_rejects_legacy_arm_without_pre_execution_provenance(
    tmp_path: Path,
) -> None:
    campaign = tmp_path / "campaign"
    control = campaign / "control"
    candidate = campaign / "candidate"
    control.mkdir(parents=True)
    candidate.mkdir()
    jd = tmp_path / "jd.txt"
    brief = tmp_path / "brief.txt"
    resume = tmp_path / "resume.json"
    jd.write_text("Required platform leadership", encoding="utf-8")
    brief.write_text("Targeting brief", encoding="utf-8")
    resume.write_text("{}", encoding="utf-8")
    frozen = build_l1_cognitive_pair_input_receipt(
        target_company="Acme",
        target_role="VP Engineering",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
    )
    config = build_l1_cognitive_pair_config_receipt(
        generation_mode="strategic_tailor", auto_research_internal=False
    )
    jd_payload_digest = frozen["inputs"]["job_description"]["u0_payload_digest"]
    _write_run(
        control, arm=L1_COGNITIVE_V2_CONTROL_ARM, jd_payload_digest=jd_payload_digest
    )
    _write_run(
        candidate,
        arm=L1_COGNITIVE_V3_CANDIDATE_ARM,
        jd_payload_digest=jd_payload_digest,
    )
    _write_run_binding(control, frozen=frozen, config=config)

    with pytest.raises(
        L1CognitivePairedShadowCaptureError,
        match="required pre-execution Apps RG-local input/config binding",
    ):
        capture_l1_cognitive_paired_shadow(
            campaign_root=campaign,
            pair_id="legacy-without-provenance",
            control_run_root=control,
            candidate_run_root=candidate,
            frozen_input_receipt=frozen,
            config_receipt=config,
        )


def test_capture_rejects_run_that_did_not_admit_the_frozen_u0_jd(
    tmp_path: Path,
) -> None:
    campaign = tmp_path / "campaign"
    control = campaign / "control"
    candidate = campaign / "candidate"
    control.mkdir(parents=True)
    candidate.mkdir()
    jd = tmp_path / "jd.txt"
    brief = tmp_path / "brief.txt"
    resume = tmp_path / "resume.json"
    jd.write_text("Required platform leadership", encoding="utf-8")
    brief.write_text("Targeting brief", encoding="utf-8")
    resume.write_text("{}", encoding="utf-8")
    frozen = build_l1_cognitive_pair_input_receipt(
        target_company="Acme",
        target_role="VP Engineering",
        target_level="EXECUTIVE",
        generation_mode="strategic_tailor",
        jd_path=jd,
        briefing_path=brief,
        resume_path=resume,
    )
    config = build_l1_cognitive_pair_config_receipt(
        generation_mode="strategic_tailor", auto_research_internal=False
    )
    valid_digest = frozen["inputs"]["job_description"]["u0_payload_digest"]
    _write_run(control, arm=L1_COGNITIVE_V2_CONTROL_ARM, jd_payload_digest=valid_digest)
    _write_run(
        candidate,
        arm=L1_COGNITIVE_V3_CANDIDATE_ARM,
        jd_payload_digest="sha256:" + "0" * 64,
    )
    _write_run_binding(control, frozen=frozen, config=config)
    _write_run_binding(candidate, frozen=frozen, config=config)

    with pytest.raises(
        L1CognitivePairedShadowCaptureError,
        match="candidate v2 capsule is not bound to the frozen U0 JD payload",
    ):
        capture_l1_cognitive_paired_shadow(
            campaign_root=campaign,
            pair_id="pair-jd-mismatch",
            control_run_root=control,
            candidate_run_root=candidate,
            frozen_input_receipt=frozen,
            config_receipt=config,
        )
