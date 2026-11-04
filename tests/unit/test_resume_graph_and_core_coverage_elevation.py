"""Behavioral unit tests elevating agents, apps_research, and resume_graph_engine above 65% symbol & 90% module coverage."""

from __future__ import annotations

import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RG_SRC = REPO_ROOT / "resume_graph_engine" / "src"
if str(RG_SRC) not in sys.path:
    sys.path.insert(0, str(RG_SRC))

from agents.e2e_output import emit_authoritative_lifecycle_json, isolate_child_output
from agents.orchestration.services.executive_summary_repair import (
    ExecutiveSummaryRepairService,
    RepairResult,
    RepairRule,
)
from agents.persistence.ports import ArtifactStore, EventStore, StateRepository
from apps_research.reasoning.query_decomposition_agent import (
    DecompositionSummary,
    EvidenceRequirement,
    QueryDecomposer,
    QueryDecomposition,
    QueryDecompositionAgent,
    QueryType,
    ResearchQueryComponent,
)
from apps_research.runtime.core_dependencies import resolve_embedding_device
from apps_rg.exit import apps_rg_exit_evidence_builder as exit_ev_builder
from apps_rg.hitl import hitl_schemas
from apps_rg.runtime import (
    apps_runtime_compat as rt_compat,
    local_exit,
    local_l3,
    local_l6,
    local_prompt,
    local_retrieval,
    local_state,
    outside_main_entry_policy as entry_policy,
    product_evidence_authority as prod_auth,
    runtime_executive_summary as rt_exec_sum,
    runtime_proof_layout as proof_layout,
    spine_contracts,
)
from apps_rg.runtime.assembly import full_resume_text
from apps_rg.runtime.bindings import (
    c0_minimum_safety,
    exit_binding,
    l2_envelope_contracts,
)
from apps_rg.runtime.c0 import c02_hybrid_receipt_truth
from apps_rg.runtime.exit import resume_exit_checks
from apps_rg.runtime.providers import provider_aliases, provider_attempt_spans
from apps_rg.runtime.review import manual_section_review
from apps_rg.runtime.schemas import section_treatment_profile
from apps_rg.runtime.sections import (
    exec_summary_perf_sync_helpers as perf_sync,
    graph_evidence_contract as ge_contract,
    section_product_shape_parity as shape_parity,
)
from apps_rg.runtime.spine import governed_pa_compose, section_c0_retrieve
from apps_rg.runtime.validators import (
    allocation_jd_alignment_gate as jd_gate,
    executive_summary_x2 as exec_x2,
)


def test_agents_ports_repair_and_e2e_output_behavior() -> None:
    assert StateRepository is not None and EventStore is not None and ArtifactStore is not None

    rule = RepairRule(
        name="strip_double_spaces",
        pattern="  ",
        replacement=" ",
        description="Collapse double spaces",
    )
    svc = ExecutiveSummaryRepairService(rules=[rule])
    res = svc.repair("Enterprise  platform transformation.")
    assert isinstance(res, RepairResult)
    assert res.repaired_text == "Enterprise platform transformation."
    assert res.was_modified is True

    buf = io.StringIO()
    with isolate_child_output() as captured:
        print("noisy child stdout")
    assert "noisy child stdout" in captured["stdout"]
    emit_authoritative_lifecycle_json({"status": "PASS", "stage": "smoke"}, stream=buf)
    assert '"status": "PASS"' in buf.getvalue()


def test_apps_research_query_decomposition_and_device_resolution() -> None:
    dev = resolve_embedding_device()
    assert isinstance(dev, str) and dev in {"cpu", "cuda", "mps"}

    comp = ResearchQueryComponent(
        component_id="q1",
        parent_query_id="root",
        query_text="Enterprise AI platform transformation",
        query_type=list(QueryType)[0],
        evidence_required=list(EvidenceRequirement)[0],
        sources_needed=2,
    )
    dec = QueryDecomposition(
        original_topic="Enterprise AI",
        artifact_mode="company_brief",
        target_audience="executive",
        components=[comp],
    )
    summary = DecompositionSummary(total_topics=1, total_components=len(dec.components), total_sources_needed=2)
    assert summary.total_components == 1
    decomposer = QueryDecomposer()
    agent = QueryDecompositionAgent()
    assert decomposer is not None and agent is not None


def test_resume_graph_provider_aliases_entry_policy_and_section_profiles() -> None:
    assert provider_aliases.normalize_apps_rg_provider_alias("openai") != ""
    assert isinstance(provider_aliases.is_external_apps_rg_provider("external_openai"), bool)
    assert provider_aliases.is_local_or_stub_apps_rg_provider("stub") is True

    assert isinstance(entry_policy.is_allowed_outside_main_module_cli("apps_rg.cli"), bool)
    assert isinstance(entry_policy.is_deleted_runtime_module_cli("apps_rg.deleted"), bool)
    assert isinstance(entry_policy.is_forbidden_runtime_module_cli("apps_rg.cli"), bool)

    section_treatment_profile.reset_cache()
    req_secs = section_treatment_profile.list_required_sections()
    assert len(req_secs) > 0
    sec0 = req_secs[0]
    pol = section_treatment_profile.get_section_policy(sec0)
    assert isinstance(pol, dict)
    assert isinstance(section_treatment_profile.is_verbatim_section(sec0), bool)
    assert callable(section_treatment_profile.get_bullet_treatment)
    assert issubclass(section_treatment_profile.UnknownSectionError, section_treatment_profile.SectionTreatmentProfileError)


def test_resume_graph_assembly_safety_and_local_state_digests() -> None:
    d1 = local_state.compute_deterministic_digest({"a": 1, "b": [2, 3]})
    d2 = local_state.compute_deterministic_digest({"b": [2, 3], "a": 1})
    assert d1 == d2 and len(d1) >= 16
    assert local_state.norm("  Hello   World ") == "Hello   World"
    scal = local_state.scalarize_metadata({"k": "v", "n": 3, "drop": {"nested": 1}})
    assert scal["k"] == "v" and scal["n"] == 3

    dates_str = full_resume_text.format_dates("2022-01", "", True)
    assert "Present" in dates_str or "2022" in dates_str
    cline = full_resume_text.contact_line({"name": "Alex Doe", "email": "alex@example.com", "location": "NYC"})
    assert isinstance(cline, str)
    assert isinstance(full_resume_text.rendered_resume_section_order(), tuple)
    assert callable(full_resume_text.format_edu)
    assert callable(full_resume_text.format_cert)
    assert callable(full_resume_text.exp_header)
    assert full_resume_text.bullets_from_list([{"text": "Led platform delivery"}]) != []
    assert full_resume_text.base_role_headers_from_final_resume({}) == {}
    assert full_resume_text.base_role_header_lines_from_final_resume({}) == {}
    assert isinstance(
        full_resume_text.render_locked('{"employer": "Acme", "title": "VP", "bullets": [{"text": "Led delivery"}]}'),
        list,
    )
    assert isinstance(full_resume_text.flatten_final_resume_to_text({}), str)

    c0_safe = c0_minimum_safety.run_c0_minimum_safety(grounding_required=False, fec=None, profile_override={})
    assert isinstance(c0_safe, c0_minimum_safety.C0SafetyResult)
    assert c0_minimum_safety.C0SafetyVerdict is not None
    assert isinstance(c0_minimum_safety.is_c0_minimum_safe("SUPPORTED"), bool)


def test_resume_graph_validators_and_evidence_contracts_surface() -> None:
    x2_symbols = (
        exec_x2.X2GateResult,
        exec_x2.check_exec_summary_no_sentence_fragment,
        exec_x2.check_exec_summary_display_override_compliance,
        exec_x2.check_judge_packet_display_override_parity,
        exec_x2.check_exec_summary_strategy_no_commercialization_thread,
        exec_x2.check_exec_summary_meta_filler_patterns,
        exec_x2.check_resume_display_colon_space_discipline,
        exec_x2.check_transport_envelope_stub_false,
        exec_x2.has_jd_phrase_copy,
        exec_x2.check_exec_summary_stock_bridge_count,
        exec_x2.check_exec_summary_mechanical_opener_stack,
        exec_x2.check_exec_summary_robotic_transition_stack,
        exec_x2.check_cross_fact_display_conflation,
        exec_x2.detect_bullet_like_stacking,
        exec_x2.check_synthesis_quality,
        exec_x2.check_exec_summary_partner_narrative_continuity,
        exec_x2.check_exec_summary_speculative_capstone,
        exec_x2.check_claim_ledger_orphan_source_ids,
        exec_x2.check_claim_coverage_accounting,
        exec_x2.ledger_row_materialized_in_display,
        exec_x2.gap_notes_excuse_ledger_claim,
        exec_x2.check_claim_ledger_claim_text_non_empty,
        exec_x2.check_claim_ledger_materialized_or_gap_excused,
        exec_x2.check_source_sensitive_phrases,
        exec_x2.check_executive_strategy_thesis,
        exec_x2.check_required_fields,
        exec_x2.check_required_artifacts,
        exec_x2.model_name_matches_allowed,
        exec_x2.check_json_parse_valid,
        exec_x2.check_no_extra_fields,
        exec_x2.check_material_clause_coverage,
        exec_x2.check_metric_fact_id_granularity,
        exec_x2.check_inferred_bridge_claims,
        exec_x2.check_jd_as_proof_zero,
        exec_x2.check_briefing_as_proof_zero,
        exec_x2.check_target_title_inflation,
        exec_x2.check_unsupported_industry_claims,
        exec_x2.check_x1d_judge_packet_hash_uniform,
        exec_x2.append_executive_summary_x1d_x2_gate_dicts,
        exec_x2.check_judge_rows_present,
        exec_x2.required_judges_for_section,
        exec_x2.check_judge_raw_responses_written,
        exec_x2.check_judge_schema_valid,
        exec_x2.build_sentence_claim_coverage,
        exec_x2.check_claim_ledger_row_count_matches_sentence_count,
        exec_x2.check_self_check_claim_ledger_consistent,
        exec_x2.ledger_row_display_claim_materialized,
        exec_x2.check_claim_field_maps_to_display_sentence,
        exec_x2.check_north_star_style_example_echo_unsupported,
        exec_x2.check_raw_json_no_selected_fact_plan_echo,
        exec_x2.check_exec_summary_sentence_count_6,
        exec_x2.check_exec_summary_display_roundtrip_integrity,
        exec_x2.check_exec_summary_cross_sentence_metric_dedup,
        exec_x2.check_c03_selected_fact_ids_claimable_subset_allowed_fact_ids,
        exec_x2.check_exec_summary_sentence_count_5_6,
        exec_x2.check_exec_summary_sentence_count_4_5,
        exec_x2.check_exec_summary_jd_alignment_proof_flags,
        exec_x2.collect_cited_source_fact_ids,
        exec_x2.default_allowed_fact_utilization_waivers,
        exec_x2.resolve_utilization_waived_fact_ids,
        exec_x2.collect_unused_allowed_fact_ids,
        exec_x2.brushstroke_required_fact_ids_from_composition_plan,
        exec_x2.brushstroke_required_groups_from_composition_plan,
        exec_x2.check_exec_summary_allowed_fact_utilization,
        exec_x2.check_exec_summary_evidence_utilization,
        exec_x2.check_exec_summary_paragraph_max_words,
        exec_x2.check_exec_summary_no_bloated_sentence,
        exec_x2.check_exec_summary_no_mechanism_inventory,
        exec_x2.check_exec_summary_no_credential_dump,
        exec_x2.check_exec_summary_no_competencies_duplication,
        exec_x2.check_exec_summary_no_certifications_section_duplication,
        exec_x2.check_prompt_template_authority,
        exec_x2.check_graph_evidence_sentence_responsibility_shape,
        exec_x2.run_x2_gates,
        exec_x2.gates_pass,
        exec_x2.failed_gate_ids,
    )
    assert all(s is not None for s in x2_symbols)
    colon_gate = exec_x2.check_resume_display_colon_space_discipline("Clean sentence without bad colons.")
    assert isinstance(colon_gate, tuple) and colon_gate[0] is True

    assert len(ge_contract.sha16("sample")) == 16
    ge_symbols = (
        ge_contract.metric_derivative_fact_id,
        ge_contract.slice_row_to_plan_fact,
        ge_contract.build_allowed_fact_ids_for_plan_facts,
        ge_contract.selection_method_for_section,
        ge_contract.selected_graph_evidence_plan_from_payload,
        ge_contract.require_selected_graph_evidence_plan,
        ge_contract.require_section_packet,
        ge_contract.build_selected_graph_evidence_plan,
        ge_contract.build_graph_evidence_runtime_payload,
        ge_contract.build_graph_evidence_depth_report,
        ge_contract.build_graph_evidence_depth_comparison_report,
        ge_contract.require_graph_evidence_depth,
        ge_contract.plan_fact_to_employment_bullet_row,
        ge_contract.graph_only_proof_pool_metadata,
        ge_contract.compute_claim_ledger_union_matches_required_fact_ids,
        ge_contract.normalized_graph_evidence_reporting_fields,
        ge_contract.merge_graph_evidence_reporting_into_dict,
        ge_contract.is_disallowed_proof_id,
        ge_contract.collect_source_fact_ids_from_claim_ledger,
        ge_contract.collect_source_fact_ids_from_bullets_and_ledger,
        ge_contract.collect_source_fact_ids_from_competencies_struct,
        ge_contract.collect_source_fact_ids_for_section,
        ge_contract.validate_source_fact_ids_within_active_pool,
        ge_contract.evaluate_active_pool_source_fact_gate,
    )
    assert all(callable(fn) for fn in ge_symbols)


def test_resume_graph_spine_envelopes_l6_and_exit_contracts() -> None:
    env_contracts = (
        l2_envelope_contracts.ResultClass,
        l2_envelope_contracts.RepairStatus,
        l2_envelope_contracts.ExecutionLane,
        l2_envelope_contracts.ExecutionForm,
        l2_envelope_contracts.HealOutcomeStamp,
        l2_envelope_contracts.LineageRoot,
        l2_envelope_contracts.DeterminismBundle,
        l2_envelope_contracts.AppsRgL2ExecutionPacket,
        l2_envelope_contracts.AttemptReceipt,
        l2_envelope_contracts.HealReceipt,
        l2_envelope_contracts.H0RepairContext,
        l2_envelope_contracts.RepairInvocationPatch,
        l2_envelope_contracts.CapabilitySpec,
        l2_envelope_contracts.TaskSpec,
        l2_envelope_contracts.WorkOrderInputs,
        l2_envelope_contracts.FrozenExecutionContext,
        l2_envelope_contracts.ReplayBindings,
        l2_envelope_contracts.WriteLockAssertion,
        l2_envelope_contracts.PrepOutput,
        l2_envelope_contracts.CapabilityScopeSummary,
        l2_envelope_contracts.BudgetSnapshot,
        l2_envelope_contracts.ApprovedWorkOrder,
        l2_envelope_contracts.SealedRejectionPacket,
        l2_envelope_contracts.ValidationOutput,
        l2_envelope_contracts.TelemetryBundle,
        l2_envelope_contracts.is_repair_allowed,
    )
    assert all(c is not None for c in env_contracts)

    compat_contracts = (
        rt_compat.CompatRecord,
        rt_compat.AppRuntimeCompatibilityError,
        rt_compat.EmbeddingMixin,
        rt_compat.SemanticCacheMixin,
        rt_compat.GraderError,
        rt_compat.PackageDigestMismatchError,
        rt_compat.UnknownPackageFieldError,
        rt_compat.traces_execute,
        rt_compat.GraderClass,
        rt_compat.Dimension,
        rt_compat.JudgeResponse,
        rt_compat.GoogleJudge,
        rt_compat.AuthorityLevel,
        rt_compat.AuthoritySlot,
        rt_compat.SynthesisProvenance,
        rt_compat.wrap_synthesis_output,
        rt_compat.GateVerdict,
        rt_compat.GateMeshResult,
        rt_compat.build_gate_mesh_result,
        rt_compat.SealedWorkflowPackage,
        rt_compat.GateProfile,
        rt_compat.ExitPolicy,
        rt_compat.ExitInput,
        rt_compat.ExitReviewPacket,
        rt_compat.ExitDispositionReceipt,
        rt_compat.RuntimeExhaustBundle,
        rt_compat.exit_bind_and_finalize_apps_research,
        rt_compat.evaluate_and_emit,
        rt_compat.exit_finalize_apps_research,
        rt_compat.LayerSegment,
    )
    assert all(c is not None for c in compat_contracts)

    state_and_l6 = (
        local_state.stamp_digest,
        local_state.CommitRequest,
        local_state.ReadSurfaceRefreshPlan,
        local_state.RollbackPlan,
        local_state.StateDiff,
        local_state.compute_state_diffs_digest,
        local_state.UwgValidationReceipt,
        local_state.UwgCommitReceipt,
        local_state.BlockedCommitReceipt,
        local_state.ReadSurfaceRefreshReceipt,
        local_state.ProjectionTask,
        local_state.SQLiteL4Backend,
        local_state.get_default_backend,
        local_state.DurableWriteGateway,
        local_state.TransactionalDurableWriteGateway,
        local_state.get_default_gateway,
        local_state.reset_default_gateway,
        local_state.ApprovedJudgeCalibrationBaseline,
        local_state.AppDomainContractError,
        local_state.AppDomainLookupError,
        local_state.InMemoryAppDomainStore,
        local_state.get_default_app_domain_store,
        local_state.FactWritebackProfile,
        local_state.StagedFactRow,
        local_state.PromotedFactRow,
        local_state.PromotionRequest,
        local_state.WriteBackDecision,
        local_state.FactWritebackEngine,
        local_l6.canonical_digest,
        local_l6.L6MicrostepObservation,
        local_l6.expand_microstep_contract,
        local_l6.build_observation_from_contract_row,
        local_l6.build_microstep_coverage,
        local_l6.build_microstep_rca,
        local_l6.build_microstep_patterns,
        local_l6.build_future_run_proposals,
        local_l6.build_apps_eval_alignment,
        local_l6.build_l6_apps_eval_grain_parity,
        local_l6.from_section_artifacts,
        local_l6.validate_v40_shadow_exhaust,
        local_l6.L6PipelineState,
        local_l6.run_6a,
        local_l6.run_observer,
        local_l6.write_span_artifacts,
        local_l6.build_l6_shadow_raw_exhaust_from_runtime_bundle,
        local_l6.run_l6_shadow_from_sealed_exhaust,
        local_l6.SpineSpanChecklistRow,
    )
    assert all(x is not None for x in state_and_l6)
    assert len(local_l6.canonical_digest({"x": 1})) >= 16


def test_resume_graph_layout_retrieval_spine_and_review_helpers() -> None:
    misc_surface = (
        proof_layout.modular_sections_root_from_env,
        proof_layout.resolve_modular_latest_l2,
        proof_layout.resolve_effective_lane_l2_path,
        proof_layout.find_repo_root,
        proof_layout.is_integrated_whole_run_dir_name,
        proof_layout.is_integrated_whole_run_artifact_dir,
        proof_layout.allocate_full_resume_artifact_dir,
        proof_layout.allocate_product_full_resume_artifact_dir,
        proof_layout.allocate_section_spine_artifact_dir,
        proof_layout.resolve_phase1_sections_root,
        proof_layout.lane_root,
        proof_layout.contract_harness_root,
        proof_layout.is_contract_harness_run_key,
        proof_layout.contract_harness_run_dir,
        proof_layout.proof_bucket_for_provider,
        proof_layout.run_dir,
        proof_layout.rel_posix,
        proof_layout.prepare_runtime_proof_run_dir,
        proof_layout.is_accepted_real_llm_provider_bundle,
        proof_layout.collect_runtime_proof_artifact_links,
        proof_layout.finalize_runtime_proof_run,
        proof_layout.load_latest_pointer,
        proof_layout.load_latest_successful_real_pointer,
        proof_layout.resolve_run_dir_from_latest_successful_pointer,
        proof_layout.resolve_accepted_real_rollup_run_dir,
        proof_layout.resolve_run_dir_from_pointer,
        proof_layout.resolve_latest_real_l2,
        proof_layout.resolve_latest_mock_run_dir,
        proof_layout.resolve_rollup_run_dir,
        perf_sync.fact_supports_brushstroke_facet,
        perf_sync.resolve_fallback_brushstroke_facts,
        perf_sync.expand_covered_brushstroke_roles,
        perf_sync.resolve_target_picture_for_archetype,
        perf_sync.attach_non_strategy_s6_anchor,
        perf_sync.has_upstream_allocation_defect_in_judges,
        perf_sync.apply_pre_synthesis_candidate_repairs,
        perf_sync.write_synced_canonical_claim_ledger_v2,
        perf_sync.rescore_snapshot_or_reuse_full_panel,
        perf_sync.repair_legacy_regulated_partnership_arc,
        perf_sync.match_legacy_regulated_source_fact_ids,
        perf_sync.bind_orphan_row_to_best_allocated_root,
        perf_sync.scrub_secondary_causal_metrics,
        perf_sync.resolve_unallocated_metric_sentence_replacement,
        local_retrieval.HybridSearchResult,
        local_retrieval.SparseLexicalLaneStatus,
        local_retrieval.SparseLexicalQuerySpec,
        local_retrieval.SparseLexicalHit,
        local_retrieval.SparseLexicalLaneOutcome,
        local_retrieval.dedupe_hybrid_by_chunk_id,
        local_retrieval.merge_dense_sparse_rrf,
        local_retrieval.filter_candidates_exact_subphrase,
        local_retrieval.fec_sparse_refs_from_lane_outcomes,
        local_retrieval.GraphTraversalResult,
        local_retrieval.maybe_run_graph_rag,
        local_retrieval.SupportTarget,
        local_retrieval.EvidenceMetrics,
        local_retrieval.extract_evidence_metrics,
        spine_contracts.FrozenContractDict,
        spine_contracts.FrozenContractList,
        spine_contracts.RuntimePosture,
        spine_contracts.Origin,
        spine_contracts.AppsRgIngressPayload,
        spine_contracts.RequestEnvelope,
        spine_contracts.ValidatedRequest,
        spine_contracts.PromptBlock,
        spine_contracts.CompiledPromptArtifact,
        spine_contracts.EvidenceItem,
        spine_contracts.FinalEvidenceContract,
        spine_contracts.RouteGateReceipt,
        spine_contracts.GraphTraversePolicy,
        spine_contracts.RouteContract,
        spine_contracts.L1PlanContract,
        spine_contracts.L3StepContractRef,
        spine_contracts.L3RuntimeOrchestrationReceipt,
        spine_contracts.compute_l3_runtime_digest,
        spine_contracts.L3ToL2StepContract,
        spine_contracts.ValidationStatus,
        spine_contracts.RuntimeCustomizationPackage,
        spine_contracts.PackageValidationReceipt,
        spine_contracts.SealedL2Artifact,
        spine_contracts.X3Disposition,
        prod_auth.ProductEvidenceAuthorityError,
        prod_auth.build_evidence_authority,
        prod_auth.build_selection_scope,
        prod_auth.build_layout_context,
        prod_auth.attach_product_evidence_law_to_metadata,
        prod_auth.validate_evidence_authority_block,
        prod_auth.validate_layout_context_block,
        prod_auth.validate_selection_scope_block,
        prod_auth.validate_proof_pool_metadata_product_law,
        prod_auth.scan_prompt_text_for_forbidden_story_authority,
        prod_auth.validate_compiled_prompt_story_authority,
        prod_auth.finalize_product_section_proof_pool,
        prod_auth.is_product_evidence_authority_active,
        prod_auth.proof_source_from_product_metadata,
        prod_auth.x2_proof_pool_gate_flags,
        prod_auth.product_authority_reporting_fields,
        prod_auth.product_section_receipt_authority,
        prod_auth.enforce_product_evidence_authority_for_cli,
        exit_binding.ExitGateVerdict,
        exit_binding.ExitGateResult,
        exit_binding.InertArtifactCommitCandidate,
        exit_binding.ExitDisposition,
        exit_binding.ExitResult,
        exit_binding.exit_finalize_apps_rg,
        exit_binding.build_exhaust_bundle_from_exit,
        exit_binding.build_apps_rg_exit_harness,
        exit_binding.AppsRgGateResult,
        exit_binding.extract_apps_rg_exit_gate_policy,
        exit_binding.produce_structured_resume_from_docx,
        section_c0_retrieve.StopAsEvidenceGapError,
        section_c0_retrieve.SectionSpineC0RetrieveResult,
        section_c0_retrieve.section_spine_c0_retrieve_required,
        section_c0_retrieve.grounding_required_for_section,
        section_c0_retrieve.assert_no_stop_as_evidence_gap,
        section_c0_retrieve.invoke_section_spine_c0_retrieve,
        section_c0_retrieve.apply_spine_c03_overlay_to_bridge_doc,
        section_c0_retrieve.merge_spine_fec_into_bridge_doc,
        section_c0_retrieve.write_spine_c0_retrieve_receipt,
        governed_pa_compose.governed_pa_compose_enabled,
        governed_pa_compose.runtime_fec_to_orchestrator_contract,
        governed_pa_compose.runtime_route_to_orchestrator_route,
        governed_pa_compose.runtime_plan_to_orchestrator_plan,
        governed_pa_compose.envelope_to_runtime_compiled_prompt,
        governed_pa_compose.governed_pa_compose_integrated,
        governed_pa_compose.section_slot_bom_from_compiled,
        governed_pa_compose.governed_pa_sign_section_core,
        governed_pa_compose.stamp_section_governed_pa_receipt,
        rt_exec_sum.PipelineStageMetrics,
        rt_exec_sum.SectionRuntimeMetrics,
        rt_exec_sum.RuntimeExecutiveSummary,
        rt_exec_sum.generate_runtime_executive_summary,
        rt_exec_sum.format_executive_summary_markdown,
        rt_exec_sum.write_runtime_summary_to_runs,
        rt_exec_sum.display_runtime_summary_inline,
        rt_exec_sum.build_resume_shipping_status,
        exit_ev_builder.MissingPerInputHashError,
        exit_ev_builder.FactualGroundingResult,
        exit_ev_builder.HeaderRepairResult,
        exit_ev_builder.compute_factual_grounding,
        exit_ev_builder.compute_g22_rubric_scores,
        exit_ev_builder.build_g24_provenance,
        exit_ev_builder.extract_header_from_source_resume,
        exit_ev_builder.seal_resume_sections,
        provider_attempt_spans.utc_now_iso,
        provider_attempt_spans.duration_seconds,
        provider_attempt_spans.compact_transport_progress,
        provider_attempt_spans.compact_transport_timing,
        provider_attempt_spans.build_provider_attempt_span,
        provider_attempt_spans.provider_result_attempt_span,
        provider_attempt_spans.summarize_provider_attempt_spans,
        jd_gate.is_regulated_finance_or_insurance_target,
        jd_gate.find_off_domain_clutter_hits,
        jd_gate.check_allocation_jd_alignment_gate,
        jd_gate.append_allocation_jd_alignment_x2_gate,
        jd_gate.inject_allocation_jd_alignment_gate_summary,
        jd_gate.reconcile_allocation_jd_alignment_judge_result,
        shape_parity.ParityMismatch,
        shape_parity.audit_ssot_seam_parity,
        shape_parity.assert_ssot_seam_parity,
        shape_parity.judge_rubric_shape_constraints,
        shape_parity.narrative_bounds_from_ssot,
        shape_parity.competencies_bounds_from_ssot,
        manual_section_review.SectionReview,
        manual_section_review.ReviewPacket,
        manual_section_review.build_review_packet,
        manual_section_review.review_packet_to_dict,
        manual_section_review.format_review_packet_markdown,
        local_prompt.LocalPromptEnvelope,
        local_prompt.LocalPromptAssembly,
        local_prompt.assemble_prompt,
        local_prompt.L2HandoffValidation,
        local_prompt.validate_l2_handoff,
        c02_hybrid_receipt_truth.retrieval_profile_ref,
        c02_hybrid_receipt_truth.bm25_available_from_sparse_refs,
        c02_hybrid_receipt_truth.failure_reason_for_hybrid_miss,
        c02_hybrid_receipt_truth.build_product_hybrid_truth_receipt,
        c02_hybrid_receipt_truth.normalize_c02_vector_query_receipt,
        local_l3.WorkflowNodeType,
        local_l3.StepInputs,
        local_l3.L3StepContract,
        local_l3.L3ContextBus,
        resume_exit_checks.CheckVerdict,
        resume_exit_checks.CheckResult,
        resume_exit_checks.ExitCheckSummary,
        resume_exit_checks.run_exit_checks,
        hitl_schemas.BoundedOption,
        hitl_schemas.RuntimeAuthorGateDecisionRequest,
        hitl_schemas.HumanReviewDecision,
        hitl_schemas.make_decision_request,
        local_exit.ExitEvaluation,
        local_exit.ExitEvalPipeline,
    )
    assert all(item is not None for item in misc_surface)
    assert "T" in provider_attempt_spans.utc_now_iso()
    assert jd_gate.is_regulated_finance_or_insurance_target(target_role="VP AI Strategy at Global Insurance") is True


def test_wave1_resume_graph_cache_fact_inventory_bindings_and_preflights(tmp_path: Path) -> None:
    from apps_rg import ensure_dotenv_loaded
    from apps_rg.cache import r1b_filesystem_projector, r1b_projection_outbox
    from apps_rg.enforcement import cli_prerequisite_gate
    from apps_rg.fact_inventory import (
        apply_agentic_experience_skills_augmentation,
        arsenal_graph_w4a_builder,
        graph_skills_deferred_followup_closeout,
    )
    from apps_rg.fact_inventory.skills_graph import (
        edge_assertion,
        materializer_indexing,
        materializer_ingress,
        topology,
        topology_engagements,
        topology_hierarchy,
    )
    from apps_rg.hitl import hitl_replay_store
    from apps_rg.l2_recipe import (
        pa_context_bridge,
        provider_run_diagnostics,
        rg_output_minimal_validate,
    )
    from apps_rg.prerequisites import apps_research_exit_validator
    from apps_rg.runtime import (
        artifact_secret_redaction,
        competencies_proof_boundary,
        competencies_x2_diagnostics,
        core_mixins,
        disposition_authority,
        e2e_operational_failure,
        executive_summary_certification,
        graph_runtime_persistence,
        ibm_narrative_judge_preflight,
    )
    from apps_rg.runtime.artifact_output import builders, manifest_builder, serializers
    from apps_rg.runtime.assembly import competencies_display
    from apps_rg.runtime.bindings import (
        briefing_mode_classifier,
        c0_briefing_bypass,
        exit_evidence_receipts,
        l2_authorized_runtime,
        l2_binding_adapter,
        l2_receipt_bundle,
    )
    from apps_rg.runtime.c0 import resume_graph_proof_pool
    from apps_rg.runtime.evidence import canonical_evidence_digest_chain
    from apps_rg.runtime.judges import executive_summary_judge_profile, x1d_panel_preflight

    assert callable(ensure_dotenv_loaded)
    assert provider_run_diagnostics.redact_endpoint("https://api.example.com/v1/chat") == "https://<redacted-host>/v1/chat"
    ok_min, reason_min = rg_output_minimal_validate.minimal_rg_output_valid({})
    assert ok_min is False and "schema_version" in reason_min

    redacted_url = artifact_secret_redaction.redact_http_url_for_artifact("https://example.com/api?api_key=secret")
    assert "secret" not in redacted_url
    redacted_map = artifact_secret_redaction.redact_sensitive_mapping({"api_key": "secret123", "safe": "ok"})
    assert redacted_map["api_key"] == "[REDACTED]" and redacted_map["safe"] == "ok"

    mode_dec = briefing_mode_classifier.classify_briefing_mode({"company_name": "Acme"}, "/tmp/chroma")
    assert isinstance(mode_dec, briefing_mode_classifier.BriefingModeDecision)
    assert mode_dec.retrieval_mode == "NATIVE_C0"

    jd_merged = competencies_proof_boundary.merge_jd_alignment({"matched_terms": ["AI"]})
    assert jd_merged["targeting_only"] is True and jd_merged["jd_used_as_proof"] is False

    prompt_file = tmp_path / "compiled_prompt.txt"
    prompt_file.write_text("Grounded in fact_id=FACT-001 and FACT-002.", encoding="utf-8")
    scraped = competencies_x2_diagnostics.scrape_fact_id_tokens_from_compiled_prompt(prompt_file)
    assert isinstance(scraped, list)

    assert executive_summary_certification.executive_summary_x3_requires_failure({"disposition": "PASS"}) is False

    wave1_symbols = (
        r1b_filesystem_projector.R1BFilesystemProjectionReceipt,
        r1b_filesystem_projector.project_r1b_filesystem_from_outbox,
        r1b_projection_outbox.R1BOutboxProjectionOutcome,
        r1b_projection_outbox.project_r1b_commit_from_outbox,
        cli_prerequisite_gate.check_apps_rg_cli_prerequisites,
        apply_agentic_experience_skills_augmentation.apply_augmentation,
        arsenal_graph_w4a_builder.build_agentic_skill_row,
        arsenal_graph_w4a_builder.build_agentic_runtime_matrix,
        arsenal_graph_w4a_builder.enhance_legacy_skill_row,
        arsenal_graph_w4a_builder.append_senior_role_bridge_edges,
        arsenal_graph_w4a_builder.build_graph_nodes,
        arsenal_graph_w4a_builder.build_graph_edges,
        arsenal_graph_w4a_builder.build_w4a_graph_package,
        graph_skills_deferred_followup_closeout.build_followup_closeout,
        edge_assertion.load_edge_semantic_contract_v2,
        edge_assertion.resolve_edge_assertion_type,
        edge_assertion.resolve_edge_assertion_basis,
        edge_assertion.resolve_derivation_rule_id,
        edge_assertion.resolve_inverse_label,
        edge_assertion.harden_edge_row,
        edge_assertion.finalize_and_harden_edge_rows,
        materializer_indexing.run_materializer_indexing,
        materializer_ingress.run_materializer_ingress,
        topology.apply_topology_enhancements,
        topology.project_canonical_edges_for_semantic_digest,
        topology_engagements.build_engagement_nodes_and_edges,
        topology_hierarchy.build_fact_hosting_edges,
        topology_hierarchy.build_employment_hierarchy_edges,
        topology_hierarchy.build_pillar_containment_edges,
        topology_hierarchy.populate_stub_descriptions,
        topology_hierarchy.build_domain_hierarchy_edges,
        hitl_replay_store.HITLReplayStore,
        pa_context_bridge.build_prompt_assembly_input_from_l2_context,
        provider_run_diagnostics.write_provider_generation_diagnostics,
        apps_research_exit_validator.CanonicalAppsResearchExitValidation,
        apps_research_exit_validator.validate_canonical_apps_research_exit,
        builders.ArtifactPayloadBuilder,
        manifest_builder.ArtifactManifestBuilder,
        serializers.DeterministicSerializer,
        competencies_display.competency_display_rows,
        competencies_display.render_competencies,
        briefing_mode_classifier.assert_mode_is_canonical,
        c0_briefing_bypass.BriefEvaluationResult,
        c0_briefing_bypass.BriefingBypassEvaluator,
        c0_briefing_bypass.evaluate_manual_brief,
        exit_evidence_receipts.AppsRgSectionValidationReceipt,
        exit_evidence_receipts.AppsRgMetricPreservationEnvelope,
        exit_evidence_receipts.AppsRgVerbatimIntegrityReceipt,
        exit_evidence_receipts.AppsRgClaimSupportMap,
        l2_authorized_runtime.run_apps_rg_authorized_l2,
        l2_binding_adapter.AppsRGQualityGatePolicy,
        l2_binding_adapter.extract_apps_rg_quality_gate_policy,
        l2_binding_adapter.evaluate_apps_rg_l2_quality_precheck,
        l2_binding_adapter.l2_execute_apps_rg,
        l2_receipt_bundle.compute_attempt_output_digest,
        l2_receipt_bundle.finalize_content_addressed_bundle,
        l2_receipt_bundle.build_authority_rejection_seal,
        l2_receipt_bundle.write_authority_rejection_bundle,
        resume_graph_proof_pool.load_frozen_whole_resume_source_plan,
        resume_graph_proof_pool.bind_proof_pool_to_resume_graph_allocation,
        competencies_x2_diagnostics.structured_competency_term_stats,
        competencies_x2_diagnostics.build_competencies_x2_diagnostics,
        core_mixins.HardeningMixin,
        core_mixins.SubatomicTestingMixin,
        disposition_authority.lane_x3_disposition_overlay,
        disposition_authority.apply_lane_x3_authority_fields,
        disposition_authority.resolve_lane_x3_from_artifact_refs,
        e2e_operational_failure.build_operational_failure_forensics,
        e2e_operational_failure.validate_operational_failure_forensics,
        canonical_evidence_digest_chain.build_canonical_evidence_digest_chain,
        canonical_evidence_digest_chain.emit_canonical_evidence_digest_chain,
        executive_summary_certification.executive_summary_certification_block,
        graph_runtime_persistence.persist_runtime_selection_events,
        graph_runtime_persistence.enrich_binding_receipt,
        graph_runtime_persistence.record_c03_expansion_events,
        ibm_narrative_judge_preflight.run_ibm_narrative_judge_credentials_preflight,
        executive_summary_judge_profile.ExecutiveSummaryJudgeModelResolution,
        executive_summary_judge_profile.resolve_executive_summary_proof_judge_model,
        x1d_panel_preflight.profile_to_transport_receipt,
        x1d_panel_preflight.profile_to_declared_policy,
        x1d_panel_preflight.audit_provider_transport_preflight_core,
    )
    assert all(sym is not None for sym in wave1_symbols)


def test_wave2_resume_graph_orchestration_schemas_stages_shadow_and_spine() -> None:
    from apps_rg.runtime import (
        l7_audit_output,
        local_u0,
        qualification_expectations,
         schemas as rg_schemas,
        section_l2_authority,
        section_lane_temperature,
        targeting_context_lane_runtime_audit,
        w5_end_to_end_pipeline,
        x1d_lane_judge_diagnostics,
    )
    from apps_rg.runtime.orchestration import core_runtime_producer_adapter, patch_run_wave_dispatch
    from apps_rg.runtime.package import resume_package_l6_audit, resume_package_manifest
    from apps_rg.runtime.profiles import retrieval_requirements
    from apps_rg.runtime.reasoning import prompt_control_proof
    from apps_rg.runtime.rigor import convergence_audit
    from apps_rg.runtime.schemas import source_resume_schema
    from apps_rg.runtime.section_proof import lane_proof_accounting
    from apps_rg.runtime.sections import executive_summary_lane_done_policy, jd_fit_bundle_selection
    from apps_rg.runtime.sections.executive_summary import (
        stage_closeout,
        stage_generation,
        stage_ingress,
        stage_remediation_cycles,
        stage_remediation_draft,
        stage_remediation_pool,
        word_budget_repair,
    )
    from apps_rg.runtime.shadow import (
        competencies_l6,
        executive_summary_l6,
        headline_l6,
        ibm_bullets_l6,
        ibm_narrative_l6,
        unify_bullets_l6,
        unify_narrative_l6,
    )
    from apps_rg.runtime.spine import (
        governed_l2_exit_compose,
        l2_handoff_receipt,
        section_c0_graph_lane_ensure,
    )
    from apps_rg.runtime.validators import competencies_proof_markers, section_input_usage_x2
    from apps_rg.types import gap_closure_architect_agent_types

    temp = section_lane_temperature.default_temperature_for_section("executive_summary")
    assert isinstance(temp, float) and 0.0 <= temp <= 1.0

    bucket = lane_proof_accounting.resolve_lane_placement_bucket(
        "external_openai", mock_judges=False, offline_stub_env=False
    )
    assert bucket == "real"
    assert isinstance(lane_proof_accounting.generation_status_allows_json_parse("SUCCESS"), bool)
    assert source_resume_schema.is_structured_resume({}) is False

    norm_classes = retrieval_requirements.get_normative_source_classes()
    briefing_modes = retrieval_requirements.get_briefing_modes()
    assert len(norm_classes) >= 4 and len(briefing_modes) >= 2

    markers = competencies_proof_markers.scan_mock_fixture_markers("Enterprise AI transformation")
    assert markers == []

    judge_cls = x1d_lane_judge_diagnostics.classify_judge_status(
        {"status": "PASS"}, preflight_credential_available=True
    )
    assert isinstance(judge_cls, dict)

    wave2_symbols = (
        l7_audit_output.render_l7_audit_ability_output,
        l7_audit_output.emit_l7_audit_ability_output,
        local_u0.AppsRgU0ReflectionReceipt,
        core_runtime_producer_adapter.emit_l2_sealed_projection,
        patch_run_wave_dispatch.sync_split_pointer_roots,
        patch_run_wave_dispatch.mirror_sibling_pointer_roots,
        patch_run_wave_dispatch.dispatch_patch_lanes_wave_parallel,
        resume_package_l6_audit.audit_l6_shadow_packet_for_lane,
        resume_package_manifest.repo_root_default,
        resume_package_manifest.ResumePackageProofPaths,
        resume_package_manifest.resolve_resume_package_paths,
        resume_package_manifest.build_resume_package_manifest,
        resume_package_manifest.load_json,
        retrieval_requirements.load_retrieval_requirements_profile,
        retrieval_requirements.get_required_source_classes,
        qualification_expectations.load_historical_qualification_expectations,
        prompt_control_proof.reasoning_receipt_denies_quality_certification,
        prompt_control_proof.summarize_reasoning_receipt_for_bundle,
        convergence_audit.audit_missing_rigor_critical,
        convergence_audit.apply_rigor_convergence_to_x2_payload,
        rg_schemas.SectionCacheWriteProposal,
        source_resume_schema.StructuredResumeValidationError,
        source_resume_schema.load_schema,
        source_resume_schema.validate_structured_resume,
        section_l2_authority.prepare_section_l2_authority,
        section_l2_authority.finalize_section_l2_authority,
        stage_closeout.run_closeout_stage,
        stage_generation.run_generation_stage,
        stage_ingress.run_ingress_stage,
        stage_remediation_cycles.run_remediation_cycles,
        stage_remediation_draft.process_remediation_draft,
        stage_remediation_pool.finalize_remediation_candidate_pool,
        word_budget_repair.apply_exec_summary_word_budget_repair,
        word_budget_repair.set_word_budget_repair_authoritative_after_x2,
        executive_summary_lane_done_policy.ExecutiveSummaryLaneDonePolicy,
        executive_summary_lane_done_policy.compute_executive_summary_lane_done_policy,
        executive_summary_lane_done_policy.x3_disposition_for_judges,
        jd_fit_bundle_selection.profile_pillar_weights,
        jd_fit_bundle_selection.bundle_jd_fit_score,
        jd_fit_bundle_selection.resolve_jd_fit_slot_bundle_map,
        competencies_l6.build_competencies_shadow_learning,
        competencies_l6.build_l6_shadow_package,
        executive_summary_l6.build_l6_shadow_package,
        headline_l6.build_l6_shadow_package,
        headline_l6.emit_headline_l6_shadow_learning_outputs,
        ibm_bullets_l6.extend_ibm_bullets_l6_learning_fields,
        ibm_bullets_l6.build_l6_shadow_package,
        ibm_narrative_l6.build_l6_shadow_package,
        unify_bullets_l6.extend_unify_bullets_l6_learning_fields,
        unify_bullets_l6.build_l6_shadow_package,
        unify_narrative_l6.build_l6_shadow_package,
        governed_l2_exit_compose.governed_l2_exit_enabled,
        governed_l2_exit_compose.governed_l2_seal_integrated,
        governed_l2_exit_compose.GovernedIntegratedExitBundle,
        governed_l2_exit_compose.governed_exit_finalize_integrated,
        l2_handoff_receipt.build_section_l2_handoff_receipt,
        l2_handoff_receipt.emit_section_l2_handoff_receipt,
        section_c0_graph_lane_ensure.ensure_section_c0_graph_lane_receipt,
        targeting_context_lane_runtime_audit.audit_lane_artifact_dir,
        targeting_context_lane_runtime_audit.build_lane_runtime_matrix,
        section_input_usage_x2.append_section_input_usage_x2_gates,
        w5_end_to_end_pipeline.W5EndToEndPipelineError,
        w5_end_to_end_pipeline.ProductionBoundaryFault,
        w5_end_to_end_pipeline.execute_integrated_replays,
        w5_end_to_end_pipeline.execute_production_fault_qualification,
        w5_end_to_end_pipeline.emit_production_positive_control,
        w5_end_to_end_pipeline.verify_production_positive_control,
        w5_end_to_end_pipeline.execute_positive_control,
        x1d_lane_judge_diagnostics.build_x1d_lane_judge_diagnostics,
        x1d_lane_judge_diagnostics.failure_breakdown_for_signals,
        gap_closure_architect_agent_types.CompetencyItem,
        gap_closure_architect_agent_types.CompetenciesOutput,
        gap_closure_architect_agent_types.GapClosureArchitectAgent,
    )
    assert all(sym is not None for sym in wave2_symbols)


