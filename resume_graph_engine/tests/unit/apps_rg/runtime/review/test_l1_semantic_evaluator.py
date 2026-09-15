"""Unit tests for L1 Post-L2 Semantic Sufficiency Reasoner."""

from __future__ import annotations

import json
from typing import Any

import pytest
from apps_rg.runtime.bindings.l2_authority_contracts import SignedAppsRgL2ExecutionPacket
from apps_rg.runtime.contracts.l1_post_tool_review_contracts import (
    L1_POST_TOOL_REVIEW_SCHEMA_VERSION,
    L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
    L1DeterministicCheckResult,
    L1PostToolReviewContract,
    L1ReviewVerdict,
    L1SemanticReviewResult,
)
from apps_rg.runtime.review.l1_semantic_evaluator import (
    evaluate_l1_post_l2_review,
    l1_post_l2_semantic_evaluator,
)
from apps_rg.runtime.spine_contracts import L1PlanContract, SealedL2Artifact


def _build_sealed(**kwargs: Any) -> SealedL2Artifact:
    base = {
        "request_id": "req-999",
        "run_id": "run-999",
        "app_id": "apps_rg",
        "trace_id": "trace-999",
        "execution_status": "completed",
        "generated_content": (
            "## Summary\n"
            "Proven software engineering leadership with 10+ years driving distributed systems [fact_01].\n\n"
            "## Skills\n"
            "Advanced Python architecture and modern cloud scale systems [fact_02]."
        ),
        "sovereign_execution_receipt": "rcpt-seal-999",
        "state_diff_authorized": True,
        "proposed_state_diff": {"updated": True},
    }
    base.update(kwargs)
    return SealedL2Artifact(**base)


def _build_plan(**kwargs: Any) -> L1PlanContract:
    base = {
        "request_id": "req-999",
        "run_id": "run-999",
        "app_id": "apps_rg",
        "trace_id": "trace-999",
        "task_plan": (
            "Highlight engineering leadership across distributed systems",
            "Detail advanced Python architecture competencies",
        ),
        "grounding_required": True,
        "output_expectation": {
            "required_sections": ("Summary", "Skills"),
        },
        "support_expectation": {
            "required_fact_ids": ("fact_01", "fact_02"),
        },
    }
    base.update(kwargs)
    return L1PlanContract(**base)


def _build_packet(**kwargs: Any) -> SignedAppsRgL2ExecutionPacket:
    base = {
        "schema_version": "apps_rg.l2_execution_packet.v2",
        "request_id": "req-999",
        "run_id": "run-999",
        "app_id": "apps_rg",
        "trace_id": "trace-999",
        "tenant_id": "tenant-999",
        "route_id": "route-999",
        "workflow_id": "wf-999",
        "node_id": "node-999",
        "step_id": "step-999",
        "execution_lane": "MODEL",
        "capability_scope_digest": "cap-999",
        "sandbox_envelope_digest": "sand-999",
        "sandbox_required": False,
        "egress_policy_ref": "none",
        "policy_hash": "pol-999",
        "blueprint_hash": "blue-999",
        "prompt_hash": "prompt-999",
        "replay_key": "rep-999",
        "attempt_number": 1,
        "attempt_seed": "seed-999",
        "snapshot_manifest": "",
        "idempotency_key": "idem-999",
        "registry_digest_set": (),
        "compiled_prompt_artifact_ref": "cp-999",
        "final_evidence_contract_ref": "fec-999",
        "canonical_provider": "gemini",
        "target_model": "gemini-2.5-flash",
        "allowed_tools": (),
        "allowed_models": ("gemini-2.5-flash",),
        "allowed_networks": (),
        "allowed_file_roots": (),
        "side_effect_class": "READ",
        "budget": {"max_tokens": 2048},
        "signature_chain": (),
        "signature_chain_digest": "sig-999",
        "expected_output_schema_ref": "markdown:section",
        "success_criteria_refs": ("require_section:Summary", "require_section:Skills"),
        "evidence_requirement_refs": ("fact_01", "fact_02"),
    }
    base.update(kwargs)
    return SignedAppsRgL2ExecutionPacket(**base)


def test_semantic_evaluator_pass_when_subgoals_covered() -> None:
    sealed = _build_sealed()
    plan = _build_plan()

    res = l1_post_l2_semantic_evaluator(sealed, plan)

    assert isinstance(res, L1SemanticReviewResult)
    assert res.schema_version == L1_SEMANTIC_REVIEW_SCHEMA_VERSION
    assert res.status == "PASS"
    assert res.subgoal_accomplished is True
    assert res.evidence_sufficient is True
    assert res.plan_adaptation_required is False
    assert res.recommended_action == "PROCEED_TO_EXIT"
    assert bool(res.review_digest)


def test_semantic_evaluator_insufficient_when_subgoals_missing() -> None:
    sealed = _build_sealed(
        generated_content="## Summary\nBasic developer profile with standard coding tasks [fact_01]."
    )
    plan = _build_plan(
        task_plan=(
            "Highlight engineering leadership across distributed systems",
            "Detail specialized quantum cryptographic protocols",
        )
    )

    res = l1_post_l2_semantic_evaluator(sealed, plan)

    assert res.status == "INSUFFICIENT"
    assert res.subgoal_accomplished is False
    assert res.plan_adaptation_required is True
    assert res.recommended_action == "REPLAN_STRATEGY"
    assert "Detail specialized quantum cryptographic protocols" in res.suggested_strategy_delta["unfulfilled_subgoals"]


def test_semantic_evaluator_short_circuit_on_deterministic_tool_failure() -> None:
    sealed = _build_sealed()
    plan = _build_plan()
    det = L1DeterministicCheckResult(
        status="FAIL",
        tool_execution_success=False,
        failure_reasons=("Tool execution status 'error' is not successful",),
    )

    res = l1_post_l2_semantic_evaluator(sealed, plan, deterministic_result=det)

    assert res.status == "SKIPPED"
    assert res.subgoal_accomplished is False
    assert res.plan_adaptation_required is False
    assert res.recommended_action == "RETRY_TOOL_EXECUTION"


def test_semantic_evaluator_insufficient_on_deterministic_missing_fields() -> None:
    sealed = _build_sealed()
    plan = _build_plan()
    det = L1DeterministicCheckResult(
        status="FAIL",
        tool_execution_success=True,
        missing_fields=("section:Skills",),
        failure_reasons=("Missing required fields: ['section:Skills']",),
    )

    res = l1_post_l2_semantic_evaluator(sealed, plan, deterministic_result=det)

    assert res.status == "INSUFFICIENT"
    assert res.plan_adaptation_required is True
    assert res.recommended_action == "REPLAN_STRATEGY"
    assert "section:Skills" in res.suggested_strategy_delta["missing_fields"]


def test_custom_semantic_judge_callback() -> None:
    sealed = _build_sealed()
    plan = _build_plan()

    def custom_judge(s: Any, p: Any) -> dict[str, Any]:
        return {
            "status": "INSUFFICIENT",
            "subgoal_accomplished": False,
            "evidence_sufficient": True,
            "plan_adaptation_required": True,
            "critique": "Custom judge flagged weak action verbs.",
            "recommended_action": "REPLAN_STRATEGY",
            "suggested_strategy_delta": {"prompt_modifier": "strengthen_verbs"},
        }

    res = l1_post_l2_semantic_evaluator(sealed, plan, semantic_judge=custom_judge)

    assert res.status == "INSUFFICIENT"
    assert res.critique == "Custom judge flagged weak action verbs."
    assert res.suggested_strategy_delta["prompt_modifier"] == "strengthen_verbs"


def test_evaluate_l1_post_l2_review_full_sufficient() -> None:
    sealed = _build_sealed()
    packet = _build_packet()
    plan = _build_plan()

    contract = evaluate_l1_post_l2_review(
        sealed_artifact=sealed,
        execution_packet=packet,
        l1_plan=plan,
        review_cycle=1,
    )

    assert isinstance(contract, L1PostToolReviewContract)
    assert contract.schema_version == L1_POST_TOOL_REVIEW_SCHEMA_VERSION
    assert contract.verdict == L1ReviewVerdict.SUFFICIENT
    assert contract.deterministic_checks.status == "PASS"
    assert contract.semantic_review.status == "PASS"
    assert len(contract.review_contract_digest) == 64

    # Test round-trip JSON serialization
    as_dict = contract.as_dict()
    assert json.loads(json.dumps(as_dict)) == as_dict


def test_evaluate_l1_post_l2_review_replan_verdict() -> None:
    # Subgoals not met -> should emit INSUFFICIENT_REPLAN
    sealed = _build_sealed(
        generated_content="## Summary\nBasic text without leadership [fact_01].\n\n## Skills\nBasic Python [fact_02]."
    )
    packet = _build_packet()
    plan = _build_plan(
        task_plan=("Lead enterprise global transformation across 500 engineers",)
    )

    contract = evaluate_l1_post_l2_review(
        sealed_artifact=sealed,
        execution_packet=packet,
        l1_plan=plan,
        review_cycle=1,
    )

    assert contract.verdict == L1ReviewVerdict.INSUFFICIENT_REPLAN
    assert contract.deterministic_checks.status == "PASS"
    assert contract.semantic_review.status == "INSUFFICIENT"


def test_evaluate_l1_post_l2_review_retry_and_terminal_verdicts() -> None:
    sealed = _build_sealed(execution_status="error")
    packet = _build_packet()
    plan = _build_plan()

    # Cycle 1: retry
    c1 = evaluate_l1_post_l2_review(sealed, packet, plan, review_cycle=1)
    assert c1.verdict == L1ReviewVerdict.INSUFFICIENT_RETRY

    # Cycle 2: terminal fail
    c2 = evaluate_l1_post_l2_review(sealed, packet, plan, review_cycle=2)
    assert c2.verdict == L1ReviewVerdict.TERMINAL_FAIL
