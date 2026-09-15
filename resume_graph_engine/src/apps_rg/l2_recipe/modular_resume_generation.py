"""Phase 0 modular R4 API — backward-compatible facade delegating to decomposed services.

Decomposed Services (Wave 2 Architectural Boundaries):
- ``ResumeWorkflowCoordinator`` (``apps_rg.l2_recipe.workflow_coordinator``): Top-level pipeline orchestration.
- ``SectionGenerationService`` (``apps_rg.l2_recipe.section_generation_service``): Provider routing, graph allocation, lane dispatch.
- ``EvaluationService`` (``apps_rg.l2_recipe.evaluation_service``): Blocker derivation, dispatch status, schema validation.
- ``ReleasePolicy`` (``apps_rg.l2_recipe.release_policy``): Release qualification, fail-closed policy, decisive status.
- ``ArtifactAssembler`` (``apps_rg.l2_recipe.artifact_assembler``): Rollup aggregation, locked copy, final resume assembly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from apps_rg.l2_recipe.artifact_assembler import ArtifactAssembler
from apps_rg.l2_recipe.evaluation_service import EvaluationService
from apps_rg.l2_recipe.modular_lane_adapter import ModularLaneTargeting
from apps_rg.l2_recipe.modular_r4_generation_result import ModularR4GenerationResult
from apps_rg.l2_recipe.release_policy import ReleasePolicy
from apps_rg.l2_recipe.section_generation_service import SectionGenerationService
from apps_rg.l2_recipe.workflow_coordinator import (
    LANE_DISPATCH_MODULES,
    PHASE0_PATH_INVENTORY_NOTES,
    ResumeWorkflowCoordinator,
)
from apps_rg.runtime.assembly.final_resume_manifest import FinalResumePaths
from apps_rg.runtime.orchestration.canonical_dispatch import (
    run_canonical_apps_rg_from_cli_primitives,
)

# Re-export for backward compatibility with existing tests and tools
__all__ = [
    "LANE_DISPATCH_MODULES",
    "ModularR4GenerationResult",
    "ModularResumeInputPackage",
    "ModularResumeProfile",
    "PHASE0_PATH_INVENTORY_NOTES",
    "run_canonical_apps_rg_from_cli_primitives",
    "run_modular_resume_generation",
]


@dataclass
class ModularResumeInputPackage:
    """Inputs for modular generation (expanded in later phases)."""

    repo_root: Path
    target_company: str = ""
    target_role: str = ""
    jd_text: str | None = None
    briefing_text: str | None = None
    rg_output_fixture_path: Path | None = None
    canonical_run_identity: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModularResumeProfile:
    """Execution profile (Phase 0 synthetic assembly + optional fixture validation)."""

    run_phase0_synthetic_assembly: bool = True
    validate_rg_output_fixture: bool = True
    phase1_invoke_real_lanes: bool = False
    phase1_lane_provider: str = ""
    self_consistency_requested: int = 0
    parallel_phase1_lanes: bool = True
    phase1_max_parallel: int = 4
    phase1_allow_non_allow_exit_zero: bool = False


# Backward-compatible helper functions delegating to service implementations
def _write_json(path: Path, data: Any) -> None:
    ArtifactAssembler.write_json(path, data)


def _rel_under_repo(path: Path, repo: Path) -> str:
    return ArtifactAssembler.rel_under_repo(path, repo)


def _phase0_stub_lane_record(lane: str, i: int) -> dict[str, Any]:
    return SectionGenerationService.phase0_stub_lane_record(lane, i)


def _phase1_missing_lane_record(
    lane: str,
    i: int,
    sc_req: int,
    sc_exe: int,
    prof: str,
    *,
    decisive_reason_code: str = "PHASE1_NO_RUN_DIR",
) -> dict[str, Any]:
    return SectionGenerationService.phase1_missing_lane_record(
        lane,
        i,
        sc_req,
        sc_exe,
        prof,
        decisive_reason_code=decisive_reason_code,
    )


def _phase1_lane_dispatch_status(result: dict[str, Any] | None) -> str:
    return EvaluationService.phase1_lane_dispatch_status(result)


def _derive_pre_run_blocker(dispatch: dict[str, Any] | None) -> str:
    return EvaluationService.derive_pre_run_blocker(dispatch)


def _phase1_materialize_lane_run_dir(
    *,
    repo: Path,
    sections_root: Path,
    integrated_dir: Path,
    lane: str,
    lane_provider: str,
    lane_dispatch_results: dict[str, dict[str, Any]],
    lane_exec_status: dict[str, str],
    emit_integrated_lane_pre_run_failure: Any,
    product_fail_closed: bool,
) -> Path | None:
    return SectionGenerationService.materialize_lane_run_dir(
        repo=repo,
        sections_root=sections_root,
        integrated_dir=integrated_dir,
        lane=lane,
        lane_provider=lane_provider,
        lane_dispatch_results=lane_dispatch_results,
        lane_exec_status=lane_exec_status,
        emit_integrated_lane_pre_run_failure_fn=emit_integrated_lane_pre_run_failure,
        product_fail_closed=product_fail_closed,
    )


def _minimal_judge_blob() -> dict[str, Any]:
    return ArtifactAssembler.minimal_judge_blob()


def _minimal_x2_blob() -> dict[str, Any]:
    return ArtifactAssembler.minimal_x2_blob()


def _minimal_l2_blob(lane: str, *, run_id: str) -> dict[str, Any]:
    return ArtifactAssembler.minimal_l2_blob(lane, run_id=run_id)


def _write_synthetic_lane_bundle(repo: Path, modular_root: Path, lane: str) -> str:
    return ArtifactAssembler.write_synthetic_lane_bundle(repo, modular_root, lane)


def _synthetic_lane_row(repo: Path, modular_root: Path, lane: str) -> dict[str, Any]:
    return ArtifactAssembler.synthetic_lane_row(repo, modular_root, lane)


def _build_synthetic_rollup(repo: Path, modular_root: Path) -> dict[str, Any]:
    return ArtifactAssembler.build_synthetic_rollup(repo, modular_root)


def _resolve_phase1_lane_provider_for_section(
    configured_provider: str | None,
    lane: str,
) -> tuple[str, str]:
    return SectionGenerationService.resolve_phase1_lane_provider_for_section(
        configured_provider,
        lane,
    )


def _resolve_phase1_lane_provider_route_for_section(
    configured_provider: str | None,
    lane: str,
) -> tuple[str, str, Any]:
    return SectionGenerationService.resolve_phase1_lane_provider_route_for_section(
        configured_provider,
        lane,
    )


def _assembly_plumbing_mode(profile: ModularResumeProfile, *, use_phase0_synthetic: bool) -> bool:
    return ArtifactAssembler.assembly_plumbing_mode(profile, use_phase0_synthetic=use_phase0_synthetic)


def _assemble_modular_final_resume(
    paths: FinalResumePaths,
    *,
    plumbing_mode: bool,
) -> dict[str, Any]:
    return ArtifactAssembler.assemble_modular_final_resume(paths, plumbing_mode=plumbing_mode)


def run_modular_resume_generation(
    input_package: ModularResumeInputPackage,
    artifact_dir: Path | str,
    run_id: str,
    profile: ModularResumeProfile | None = None,
    *,
    lane_targeting: ModularLaneTargeting | None = None,
) -> ModularR4GenerationResult:
    """Run Phase 0 modular pipeline under ``artifact_dir/modular_r4`` (R4-local).

    Delegates to ``ResumeWorkflowCoordinator`` using the module-level
    ``run_canonical_apps_rg_from_cli_primitives`` dispatch target so mock patches
    remain effective.
    """
    coordinator = ResumeWorkflowCoordinator(
        dispatch_fn=run_canonical_apps_rg_from_cli_primitives,
    )
    return coordinator.run(
        input_package=input_package,
        artifact_dir=artifact_dir,
        run_id=run_id,
        profile=profile,
        lane_targeting=lane_targeting,
    )
