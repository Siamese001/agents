"""Wave 2 Architectural Boundaries Verification Suite.

Tests that the 5 decomposed services:
- ResumeWorkflowCoordinator
- SectionGenerationService
- EvaluationService
- ReleasePolicy
- ArtifactAssembler
function independently in isolation with clear single responsibilities,
and that modular_resume_generation preserves complete backward compatibility.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps_rg.l2_recipe.artifact_assembler import ArtifactAssembler
from apps_rg.l2_recipe.evaluation_service import EvaluationService
from apps_rg.l2_recipe.modular_resume_generation import (
    LANE_DISPATCH_MODULES,
    ModularResumeInputPackage,
    ModularResumeProfile,
    PHASE0_PATH_INVENTORY_NOTES,
    _derive_pre_run_blocker,
    _phase1_lane_dispatch_status,
    run_canonical_apps_rg_from_cli_primitives,
    run_modular_resume_generation,
)
from apps_rg.l2_recipe.release_policy import ReleasePolicy
from apps_rg.l2_recipe.section_generation_service import SectionGenerationService
from apps_rg.l2_recipe.workflow_coordinator import ResumeWorkflowCoordinator


def test_decomposed_services_importability():
    """Verify all Wave 2 decomposed services exist and export required classes."""
    assert isinstance(ResumeWorkflowCoordinator, type)
    assert isinstance(SectionGenerationService, type)
    assert isinstance(EvaluationService, type)
    assert isinstance(ReleasePolicy, type)
    assert isinstance(ArtifactAssembler, type)


def test_evaluation_service_isolated_contracts():
    """Verify EvaluationService performs pure classification without filesystem or model deps."""
    # Pre-run blocker classification
    assert EvaluationService.derive_pre_run_blocker({"x3_disposition": "X3_BLOCK"}) == "EXECUTED_X3_BLOCK"
    assert EvaluationService.derive_pre_run_blocker({"x3_disposition": "X3_ALLOW"}) == "EXECUTED_X3_ALLOW"
    assert EvaluationService.derive_pre_run_blocker({"prior_abort": True}) == "MISSING_NOT_ATTEMPTED"
    assert EvaluationService.derive_pre_run_blocker({"fault": "temperature_range"}) == "temperature_range"
    assert EvaluationService.derive_pre_run_blocker({"exit_status": "error"}) == "LANE_DISPATCH_EXIT_ERROR"
    assert EvaluationService.derive_pre_run_blocker({}) == "PHASE1_NO_RUN_DIR"

    # Dispatch status classification
    assert EvaluationService.phase1_lane_dispatch_status({"exit_status": "success"}) == "ok"
    assert EvaluationService.phase1_lane_dispatch_status({"exit_status": "error"}) == "dispatch_error:lane_exit_error"
    assert EvaluationService.phase1_lane_dispatch_status({"fault": "temperature_range"}) == "exit_2"
    assert EvaluationService.phase1_lane_dispatch_status({"fault": "timeout"}) == "dispatch_error:timeout"


def test_release_policy_isolated_verdicts():
    """Verify ReleasePolicy computes pure release verdicts according to deterministic policy."""
    # Rollup missing -> FAIL
    decisive, failure, source = ReleasePolicy.evaluate_phase1_release(
        rollup_blob=None,
        assembly_gates_ok=True,
        lane_load_errors={},
        build_ok=True,
        merged_err="",
        recipe_lane_policy={},
    )
    assert decisive == "FAIL"
    assert failure == "phase1_incomplete_lane_artifacts"

    # Assembly gates failed -> FAIL
    decisive, failure, source = ReleasePolicy.evaluate_phase1_release(
        rollup_blob={"lanes": {}},
        assembly_gates_ok=False,
        lane_load_errors={},
        build_ok=True,
        merged_err="",
        recipe_lane_policy={},
    )
    assert decisive == "FAIL"
    assert failure == "deterministic_assembly_gates_failed"

    # Lane load errors -> FAIL
    decisive, failure, source = ReleasePolicy.evaluate_phase1_release(
        rollup_blob={"lanes": {}},
        assembly_gates_ok=True,
        lane_load_errors={"headline": "corrupted"},
        build_ok=True,
        merged_err="",
        recipe_lane_policy={},
    )
    assert decisive == "FAIL"
    assert "lane_l2_load_errors:headline=corrupted" in failure

    # Everything ok -> PASS
    decisive, failure, source = ReleasePolicy.evaluate_phase1_release(
        rollup_blob={"lanes": {}},
        assembly_gates_ok=True,
        lane_load_errors={},
        build_ok=True,
        merged_err="",
        recipe_lane_policy={},
    )
    assert decisive == "PASS"
    assert failure == ""
    assert source == "merged_rg_output_direct_lanes"

    # Fatal lane failures override build_ok -> FAIL
    decisive, failure, source = ReleasePolicy.evaluate_phase1_release(
        rollup_blob={"lanes": {}},
        assembly_gates_ok=True,
        lane_load_errors={},
        build_ok=True,
        merged_err="",
        recipe_lane_policy={
            "fatal_lane_failures": [
                {"section_lane": "headline", "decisive_reason_code": "fatal_error"}
            ]
        },
    )
    assert decisive == "FAIL"
    assert "fatal_lane_recipe_policy:headline:fatal_error" in failure


def test_artifact_assembler_isolated_helpers():
    """Verify ArtifactAssembler produces minimal blobs and determines plumbing mode."""
    jb = ArtifactAssembler.minimal_judge_blob()
    assert "judges" in jb
    assert len(jb["judges"]) >= 1

    x2 = ArtifactAssembler.minimal_x2_blob()
    assert x2["x2_passed"] == 1
    assert x2["x2_failed"] == 0

    l2 = ArtifactAssembler.minimal_l2_blob("headline", run_id="test_run")
    assert l2["run_id"] == "test_run"
    assert "headline_line" in l2

    l2_sum = ArtifactAssembler.minimal_l2_blob("executive_summary", run_id="test_run")
    assert "resume_display_text" in l2_sum

    # Plumbing mode evaluation
    prof_synthetic = ModularResumeProfile(run_phase0_synthetic_assembly=True, phase1_invoke_real_lanes=False)
    assert ArtifactAssembler.assembly_plumbing_mode(prof_synthetic, use_phase0_synthetic=True) is True

    prof_real = ModularResumeProfile(phase1_invoke_real_lanes=True)
    assert ArtifactAssembler.assembly_plumbing_mode(prof_real, use_phase0_synthetic=False) is False


def test_facade_backward_compatibility_reexports():
    """Verify modular_resume_generation facade re-exports all legacy symbols and functions."""
    assert callable(run_modular_resume_generation)
    assert callable(run_canonical_apps_rg_from_cli_primitives)
    assert callable(_derive_pre_run_blocker)
    assert callable(_phase1_lane_dispatch_status)
    assert isinstance(LANE_DISPATCH_MODULES, tuple)
    assert len(LANE_DISPATCH_MODULES) == 8
    assert "subprocess_cwd" in PHASE0_PATH_INVENTORY_NOTES


def test_section_generation_service_stubs():
    """Verify SectionGenerationService produces well-formed stub and missing lane records."""
    stub = SectionGenerationService.phase0_stub_lane_record("headline", 0)
    assert stub["section_lane"] == "headline"
    assert stub["generation_status"] == "PHASE0_SYNTHETIC_STUB"
    assert stub["provider_call_attempted"] is False

    missing = SectionGenerationService.phase1_missing_lane_record(
        lane="headline",
        i=0,
        sc_req=1,
        sc_exe=0,
        prof="claude",
        decisive_reason_code="PHASE1_NO_RUN_DIR",
    )
    assert missing["section_lane"] == "headline"
    assert missing["generation_status"] == "MISSING_LANE_RUN"
    assert missing["decisive_reason_code"] == "PHASE1_NO_RUN_DIR"
