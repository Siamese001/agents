"""Unit tests for L1 post-tool review contracts and L2 execution packet extensions."""

from __future__ import annotations

import json
import pytest

from apps_rg.runtime.contracts.l1_post_tool_review_contracts import (
    L1_DETERMINISTIC_CHECK_SCHEMA_VERSION,
    L1_POST_TOOL_REVIEW_SCHEMA_VERSION,
    L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
    L1DeterministicCheckResult,
    L1PostToolReviewContract,
    L1ReviewVerdict,
    L1SemanticReviewResult,
    sha256_hex,
)
from apps_rg.runtime.bindings.l2_authority_contracts import SignedAppsRgL2ExecutionPacket


def test_l1_review_verdict_properties() -> None:
    assert L1ReviewVerdict.SUFFICIENT.is_sufficient is True
    assert L1ReviewVerdict.SUFFICIENT.requires_replan is False
    assert L1ReviewVerdict.SUFFICIENT.requires_retry is False

    assert L1ReviewVerdict.INSUFFICIENT_REPLAN.is_sufficient is False
    assert L1ReviewVerdict.INSUFFICIENT_REPLAN.requires_replan is True
    assert L1ReviewVerdict.INSUFFICIENT_REPLAN.requires_retry is False

    assert L1ReviewVerdict.INSUFFICIENT_RETRY.is_sufficient is False
    assert L1ReviewVerdict.INSUFFICIENT_RETRY.requires_replan is False
    assert L1ReviewVerdict.INSUFFICIENT_RETRY.requires_retry is True

    assert L1ReviewVerdict.TERMINAL_FAIL.is_sufficient is False
    assert L1ReviewVerdict.TERMINAL_FAIL.requires_replan is False
    assert L1ReviewVerdict.TERMINAL_FAIL.requires_retry is False


def test_deterministic_check_result_hashing_and_dict() -> None:
    res1 = L1DeterministicCheckResult(
        status="PASS",
        tool_execution_success=True,
        schema_valid=True,
        required_fields_present=True,
        missing_fields=(),
        missing_evidence_ids=(),
        checked_assertions={"schema": True, "token_bounds": True},
        failure_reasons=(),
    )
    assert res1.schema_version == L1_DETERMINISTIC_CHECK_SCHEMA_VERSION
    assert len(res1.check_digest) == 64

    # Identical content yields identical digest
    res2 = L1DeterministicCheckResult(
        status="PASS",
        tool_execution_success=True,
        schema_valid=True,
        required_fields_present=True,
        missing_fields=(),
        missing_evidence_ids=(),
        checked_assertions={"schema": True, "token_bounds": True},
        failure_reasons=(),
    )
    assert res1.check_digest == res2.check_digest

    # Different content yields different digest
    res_fail = L1DeterministicCheckResult(
        status="FAIL",
        tool_execution_success=False,
        schema_valid=False,
        required_fields_present=False,
        missing_fields=("executive_summary",),
        missing_evidence_ids=("fact-001",),
        checked_assertions={"schema": False},
        failure_reasons=("Output schema invalid",),
    )
    assert res_fail.check_digest != res1.check_digest
    assert res_fail.missing_fields == ("executive_summary",)

    payload = res1.as_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_semantic_review_result_hashing_and_dict() -> None:
    sem1 = L1SemanticReviewResult(
        status="PASS",
        subgoal_accomplished=True,
        evidence_sufficient=True,
        plan_adaptation_required=False,
        critique="The generated text accurately reflects the planned achievements.",
        recommended_action="PROCEED_TO_EXIT",
        suggested_strategy_delta={},
    )
    assert sem1.schema_version == L1_SEMANTIC_REVIEW_SCHEMA_VERSION
    assert len(sem1.review_digest) == 64

    sem2 = L1SemanticReviewResult(
        status="INSUFFICIENT",
        subgoal_accomplished=False,
        evidence_sufficient=False,
        plan_adaptation_required=True,
        critique="Leadership claims lack quantifiable metrics from the candidate facts.",
        recommended_action="REPLAN_STRATEGY",
        suggested_strategy_delta={"boost_metric_weight": True},
    )
    assert sem2.review_digest != sem1.review_digest
    assert sem2.plan_adaptation_required is True

    payload = sem1.as_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_l1_post_tool_review_contract_immutability_and_serialization() -> None:
    det = L1DeterministicCheckResult(status="PASS")
    sem = L1SemanticReviewResult(status="PASS")

    contract = L1PostToolReviewContract(
        request_id="req-123",
        run_id="run-456",
        trace_id="trace-789",
        parent_l1_plan_ref="sha256:plan123",
        sealed_l2_artifact_ref="sha256:l2seal123",
        verdict=L1ReviewVerdict.SUFFICIENT,
        deterministic_checks=det,
        semantic_review=sem,
        review_cycle=1,
        review_timestamp="2026-09-14T12:00:00Z",
    )

    assert contract.schema_version == L1_POST_TOOL_REVIEW_SCHEMA_VERSION
    assert len(contract.review_contract_digest) == 64
    assert contract.verdict == L1ReviewVerdict.SUFFICIENT

    # Frozen dataclass immutability
    with pytest.raises(AttributeError):
        contract.verdict = L1ReviewVerdict.INSUFFICIENT_REPLAN  # type: ignore

    as_dict = contract.as_dict()
    assert as_dict["verdict"] == "SUFFICIENT"
    assert as_dict["deterministic_checks"]["status"] == "PASS"
    assert as_dict["semantic_review"]["status"] == "PASS"

    serialized = json.dumps(as_dict)
    assert json.loads(serialized) == as_dict


def test_signed_apps_rg_l2_execution_packet_backward_compatible_fields() -> None:
    # Construct with minimum required fields and verify default outcome fields
    packet = SignedAppsRgL2ExecutionPacket(
        schema_version="apps_rg.l2_execution_packet.v2",
        request_id="req-1",
        run_id="run-1",
        app_id="apps_rg",
        trace_id="trace-1",
        tenant_id="tenant-1",
        route_id="route-1",
        workflow_id="",
        node_id="",
        step_id="step-1",
        execution_lane="MODEL",
        capability_scope_digest="cap-1",
        sandbox_envelope_digest="sand-1",
        sandbox_required=False,
        egress_policy_ref="none",
        policy_hash="pol-1",
        blueprint_hash="blue-1",
        prompt_hash="pr-1",
        replay_key="rep-1",
        attempt_number=1,
        attempt_seed="seed-1",
        snapshot_manifest="",
        idempotency_key="idem-1",
        registry_digest_set=(),
        compiled_prompt_artifact_ref="pr-1",
        final_evidence_contract_ref="ev-1",
        canonical_provider="openai",
        target_model="gpt-5",
        allowed_tools=(),
        allowed_models=("gpt-5",),
        allowed_networks=(),
        allowed_file_roots=(),
        side_effect_class="READ",
        budget={"max_tokens": 1000},
        signature_chain=(),
        signature_chain_digest="sig-1",
    )

    # Verify default fields
    assert packet.expected_output_schema_ref == ""
    assert packet.success_criteria_refs == ()
    assert packet.evidence_requirement_refs == ()

    # Verify custom outcome descriptors
    packet_with_criteria = SignedAppsRgL2ExecutionPacket(
        schema_version="apps_rg.l2_execution_packet.v2",
        request_id="req-1",
        run_id="run-1",
        app_id="apps_rg",
        trace_id="trace-1",
        tenant_id="tenant-1",
        route_id="route-1",
        workflow_id="",
        node_id="",
        step_id="step-1",
        execution_lane="MODEL",
        capability_scope_digest="cap-1",
        sandbox_envelope_digest="sand-1",
        sandbox_required=False,
        egress_policy_ref="none",
        policy_hash="pol-1",
        blueprint_hash="blue-1",
        prompt_hash="pr-1",
        replay_key="rep-1",
        attempt_number=1,
        attempt_seed="seed-1",
        snapshot_manifest="",
        idempotency_key="idem-1",
        registry_digest_set=(),
        compiled_prompt_artifact_ref="pr-1",
        final_evidence_contract_ref="ev-1",
        canonical_provider="openai",
        target_model="gpt-5",
        allowed_tools=(),
        allowed_models=("gpt-5",),
        allowed_networks=(),
        allowed_file_roots=(),
        side_effect_class="READ",
        budget={"max_tokens": 1000},
        signature_chain=(),
        signature_chain_digest="sig-1",
        expected_output_schema_ref="apps_rg.rg_output.v1",
        success_criteria_refs=("sc:all_employers_present", "sc:bullet_density_pass"),
        evidence_requirement_refs=("ev:fact_ids_bound",),
    )

    assert packet_with_criteria.expected_output_schema_ref == "apps_rg.rg_output.v1"
    assert len(packet_with_criteria.success_criteria_refs) == 2
    assert len(packet_with_criteria.evidence_requirement_refs) == 1
