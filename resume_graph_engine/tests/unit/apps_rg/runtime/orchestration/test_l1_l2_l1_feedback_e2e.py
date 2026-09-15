"""End-to-End Integration Tests for L1 -> L2 -> L1 Agentic Feedback Loop Architecture (Wave 6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest
from apps_rg.runtime.contracts.l1_post_tool_review_contracts import L1ReviewVerdict
from apps_rg.runtime.orchestration.app_single_action_spine import (
    run_apps_rg_single_action_spine,
)
from apps_rg.runtime.orchestration.l1_l2_loop_controller import (
    execute_bounded_l1_l2_loop,
)
from apps_rg.runtime.review.l1_semantic_evaluator import evaluate_l1_post_l2_review
from apps_rg.runtime.spine.section_x3_finalize import _run_section_spine_exit_eval


def test_e2e_happy_path_l1_l2_l1_sufficient_and_exit_authorized(tmp_path: Path) -> None:
    """Golden path: L1 Plan -> L2 Execution -> L1 Review (SUFFICIENT) -> Exit Gate Authorization."""
    req = {
        "request_id": "req-e2e-happy",
        "run_id": "run-e2e-happy",
        "app_id": "apps_rg",
        "execution_scope": "section",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": ["require_section:Summary", "non_empty_content"],
            "evidence_requirement_refs": ["fact_exp_01"],
        },
        "l1_plan": {
            "task_plan": ("Detail distributed systems architecture experience",),
            "output_expectation": {"required_sections": ("Summary",)},
            "support_expectation": {"required_fact_ids": ("fact_exp_01",)},
        },
    }

    # Execute L2 tool
    l2_output = {
        "execution_status": "completed",
        "generated_content": (
            "## Summary\n"
            "Led distributed systems architecture scaling to millions of daily requests [fact_exp_01]."
        ),
        "sovereign_execution_receipt": "rcpt-e2e-happy",
    }

    # 1. Single action spine execution
    res = run_apps_rg_single_action_spine(
        raw_request=req,
        artifact_dir=tmp_path,
        cache_preflight_evidence={"status": "READY"},
        l2_callable=lambda: l2_output,
    )

    assert res.fault == ""
    assert res.x3_disposition == "X3D_ALLOW_FINISH"

    # 2. Verify L1 Post-Tool Review artifact on disk
    review_path = tmp_path / "l1_post_tool_review.json"
    assert review_path.is_file()
    review_doc = json.loads(review_path.read_text(encoding="utf-8"))
    payload = review_doc.get("payload", review_doc)
    assert payload["verdict"] == L1ReviewVerdict.SUFFICIENT.value
    assert payload["deterministic_checks"]["status"] == "PASS"
    assert payload["semantic_review"]["status"] == "PASS"

    # 3. Verify Exit Gating validates L1 Review
    # Section exit preconditions require sealed_l2_artifact.json
    (tmp_path / "sealed_l2_artifact.json").write_text(
        json.dumps(l2_output, indent=2), encoding="utf-8"
    )
    x3_doc = {"pass_": True, "x3_code": "X3_PASS"}
    runtime_payload: dict[str, Any] = {
        "run_id": "run-e2e-happy",
        "request_id": "req-e2e-happy",
        "product_visible": True,
        "l1_post_tool_review": payload,
    }

    _run_section_spine_exit_eval(
        tmp_path,
        section_id="headline",
        runtime_payload=runtime_payload,
        x3_doc=x3_doc,
    )

    assert x3_doc["pass_"] is True
    assert runtime_payload.get("l1_review_blocked") is not True


def test_e2e_replan_loop_recovery_and_exit_authorized(tmp_path: Path) -> None:
    """Multi-turn recovery: L1 review detects gaps -> re-plans -> cycle 2 succeeds -> exit gates pass."""
    req = {
        "request_id": "req-e2e-replan",
        "run_id": "run-e2e-replan",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": ["require_section:Summary", "require_section:Leadership"],
            "evidence_requirement_refs": ["fact_lead_01"],
        },
    }

    def planner(r: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_plan": ("Highlight global executive leadership across engineering teams",),
            "output_expectation": {"required_sections": ("Summary", "Leadership")},
            "support_expectation": {"required_fact_ids": ("fact_lead_01",)},
        }

    def executor(plan: Any, r: Mapping[str, Any], cycle: int) -> dict[str, Any]:
        if cycle == 1:
            # Cycle 1: Missing "Leadership" section and "fact_lead_01"
            return {
                "execution_status": "completed",
                "generated_content": "## Summary\nAccomplished technical professional.",
                "sovereign_execution_receipt": "rcpt-c1",
            }
        else:
            # Cycle 2: Fully satisfies adapted plan requirements
            return {
                "execution_status": "completed",
                "generated_content": (
                    "## Summary\n"
                    "High impact technology executive.\n\n"
                    "## Leadership\n"
                    "Directed global engineering leadership driving organizational excellence [fact_lead_01]."
                ),
                "sovereign_execution_receipt": "rcpt-c2",
            }

    loop_res = execute_bounded_l1_l2_loop(
        initial_request=req,
        planner_fn=planner,
        executor_fn=executor,
        max_iterations=2,
    )

    # Assert bounded loop succeeded on cycle 2
    assert loop_res.success is True
    assert loop_res.cycles_completed == 2
    assert loop_res.review_history[0].verdict == L1ReviewVerdict.INSUFFICIENT_REPLAN
    assert loop_res.review_history[1].verdict == L1ReviewVerdict.SUFFICIENT

    # Verify Exit Gates authorize the completed cycle 2 artifact
    (tmp_path / "sealed_l2_artifact.json").write_text(
        json.dumps(loop_res.final_sealed_artifact, indent=2), encoding="utf-8"
    )
    x3_doc = {"pass_": True, "x3_code": "X3_PASS"}
    runtime_payload: dict[str, Any] = {
        "run_id": "run-e2e-replan",
        "request_id": "req-e2e-replan",
        "product_visible": True,
        "l1_post_tool_review": loop_res.latest_review.as_dict(),
    }

    _run_section_spine_exit_eval(
        tmp_path,
        section_id="headline",
        runtime_payload=runtime_payload,
        x3_doc=x3_doc,
    )

    assert x3_doc["pass_"] is True
    assert runtime_payload.get("l1_review_blocked") is not True


def test_e2e_unrecoverable_replan_halts_and_exit_blocks(tmp_path: Path) -> None:
    """Safety protection: Irreconcilable gap halts after cycle 2; exit gates block release."""
    req = {
        "request_id": "req-e2e-fail",
        "run_id": "run-e2e-fail",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": ["require_section:StrictSecretSection"],
            "evidence_requirement_refs": ["fact_unobtainable_99"],
        },
    }

    def planner(r: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "task_plan": ("Incorporate unavailable data",),
            "output_expectation": {"required_sections": ("StrictSecretSection",)},
            "support_expectation": {"required_fact_ids": ("fact_unobtainable_99",)},
        }

    def executor(plan: Any, r: Mapping[str, Any], cycle: int) -> dict[str, Any]:
        # Always fails to provide the required evidence
        return {
            "execution_status": "completed",
            "generated_content": "## Summary\nBasic text without required section or fact.",
            "sovereign_execution_receipt": f"rcpt-fail-c{cycle}",
        }

    loop_res = execute_bounded_l1_l2_loop(
        initial_request=req,
        planner_fn=planner,
        executor_fn=executor,
        max_iterations=2,
    )

    # Loop must halt at max_iterations = 2 and report failure
    assert loop_res.success is False
    assert loop_res.cycles_completed == 2
    assert loop_res.final_verdict == L1ReviewVerdict.INSUFFICIENT_REPLAN

    # Now verify Exit Gates fail closed when presented with this outcome
    (tmp_path / "sealed_l2_artifact.json").write_text(
        json.dumps(loop_res.final_sealed_artifact, indent=2), encoding="utf-8"
    )
    x3_doc = {"pass_": True, "x3_code": "X3_PASS"}
    runtime_payload: dict[str, Any] = {
        "run_id": "run-e2e-fail",
        "request_id": "req-e2e-fail",
        "product_visible": True,
        "l1_post_tool_review": loop_res.latest_review.as_dict(),
    }

    _run_section_spine_exit_eval(
        tmp_path,
        section_id="headline",
        runtime_payload=runtime_payload,
        x3_doc=x3_doc,
    )

    assert x3_doc["pass_"] is False
    assert x3_doc["blocked_by_gate"] == "l1_post_tool_review"
    assert x3_doc["x3_code"] == "X3_BLOCK_L1_REVIEW_INSUFFICIENT_REPLAN"
    assert runtime_payload["l1_review_blocked"] is True


def test_e2e_transient_tool_error_retry_and_recovery(tmp_path: Path) -> None:
    """Tool execution error in cycle 1 triggers retry; cycle 2 recovers and exit authorizes."""
    req = {
        "request_id": "req-e2e-retry",
        "run_id": "run-e2e-retry",
        "l2_execution_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": [],
            "evidence_requirement_refs": [],
        },
    }

    def planner(r: Mapping[str, Any]) -> dict[str, Any]:
        return {"output_expectation": {"required_sections": ()}}

    def executor(plan: Any, r: Mapping[str, Any], cycle: int) -> dict[str, Any]:
        if cycle == 1:
            return {"execution_status": "error", "generated_content": ""}
        return {
            "execution_status": "completed",
            "generated_content": "Successful generation on tool retry.",
            "sovereign_execution_receipt": "rcpt-retry-c2",
        }

    loop_res = execute_bounded_l1_l2_loop(
        initial_request=req,
        planner_fn=planner,
        executor_fn=executor,
        max_iterations=2,
    )

    assert loop_res.success is True
    assert loop_res.cycles_completed == 2
    assert loop_res.review_history[0].verdict == L1ReviewVerdict.INSUFFICIENT_RETRY
    assert loop_res.review_history[1].verdict == L1ReviewVerdict.SUFFICIENT
