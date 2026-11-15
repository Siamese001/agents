"""Wave 4 canonical 10-stage spine (`U0..X3`), `X3Disposition`, PCT grounding, and sequence X2 tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from apps_lic.domain.models import CandidateFact
from apps_lic.domain.repair import (
    DeterministicDraftRepairer,
    ReservePoolRepairResult,
    repair_touch_with_reserve_pool,
)
from apps_lic.domain.validators import (
    EXEMPLAR_4GRAM_OVERLAP_EXCEEDED,
    GroundingValidator,
    INV_LIC_C0_DISJOINT_TOUCH_FACTS,
    INV_RESUME_NO_UNDEFINED_ACRONYMS,
    MAX_EXEMPLAR_4GRAM_OVERLAP,
    MAX_PAIRWISE_TOUCH_COSINE,
    METRIC_LAUNDERED_FROM_OPPORTUNITY,
    MetricGroundingVerificationResult,
    PAIRWISE_COSINE_EXCEEDED,
    PCTCertificate,
    SequenceX2Report,
    TouchX2Violation,
    UNGROUNDED_CANDIDATE_METRIC,
    UndefinedAcronymValidator,
    ZERO_DUPLICATE_OPENERS_AND_CTAS,
    check_undefined_mga_acronym,
    compute_exemplar_4gram_overlap,
    compute_touch_cosine_similarity,
    extract_touch_cta,
    extract_touch_opener,
    validate_sequence_x2,
    verify_candidate_metric_grounding,
)
from apps_lic.pipeline.outreach_swarm_challenger import OutreachSwarmChallenger
from apps_lic.runtime import (
    CANONICAL_SPINE_STAGE_ORDER,
    ExecutionMode,
    OutreachStageLedgerBuilder,
    SpineExecutionContext,
    SpineRunArtifacts,
    SpineStageId,
    SpineStageStatus,
    StageExecutionRecord,
    StageLedgerOrderError,
    WholeRunExitDecision,
    X3Disposition,
    build_completion_receipt_payload,
    build_run_bundle_index,
    build_terminal_manifest_payload,
    ensure_sha256_digest,
    evaluate_whole_run_exit,
    execute_canonical_10_stage_spine,
    sanitize_stage_metrics,
    write_canonical_spine_bundle,
    write_exit_artifacts,
)
from apps_lic.runtime.canonical_dispatch import (
    build_cli_ingress_raw,
    run_canonical_apps_lic_spine,
)
from apps_lic.runtime.model_registry import OutreachModelRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "config" / "certification" / "schemas"


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _sample_candidate_facts() -> list[CandidateFact]:
    return [
        CandidateFact(
            fact_id="fact_c0_1",
            category="revenue_growth",
            statement="Scaled global enterprise platform ARR to $140M across 12 regulated markets",
            metric="$140M",
            source_reference="cand_chunk_01",
        ),
        CandidateFact(
            fact_id="fact_c0_2",
            category="cloud_efficiency",
            statement="Reduced multi-region inference latency by 42% across production clusters",
            metric="42%",
            source_reference="cand_chunk_02",
        ),
        CandidateFact(
            fact_id="fact_c0_3",
            category="team_scale",
            statement="Directed a 185-person distributed engineering organization with 99.99% uptime",
            metric="99.99%",
            source_reference="cand_chunk_03",
        ),
    ]


def test_in_opp_metric_laundering_rejected_vs_in_cand_pct_certificate_accepted() -> None:
    """Reject opportunity-research metrics laundered as candidate claims; accept C0 candidate facts with PCTCertificate."""
    cand_facts = _sample_candidate_facts()
    opp_context = "Acme Corp raised $480M Series D and expanded operating margin by 67% in 2025."

    laundered_body = (
        "Hi Jordan,\n\n"
        "In my recent role, I scaled our core platform to $480M across global markets.\n\n"
        "Would you be open to a brief conversation next week?"
    )
    laundered_res: MetricGroundingVerificationResult = verify_candidate_metric_grounding(
        laundered_body,
        candidate_facts=cand_facts,
        opportunity_context=opp_context,
        declared_fact_ids=["fact_c0_1"],
        touch_number=1,
    )
    assert laundered_res.passed is False
    assert any(METRIC_LAUNDERED_FROM_OPPORTUNITY in v for v in laundered_res.violations)
    assert len(laundered_res.certificates) == 1
    assert laundered_res.certificates[0].in_opp is True
    assert laundered_res.certificates[0].in_cand is False
    assert laundered_res.certificates[0].verified is False

    g_ok, g_viols = GroundingValidator().validate(
        ["fact_c0_1"],
        {"fact_c0_1", "fact_c0_2"},
        body=laundered_body,
        candidate_facts=cand_facts,
        opportunity_context=opp_context,
    )
    assert g_ok is False
    assert any(METRIC_LAUNDERED_FROM_OPPORTUNITY in v for v in g_viols)
    assert UNGROUNDED_CANDIDATE_METRIC == "UNGROUNDED_CANDIDATE_METRIC"

    grounded_body = (
        "Hi Jordan,\n\n"
        "In my recent work, I scaled global enterprise platform ARR to $140M across regulated markets.\n\n"
        "Would you be open to a brief conversation next week?"
    )
    grounded_res = verify_candidate_metric_grounding(
        grounded_body,
        candidate_facts=cand_facts,
        opportunity_context=opp_context,
        declared_fact_ids=["fact_c0_1"],
        touch_number=1,
    )
    assert grounded_res.passed is True
    assert grounded_res.violations == ()
    cert: PCTCertificate = grounded_res.certificates[0]
    assert cert.in_cand is True and cert.verified is True
    assert cert.fact_id == "fact_c0_1"
    assert cert.source_chunk_id == "cand_chunk_01"
    assert cert.metric_token == "$140M"


def test_sequence_x2_cosine_openers_ctas_4gram_disjoint_facts_and_mga_acronym() -> None:
    """Validate sequence-wide X2 checks: cosine <=0.32, opener/CTA dedup, 4-gram <=0.20, disjoint facts, and MGA blocker."""
    cand_facts = _sample_candidate_facts()
    allocation_plan = {
        "allocated_fact_ids_by_touch": {1: ["fact_c0_1"], 2: ["fact_c0_2"], 3: ["fact_c0_3"]},
        "reserve_repair_pool_fact_ids": ["fact_res_1"],
    }
    e0_exemplar = (
        "Following your recent digital transformation keynote at the enterprise summit, "
        "our engineering leadership team modernized legacy core banking ledgers."
    )
    clean_touches = [
        {
            "touch_number": 1,
            "subject": "Platform architecture alignment",
            "body": (
                "Hi Jordan,\n\n"
                "Targeting VP Engineering mandates where scaling enterprise platform ARR to $140M "
                "across regulated markets directly accelerates commercial velocity.\n\n"
                "Would you be open to a brief introductory call next Tuesday?"
            ),
            "grounded_facts_used": ["fact_c0_1"],
        },
        {
            "touch_number": 2,
            "subject": "Re: Platform architecture alignment",
            "body": (
                "Hi Jordan,\n\n"
                "Sharing a quick operational proof point: our infrastructure reliability program "
                "reduced multi-region inference latency by 42% across production clusters.\n\n"
                "Could we schedule ten minutes on Thursday to compare notes?"
            ),
            "grounded_facts_used": ["fact_c0_2"],
        },
        {
            "touch_number": 3,
            "subject": "Checking in: Acme Corp",
            "body": (
                "Hi Jordan,\n\n"
                "I recognize roadmap priorities shift rapidly while building Managing General Agents (MGAs) "
                "and directing a 99.99% uptime distributed organization.\n\n"
                "Would reconnecting next quarter make more sense for your calendar?"
            ),
            "grounded_facts_used": ["fact_c0_3"],
        },
    ]

    clean_report: SequenceX2Report = validate_sequence_x2(
        clean_touches,
        allocation_plan=allocation_plan,
        e0_exemplars=[e0_exemplar],
        candidate_facts=cand_facts,
    )
    assert clean_report.passed is True
    assert clean_report.max_pairwise_cosine <= MAX_PAIRWISE_TOUCH_COSINE
    assert clean_report.max_exemplar_4gram_overlap <= MAX_EXEMPLAR_4GRAM_OVERLAP
    assert clean_report.disjoint_facts_passed is True
    assert clean_report.undefined_acronyms_found == ()
    assert len(clean_report.pct_certificates) == 3

    bad_body_1 = (
        "Hi Jordan,\n\n"
        "Following your recent digital transformation keynote at the enterprise summit. "
        "We scaled MGA underwriting platform ARR to $140M.\n\n"
        "Would you be open to a brief introductory call next Tuesday?"
    )
    bad_body_2 = (
        "Hi Jordan,\n\n"
        "Following your recent digital transformation keynote at the enterprise summit. "
        "We scaled MGAs underwriting platform ARR to $140M.\n\n"
        "Would you be open to a brief introductory call next Tuesday?"
    )
    assert compute_touch_cosine_similarity(bad_body_1, bad_body_2) > MAX_PAIRWISE_TOUCH_COSINE
    assert extract_touch_opener(bad_body_1) == extract_touch_opener(bad_body_2)
    assert extract_touch_cta(bad_body_1) == extract_touch_cta(bad_body_2)
    assert compute_exemplar_4gram_overlap(bad_body_1, [e0_exemplar]) > MAX_EXEMPLAR_4GRAM_OVERLAP
    assert check_undefined_mga_acronym(bad_body_1)[0] is False
    assert UndefinedAcronymValidator().validate(bad_body_2)[0] is False

    bad_touches = [
        {"touch_number": 1, "subject": "MGA note", "body": bad_body_1, "grounded_facts_used": ["fact_c0_1"]},
        {"touch_number": 2, "subject": "Re: MGA note", "body": bad_body_2, "grounded_facts_used": ["fact_c0_1"]},
    ]
    bad_report = validate_sequence_x2(
        bad_touches,
        allocation_plan=allocation_plan,
        e0_exemplars=[e0_exemplar],
        candidate_facts=cand_facts,
    )
    assert bad_report.passed is False
    codes = set(bad_report.violation_codes)
    assert {
        PAIRWISE_COSINE_EXCEEDED,
        ZERO_DUPLICATE_OPENERS_AND_CTAS,
        EXEMPLAR_4GRAM_OVERLAP_EXCEEDED,
        INV_LIC_C0_DISJOINT_TOUCH_FACTS,
        INV_RESUME_NO_UNDEFINED_ACRONYMS,
    }.issubset(codes)
    assert all(isinstance(v, TouchX2Violation) for v in bad_report.violations)


def test_reserve_pool_repair_substitution_emits_verified_pct_certificate() -> None:
    """Verify reserve-pool repair swaps an ungrounded/colliding metric with a verified C0 reserve fact."""
    allocation_plan = {
        "allocated_fact_ids_by_touch": {1: ["fact_c0_1"], 2: ["fact_c0_2"]},
        "reserve_repair_pool_fact_ids": ["fact_reserve_09"],
        "reserve_repair_pool_facts": [
            {
                "fact_id": "fact_reserve_09",
                "source_chunk_id": "chunk_reserve_09",
                "verbatim_span": "Delivered $85M in annualized cloud FinOps savings across 4 business units",
                "metric_tokens": ["$85M"],
                "has_provenance": True,
            }
        ],
    }
    failing_touch = {
        "touch_number": 2,
        "subject": "Follow-up on platform scale",
        "body": (
            "Hi Jordan,\n\n"
            "Following up briefly: we achieved $999M in unverified savings last year.\n\n"
            "Could we connect for ten minutes on Thursday?"
        ),
        "grounded_facts_used": ["fact_c0_2"],
    }

    repair_res: ReservePoolRepairResult = DeterministicDraftRepairer.repair_touch_with_reserve_pool(
        failing_touch,
        allocation_plan=allocation_plan,
        colliding_metric="$999M",
    )
    assert repair_res.repaired is True
    assert repair_res.replacement_fact_id == "fact_reserve_09"
    assert "$85M" in repair_res.repaired_body and "$999M" not in repair_res.repaired_body
    assert repair_res.certificate.verified is True
    assert repair_res.certificate.in_cand is True and repair_res.certificate.in_opp is False
    assert repair_res.certificate.fact_id == "fact_reserve_09"
    assert repair_res.certificate.source_chunk_id == "chunk_reserve_09"

    direct_res = repair_touch_with_reserve_pool(
        "We drove $777M in unverified pipeline.",
        allocation_plan=allocation_plan,
        touch_number=3,
    )
    assert direct_res.repaired is True and "$85M" in direct_res.body


def test_canonical_10_stage_spine_schemas_and_x3_dispositions(tmp_path: Path) -> None:
    """Validate 10-stage spine order U0..X3, JSON schemas via Draft202012Validator, and X3Disposition rules."""
    expected_order = ("U0", "D0", "C0", "PA", "X1A", "X1B", "X1C", "X2", "X1D", "X3")
    assert tuple(s.value for s in CANONICAL_SPINE_STAGE_ORDER) == expected_order

    ctx = SpineExecutionContext(run_id="run_ctx_01", mission_id="mission_ctx_01")
    assert ctx.execution_mode == ExecutionMode.REAL_LLM
    assert ensure_sha256_digest("test-payload").startswith("sha256:")
    assert sanitize_stage_metrics({"ok": True, "nested": ["a", "b"]})["nested"] == '["a", "b"]'

    strict_builder = OutreachStageLedgerBuilder(run_id="run_ord", mission_id="mission_ord")
    strict_builder.record_stage(SpineStageId.U0, SpineStageStatus.PASS)
    with pytest.raises(StageLedgerOrderError):
        strict_builder.record_stage(SpineStageId.C0, SpineStageStatus.PASS)

    ledger_validator = Draft202012Validator(_load_schema("apps_lic_stage_ledger.v1.schema.json"))
    manifest_validator = Draft202012Validator(_load_schema("apps_lic_terminal_manifest.v1.schema.json"))
    receipt_validator = Draft202012Validator(_load_schema("apps_lic_completion_receipt.v1.schema.json"))

    real_dir = tmp_path / "real_llm_run"
    real_bundle: SpineRunArtifacts = execute_canonical_10_stage_spine(
        real_dir,
        run_id="run_real_001",
        mission_id="mission_real_001",
        execution_mode=ExecutionMode.REAL_LLM,
        x2_passed=True,
        quorum_passed=True,
        drafter_judge_orthogonal=True,
        used_fallback=False,
        drafter_family="anthropic",
        pct_certificates_count=3,
    )
    assert real_bundle.x3_disposition == X3Disposition.X3D_ALLOW_FINISH
    assert [s["stage_id"] for s in real_bundle.stage_ledger["stages"]] == list(expected_order)
    ledger_validator.validate(real_bundle.stage_ledger)
    manifest_validator.validate(real_bundle.terminal_manifest)
    receipt_validator.validate(real_bundle.completion_receipt)
    assert (real_dir / "RUN_BUNDLE_INDEX.json").is_file()

    smoke_decision: WholeRunExitDecision = evaluate_whole_run_exit(
        run_id="run_smoke_001",
        mission_id="mission_smoke_001",
        execution_mode=ExecutionMode.OFFLINE_SMOKE,
        x2_passed=True,
        quorum_passed=True,
        drafter_judge_orthogonal=True,
        pct_certificates_count=3,
    )
    assert smoke_decision.x3_disposition == X3Disposition.X3E_SAFE_ABSTAIN and not smoke_decision.allow_finish
    smoke_builder = OutreachStageLedgerBuilder(
        run_id="run_smoke_001", mission_id="mission_smoke_001", execution_mode=ExecutionMode.OFFLINE_SMOKE
    )
    smoke_bundle = write_canonical_spine_bundle(
        tmp_path / "offline_smoke_run", ledger_builder=smoke_builder, exit_decision=smoke_decision
    )
    assert smoke_bundle.x3_disposition == X3Disposition.X3E_SAFE_ABSTAIN
    ledger_validator.validate(smoke_bundle.stage_ledger)
    manifest_validator.validate(smoke_bundle.terminal_manifest)
    receipt_validator.validate(smoke_bundle.completion_receipt)

    fallback_pin = OutreachModelRegistry.get_model_pin("executive_outreach_generator")
    fallback_decision = evaluate_whole_run_exit(
        run_id="run_fallback_001",
        mission_id="mission_fallback_001",
        execution_mode=ExecutionMode.REAL_LLM,
        x2_passed=True,
        quorum_passed=True,
        used_fallback=True,
        drafter_family="openai",
        model_id=fallback_pin.backup_model,
        pct_certificates_count=2,
    )
    assert fallback_decision.x3_disposition == X3Disposition.X3B_ESCALATE_HITL and not fallback_decision.allow_finish

    assert evaluate_whole_run_exit(
        run_id="run_x3a", mission_id="mission_x3a", x2_passed=False, quorum_passed=True, repairable_inline=True
    ).x3_disposition == X3Disposition.X3A_REPAIR_INLINE
    assert evaluate_whole_run_exit(
        run_id="run_x3c", mission_id="mission_x3c", x2_passed=True, quorum_passed=False, patch_rerun_eligible=True
    ).x3_disposition == X3Disposition.X3C_PATCH_RERUN

    m_path, r_path, m_payload, r_payload = write_exit_artifacts(
        tmp_path / "exit_helpers",
        fallback_decision,
        prompt_hash=ensure_sha256_digest("prompt"),
        allocation_plan_digest=ensure_sha256_digest("alloc"),
        artifacts=["stage_execution_ledger.json"],
        bundle_index_digest=ensure_sha256_digest("idx"),
    )
    assert m_path.is_file() and r_path.is_file()
    manifest_validator.validate(m_payload)
    receipt_validator.validate(r_payload)
    assert build_terminal_manifest_payload(
        fallback_decision,
        prompt_hash=ensure_sha256_digest("p"),
        allocation_plan_digest=ensure_sha256_digest("a"),
        artifacts=[],
        bundle_index_digest=ensure_sha256_digest("b"),
    )["x3_disposition"] == "X3B_ESCALATE_HITL"
    assert build_completion_receipt_payload(fallback_decision)["x3_disposition"] == "X3B_ESCALATE_HITL"
    assert build_run_bundle_index(
        run_id="r1", mission_id="m1", execution_mode=ExecutionMode.REAL_LLM, x3_disposition="X3D_ALLOW_FINISH", artifact_entries=[]
    )["x3_disposition"] == "X3D_ALLOW_FINISH"
    assert StageExecutionRecord(
        stage_id=SpineStageId.U0, status=SpineStageStatus.PASS, input_digest=ensure_sha256_digest("in"), output_digest=ensure_sha256_digest("out")
    ).to_schema_dict()["stage_id"] == "U0"

    dispatch_res = run_canonical_apps_lic_spine(
        build_cli_ingress_raw(company="Acme", role="VP Engineering", offline_smoke=True),
        tmp_path / "dispatch_smoke",
    )
    assert dispatch_res["x3_disposition"] == "X3E_SAFE_ABSTAIN"
    assert dispatch_res["x3_code"] == "X3D_BLOCK"

    challenger = OutreachSwarmChallenger()
    challenger_receipt = challenger.execute(
        "Hi Jordan, sharing our platform architecture roadmap where we scaled enterprise reliability "
        "across twelve global regions and improved deployment velocity for engineering teams. "
        "Would you be open to a brief conversation next week?",
        campaign_id="camp_spine_01",
    )
    assert challenger_receipt.campaign_id == "camp_spine_01"
    assert challenger.last_stage_ledger is not None
    ledger_validator.validate(challenger.last_stage_ledger)
