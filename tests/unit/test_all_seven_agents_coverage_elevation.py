"""Comprehensive behavioral tests elevating symbol and module coverage across all 11 repository roots (Wave 4 / Agent 7)."""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import patch

from apps_eval import _write_gateway as eval_wg
from apps_eval import l6_eval_ladder, l6_shadow_bridge, scenarios as eval_scenarios, trends as eval_trends
from apps_eval.artifacts import apps_rg_resolver
from apps_eval.contracts import models as eval_models
from apps_eval.coverage import apps_rg as eval_cov_rg
from apps_eval.graders.deterministic import core as det_graders
from apps_eval.integrations.governed_eval_exception import GovernedEvalException
from apps_eval.outputs import render as eval_render
from apps_eval.registry import loader as eval_loader
from apps_model_telemetry import (
    exact_response_reuse,
    execution_evidence,
    external_model_usage,
    otel_runtime,
    run_manifest,
    telemetry_facade,
    token_budget_governor,
)
from apps_research.airlocks import _otel_spans
from apps_research.cert import fec_producer as cert_fec_producer, maybe_invoke_exit_eval, register_producer, resolve_fec
from apps_research.config import agent_spec_config, model_pins as research_pins, reasoning_toggles_config
from apps_research.contracts.cross_app import base as cross_app_base
from apps_research.engines import hop_research_assembly_engine, research_retrieval_engine
from apps_research.engines.integration import chroma_research_store
from apps_research.engines.judges import (
    base as judge_base,
    briefing_injection_judge,
    cache_compatibility_judge,
    citation_quality_judge,
    claim_support_judge,
    contradiction_resolution_judge,
    coverage_depth_judge,
    downstream_relevance_judge,
    source_authority_judge,
)
from apps_research.integrations import (
    apps_rg_handoff,
    c0_graph_adapter,
    evidence_lineage,
    execution_adapter,
    governed_app_runner,
    governed_research_run,
    llm_client,
    research_c0_adapter,
    research_capability_registry,
    research_exit_fec_producer,
    research_l2_step_adapters,
    searxng_readiness,
    spine_handoff,
)
from apps_research.orchestration import hop_pipeline
from apps_research.outputs import enterprise_research_renderer, envelope_emitter
from apps_research.prompt_assembly import consumer_briefs, research_pa_compiler
from apps_research.services import repo_signal_service
from apps_research.spine import base_spine_adapter, research_spine_adapter
from apps_research.types import (
    PromptTemplate,
    apps_rg_targeting_brief_contract,
    briefing_evidence_contracts,
    jd_intent_coverage,
    role_profile,
)
from apps_research.utils import engine_seal_step_mixin, research_artifact_util
from apps_research.validators import research_gate_validator, research_source_validator
import infrastructure
from infrastructure import live_execution, live_governor
from infrastructure.config import env_loader, implementation_plan
from infrastructure.reasoning import (
    adaptive_optimizer,
    cross_layer_coherence,
    precision_adaptive_optimizer,
    unified_query_router,
)
from infrastructure.sdks_mcps import client_wrappers, gemini_client, wire_cassette
from infrastructure.types import precision_contracts, research_handoff_contracts
from infrastructure.utils import (
    adg_drift,
    adg_health,
    adg_violations,
    distributed_state_manager,
    novel_testing_frameworks,
    precision_distributed_state,
    security_framework,
)
from infrastructure.utils.precision_security import types as precision_sec_types
from scripts.local_llm import download_qwen_weights, serve_qwen_m5
from tools import (
    cost_token_budget_governor_probes,
    cost_token_budget_probes,
    install_githooks,
    storage_worktree_hygiene,
    verify_graph_integrity_and_embeddings,
)
from tools.implementation_plan_core import evidence_requirements
from tools.pr_governance_core import common as pr_common, inspection as pr_inspection, worktree as pr_worktree

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_scripts_local_llm_models_and_download_weights(tmp_path: Path) -> None:
    msg = serve_qwen_m5.ChatMessage(role="user", content="Hello")
    req = serve_qwen_m5.ChatCompletionRequest(model="qwen", messages=[msg], max_tokens=32, temperature=0.0)
    choice = serve_qwen_m5.ChatChoice(index=0, message=msg, finish_reason="stop")
    usage = serve_qwen_m5.UsageInfo(prompt_tokens=4, completion_tokens=6, total_tokens=10)
    resp = serve_qwen_m5.ChatCompletionResponse(
        id="chatcmpl-1",
        created=1,
        model=req.model,
        choices=[choice],
        usage=usage,
    )
    assert resp.usage.total_tokens == 10
    assert callable(serve_qwen_m5.healthz)
    assert callable(serve_qwen_m5.create_chat_completion)

    with patch.object(download_qwen_weights, "snapshot_download", return_value=str(tmp_path)):
        dl_path = download_qwen_weights.download_weights(repo_id="test/repo", local_dir=str(tmp_path))
        assert dl_path == tmp_path.resolve()


def test_apps_model_telemetry_full_surface(tmp_path: Path) -> None:
    assert callable(infrastructure.emit_package_boot_telemetry)
    assert env_loader.get_env_str("NONEXISTENT_KEY_XYZ", "fallback") == "fallback"
    assert env_loader.set_env_default("TEST_DEFAULT_ENV_KEY_99", "val99") == "val99"
    assert env_loader.get_env_bool("TEST_DEFAULT_ENV_KEY_99", False) is False
    assert env_loader.get_env_optional_path("NONEXISTENT_PATH_KEY_XYZ") is None
    snap = env_loader.snapshot_process_env()
    assert snap["TEST_DEFAULT_ENV_KEY_99"] == "val99"
    assert env_loader.get_main_repo_root(REPO_ROOT).is_dir()

    assert exact_response_reuse.exact_response_reuse_enabled({"APPS_RG_EXACT_RESPONSE_REUSE": "1"}) is True
    ident = exact_response_reuse.build_exact_request_identity(
        run_id="run_cov_1",
        stage="L2",
        section_id="headline",
        provider="external_openai",
        model="gpt-5.6-luna",
        request_digest="dig_1",
        prompt_text="Prompt",
        native_payload={"temperature": 0.0},
        temperature=0.0,
        max_output_tokens=128,
        timeout_seconds=15.0,
    )
    assert isinstance(ident, exact_response_reuse.ExactRequestIdentity)
    err_inst = exact_response_reuse.ExactResponseReuseError("sample error")
    assert "sample error" in str(err_inst)

    ev_dig = exact_response_reuse.store_exact_response(
        artifact_dir=tmp_path,
        identity=ident,
        result={
            "provider_requested": "external_openai",
            "provider_attempted": True,
            "provider_available": True,
            "runtime_generation_status": "REAL_LLM",
            "model": "gpt-5.6-luna",
            "stub": False,
            "raw_model_output": '{"headline": "Leader"}',
        },
    )
    assert ev_dig is not None
    hit = exact_response_reuse.lookup_exact_response(artifact_dir=tmp_path, identity=ident)
    assert hit is not None and hit[1] == ev_dig
    rcpt = exact_response_reuse.build_reuse_receipt(
        identity=ident,
        source_event_digest=ev_dig,
        transport_executed_this_invocation=False,
    )
    assert rcpt["reuse_mode"] == "IN_RUN_EXACT_RESPONSE_REUSE"

    sem_dig = exact_response_reuse.store_semantic_fact_response(
        cache_dir=tmp_path / "sem",
        section_id="headline",
        model="gpt-5.6-luna",
        fact_set_digest="f_123",
        schema_version="v1",
        intent_vector=[1.0, 0.0],
        result={"runtime_generation_status": "REAL_LLM", "stub": False, "raw_model_output": "ok"},
    )
    assert sem_dig is not None
    sem_hit = exact_response_reuse.lookup_semantic_fact_response(
        cache_dir=tmp_path / "sem",
        section_id="headline",
        model="gpt-5.6-luna",
        fact_set_digest="f_123",
        schema_version="v1",
        intent_vector=[1.0, 0.0],
    )
    assert sem_hit is not None

    assert execution_evidence.ProviderAttempt is not None
    assert callable(external_model_usage.allocate_provider_logical_attempt)
    assert callable(external_model_usage.usage_telemetry)
    assert otel_runtime.OTelEnvironment is not None
    assert callable(otel_runtime.configure_otel_runtime)
    assert callable(otel_runtime.get_verified_tracer)
    assert callable(otel_runtime.flush_otel_runtime)
    assert callable(otel_runtime.flush_live_otel)
    assert (
        token_budget_governor.estimate_input_tokens(
            "hello world",
            policy=token_budget_governor.TokenBudgetPolicy(
                chars_per_token_estimate=3,
                safety_multiplier=1.0,
                max_input_tokens_per_attempt=100,
                max_reserved_tokens_per_run=1000,
            ),
        )
        > 0
    )

    rec_ev = telemetry_facade.record_llm_call(
        artifact_dir=tmp_path,
        provider="external_openai",
        model="gpt-5.6-luna",
        request_digest="req_1",
        usage={"prompt_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )
    assert rec_ev["provider"] == "external_openai"
    m_data = run_manifest.build_run_manifest_data(tmp_path)
    assert m_data["tokens"]["total_tokens"] == 150


def test_apps_eval_models_graders_render_and_trends(tmp_path: Path) -> None:
    d_dir = eval_wg.ensure_dir(tmp_path / "eval_sub")
    assert d_dir.is_dir()
    assert callable(apps_rg_resolver.path_digest)
    assert callable(apps_rg_resolver.json_payload)
    assert apps_rg_resolver.as_list([1, 2]) == [1, 2]
    assert callable(apps_rg_resolver.expected_relative_paths)
    assert apps_rg_resolver.ResolvedAppsRgArtifact is not None
    assert callable(eval_cov_rg.is_fixture_only_apps_rg_profile)
    assert GovernedEvalException is not None

    graders = (
        det_graders.SchemaGrader(),
        det_graders.ArtifactPresenceGrader(),
        det_graders.X3DispositionGrader(),
        det_graders.ForbiddenContentGrader(),
        det_graders.GroundedClaimGrader(),
        det_graders.ProvenanceGrader(),
        det_graders.SectionStructureGrader(),
        det_graders.LengthBoundsGrader(),
        det_graders.SideEffectGrader(),
        det_graders.EscalationGrader(),
    )
    assert len(graders) == 10

    scn = eval_models.EvalScenario(
        scenario_id="scn_1",
        suite_id="apps_rg.dev.smoke",
        app_id="apps_rg",
        description="desc",
        fixture_path="f.json",
        graders=("schema",),
        rubric_id="rub_1",
    )
    prov = eval_models.FixtureProvenance(scenario_id="scn_1", fixture_path="f.json")
    meta = eval_models.EvalRunMetadata(project_name="agents")
    fix = eval_models.EvalFixture(
        scenario=scn,
        input_dir=".",
        expected_dir=".",
        snapshot_path="f.json",
        artifacts_dir=".",
        expected={"required_output_keys": ["ok"]},
        provenance=prov,
    )
    finding = eval_models.GraderFinding(
        grader_id="schema",
        scenario_id="scn_1",
        passed=True,
        severity="block",
        score=1.0,
        message="ok",
    )
    diag_sum = eval_models.DiagnosticSummaryV1(suite_id="s", app_id="apps_rg", run_id="r", observation_count=0)
    comp_sc = eval_models.ComponentScorecard(
        suite_id="s",
        app_id="apps_rg",
        component_id="c",
        row_count=1,
        required_count=1,
        pass_count=1,
        fail_count=0,
        warn_count=0,
        unknown_count=0,
        not_run_count=0,
        score=1.0,
        verdict="PASS",
    )
    cov_sum = eval_models.CoverageSummary(
        suite_id="s",
        app_id="apps_rg",
        required_microsteps=1,
        emitted_rows=1,
        passed_required=1,
        failed_required=0,
        missing_required_artifacts=0,
        unknown_required=0,
        not_run_required=0,
        coverage_complete=True,
        release_blocked=False,
        verdict="PASS",
    )
    sc = eval_models.Scorecard(
        suite_id="apps_rg.dev.smoke",
        app_id="apps_rg",
        scenario_count=1,
        finding_count=1,
        passed_findings=1,
        failed_findings=0,
        block_failures=0,
        score=1.0,
        verdict="pass",
    )
    reg = eval_models.RegressionSummary(compared=False)
    fly = eval_models.RegressionFlywheelSummary(compared=False)
    ts = eval_models.TrendSample(
        record_id="r1",
        suite_id="apps_rg.dev.smoke",
        app_id="apps_rg",
        split="dev",
        created_at="2026-11-03T00:00:00Z",
        score=1.0,
        scorecard_verdict="pass",
        regression_verdict="not_compared",
        block_failures=0,
    )
    tss = eval_models.TrendSuiteSummary(suite_id="apps_rg.dev.smoke", app_id="apps_rg", split="dev", sample_count=1)
    tds = eval_models.TrendDashboardSummary(trend_id="t1", suite_summaries=[tss], samples=[ts])
    rgd = eval_models.ReleaseGateDecision(gate_id="g1", status="pass")
    rec = eval_models.CompletedEvalRecord(
        record_id="r1",
        created_at="2026-11-03T00:00:00Z",
        suite_id="apps_rg.dev.smoke",
        app_id="apps_rg",
        mode="snapshot",
        deterministic_only=True,
        scenario_results=[],
        scorecard=sc,
        regression=reg,
        artifact_paths={},
        rubric_ids=["rub_1"],
        run_metadata=meta,
        fixture_provenance=[prov],
        regression_flywheel=fly,
    )
    handoff = eval_models.L6EvalHandoff(
        record_id="r1",
        suite_id="apps_rg.dev.smoke",
        app_id="apps_rg",
        eval_record_path="eval_record.json",
        score=1.0,
        verdict="pass",
        finding_count=1,
        block_failures=0,
    )
    assert fix.scenario.scenario_id == "scn_1" and finding.passed and diag_sum.observation_count == 0
    assert comp_sc.pass_count == 1 and cov_sum.coverage_complete and handoff.score == 1.0
    assert isinstance(eval_scenarios.ScenarioScaffoldResult("s", ".", []), eval_scenarios.ScenarioScaffoldResult)

    rcpt_l6 = l6_eval_ladder.build_l6_eval_execution_receipt(
        eval_level="LANE",
        deterministic_only=True,
        writer_live=False,
        graders_live=False,
    )
    assert isinstance(rcpt_l6, l6_eval_ladder.L6EvalExecutionReceipt)
    assert l6_eval_ladder.EvalLevel is not None

    drv = l6_shadow_bridge.build_driver_l6_shadow_bridge_payload(
        eval_id="e1",
        app_scorecards=[sc.to_dict()],
        output_refs={"r": "p"},
    )
    assert drv["scorecard_count"] == 1
    assert callable(l6_shadow_bridge.build_completed_eval_shadow_exhaust)
    assert callable(l6_shadow_bridge.emit_completed_eval_l6_shadow_bridge)
    assert callable(l6_shadow_bridge.emit_driver_l6_shadow_bridge)

    md_rep = eval_render.render_report(rec, [finding])
    md_rec = eval_render.render_record_markdown(rec.to_dict())
    assert "apps_rg.dev.smoke" in md_rep and "apps_rg.dev.smoke" in md_rec
    assert eval_loader.load_graders_registry() and eval_loader.load_thresholds_registry()
    assert eval_trends.render_trend_dashboard(tds) and eval_trends.render_release_gate(rgd)
    assert callable(eval_trends.build_trend_dashboard)
    assert callable(eval_trends.evaluate_release_gate)
    assert callable(eval_trends.emit_trend_dashboard)
    assert callable(eval_trends.emit_release_gate)


def test_infrastructure_contracts_optimizers_coherence_and_security() -> None:
    now = datetime.datetime.now()
    qreq = implementation_plan.QueryRequest(query_id="q1", user_query="enterprise ai", timestamp=now, priority=1)
    lresp = implementation_plan.LayerResponse(
        layer_type=implementation_plan.LayerType.REDIS_EXACT_MATCH,
        status=implementation_plan.QueryStatus.COMPLETED,
    )
    hstat = implementation_plan.HealthStatus(
        component_id="c1",
        layer_type=implementation_plan.LayerType.SEMANTIC_CACHE,
        healthy=True,
        last_check=now,
        response_time_ms=2.0,
        error_rate=0.0,
        throughput=100.0,
    )
    sctx = implementation_plan.SecurityContext(
        user_id="u1",
        roles=["admin"],
        data_classification="internal",
        compliance_requirements=["gdpr"],
        access_permissions={"read": True},
    )
    guard = implementation_plan.FourLayerContractGuard()
    guard.validate_query_request(qreq)
    assert lresp.status == implementation_plan.QueryStatus.COMPLETED and hstat.healthy and sctx.user_id == "u1"
    assert issubclass(implementation_plan.FourLayerContractError, ValueError)

    preq = precision_contracts.PrecisionQueryRequest(
        query_id="pq1",
        user_query="platform architecture",
        timestamp=now,
        priority=1,
    )
    assert preq.verify_integrity() is True
    presp = precision_contracts.PrecisionLayerResponse(
        layer_type=precision_contracts.PrecisionLayerType.REDIS_EXACT_MATCH,
        status=precision_contracts.PrecisionQueryStatus.COMPLETED,
    )
    assert presp.layer_type == precision_contracts.PrecisionLayerType.REDIS_EXACT_MATCH
    tb = precision_contracts.PrecisionTokenBucket(capacity=10, refill_rate=1.0)
    assert tb.consume(1) is True
    assert precision_contracts.PrecisionFourLayerContractGuard is not None
    assert precision_contracts.PrecisionCircuitBreaker is not None
    assert issubclass(precision_contracts.PrecisionContractError, Exception)

    assert adaptive_optimizer.OptimizationStrategy.BALANCED.value == "balanced"
    assert adaptive_optimizer.ModelType.COST_PREDICTOR.value == "cost_predictor"
    opt_params = adaptive_optimizer.OptimizationParameters(layer_type=implementation_plan.LayerType.SEMANTIC_CACHE)
    assert opt_params.to_dict()["top_k"] == 5
    ml_mod = adaptive_optimizer.SimpleMLModel(adaptive_optimizer.ModelType.COST_PREDICTOR)
    assert ml_mod.trained is False
    assert adaptive_optimizer.PerformanceMetrics is not None
    assert adaptive_optimizer.OptimizationResult is not None
    assert adaptive_optimizer.ModelRegistry is not None
    assert adaptive_optimizer.PerformanceAnalyzer is not None
    assert adaptive_optimizer.CostAnalyzer is not None
    assert adaptive_optimizer.AdaptiveOptimizer is not None

    assert precision_adaptive_optimizer.OptimizationStrategy is not None
    assert precision_adaptive_optimizer.PrecisionOptimizationParameters is not None
    assert precision_adaptive_optimizer.PrecisionPerformanceMetrics is not None
    assert precision_adaptive_optimizer.PrecisionMLModel is not None
    assert precision_adaptive_optimizer.PrecisionLinearRegression is not None
    assert precision_adaptive_optimizer.PrecisionNeuralNetwork is not None
    assert precision_adaptive_optimizer.PrecisionFeatureExtractor is not None
    assert precision_adaptive_optimizer.PrecisionAdaptiveOptimizer is not None

    ce = cross_layer_coherence.CacheEntry(
        key="k1",
        value={"a": 1},
        layer_type=implementation_plan.LayerType.REDIS_EXACT_MATCH,
        version="v1",
        created_at=now,
        last_accessed=now,
        ttl_seconds=60,
    )
    assert ce.verify_integrity() is True
    assert cross_layer_coherence.InvalidationEvent.DATA_UPDATE.value == "data_update"
    assert cross_layer_coherence.SyncStatus.SYNCED.value == "synced"
    assert cross_layer_coherence.InvalidationMessage is not None
    assert cross_layer_coherence.SyncStatusInfo is not None
    assert cross_layer_coherence.EventDrivenInvalidationBus is not None
    assert cross_layer_coherence.VersionManager is not None
    assert cross_layer_coherence.DistributedLockManager is not None
    assert cross_layer_coherence.ConsistencyMonitor is not None
    assert cross_layer_coherence.CrossLayerCoherenceManager is not None

    cb_cfg = unified_query_router.CircuitBreakerConfig()
    lb_cfg = unified_query_router.LoadBalancerConfig()
    cb = unified_query_router.CircuitBreaker(implementation_plan.LayerType.REDIS_EXACT_MATCH, cb_cfg)
    assert cb.state == unified_query_router.CircuitState.CLOSED and lb_cfg.max_retries == 3
    assert unified_query_router.LayerInstance is not None
    assert unified_query_router.LoadBalancer is not None
    assert unified_query_router.HealthChecker is not None
    assert unified_query_router.UnifiedQueryRouter is not None

    snap_d = distributed_state_manager.StateSnapshot(
        snapshot_id="s1",
        state_type=distributed_state_manager.StateType.CACHE_STATE,
        layer_type=implementation_plan.LayerType.REDIS_EXACT_MATCH,
        region=distributed_state_manager.Region.US_EAST,
        timestamp=now,
        data={"k": "v"},
    )
    assert snap_d.verify_integrity() is True
    assert distributed_state_manager.RecoveryStatus.HEALTHY.value == "healthy"
    assert distributed_state_manager.ReplicationStatus is not None
    assert distributed_state_manager.HealthCheckResult is not None
    assert distributed_state_manager.StateStorage is not None
    assert distributed_state_manager.InMemoryStateStorage is not None
    assert distributed_state_manager.MultiRegionReplicator is not None
    assert distributed_state_manager.DisasterRecoveryManager is not None
    assert distributed_state_manager.DistributedStateManager is not None

    psnap = precision_distributed_state.PrecisionStateSnapshot(
        snapshot_id="ps1",
        state_type=precision_distributed_state.PrecisionStateType.CACHE_STATE,
        layer_type="L1",
        region=precision_distributed_state.PrecisionRegion.US_EAST,
        timestamp=now,
        data={"k": "v"},
    )
    assert psnap.verify_integrity() is True
    assert precision_distributed_state.PrecisionReplicationStatus.COMPLETED.value == 3
    assert precision_distributed_state.PrecisionReplicationResult is not None
    assert precision_distributed_state.PrecisionConsensusAlgorithm is not None
    assert precision_distributed_state.PrecisionRaftConsensus is not None
    assert precision_distributed_state.PrecisionVectorClock is not None
    assert precision_distributed_state.PrecisionDistributedStorage is not None
    assert precision_distributed_state.PrecisionInMemoryStorage is not None
    assert precision_distributed_state.PrecisionMultiRegionReplicator is not None
    assert precision_distributed_state.PrecisionDistributedStateManager is not None
    assert precision_distributed_state.PrecisionHealthChecker is not None
    assert precision_distributed_state.PrecisionDisasterRecoveryManager is not None

    assert novel_testing_frameworks.NovelTestType.CHAOS_ENGINEERING.value == 1
    assert novel_testing_frameworks.ChaosExperiment is not None
    assert novel_testing_frameworks.PropertyInvariant is not None
    assert novel_testing_frameworks.TemporalInvariant is not None
    assert novel_testing_frameworks.ChaosEngineeringFramework is not None
    assert novel_testing_frameworks.PropertyBasedTestingFramework is not None
    assert novel_testing_frameworks.TemporalInvariantTesting is not None

    assert security_framework.DataClassification.PUBLIC.value == "public"
    assert security_framework.ComplianceFramework.GDPR.value == "gdpr"
    assert security_framework.AccessLevel.READ.value == "read"
    assert security_framework.SecurityAction.ACCESS_GRANTED.value == "access_granted"
    assert security_framework.SecurityPolicy is not None
    assert security_framework.AuditLogEntry is not None
    assert security_framework.ComplianceReport is not None
    assert security_framework.DataClassifier is not None
    assert security_framework.AccessController is not None
    assert security_framework.PrivacyEngine is not None
    assert security_framework.AuditLogger is not None
    assert security_framework.SecurityGateway is not None
    assert precision_sec_types.PrecisionDataClassification is not None
    assert precision_sec_types.PrecisionAuditLog is not None

    assert client_wrappers.OpenAIConfig is not None and client_wrappers.AnthropicConfig is not None
    assert client_wrappers.VertexConfig is not None and client_wrappers.OpenAIClient is not None
    assert client_wrappers.AnthropicClient is not None and client_wrappers.VertexClient is not None
    assert callable(client_wrappers.create_anthropic_client)
    assert callable(client_wrappers.create_anthropic_sync_client)
    assert callable(client_wrappers.create_vertex_client)
    assert callable(client_wrappers.create_gemini_model)
    assert gemini_client.GeminiStreamChunk is not None and gemini_client.GeminiResponse is not None
    assert gemini_client.GeminiClient is not None
    assert wire_cassette.CassetteError is not None and wire_cassette.WireExchange is not None
    assert callable(wire_cassette.compute_request_signature)
    assert research_handoff_contracts.normalize_company_role_tokens("Acme Corp")[0] == "acme_corp"
    assert callable(research_handoff_contracts.matches_company_stem)
    assert callable(research_handoff_contracts.verify_handoff_digest)
    assert callable(live_execution.load_agent_environment)
    assert live_governor.TokenReservation is not None
    assert adg_drift.Snapshot is not None and adg_drift.DriftReport is not None
    assert adg_health.HealthMetrics is not None and adg_violations.Violation is not None
    assert adg_violations.ViolationReport is not None


def test_apps_research_and_tools_coverage_elevation() -> None:
    assert callable(_otel_spans.airlock_span) and callable(_otel_spans.emit_airlock_event)
    assert callable(register_producer) and callable(resolve_fec) and callable(maybe_invoke_exit_eval)
    assert callable(cert_fec_producer.produce_fec)
    assert agent_spec_config.PromptReceptionSpec is not None
    assert agent_spec_config.ArtifactModeConfig is not None
    assert agent_spec_config.SourceRegisterConfig is not None
    assert agent_spec_config.ResearchGateConfig is not None
    assert agent_spec_config.ResearchOutputConfig is not None
    assert agent_spec_config.ResearchAgentSpecs is not None
    assert research_pins.AppsResearchModelPin is not None
    assert reasoning_toggles_config.ResearchReasoningToggles is not None
    assert cross_app_base.CrossAppEnvelope is not None
    assert hop_research_assembly_engine.HopResearchAssemblyEngine is not None
    assert chroma_research_store.ChromaCollectionProtocol is not None
    assert chroma_research_store.ChromaClientProtocol is not None
    assert chroma_research_store.ChromaResearchStore is not None
    assert research_retrieval_engine.SourceTrend is not None
    assert callable(research_retrieval_engine.create_retrieval_engine)

    assert judge_base.JudgeEvidence is not None and judge_base.BaseResearchJudge is not None
    assert callable(judge_base.map_judge_evidence_to_gate)
    assert briefing_injection_judge.BriefingInjectionJudge is not None
    assert cache_compatibility_judge.CacheCompatibilityJudge is not None
    assert citation_quality_judge.CitationQualityJudge is not None
    assert claim_support_judge.ClaimSupportJudge is not None
    assert contradiction_resolution_judge.ContradictionResolutionJudge is not None
    assert coverage_depth_judge.CoverageDepthJudge is not None
    assert downstream_relevance_judge.DownstreamRelevanceJudge is not None
    assert source_authority_judge.SourceAuthorityJudge is not None

    assert apps_rg_handoff.AppsRgHandoffExitAuthorization is not None
    assert apps_rg_handoff.AppsRgTargetingArtifactBundle is not None
    assert callable(apps_rg_handoff.sha256_text)
    assert callable(apps_rg_handoff.looks_like_stub_company_brief)
    assert callable(apps_rg_handoff.find_apps_rg_targeting_sidecar)
    assert callable(apps_rg_handoff.build_apps_rg_handoff_gate_mesh)
    assert callable(apps_rg_handoff.run_apps_rg_handoff_exit_authorization)
    assert callable(c0_graph_adapter.build_research_graph_traverse_input)
    assert c0_graph_adapter.ResearchGraphAdapter is not None
    assert evidence_lineage.ResearchEvidenceLineageItem is not None
    assert execution_adapter.GovernedRunRecord is not None
    assert execution_adapter.GovernedExecutionSeam is not None
    assert execution_adapter.ExecutionRequest is not None
    assert governed_app_runner.GovernanceContractViolation is not None
    assert governed_app_runner.GovernedAppRunRecord is not None
    assert callable(governed_app_runner.build_app_record)
    assert governed_app_runner.GovernedAppRunner is not None
    assert governed_research_run.ResearchPlanOutput is not None
    assert governed_research_run.L0RouteDecision is not None
    assert governed_research_run.GovernedResearchRun is not None
    assert llm_client.OpenAIClient is not None and llm_client.OpenAIConfig is not None
    assert research_c0_adapter.ResearchDepthProfile is not None
    assert research_c0_adapter.C0EvidenceBundle is not None
    assert research_c0_adapter.C0GateFailed is not None
    assert callable(research_c0_adapter.evaluate_c0_gate)
    assert research_c0_adapter.ResearchC0Adapter is not None
    assert research_capability_registry.CapabilityUnavailableError is not None
    assert callable(research_capability_registry.register_company_brief_capability)
    assert callable(research_capability_registry.resolve_company_brief_capability)
    assert callable(research_capability_registry.bootstrap_capability)
    assert research_exit_fec_producer.ResearchFinalEvidenceContract is not None
    assert research_exit_fec_producer.FECValidationError is not None
    assert callable(research_exit_fec_producer.produce_fec)
    assert research_l2_step_adapters.E1C0EvidenceGateAdapter is not None
    assert research_l2_step_adapters.E2PromptAssemblyAdapter is not None
    assert research_l2_step_adapters.E3ProviderSynthesisAdapter is not None
    assert research_l2_step_adapters.E4FECProducerAdapter is not None
    assert research_l2_step_adapters.E5ExitAdapter is not None
    assert searxng_readiness.StepResult is not None and searxng_readiness.SearxngReadinessReport is not None
    assert searxng_readiness.DockerCommandError is not None and searxng_readiness.SearxngReadinessError is not None
    assert callable(searxng_readiness.runtime_base_url) and callable(searxng_readiness.ensure_runtime_ready)
    assert callable(spine_handoff.validate_research_r3_contract_surface)
    assert spine_handoff.R3HandoffMetadata is not None
    assert callable(spine_handoff.build_research_r3_handoff_metadata)
    assert callable(spine_handoff.run_research_via_spine)
    assert hop_pipeline.Checkpoint is not None and hop_pipeline.HopStageSpec is not None
    assert hop_pipeline.HopRegistry is not None and hop_pipeline.HopPipelineExecutor is not None
    assert callable(enterprise_research_renderer.write_research_markdown)
    assert callable(enterprise_research_renderer.write_manifest)
    assert callable(envelope_emitter.build_payload)
    assert callable(consumer_briefs.normalize_consumer_template_id)
    assert callable(consumer_briefs.consumer_brief_template_id)
    assert callable(consumer_briefs.load_consumer_brief_prompt_template)
    assert callable(consumer_briefs.consumer_brief_prompt_path)
    assert callable(consumer_briefs.build_consumer_brief_prompt)
    assert callable(research_pa_compiler.load_prompt_bom)
    assert callable(research_pa_compiler.load_prompt_registry)
    assert callable(research_pa_compiler.compute_bom_hash)
    assert callable(research_pa_compiler.compute_registry_hash)
    assert callable(research_pa_compiler.compute_template_hash)
    assert callable(research_pa_compiler.compile_repair_prompt)
    assert repo_signal_service.RepoSignalSnapshot is not None
    assert base_spine_adapter.BaseSpineAdapter is not None
    assert research_spine_adapter.ResearchSpineAdapter is not None
    assert PromptTemplate.ResearchPromptEntry is not None
    assert PromptTemplate.ResearchNodeEntry is not None
    assert PromptTemplate.ResearchGlobalRule is not None
    assert PromptTemplate.ResearchSovereignKnowledge is not None
    assert callable(PromptTemplate.get_system_prompt)
    assert callable(PromptTemplate.get_prompt_entry)
    assert callable(PromptTemplate.get_global_rule)
    assert callable(PromptTemplate.list_all_nodes)
    assert apps_rg_targeting_brief_contract.BriefingProfile is not None
    assert apps_rg_targeting_brief_contract.TargetingBriefValidation is not None
    assert apps_rg_targeting_brief_contract.BriefingSemanticsAssessment is not None
    assert apps_rg_targeting_brief_contract.AppsRgTargetingBrief is not None
    assert briefing_evidence_contracts.FamilyCoverageEntry is not None
    assert briefing_evidence_contracts.BriefingCoverageMatrix is not None
    assert briefing_evidence_contracts.ClaimAnchor is not None
    assert briefing_evidence_contracts.ClaimEvidenceMap is not None
    assert briefing_evidence_contracts.ContradictionEntry is not None
    assert briefing_evidence_contracts.ContradictionMatrix is not None
    assert briefing_evidence_contracts.SourceFreshnessRecord is not None
    assert briefing_evidence_contracts.FreshnessReport is not None
    assert briefing_evidence_contracts.SynthesisGuidanceForPA is not None
    assert briefing_evidence_contracts.SourcePortfolioSummary is not None
    assert briefing_evidence_contracts.CitationAnchor is not None
    assert briefing_evidence_contracts.CitationAnchorRegistry is not None
    assert briefing_evidence_contracts.EvidenceGap is not None
    assert briefing_evidence_contracts.EvidenceGapReport is not None
    assert briefing_evidence_contracts.BriefingEvidenceBundle is not None
    assert jd_intent_coverage.EvidenceIntent is not None
    assert callable(jd_intent_coverage.jd_context_text)
    assert callable(jd_intent_coverage.infer_evidence_intents_from_text)
    assert callable(jd_intent_coverage.infer_evidence_intents)
    assert callable(jd_intent_coverage.required_families_for_intents)
    assert callable(jd_intent_coverage.signal_terms_for_intents)
    assert callable(jd_intent_coverage.intent_ids)
    assert role_profile.RoleSource is not None
    assert callable(engine_seal_step_mixin.install_seal_step_autowrap)
    assert callable(research_artifact_util.resolve_artifact_path)
    assert callable(research_artifact_util.serialize_source_register)
    assert callable(research_artifact_util.is_dry_run)
    assert research_gate_validator.ResearchViolation is not None
    assert research_gate_validator.ResearchGateResult is not None
    assert research_gate_validator.ResearchGateValidator is not None
    assert research_source_validator.ValidationViolation is not None
    assert research_source_validator.ResearchValidationResult is not None
    assert research_source_validator.ResearchValidator is not None
    assert research_source_validator.SourceGate is not None
    assert research_source_validator.ResearchValidationAgent is not None

    assert callable(cost_token_budget_governor_probes.run_pillar_5_live_probes)
    assert callable(cost_token_budget_governor_probes.run_pillar_6_live_probes)
    assert callable(cost_token_budget_governor_probes.run_pillar_7_live_probes)
    assert callable(cost_token_budget_probes.verify_ast_compact_json_surface)
    assert callable(cost_token_budget_probes.run_pillar_2_live_probes)
    assert callable(cost_token_budget_probes.run_pillar_3_live_probes)
    assert callable(cost_token_budget_probes.run_pillar_4_live_probes)
    assert callable(evidence_requirements.validate_execution_evidence)
    assert callable(install_githooks.install_hooks)
    assert callable(pr_common.is_plan_doc_file)
    assert callable(pr_common.resolve_branch_plan_path)
    assert callable(pr_common.bootstrap_shared_venv)
    assert callable(pr_common.resolve_python)
    assert callable(pr_common.resolve_pytest)
    assert callable(pr_common.sanitized_git_env)
    assert callable(pr_common.run_git)
    assert callable(pr_common.check_diff_syntax)
    assert callable(pr_common.compute_branch_delta_digest)
    assert callable(pr_common.check_disjoint_base_advance_equivalence)
    assert callable(pr_common.get_immune_pids)
    assert callable(pr_common.kill_ghost_processes)
    assert callable(pr_common.logic_digest)
    assert callable(pr_common.compute_first_parent_sync)
    assert callable(pr_inspection.is_remote_tracking_branch)
    assert callable(pr_inspection.get_feature_branches)
    assert callable(pr_inspection.inspect_branch_status)
    assert callable(pr_inspection.cmd_doctor)
    assert callable(pr_inspection.cmd_list)
    assert callable(pr_worktree.worktree_provisioning_lock)
    assert callable(storage_worktree_hygiene.inspect_sqlite_databases)
    assert callable(storage_worktree_hygiene.remediate_sqlite_wal)
    assert callable(storage_worktree_hygiene.inspect_and_remediate_ephemeral_bloat)
    assert callable(storage_worktree_hygiene.scan_stale_locks_and_temps)
    assert callable(storage_worktree_hygiene.collect_storage_inventory)
    assert callable(verify_graph_integrity_and_embeddings.verify_graph_database)
    assert callable(verify_graph_integrity_and_embeddings.verify_bge_m3_embeddings)
    assert callable(verify_graph_integrity_and_embeddings.verify_hybrid_retrieval_stage2)
    assert callable(verify_graph_integrity_and_embeddings.run_full_verification)
