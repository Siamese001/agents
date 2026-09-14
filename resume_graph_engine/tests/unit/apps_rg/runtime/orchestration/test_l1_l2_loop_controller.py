"""Unit tests for Bounded L1 -> L2 -> L1 Loop Controller (Wave 5)."""

from __future__ import annotations

from typing import Any, Mapping

import pytest
from apps_rg.runtime.contracts.l1_post_tool_review_contracts import (
    L1DeterministicCheckResult,
    L1PostToolReviewContract,
    L1ReviewVerdict,
    L1SemanticReviewResult,
)
from apps_rg.runtime.orchestration.l1_l2_loop_controller import (
    L1L2LoopResult,
    adapt_l1_plan_from_review,
    execute_bounded_l1_l2_loop,
)


def test_adapt_l1_plan_from_review() -> None:
    current_plan = {
        "request_id": "req-100",
        "task_plan": ("Draft summary",),
        "output_expectation": {"required_sections": ("Summary",)},
        "support_expectation": {"required_fact_ids": ("fact_1",)},
    }
    review = L1PostToolReviewContract(
        request_id="req-100",
        run_id="run-100",
        trace_id="tr-100",
        parent_l1_plan_ref="plan:123",
        sealed_l2_artifact_ref="sealed:123",
        verdict=L1ReviewVerdict.INSUFFICIENT_REPLAN,
        deterministic_checks=L1DeterministicCheckResult(
            status="FAIL",
            missing_fields=("section:Experience",),
            missing_evidence_ids=("fact_2",),
        ),
        semantic_review=L1SemanticReviewResult(
            status="INSUFFICIENT",
            subgoal_accomplished=False,
            critique="Missing leadership metrics",
            suggested_strategy_delta={"unfulfilled_subgoals": ["Quantify 10M user scaling"]},
        ),
        review_cycle=1,
    )

    adapted = adapt_l1_plan_from_review(current_plan, review)

    assert "Experience" in adapted["output_expectation"]["required_sections"]
    assert "fact_2" in adapted["support_expectation"]["required_fact_ids"]
    assert any("Quantify 10M user scaling" in sg for sg in adapted["task_plan"])
    assert adapted["replan_cycle"] == 2
    assert adapted["prior_review_contract_ref"] == review.review_contract_digest


def test_loop_controller_succeeds_on_first_cycle() -> None:
    req = {
        "request_id": "req-1",
        "run_id": "run-1",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": ["require_section:Summary"],
            "evidence_requirement_refs": [],
        },
    }

    def mock_planner(r: Mapping[str, Any]) -> dict[str, Any]:
        return {"output_expectation": {"required_sections": ("Summary",)}}

    def mock_executor(plan: Any, r: Mapping[str, Any], cycle: int) -> dict[str, Any]:
        return {
            "execution_status": "completed",
            "generated_content": "## Summary\nAccomplished engineer.",
            "sovereign_execution_receipt": "rcpt-1",
        }

    res = execute_bounded_l1_l2_loop(
        initial_request=req,
        planner_fn=mock_planner,
        executor_fn=mock_executor,
    )

    assert isinstance(res, L1L2LoopResult)
    assert res.success is True
    assert res.cycles_completed == 1
    assert res.final_verdict == L1ReviewVerdict.SUFFICIENT
    assert len(res.review_history) == 1


def test_loop_controller_recovers_via_replan_on_second_cycle() -> None:
    req = {
        "request_id": "req-replan",
        "run_id": "run-replan",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": [],
            "evidence_requirement_refs": [],
        },
    }

    def mock_planner(r: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_plan": ("Cover cloud architecture",),
            "output_expectation": {"required_sections": ("Summary", "Projects")},
        }

    def mock_executor(plan: Any, r: Mapping[str, Any], cycle: int) -> dict[str, Any]:
        if cycle == 1:
            # Cycle 1: Missing "Projects" section
            return {
                "execution_status": "completed",
                "generated_content": "## Summary\nStandard summary without projects.",
                "sovereign_execution_receipt": "rcpt-c1",
            }
        else:
            # Cycle 2: Adapted plan addressed "Projects"
            return {
                "execution_status": "completed",
                "generated_content": "## Summary\nArchitected cloud.\n\n## Projects\nLed cloud migration.",
                "sovereign_execution_receipt": "rcpt-c2",
            }

    res = execute_bounded_l1_l2_loop(
        initial_request=req,
        planner_fn=mock_planner,
        executor_fn=mock_executor,
    )

    assert res.success is True
    assert res.cycles_completed == 2
    assert len(res.review_history) == 2
    assert res.review_history[0].verdict == L1ReviewVerdict.INSUFFICIENT_REPLAN
    assert res.review_history[1].verdict == L1ReviewVerdict.SUFFICIENT
    assert len(res.plan_history) == 2


def test_loop_controller_recovers_via_retry_on_second_cycle() -> None:
    req = {
        "request_id": "req-retry",
        "run_id": "run-retry",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": [],
            "evidence_requirement_refs": [],
        },
    }

    def mock_planner(r: Mapping[str, Any]) -> dict[str, Any]:
        return {"output_expectation": {"required_sections": ()}}

    def mock_executor(plan: Any, r: Mapping[str, Any], cycle: int) -> dict[str, Any]:
        if cycle == 1:
            # Transient execution failure
            return {"execution_status": "error", "generated_content": ""}
        return {
            "execution_status": "completed",
            "generated_content": "Output after retry.",
            "sovereign_execution_receipt": "rcpt-c2",
        }

    res = execute_bounded_l1_l2_loop(
        initial_request=req,
        planner_fn=mock_planner,
        executor_fn=mock_executor,
    )

    assert res.success is True
    assert res.cycles_completed == 2
    assert res.review_history[0].verdict == L1ReviewVerdict.INSUFFICIENT_RETRY
    assert res.review_history[1].verdict == L1ReviewVerdict.SUFFICIENT


def test_loop_controller_halts_at_max_bound_on_persistent_failure() -> None:
    req = {
        "request_id": "req-persist-fail",
        "run_id": "run-persist-fail",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": ["require_section:ImpossibleSection"],
            "evidence_requirement_refs": [],
        },
    }

    def mock_planner(r: Mapping[str, Any]) -> dict[str, Any]:
        return {"output_expectation": {"required_sections": ("ImpossibleSection",)}}

    def mock_executor(plan: Any, r: Mapping[str, Any], cycle: int) -> dict[str, Any]:
        # Always fails to provide the section
        return {
            "execution_status": "completed",
            "generated_content": "## Summary\nNever provides impossible section.",
            "sovereign_execution_receipt": f"rcpt-c{cycle}",
        }

    res = execute_bounded_l1_l2_loop(
        initial_request=req,
        planner_fn=mock_planner,
        executor_fn=mock_executor,
        max_iterations=2,
    )

    assert res.success is False
    assert res.cycles_completed == 2
    assert res.final_verdict != L1ReviewVerdict.SUFFICIENT
