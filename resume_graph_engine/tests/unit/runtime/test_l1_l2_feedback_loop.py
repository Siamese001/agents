"""Unit tests for Wave 4: Post-L2 Structured Model Review & Bounded Replan Loop Wiring."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from apps_rg.runtime.contracts.l1_post_tool_review_contracts import L1ReviewVerdict
from apps_rg.runtime.orchestration.app_single_action_spine import (
    run_apps_rg_single_action_spine,
)
from apps_rg.runtime.orchestration.l1_l2_loop_controller import (
    L1L2LoopController,
    adapt_l1_plan_from_review,
)
from apps_rg.runtime.review.l1_semantic_evaluator import (
    evaluate_l1_post_l2_review,
    l1_post_l2_semantic_evaluator,
    resolve_l1_post_l2_reviewer_role,
)


def test_l1_post_l2_reviewer_role_is_orthogonal_and_low_effort() -> None:
    reviewer = resolve_l1_post_l2_reviewer_role()
    assert reviewer["role_key"] == "reasoning.l1_post_l2_reviewer"
    assert reviewer["reasoning_effort"] == "low"
    assert reviewer["provider"]
    assert reviewer["model"]


def test_structured_json_disposition_and_stage_identifier_filtering() -> None:
    sealed = {
        "execution_status": "completed",
        "generated_content": "## Summary\nLed AI platform governance and distributed systems [fact_001].",
        "sovereign_execution_receipt": "rcpt-wave4-1",
    }
    plan = {
        "task_plan": (
            "u0_validate_apps_rg",
            "l1_plan_apps_rg",
            "c0_retrieve_apps_rg",
            "Lead AI platform governance and distributed systems",
        ),
        "grounding_required": True,
    }

    # Native evaluation ignores canonical stage identifiers in task_plan and passes
    native_res = l1_post_l2_semantic_evaluator(sealed, plan)
    assert native_res.status == "PASS"
    assert native_res.suggested_strategy_delta["disposition"] == "SUFFICIENT"
    assert native_res.suggested_strategy_delta["reviewer_role"] == "reasoning.l1_post_l2_reviewer"

    # Structured JSON judge returning REPLAN with violated_facts and repair_hint
    def _structured_judge(_sealed: Any, _plan: Any) -> Mapping[str, Any]:
        return {
            "disposition": "REPLAN",
            "violated_facts": ["fact_002"],
            "repair_hint": "Include explicit latency SLA metric from fact_002.",
        }

    review = evaluate_l1_post_l2_review(
        sealed_artifact=sealed,
        l1_plan=plan,
        review_cycle=1,
        semantic_judge=_structured_judge,
    )
    assert review.verdict == L1ReviewVerdict.INSUFFICIENT_REPLAN
    assert review.semantic_review.suggested_strategy_delta["disposition"] == "REPLAN"
    assert review.semantic_review.suggested_strategy_delta["violated_facts"] == ["fact_002"]
    assert (
        review.semantic_review.suggested_strategy_delta["repair_hint"]
        == "Include explicit latency SLA metric from fact_002."
    )

    adapted = adapt_l1_plan_from_review(plan, review)
    assert "fact_002" in adapted["support_expectation"]["required_fact_ids"]
    assert adapted["repair_hint"] == "Include explicit latency SLA metric from fact_002."
    assert any("Include explicit latency SLA metric from fact_002." in item for item in adapted["task_plan"])


def test_single_action_spine_executes_bounded_replan_loop_max_cycles_2(
    tmp_path: Path,
) -> None:
    observed_cycles: list[int] = []
    observed_repair_hints: list[str] = []

    req: dict[str, Any] = {
        "request_id": "req-wave4-spine",
        "run_id": "run-wave4-spine",
        "app_id": "apps_rg",
        "execution_scope": "section",
        "_canonical_l2_packet": {
            "expected_output_schema_ref": "markdown:section",
            "success_criteria_refs": ["require_section:Summary"],
            "evidence_requirement_refs": ["fact_001"],
        },
        "l1_plan": {
            "task_plan": ("u0_validate_apps_rg", "Highlight distributed AI architecture"),
            "output_expectation": {"required_sections": ("Summary",)},
            "support_expectation": {"required_fact_ids": ("fact_001",)},
        },
    }

    def _l2_callable(plan: Any, cycle_req: Mapping[str, Any], cycle: int) -> dict[str, Any]:
        observed_cycles.append(cycle)
        observed_repair_hints.append(str(cycle_req.get("repair_hint") or ""))
        if cycle == 1:
            return {
                "execution_status": "completed",
                "generated_content": "## Summary\nGeneric summary missing required fact and topic.",
                "sovereign_execution_receipt": "rcpt-c1",
            }
        return {
            "execution_status": "completed",
            "generated_content": (
                "## Summary\n"
                "Highlighted distributed AI architecture across global clusters [fact_001]."
            ),
            "sovereign_execution_receipt": "rcpt-c2",
        }

    result = run_apps_rg_single_action_spine(
        raw_request=req,
        artifact_dir=tmp_path,
        cache_preflight_evidence={"status": "READY"},
        l2_callable=_l2_callable,
        max_cycles=2,
    )

    assert observed_cycles == [1, 2]
    assert observed_repair_hints[0] == ""
    assert observed_repair_hints[1] != ""
    assert result.fault == ""
    assert result.x3_disposition == "X3D_ALLOW_FINISH"

    review_doc = json.loads((tmp_path / "l1_post_tool_review.json").read_text(encoding="utf-8"))
    payload = review_doc.get("payload", review_doc)
    assert payload["verdict"] == L1ReviewVerdict.SUFFICIENT.value
    assert payload["review_cycle"] == 2
