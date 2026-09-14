"""Resume Workflow Coordinator for modular R4 resume generation.

Orchestrates:
1. Environment & Path Initialization.
2. Lane Execution (via SectionGenerationService or ArtifactAssembler synthetic stubs).
3. Rollup & Deterministic Locked Copy Assembly (via ArtifactAssembler).
4. Direct Section Merging and Schema Validation.
5. Release Qualification and Gating (via ReleasePolicy).
6. Evidence Packaging and Generation Result Synthesis.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from apps_rg.l2_recipe.artifact_assembler import ArtifactAssembler
from apps_rg.l2_recipe.evaluation_service import EvaluationService
from apps_rg.l2_recipe.modular_lane_adapter import ModularLaneTargeting
from apps_rg.l2_recipe.modular_r4_generation_result import ModularR4GenerationResult
from apps_rg.l2_recipe.modular_rg_output_builder import (
    build_rg_output_from_modular_sections,
    load_lane_l2_from_section_refs,
)
from apps_rg.l2_recipe.release_policy import ReleasePolicy
from apps_rg.l2_recipe.section_generation_service import SectionGenerationService
from apps_rg.runtime.internal.generated_lane_rollup import (
    GENERATED_LANES,
    build_modular_lane_rollup,
)
from apps_rg.runtime.resume_resolution import load_lane_base_resume_json

PHASE0_PATH_INVENTORY_NOTES: dict[str, Any] = {
    "subprocess_cwd": (
        "modular Phase1 invokes in-process run_canonical_apps_rg_from_cli_primitives per lane "
        "(same surface as python -m apps_rg --section); offline batch is tests.helpers.offline_lane_orchestration only; "
        "lane order matches GENERATED_LANES."
    ),
    "runtime_proofs_strings": [
        "orchestrate_full_resume.RUNTIME_PROOFS = artifacts/apps_rg/runtime_proofs",
        "generated_lane_rollup.RUNTIME_PROOFS under repo/artifacts/.../runtime_proofs",
        "locked_copy_builder.ARTIFACT_REL = artifacts/apps_rg/runtime_proofs/locked_copy",
        "final_resume_manifest.DEFAULT_*_REL under runtime_proofs",
        "resume_package_manifest.RUNTIME_PROOFS",
    ],
    "lane_run_layout": "artifacts/apps_rg/runtime_proofs/<lane>/{real|mock}/<run_id>/",
    "r4_modular_replacement": (
        "run_modular_resume_generation writes under artifact_dir/modular_r4 only; "
        "no runtime_proofs dependency for canonical R4 modular outputs when this API is used."
    ),
    "modular_r4_sections_env": (
        "When APPS_RG_MODULAR_R4_SECTIONS_ROOT is set, dispatch prepare/finalize scope pointers "
        "to <env_root>/<lane>/latest_*.json and run directories under "
        "<env_root>/<lane>/{mock|real}/<run_id>/ (Phase 1 real lane invocation)."
    ),
}

LANE_DISPATCH_MODULES: tuple[str, ...] = (
    "apps_rg.runtime.sections.headline_lane",
    "apps_rg.runtime.sections.executive_summary_lane",
    "apps_rg.runtime.sections.unify_bullets_lane",
    "apps_rg.runtime.sections.unify_narrative_lane",
    "apps_rg.runtime.sections.ibm_bullets_lane",
    "apps_rg.runtime.sections.ibm_narrative_lane",
    "apps_rg.runtime.sections.role_episode_lane",
    "apps_rg.runtime.sections.competencies_lane",
)


class ResumeWorkflowCoordinator:
    """Coordinates modular resume generation across decomposed services."""

    def __init__(
        self,
        dispatch_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.dispatch_fn = dispatch_fn

    def run(
        self,
        input_package: Any,
        artifact_dir: Path | str,
        run_id: str,
        profile: Any | None = None,
        *,
        lane_targeting: ModularLaneTargeting | None = None,
    ) -> ModularR4GenerationResult:
        """Run modular generation workflow."""
        from apps_rg.l2_recipe.modular_resume_generation import ModularResumeProfile

        profile = profile or ModularResumeProfile()
        repo = input_package.repo_root.resolve()
        art = Path(str(artifact_dir)).resolve()
        modular_root = art / "modular_r4"
        try:
            art.relative_to(repo)
        except ValueError as exc:
            raise ValueError(
                "artifact_dir must be inside input_package.repo_root for Phase 0 path-relative contracts "
                f"(got artifact_dir={art}, repo_root={repo})"
            ) from exc
        modular_root.mkdir(parents=True, exist_ok=True)

        rel_mod = modular_root.relative_to(repo).as_posix()
        ArtifactAssembler.write_json(
            art / "modular_r4" / "phase0_path_inventory.json",
            PHASE0_PATH_INVENTORY_NOTES,
        )

        use_phase0_synthetic = profile.run_phase0_synthetic_assembly and not profile.phase1_invoke_real_lanes
        real_lane_invocation_attempted = bool(profile.phase1_invoke_real_lanes)

        merge_receipt_rel: str | None = None
        assembly_gates_ok: bool | None = None
        section_output_refs: dict[str, str] = {}
        rollup_blob: dict[str, Any] | None = None
        section_call_records: list[dict[str, Any]] = []
        lane_exec_status: dict[str, str] = {}
        provider_call_total = 0
        locked_provider = False
        pass_source = ""
        merged_err = ""
        phase0_blocked_on_product_fail_closed = False
        lanes_executed = 0
        lane_outputs_valid = False
        final_merge_attempted = False
        rg_output_merge_receipt_rel: str | None = None
        resume_graph_allocation_digest = ""
        resume_graph_allocation_refs: dict[str, str] = {}
        graph_skill_embedding_required = False
        graph_skill_embedding_allowlists_digest = ""
        graph_skill_embedding_runtime_refs: dict[str, str] = {}

        dispatch_func = self.dispatch_fn
        if dispatch_func is None:
            from apps_rg.runtime.orchestration.canonical_dispatch import (
                run_canonical_apps_rg_from_cli_primitives,
            )

            dispatch_func = run_canonical_apps_rg_from_cli_primitives

        if profile.phase1_invoke_real_lanes:
            (
                lane_run_dirs,
                lane_exec_status,
                section_call_records,
                resume_graph_allocation_digest,
                resume_graph_allocation_refs,
                graph_skill_embedding_required,
                graph_skill_embedding_allowlists_digest,
                graph_skill_embedding_runtime_refs,
            ) = SectionGenerationService.execute_phase1_lanes(
                repo=repo,
                art=art,
                modular_root=modular_root,
                run_id=run_id,
                input_package=input_package,
                profile=profile,
                lane_targeting=lane_targeting,
                dispatch_fn=dispatch_func,
            )

            if len(lane_run_dirs) == len(GENERATED_LANES):
                rollup_blob = build_modular_lane_rollup(repo, lane_run_dirs)
            else:
                rollup_blob = None

            if rollup_blob is not None:
                rollup_blob["resume_graph_allocation_plan_digest"] = resume_graph_allocation_digest
                rollup_blob["resume_graph_allocation_refs"] = dict(resume_graph_allocation_refs)
                rollup_blob["graph_skill_embeddings_required"] = graph_skill_embedding_required
                rollup_blob["graph_skill_embedding_allowlists_digest"] = (
                    graph_skill_embedding_allowlists_digest
                )
                rollup_blob["graph_skill_embedding_runtime_refs"] = dict(
                    graph_skill_embedding_runtime_refs
                )
                for lane in GENERATED_LANES:
                    row = rollup_blob["lanes"].get(lane)
                    if isinstance(row, dict):
                        rel_run = str(row.get("rollup_source_run_dir") or "")
                        if rel_run:
                            section_output_refs[lane] = f"{rel_run}/l2_output.json"

                assembly_gates_ok, merge_receipt_rel = ArtifactAssembler.execute_phase1_assembly(
                    repo=repo,
                    modular_root=modular_root,
                    art=art,
                    rollup_blob=rollup_blob,
                    profile=profile,
                )
            else:
                assembly_gates_ok = False

            provider_call_total = sum(
                1 for r in section_call_records if r.get("provider_call_attempted") is True
            )
            lanes_executed = sum(
                1 for lane in GENERATED_LANES if lane in lane_run_dirs and lane_run_dirs[lane].is_dir()
            )
            lane_outputs_valid = bool(rollup_blob is not None and assembly_gates_ok is True)

        elif use_phase0_synthetic:
            if ReleasePolicy.is_product_fail_closed():
                phase0_blocked_on_product_fail_closed = True
                section_call_records = [
                    SectionGenerationService.phase0_stub_lane_record(lane, i)
                    for i, lane in enumerate(GENERATED_LANES)
                ]
                rollup_blob = None
                assembly_gates_ok = False
                merge_receipt_rel = None
                lanes_executed = 0
                lane_outputs_valid = False
                ArtifactAssembler.write_json(
                    art / "modular_r4" / "phase0_product_fail_closed_block.json",
                    {
                        "blocked": True,
                        "reason": "phase0_synthetic_not_permitted_on_product_fail_closed_path",
                        "note": "Product runs require phase1_invoke_real_lanes; phase0 stubs are plumbing-only.",
                    },
                )
            else:
                for i, lane in enumerate(GENERATED_LANES):
                    section_call_records.append(
                        SectionGenerationService.phase0_stub_lane_record(lane, i)
                    )
                rollup_blob = ArtifactAssembler.build_synthetic_rollup(repo, modular_root)
                for lane in GENERATED_LANES:
                    row = rollup_blob["lanes"].get(lane)
                    if isinstance(row, dict):
                        rel_run = str(row.get("rollup_source_run_dir") or "")
                        if rel_run:
                            section_output_refs[lane] = f"{rel_run}/l2_output.json"

                (
                    assembly_gates_ok,
                    merge_receipt_rel,
                ) = ArtifactAssembler.execute_phase0_synthetic_assembly(
                    repo=repo,
                    modular_root=modular_root,
                    art=art,
                    rollup_blob=rollup_blob,
                    profile=profile,
                )
                lanes_executed = len(GENERATED_LANES)
                lane_outputs_valid = bool(assembly_gates_ok is True)

        schema_receipt_path = modular_root / "rg_output_schema_validation_receipt.json"
        fixture_ok = False
        fixture_err = "no_fixture_provided"
        fixture_candidate: dict[str, Any] | None = None
        if profile.validate_rg_output_fixture:
            fixture_ok, fixture_err, fixture_candidate = EvaluationService.validate_rg_output_fixture(
                input_package.rg_output_fixture_path
            )

        gen_resume: dict[str, Any] | None = None
        final_schema_valid = False

        if profile.phase1_invoke_real_lanes:
            assembled_path = modular_root / "final_resume_assembly" / "final_resume.json"
            build_ok = False
            merged_err = "phase1_merge_not_attempted"
            gen_resume = None
            final_schema_valid = False
            lane_load_errors: dict[str, str] = {}
            if assembly_gates_ok is True:
                final_merge_attempted = True
                base_resume_obj, _, _ = load_lane_base_resume_json(repo_root=repo)
                rollup_lanes = rollup_blob.get("lanes") if isinstance(rollup_blob, dict) else {}
                lane_map, lane_load_errors = load_lane_l2_from_section_refs(
                    repo,
                    section_output_refs,
                    rollup_lanes=rollup_lanes if isinstance(rollup_lanes, dict) else None,
                )
                build = build_rg_output_from_modular_sections(
                    lane_l2_by_id=lane_map,
                    base_resume=base_resume_obj,
                    input_package=input_package,
                    modular_root=modular_root,
                    artifact_dir=art,
                    run_id=run_id,
                    reject_mocked_lanes=True,
                )
                build_ok = bool(build.ok)
                merged_err = build.failure_reason or build.schema_error or ""
                final_schema_valid = bool(build.schema_valid and build.ok)
                gen_resume = build.rg_output if build_ok else None
                merge_out = modular_root / "outputs" / "rg_output_merge_receipt.json"
                merge_out.parent.mkdir(parents=True, exist_ok=True)
                ArtifactAssembler.write_json(merge_out, build.merge_receipt)
                try:
                    rg_output_merge_receipt_rel = merge_out.relative_to(art).as_posix()
                except ValueError:
                    rg_output_merge_receipt_rel = str(merge_out).replace("\\", "/")
                if build_ok and gen_resume is not None:
                    prod_out = art / "outputs" / "generated_resume.json"
                    prod_out.parent.mkdir(parents=True, exist_ok=True)
                    prod_out.write_text(
                        json.dumps(gen_resume, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )

            recipe_lane_policy = EvaluationService.summarize_recipe_lane_policy(
                section_call_records,
                enforce_product_lane_requirements=True,
            )

            decisive, failure, pass_source = ReleasePolicy.evaluate_phase1_release(
                rollup_blob=rollup_blob,
                assembly_gates_ok=assembly_gates_ok,
                lane_load_errors=lane_load_errors,
                build_ok=build_ok,
                merged_err=merged_err,
                recipe_lane_policy=recipe_lane_policy,
            )

            out_fr = modular_root / "outputs" / "final_resume.json"
            ArtifactAssembler.write_json(
                schema_receipt_path,
                {
                    "receipt_id": "rg_output_schema_validation_receipt.phase1.v3",
                    "validated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "final_schema_valid": final_schema_valid,
                    "error": merged_err if not build_ok else "",
                    "lane_l2_load_errors": lane_load_errors,
                    "assembler_final_resume_relpath": (
                        assembled_path.relative_to(art).as_posix() if assembled_path.is_file() else None
                    ),
                    "rg_output_final_resume_relpath": (
                        out_fr.relative_to(art).as_posix() if out_fr.is_file() else None
                    ),
                    "generated_resume_json_relpath": (
                        "outputs/generated_resume.json"
                        if (art / "outputs" / "generated_resume.json").is_file()
                        else None
                    ),
                    "rg_output_merge_receipt_relpath": rg_output_merge_receipt_rel,
                    "assembly_gates_all_pass": assembly_gates_ok,
                    "fixture_validated_ok": fixture_ok,
                    "fixture_error": fixture_err if not fixture_ok else "",
                    "fixture_path": (
                        str(input_package.rg_output_fixture_path)
                        if input_package.rg_output_fixture_path
                        else None
                    ),
                    "note": (
                        "Phase 1 v3: rg_output merge from lane l2_output.json refs (not assembler bridge); "
                        "PASS requires assembly gates_all_pass + valid outputs/generated_resume.json."
                    ),
                },
            )
        else:
            final_schema_valid = bool(fixture_ok)
            (
                decisive,
                failure,
                pass_source,
                gen_resume,
            ) = ReleasePolicy.evaluate_phase0_synthetic_release(
                phase0_blocked_on_product_fail_closed=phase0_blocked_on_product_fail_closed,
                run_phase0_synthetic_assembly=bool(profile.run_phase0_synthetic_assembly),
                assembly_gates_ok=assembly_gates_ok,
                validate_rg_output_fixture=bool(profile.validate_rg_output_fixture),
                has_fixture_path=bool(input_package.rg_output_fixture_path is not None),
                fixture_ok=fixture_ok,
                fixture_err=fixture_err,
                fixture_candidate=fixture_candidate,
            )
            recipe_lane_policy = EvaluationService.summarize_recipe_lane_policy(
                section_call_records,
                enforce_product_lane_requirements=False,
            )
            ArtifactAssembler.write_json(
                schema_receipt_path,
                {
                    "receipt_id": "rg_output_schema_validation_receipt.phase0.v1",
                    "validated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "final_schema_valid": final_schema_valid,
                    "error": fixture_err if not fixture_ok else "",
                    "fixture_path": (
                        str(input_package.rg_output_fixture_path)
                        if input_package.rg_output_fixture_path
                        else None
                    ),
                    "note": (
                        "Phase 0: validates optional fixture JSON only; assembler output remains "
                        "final_resume_assembler_v1, not rg_output_schema."
                    ),
                },
            )

        if profile.phase1_invoke_real_lanes:
            from apps_rg.runtime.integrated_lane_evidence_packaging import (
                finalize_integrated_run_lane_evidence,
            )

            finalize_integrated_run_lane_evidence(
                repo,
                art,
                correlation_id=run_id,
                section_call_records=section_call_records,
                recipe_lane_policy=recipe_lane_policy,
            )

        section_calls_path = modular_root / "section_provider_calls.json"
        calls_schema = (
            "apps_rg.section_provider_calls.phase1.v2"
            if profile.phase1_invoke_real_lanes
            else "apps_rg.section_provider_calls.phase0.v1"
        )
        locked_provider = any(str(r.get("section_lane")) == "full_resume" for r in section_call_records)
        ArtifactAssembler.write_json(
            section_calls_path,
            {
                "schema_version": calls_schema,
                "run_id": run_id,
                "modular_root_rel": rel_mod,
                "provider_call_count": provider_call_total,
                "locked_sections_provider_calls_detected": locked_provider,
                "real_lane_invocation_attempted": real_lane_invocation_attempted,
                "records": section_call_records,
                "lane_dispatch_modules": list(LANE_DISPATCH_MODULES),
                "decisive_status": decisive,
                "pass_source": pass_source,
                "recipe_lane_policy": recipe_lane_policy,
                "resume_graph_allocation_plan_digest": resume_graph_allocation_digest,
                "resume_graph_allocation_refs": resume_graph_allocation_refs,
                "graph_skill_embeddings_required": graph_skill_embedding_required,
                "graph_skill_embedding_allowlists_digest": graph_skill_embedding_allowlists_digest,
                "graph_skill_embedding_runtime_refs": graph_skill_embedding_runtime_refs,
            },
        )

        schema_rel = schema_receipt_path.relative_to(art).as_posix()

        return ModularR4GenerationResult(
            generated_resume=gen_resume,
            section_provider_calls_ref=section_calls_path.relative_to(art).as_posix(),
            section_output_refs=section_output_refs,
            merge_receipt_ref=merge_receipt_rel,
            schema_validation_receipt_ref=schema_rel,
            final_schema_valid=final_schema_valid,
            decisive_status=decisive,
            failure_reason=failure,
            provider_call_count=provider_call_total,
            locked_sections_provider_calls_detected=locked_provider,
            lanes_executed=lanes_executed,
            lane_outputs_valid=lane_outputs_valid,
            final_merge_attempted=final_merge_attempted,
            rg_output_merge_receipt_ref=rg_output_merge_receipt_rel,
            extras={
                "modular_root_rel": rel_mod,
                "assembly_gates_all_pass": assembly_gates_ok,
                "lane_count": len(GENERATED_LANES),
                "pass_source": pass_source,
                "real_lane_invocation_attempted": real_lane_invocation_attempted,
                "phase1_lane_status": lane_exec_status if profile.phase1_invoke_real_lanes else {},
                "lanes_executed": lanes_executed,
                "lane_outputs_valid": lane_outputs_valid,
                "final_merge_attempted": final_merge_attempted,
                "recipe_lane_policy": recipe_lane_policy,
            },
        )


__all__ = [
    "LANE_DISPATCH_MODULES",
    "PHASE0_PATH_INVENTORY_NOTES",
    "ResumeWorkflowCoordinator",
]
