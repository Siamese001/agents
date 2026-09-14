"""Section Generation Service for modular resume generation.

Handles:
- Provider route resolution per lane.
- Whole-resume graph evidence allocation and graph skill embeddings.
- Concurrency configuration and managed lane dispatch.
- Materialization of lane run directories and failure recording.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from apps_rg.l2_recipe.evaluation_service import EvaluationService
from apps_rg.l2_recipe.modular_lane_adapter import (
    ModularLaneTargeting,
    build_modular_lane_argv,
    build_section_provider_call_record,
    phase1_jd_dispatch_refs,
    phase1_manual_brief_for_dispatch,
    resolve_latest_lane_run_dir,
)
from apps_rg.runtime.c0.graph_skill_embedding_allocation import (
    GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV,
    build_lane_embedding_allowlists,
    build_whole_resume_graph_embedding_candidates,
    candidate_skill_scores_by_section,
    graph_skill_embeddings_required,
    write_graph_skill_embedding_runtime_bundle,
)
from apps_rg.runtime.c0.resume_graph_allocation import (
    ALLOCATION_PLAN_ENV,
    ALLOCATION_USAGE_LEDGER_ENV,
    SECTION_EVIDENCE_CONTRACTS_ENV,
    SECTION_SOURCE_PLANS_ENV,
    build_whole_resume_graph_allocation,
    write_whole_resume_graph_allocation_bundle,
)
from apps_rg.runtime.integrated_lane_evidence_packaging import (
    emit_integrated_lane_pre_run_failure,
)
from apps_rg.runtime.internal.generated_lane_rollup import GENERATED_LANES
from apps_rg.runtime.orchestration.managed_section_lane_dispatcher import (
    dispatch_phase1_lanes_managed,
)
from apps_rg.runtime.orchestration.section_lane_concurrency import (
    phase1_parallel_enabled,
    resolve_max_parallel,
)
from apps_rg.runtime.orchestration.section_lane_executor import (
    LaneExecutionContext,
    run_lane_in_context,
)
from apps_rg.runtime.product_output_policy import (
    PHASE1_PRIOR_LANE_FAILED_BLOCKER,
    lane_run_dir_meets_product_bar,
    phase1_dispatch_hard_failed,
    product_fail_closed_runtime,
)
from apps_rg.runtime.providers.anthropic_limit_preflight import (
    resolve_anthropic_limit_preflight_route,
    route_whole_run_provider_for_known_anthropic_limit,
)
from apps_rg.runtime.reasoning.employment_bullet_pool import REQUIRED_BULLET_IDS
from apps_rg.runtime.run_bundle_index import repo_relative_posix
from apps_rg.runtime.runtime_proof_layout import (
    MODULAR_R4_SECTIONS_ROOT_ENV,
    resolve_phase1_sections_root,
)
from apps_rg.runtime.section_cli_defaults import (
    CLI_PROVIDER_RESOLUTION_DEV_DEFAULT_EXTERNAL_CLAUDE,
    CLI_PROVIDER_RESOLUTION_ENV_APPS_RG_MODULAR_LANE_PROVIDER,
    resolve_cli_lane_provider_with_source,
    resolve_cli_x1d_judges,
    resolve_phase1_lane_allow_non_allow_exit_zero,
)
from apps_rg.runtime.section_execution_plan import NARRATIVE_UPSTREAM_BULLET_LANE
from apps_rg.runtime.sections_root_manifest import (
    emit_sections_root_manifest,
    log_sections_manifest_write_failed,
)
from apps_rg.runtime.validators.companion_bullet_finalization import (
    PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER,
    companion_accepted_in_modular_sections_root,
)


class SectionGenerationService:
    """Encapsulates section provider routing, graph allocation, lane dispatch, and materialization."""

    @staticmethod
    def phase0_stub_lane_record(lane: str, i: int) -> dict[str, Any]:
        """Produce synthetic lane call record for Phase 0."""
        return {
            "section_lane": lane,
            "provider_call_attempted": False,
            "provider_profile": "phase0_synthetic",
            "model_id": "none",
            "candidate_index": i,
            "self_consistency_requested": 1,
            "self_consistency_executed": 0,
            "prompt_chars": 0,
            "prompt_truncated": False,
            "max_tokens": 0,
            "temperature": 0.0,
            "top_p": 1.0,
            "response_format_sent": None,
            "generation_status": "PHASE0_SYNTHETIC_STUB",
            "parsed_output_shape": "lane_l2_stub",
            "section_schema_validation_status": "skipped_phase0",
            "decisive_reason_code": "PHASE0_NO_PROVIDER",
            "output_ref": f"modular_r4/lanes/{lane}/real/phase0_synthetic/l2_output.json",
            "reasoning_execution_receipt_ref": None,
        }

    @staticmethod
    def phase1_missing_lane_record(
        lane: str,
        i: int,
        sc_req: int,
        sc_exe: int,
        prof: str,
        *,
        decisive_reason_code: str = "PHASE1_NO_RUN_DIR",
    ) -> dict[str, Any]:
        """Produce missing lane record for unmaterialized lane."""
        return {
            "section_lane": lane,
            "provider_call_attempted": False,
            "provider_profile": f"{prof}_section_lane",
            "model_id": "",
            "candidate_index": i,
            "self_consistency_requested": sc_req,
            "self_consistency_executed": sc_exe,
            "prompt_chars": 0,
            "prompt_truncated": False,
            "max_tokens": 0,
            "temperature": 0.0,
            "top_p": 1.0,
            "response_format_sent": None,
            "generation_status": "MISSING_LANE_RUN",
            "parsed_output_shape": "none",
            "section_schema_validation_status": "missing",
            "decisive_reason_code": str(decisive_reason_code or "PHASE1_NO_RUN_DIR"),
            "output_ref": "",
            "reasoning_execution_receipt_ref": None,
        }

    @classmethod
    def resolve_phase1_lane_provider_for_section(
        cls,
        configured_provider: str | None,
        lane: str,
    ) -> tuple[str, str]:
        """Resolve the effective Phase-1 provider for one lane."""
        provider, source, _route = cls.resolve_phase1_lane_provider_route_for_section(
            configured_provider,
            lane,
        )
        return provider, source

    @staticmethod
    def resolve_phase1_lane_provider_route_for_section(
        configured_provider: str | None,
        lane: str,
    ) -> tuple[str, str, Any]:
        """Resolve provider plus the Anthropic-limit preflight route."""
        configured = str(configured_provider or "").strip()
        provider, source = resolve_cli_lane_provider_with_source(
            configured or None,
            section_id=lane,
        )
        if (
            lane in {"competencies", "executive_summary"}
            and source == CLI_PROVIDER_RESOLUTION_ENV_APPS_RG_MODULAR_LANE_PROVIDER
            and provider != "external_claude"
        ):
            provider = "external_claude"
            source = CLI_PROVIDER_RESOLUTION_DEV_DEFAULT_EXTERNAL_CLAUDE
        return route_whole_run_provider_for_known_anthropic_limit(
            provider,
            source,
            section_id=lane,
        )

    @staticmethod
    def materialize_lane_run_dir(
        *,
        repo: Path,
        sections_root: Path,
        integrated_dir: Path,
        lane: str,
        lane_provider: str,
        lane_dispatch_results: dict[str, dict[str, Any]],
        lane_exec_status: dict[str, str],
        emit_integrated_lane_pre_run_failure_fn: Any = emit_integrated_lane_pre_run_failure,
        product_fail_closed: bool,
    ) -> Path | None:
        """Resolve lane run_dir from pointers for recipe rollup (decoupled from dispatch exit_status)."""
        try:
            run_dir = resolve_latest_lane_run_dir(
                repo,
                sections_root,
                lane,
                lane_provider=lane_provider,
            )
        except FileNotFoundError as exc:  # guardian: allow-return-none-swallow
            dispatch = lane_dispatch_results.get(lane) or {}
            blocker = EvaluationService.derive_pre_run_blocker(dispatch)
            emit_integrated_lane_pre_run_failure_fn(
                sections_root=sections_root,
                integrated_dir=integrated_dir,
                repo_root=repo,
                lane_id=lane,
                blocker=blocker,
                dispatch_result=dispatch,
                lane_exec_status=str(lane_exec_status.get(lane) or ""),
                downstream_consequences=[
                    {
                        "stage": "PHASE1_LANE_MATERIALIZATION",
                        "operation": "resolve_latest_lane_run_dir",
                        "code": "LANE_RUN_POINTER_NOT_FOUND",
                        "exception_class": type(exc).__name__,
                        "exception_message": str(exc),
                    }
                ],
            )
            return None

        if product_fail_closed:
            ok, bar_reason = lane_run_dir_meets_product_bar(run_dir)
            if not ok:
                emit_integrated_lane_pre_run_failure_fn(
                    sections_root=sections_root,
                    integrated_dir=integrated_dir,
                    repo_root=repo,
                    lane_id=lane,
                    blocker=f"LANE_PRODUCT_BAR_FAILED:{bar_reason}",
                    dispatch_result=lane_dispatch_results.get(lane) or {},
                    lane_exec_status=lane_exec_status.get(lane, ""),
                )
                return None

        return run_dir

    @classmethod
    def execute_phase1_lanes(
        cls,
        *,
        repo: Path,
        art: Path,
        modular_root: Path,
        run_id: str,
        input_package: Any,
        profile: Any,
        lane_targeting: ModularLaneTargeting | None,
        dispatch_fn: Callable[..., Any],
    ) -> tuple[
        dict[str, Path],
        dict[str, str],
        list[dict[str, Any]],
        str,
        dict[str, str],
        bool,
        str,
        dict[str, str],
    ]:
        """Execute Phase 1 lane generation workflow with scoped environment isolation."""
        sections_root = resolve_phase1_sections_root(art, modular_root)
        rel_mod = modular_root.relative_to(repo).as_posix()
        try:
            emit_sections_root_manifest(
                repo_root=repo,
                sections_root_abs=sections_root,
                source_env_literal=MODULAR_R4_SECTIONS_ROOT_ENV,
                correlation_id=None,
                integrated_run_ref=repo_relative_posix(repo, art.resolve()),
                run_links_ref=None,
                notes=f"scoped Phase 1 sections root modular_r4/{rel_mod}/sections (run_id={run_id})",
            )
        except OSError as exc:
            log_sections_manifest_write_failed("run_modular_resume_generation_phase1", exc)
            raise

        prev_env = os.environ.get(MODULAR_R4_SECTIONS_ROOT_ENV)
        os.environ[MODULAR_R4_SECTIONS_ROOT_ENV] = str(sections_root.resolve())
        lane_argv = build_modular_lane_argv(
            provider=profile.phase1_lane_provider,
            targeting=lane_targeting,
        )
        lane_run_dirs: dict[str, Path] = {}
        lane_dispatch_results: dict[str, dict[str, Any]] = {}
        _ = lane_argv
        lane_mock_j_for_phase1 = False
        tc = str(lane_targeting.target_company or "") if lane_targeting is not None else ""
        tr = str(lane_targeting.target_title or "") if lane_targeting is not None else ""
        jd_ref, jd_txt = phase1_jd_dispatch_refs(lane_targeting)
        br_dispatch = phase1_manual_brief_for_dispatch(lane_targeting)

        # Resolve effective text
        effective_jd_text = ""
        if lane_targeting is not None and lane_targeting.jd_text:
            effective_jd_text = str(lane_targeting.jd_text).strip()
        elif jd_txt:
            effective_jd_text = jd_txt.strip()
        elif jd_ref:
            try:
                _p = Path(jd_ref)
                if _p.is_file():
                    effective_jd_text = _p.read_text(encoding="utf-8").strip()
            except (OSError, ValueError):
                pass
        if not effective_jd_text and input_package.jd_text:
            effective_jd_text = str(input_package.jd_text).strip()

        effective_briefing_text = ""
        if lane_targeting is not None and lane_targeting.briefing_text:
            effective_briefing_text = str(lane_targeting.briefing_text).strip()
        elif br_dispatch:
            try:
                _p = Path(br_dispatch)
                if _p.is_file():
                    effective_briefing_text = _p.read_text(encoding="utf-8").strip()
            except (OSError, ValueError):
                pass
        if not effective_briefing_text and input_package.briefing_text:
            effective_briefing_text = str(input_package.briefing_text).strip()

        graph_skill_embedding_required = graph_skill_embeddings_required()
        graph_skill_embedding_candidates: dict[str, Any] | None = None
        graph_skill_embedding_scores: dict[str, dict[str, float]] | None = None
        if graph_skill_embedding_required:
            graph_skill_embedding_candidates = (
                build_whole_resume_graph_embedding_candidates(
                    repo_root=repo,
                    target_company=tc or str(input_package.target_company or ""),
                    target_role=tr or str(input_package.target_role or ""),
                    jd_text=effective_jd_text,
                    briefing_text=effective_briefing_text,
                )
            )
            graph_skill_embedding_scores = candidate_skill_scores_by_section(
                graph_skill_embedding_candidates["candidates_by_section"]
            )

        resume_graph_bundle = build_whole_resume_graph_allocation(
            repo_root=repo,
            target_role=tr or str(input_package.target_role or ""),
            jd_text=effective_jd_text,
            briefing_text=effective_briefing_text,
            embedding_skill_scores_by_section=graph_skill_embedding_scores,
        )
        resume_graph_allocation_refs = write_whole_resume_graph_allocation_bundle(
            resume_graph_bundle,
            output_dir=modular_root / "resume_graph_allocation",
        )
        resume_graph_allocation_digest = str(
            resume_graph_bundle["allocation_plan"].get("allocation_plan_digest") or ""
        )

        graph_skill_embedding_allowlists_digest = ""
        graph_skill_embedding_runtime_refs: dict[str, str] = {}
        if graph_skill_embedding_candidates is not None:
            lane_embedding_allowlists = build_lane_embedding_allowlists(
                allocation_plan=resume_graph_bundle["allocation_plan"],
                candidates_by_section=graph_skill_embedding_candidates[
                    "candidates_by_section"
                ],
                authority_pins=graph_skill_embedding_candidates["authority"],
            )
            graph_skill_embedding_allowlists_digest = str(
                lane_embedding_allowlists.get("allowlists_digest") or ""
            )
            graph_skill_embedding_runtime_refs = (
                write_graph_skill_embedding_runtime_bundle(
                    {
                        "lane_allowlists": lane_embedding_allowlists,
                        "runtime_receipt": {
                            "schema_version": (
                                "apps_rg.graph_skill_embedding_runtime_receipt.v1"
                            ),
                            "status": "PASS",
                            "authority": graph_skill_embedding_candidates["authority"],
                            "allocation_plan_digest": resume_graph_allocation_digest,
                            "allowlists_digest": graph_skill_embedding_allowlists_digest,
                            "query_receipts": graph_skill_embedding_candidates[
                                "query_receipts"
                            ],
                            "runtime_proof": graph_skill_embedding_candidates[
                                "runtime_proof"
                            ],
                            "projection_sha256_before": graph_skill_embedding_candidates[
                                "projection_sha256_before"
                            ],
                            "projection_sha256_after": graph_skill_embedding_candidates[
                                "projection_sha256_after"
                            ],
                            "candidate_payload_fields": [
                                "assertion_id",
                                "similarity",
                            ],
                            "similarity_is_claim_authority": False,
                            "provider_call_attempted_before_preflight": False,
                            "durable_graph_state_mutated": False,
                            "network_used": False,
                            "fallback_used": False,
                            "pass": True,
                        },
                    },
                    output_dir=modular_root / "graph_skill_embedding_allocation",
                )
            )

        def _lane_x1d_judges(lane_id: str) -> str:
            return resolve_cli_x1d_judges(None, section_id=lane_id)

        phase1_lane_provider_by_lane: dict[str, str] = {}
        phase1_lane_provider_source_by_lane: dict[str, str] = {}
        phase1_anthropic_limit_preflight_by_lane: dict[str, dict[str, Any]] = {}

        def _lane_provider_for_lane(lane_id: str) -> str:
            lane_key = str(lane_id or "").strip()
            if lane_key not in phase1_lane_provider_by_lane:
                provider, source, route = cls.resolve_phase1_lane_provider_route_for_section(
                    profile.phase1_lane_provider,
                    lane_key,
                )
                phase1_lane_provider_by_lane[lane_key] = provider
                phase1_lane_provider_source_by_lane[lane_key] = source
                phase1_anthropic_limit_preflight_by_lane[lane_key] = route.to_dict()
            return phase1_lane_provider_by_lane[lane_key]

        def _lane_provider_source_for_lane(lane_id: str) -> str:
            lane_key = str(lane_id or "").strip()
            _lane_provider_for_lane(lane_key)
            return phase1_lane_provider_source_by_lane[lane_key]

        prev_whole_run_env = os.environ.get("APPS_RG_WHOLE_RUN_ENVELOPE")
        prev_corr_env = os.environ.get("APPS_RG_CORRELATED_CLI_RUN")
        prev_graph_allocation_env = {
            ALLOCATION_PLAN_ENV: os.environ.get(ALLOCATION_PLAN_ENV),
            ALLOCATION_USAGE_LEDGER_ENV: os.environ.get(ALLOCATION_USAGE_LEDGER_ENV),
            SECTION_EVIDENCE_CONTRACTS_ENV: os.environ.get(SECTION_EVIDENCE_CONTRACTS_ENV),
            SECTION_SOURCE_PLANS_ENV: os.environ.get(SECTION_SOURCE_PLANS_ENV),
            GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV: os.environ.get(
                GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV
            ),
        }
        try:
            rel_art = art.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            rel_art = str(art.resolve()).replace("\\", "/")

        os.environ["APPS_RG_WHOLE_RUN_ENVELOPE"] = "1"
        os.environ["APPS_RG_CORRELATED_CLI_RUN"] = rel_art
        os.environ[ALLOCATION_PLAN_ENV] = resume_graph_allocation_refs["allocation_plan"]
        os.environ[ALLOCATION_USAGE_LEDGER_ENV] = resume_graph_allocation_refs["usage_ledger"]
        os.environ[SECTION_EVIDENCE_CONTRACTS_ENV] = resume_graph_allocation_refs[
            "section_final_evidence_contracts"
        ]
        os.environ[SECTION_SOURCE_PLANS_ENV] = resume_graph_allocation_refs[
            "section_plans"
        ]
        if graph_skill_embedding_required:
            os.environ[GRAPH_SKILL_EMBEDDING_ALLOWLISTS_ENV] = (
                graph_skill_embedding_runtime_refs["lane_allowlists"]
            )

        lane_exec_status: dict[str, str] = {}
        section_call_records: list[dict[str, Any]] = []

        try:
            narrative_upstream: dict[str, tuple[str, tuple[str, ...]]] = {
                narrative: (upstream, tuple(REQUIRED_BULLET_IDS.get(upstream, ())))
                for narrative, upstream in NARRATIVE_UPSTREAM_BULLET_LANE.items()
            }

            phase1_aborted = False
            phase1_abort_reason = ""

            parallel_phase1 = phase1_parallel_enabled(
                profile_flag=bool(profile.parallel_phase1_lanes)
            )
            max_par = resolve_max_parallel(default=int(profile.phase1_max_parallel or 2))
            phase1_allow_exit = resolve_phase1_lane_allow_non_allow_exit_zero(
                bool(profile.phase1_allow_non_allow_exit_zero)
            )

            def _phase1_dispatch_one_lane(**kwargs: Any) -> dict[str, Any]:
                lane = str(kwargs.get("section") or "")
                upstream_spec = narrative_upstream.get(lane)
                if upstream_spec is not None:
                    upstream_lane, expected_ids = upstream_spec
                    if not companion_accepted_in_modular_sections_root(
                        repo,
                        sections_root,
                        upstream_section_id=upstream_lane,
                        expected_bullet_ids=expected_ids,
                    ):
                        emit_integrated_lane_pre_run_failure(
                            sections_root=sections_root,
                            integrated_dir=art,
                            repo_root=repo,
                            lane_id=lane,
                            blocker=PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER,
                            dispatch_result={
                                "fault": "upstream_not_finalized",
                                "upstream_lane": upstream_lane,
                            },
                            lane_exec_status=f"pre_run_blocked:{PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER}",
                        )
                        return {
                            "fault": "upstream_not_finalized",
                            "upstream_lane": upstream_lane,
                            "exit_status": "error",
                        }
                result = dispatch_fn(**kwargs)
                return dict(result) if isinstance(result, dict) else {}

            def _phase1_dependency_ready(lane: str) -> tuple[bool, str]:
                upstream_spec = narrative_upstream.get(lane)
                if upstream_spec is None:
                    return True, ""
                upstream_lane, expected_ids = upstream_spec
                accepted = companion_accepted_in_modular_sections_root(
                    repo,
                    sections_root,
                    upstream_section_id=upstream_lane,
                    expected_bullet_ids=expected_ids,
                )
                return accepted, "" if accepted else PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER

            lane_ctx = LaneExecutionContext(
                sections_root=str(sections_root.resolve()),
                target_company=tc,
                target_role=tr,
                job_description_ref=jd_ref,
                job_description_text=jd_txt,
                manual_brief=br_dispatch,
                lane_provider=_lane_provider_for_lane,
                lane_provider_resolution_source=_lane_provider_source_for_lane,
                lane_x1d_judges=_lane_x1d_judges,
                lane_mock_judges=lane_mock_j_for_phase1,
                lane_allow_non_allow_exit_zero=phase1_allow_exit,
                integrated_artifact_dir=str(art),
                run_id=str(run_id),
                canonical_run_identity=dict(input_package.canonical_run_identity),
            )

            if parallel_phase1:
                outcomes = dispatch_phase1_lanes_managed(
                    GENERATED_LANES,
                    lane_ctx,
                    dispatch_fn=_phase1_dispatch_one_lane,
                    parallel=True,
                    max_parallel=max_par,
                    dependency_ready_fn=_phase1_dependency_ready,
                )
                for lane, oc in outcomes.items():
                    lane_dispatch_results[lane] = dict(oc.dispatch_result)
                    if oc.exec_status.startswith("pre_run_blocked:"):
                        lane_exec_status[lane] = oc.exec_status
                        blocker = oc.exec_status.removeprefix("pre_run_blocked:") or PHASE1_PRIOR_LANE_FAILED_BLOCKER
                        emit_integrated_lane_pre_run_failure(
                            sections_root=sections_root,
                            integrated_dir=art,
                            repo_root=repo,
                            lane_id=lane,
                            blocker=blocker,
                            dispatch_result=lane_dispatch_results[lane],
                            lane_exec_status=oc.exec_status,
                        )
                        continue
                    lane_exec_status[lane] = EvaluationService.phase1_lane_dispatch_status(
                        lane_dispatch_results[lane]
                    )
                    if oc.exec_status.startswith("error:") and not lane_dispatch_results[lane].get("fault"):
                        lane_exec_status[lane] = oc.exec_status
            else:
                for lane in GENERATED_LANES:
                    os.environ[MODULAR_R4_SECTIONS_ROOT_ENV] = str(sections_root.resolve())
                    if phase1_aborted:
                        emit_integrated_lane_pre_run_failure(
                            sections_root=sections_root,
                            integrated_dir=art,
                            repo_root=repo,
                            lane_id=lane,
                            blocker=PHASE1_PRIOR_LANE_FAILED_BLOCKER,
                            dispatch_result={"prior_abort": phase1_abort_reason},
                            lane_exec_status=f"pre_run_blocked:{PHASE1_PRIOR_LANE_FAILED_BLOCKER}",
                        )
                        lane_exec_status[lane] = f"pre_run_blocked:{PHASE1_PRIOR_LANE_FAILED_BLOCKER}"
                        continue
                    upstream_spec = narrative_upstream.get(lane)
                    if upstream_spec is not None:
                        upstream_lane, expected_ids = upstream_spec
                        if not companion_accepted_in_modular_sections_root(
                            repo,
                            sections_root,
                            upstream_section_id=upstream_lane,
                            expected_bullet_ids=expected_ids,
                        ):
                            emit_integrated_lane_pre_run_failure(
                                sections_root=sections_root,
                                integrated_dir=art,
                                repo_root=repo,
                                lane_id=lane,
                                blocker=PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER,
                                dispatch_result={
                                    "fault": "upstream_not_finalized",
                                    "upstream_lane": upstream_lane,
                                },
                                lane_exec_status=f"pre_run_blocked:{PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER}",
                            )
                            lane_dispatch_results[lane] = {
                                "fault": "upstream_not_finalized",
                                "upstream_lane": upstream_lane,
                                "exit_status": "error",
                            }
                            lane_exec_status[lane] = f"pre_run_blocked:{PRE_RUN_UPSTREAM_NOT_FINALIZED_BLOCKER}"
                            continue
                    outcome = run_lane_in_context(
                        lane_ctx,
                        lane,
                        dispatch_fn=_phase1_dispatch_one_lane,
                    )
                    lane_dispatch_results[lane] = dict(outcome.dispatch_result)
                    lane_exec_status[lane] = (
                        outcome.exec_status
                        if outcome.exec_status.startswith("error:")
                        else EvaluationService.phase1_lane_dispatch_status(lane_dispatch_results[lane])
                    )
                    if product_fail_closed_runtime() and phase1_dispatch_hard_failed(
                        lane_dispatch_results[lane]
                    ):
                        phase1_aborted = True
                        phase1_abort_reason = f"dispatch_failed:{lane}:{lane_exec_status[lane]}"

            product_fail_closed = product_fail_closed_runtime()
            for lane in GENERATED_LANES:
                run_dir = cls.materialize_lane_run_dir(
                    repo=repo,
                    sections_root=sections_root,
                    integrated_dir=art,
                    lane=lane,
                    lane_provider=_lane_provider_for_lane(lane),
                    lane_dispatch_results=lane_dispatch_results,
                    lane_exec_status=lane_exec_status,
                    emit_integrated_lane_pre_run_failure_fn=emit_integrated_lane_pre_run_failure,
                    product_fail_closed=product_fail_closed,
                )
                if run_dir is not None:
                    lane_run_dirs[lane] = run_dir

            inv_extra: dict[str, Any] = {
                "run_id": run_id,
                "lane_status": lane_exec_status,
                "sections_root_rel": sections_root.resolve().relative_to(repo.resolve()).as_posix(),
                "phase1_parallel_enabled": parallel_phase1,
                "phase1_max_parallel": max_par if parallel_phase1 else 1,
                "phase1_allow_non_allow_exit_zero_effective": phase1_allow_exit,
                "phase1_lane_provider_global_override": str(profile.phase1_lane_provider or ""),
                "phase1_lane_provider_by_lane": {
                    lane: _lane_provider_for_lane(lane) for lane in GENERATED_LANES
                },
                "phase1_lane_provider_resolution_source_by_lane": {
                    lane: _lane_provider_source_for_lane(lane) for lane in GENERATED_LANES
                },
                "phase1_anthropic_limit_preflight": resolve_anthropic_limit_preflight_route().to_dict(),
                "phase1_anthropic_limit_preflight_by_lane": {
                    lane: phase1_anthropic_limit_preflight_by_lane.get(lane, {})
                    for lane in GENERATED_LANES
                },
                "resume_graph_allocation_plan_digest": resume_graph_allocation_digest,
                "resume_graph_allocation_refs": resume_graph_allocation_refs,
                "graph_skill_embeddings_required": graph_skill_embedding_required,
                "graph_skill_embedding_allowlists_digest": graph_skill_embedding_allowlists_digest,
                "graph_skill_embedding_runtime_refs": graph_skill_embedding_runtime_refs,
            }
            if lane_targeting is not None:
                inv_extra["lane_argv_targeting"] = asdict(lane_targeting)

            # Write phase1 lane inventory
            from apps_rg.l2_recipe.artifact_assembler import ArtifactAssembler

            ArtifactAssembler.write_json(
                modular_root / "phase1_lane_inventory.json",
                inv_extra,
            )

            sc_req = profile.self_consistency_requested
            sc_exe = 0
            for i, lane in enumerate(GENERATED_LANES):
                prof = _lane_provider_for_lane(lane)
                rd = lane_run_dirs.get(lane)
                if rd is None or not rd.is_dir():
                    pre_run = None
                    try:
                        from apps_rg.runtime.integrated_lane_evidence_packaging import (
                            load_integrated_lane_pre_run_failure,
                        )

                        pre_run = load_integrated_lane_pre_run_failure(art, lane)
                    except ImportError:
                        pre_run = None
                    decisive = str((pre_run or {}).get("blocker") or "PHASE1_NO_RUN_DIR")
                    section_call_records.append(
                        cls.phase1_missing_lane_record(
                            lane,
                            i,
                            sc_req,
                            sc_exe,
                            prof,
                            decisive_reason_code=decisive,
                        ),
                    )
                    continue
                section_call_records.append(
                    build_section_provider_call_record(
                        lane=lane,
                        candidate_index=i,
                        run_dir=rd,
                        artifact_dir=art,
                        self_consistency_requested=sc_req,
                        self_consistency_executed=sc_exe,
                        provider_profile=prof,
                    ),
                )

        finally:
            if prev_whole_run_env is None:
                os.environ.pop("APPS_RG_WHOLE_RUN_ENVELOPE", None)
            else:
                os.environ["APPS_RG_WHOLE_RUN_ENVELOPE"] = prev_whole_run_env
            if prev_corr_env is None:
                os.environ.pop("APPS_RG_CORRELATED_CLI_RUN", None)
            else:
                os.environ["APPS_RG_CORRELATED_CLI_RUN"] = prev_corr_env
            for key, previous in prev_graph_allocation_env.items():
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous
            if prev_env is None:
                os.environ.pop(MODULAR_R4_SECTIONS_ROOT_ENV, None)
            else:
                os.environ[MODULAR_R4_SECTIONS_ROOT_ENV] = prev_env

        return (
            lane_run_dirs,
            lane_exec_status,
            section_call_records,
            resume_graph_allocation_digest,
            resume_graph_allocation_refs,
            graph_skill_embedding_required,
            graph_skill_embedding_allowlists_digest,
            graph_skill_embedding_runtime_refs,
        )


__all__ = ["SectionGenerationService"]
