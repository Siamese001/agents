"""Bounded L1 -> L2 -> L1 Feedback Loop Controller.

This module provides the bounded loop controller that connects L1 review
verdicts back to planning or tool retry, strictly bounded to a maximum of
2 iterations, and decouples exit evaluation (X1D) from inline text repairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from apps_rg.runtime.contracts.l1_post_tool_review_contracts import (
    L1PostToolReviewContract,
    L1ReviewVerdict,
)
from apps_rg.runtime.review.l1_semantic_evaluator import evaluate_l1_post_l2_review

MAX_LOOP_ITERATIONS_LIMIT: int = 2


@dataclass(frozen=True, slots=True)
class L1L2LoopResult:
    """Outcome of the bounded L1 -> L2 -> L1 feedback loop."""

    success: bool
    cycles_completed: int
    final_verdict: L1ReviewVerdict
    final_sealed_artifact: Any
    review_history: tuple[L1PostToolReviewContract, ...] = field(default_factory=tuple)
    plan_history: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    @property
    def latest_review(self) -> L1PostToolReviewContract | None:
        return self.review_history[-1] if self.review_history else None


def adapt_l1_plan_from_review(
    current_plan: Any,
    review: L1PostToolReviewContract,
) -> dict[str, Any]:
    """Derive an adapted L1 plan incorporating review critique and strategic deltas.

    Extracts gaps from:
      1. Deterministic missing sections/fields and missing evidence IDs.
      2. Semantic unfulfilled subgoals and evidence grounding requirements.
    """
    plan_dict: dict[str, Any] = {}
    if isinstance(current_plan, Mapping):
        plan_dict = dict(current_plan)
    elif hasattr(current_plan, "as_dict"):
        plan_dict = dict(current_plan.as_dict())
    else:
        for attr in ("task_plan", "output_expectation", "support_expectation", "request_id", "run_id", "trace_id"):
            val = getattr(current_plan, attr, None)
            if val is not None:
                plan_dict[attr] = val

    det = review.deterministic_checks
    sem = review.semantic_review
    strategy_delta = dict(sem.suggested_strategy_delta)

    # 1. Adapt Output Expectations (required sections / fields)
    output_exp = dict(plan_dict.get("output_expectation") or {})
    req_sections = list(output_exp.get("required_sections") or [])
    for field_gap in det.missing_fields:
        if field_gap.startswith("section:"):
            sec = field_gap.split("section:", 1)[1]
            if sec not in req_sections:
                req_sections.append(sec)
    output_exp["required_sections"] = tuple(req_sections)
    plan_dict["output_expectation"] = output_exp

    # 2. Adapt Support Expectations (evidence citations)
    support_exp = dict(plan_dict.get("support_expectation") or {})
    req_facts = list(support_exp.get("required_fact_ids") or [])
    for ev_id in det.missing_evidence_ids:
        if ev_id not in req_facts:
            req_facts.append(ev_id)
    support_exp["required_fact_ids"] = tuple(req_facts)
    plan_dict["support_expectation"] = support_exp

    # 3. Adapt Task Plan (subgoals)
    current_subgoals = list(plan_dict.get("task_plan") or [])
    unfulfilled = strategy_delta.get("unfulfilled_subgoals", [])
    for unf in unfulfilled:
        directive = f"Ensure complete and explicit fulfillment of: {unf}"
        if directive not in current_subgoals:
            current_subgoals.append(directive)
    plan_dict["task_plan"] = tuple(current_subgoals)

    # 4. Attach Re-plan Metadata
    plan_dict["prior_review_contract_ref"] = review.review_contract_digest
    plan_dict["replan_cycle"] = review.review_cycle + 1
    plan_dict["adaptation_critique"] = sem.critique

    return plan_dict


def execute_bounded_l1_l2_loop(
    *,
    initial_request: Mapping[str, Any],
    planner_fn: Callable[[Mapping[str, Any]], Any],
    executor_fn: Callable[[Any, Mapping[str, Any], int], Any],
    execution_packet_resolver_fn: Callable[[Any, int], Any] | None = None,
    max_iterations: int = 2,
    semantic_judge: Callable[[Any, Any], Mapping[str, Any]] | None = None,
) -> L1L2LoopResult:
    """Execute bounded L1 -> L2 -> L1 feedback loop with strict max_iterations bound.

    Args:
      initial_request: Input user/application request payload.
      planner_fn: Callable(request_or_replan) -> L1PlanContract or dict.
      executor_fn: Callable(plan, request, cycle) -> SealedL2Artifact or dict.
      execution_packet_resolver_fn: Optional callable(plan, cycle) -> packet.
      max_iterations: Bound on execution cycles (hard capped at 2).
      semantic_judge: Optional semantic judge callback.

    Returns:
      L1L2LoopResult with full cycle telemetry and immutable review history.
    """
    bounded_max = min(max(1, max_iterations), MAX_LOOP_ITERATIONS_LIMIT)

    review_history: list[L1PostToolReviewContract] = []
    plan_history: list[Mapping[str, Any]] = []

    current_plan = planner_fn(initial_request)
    plan_history.append(dict(current_plan) if isinstance(current_plan, Mapping) else {"plan": str(current_plan)})

    final_sealed: Any = None
    final_verdict = L1ReviewVerdict.TERMINAL_FAIL

    for cycle in range(1, bounded_max + 1):
        # 1. Resolve execution packet for this cycle if resolver provided
        packet = None
        if execution_packet_resolver_fn is not None:
            packet = execution_packet_resolver_fn(current_plan, cycle)
        else:
            packet = initial_request.get("l2_execution_packet")

        # 2. Execute L2 tool
        sealed_l2 = executor_fn(current_plan, initial_request, cycle)
        final_sealed = sealed_l2

        # 3. L1 Post-L2 Review
        review = evaluate_l1_post_l2_review(
            sealed_artifact=sealed_l2,
            execution_packet=packet,
            l1_plan=current_plan,
            review_cycle=cycle,
            semantic_judge=semantic_judge,
        )
        review_history.append(review)
        final_verdict = review.verdict

        # 4. Check termination criteria
        if review.verdict == L1ReviewVerdict.SUFFICIENT:
            return L1L2LoopResult(
                success=True,
                cycles_completed=cycle,
                final_verdict=review.verdict,
                final_sealed_artifact=sealed_l2,
                review_history=tuple(review_history),
                plan_history=tuple(plan_history),
            )

        # Stop if we have reached the bound
        if cycle >= bounded_max:
            break

        # 5. Handle Feedback Loop routing
        if review.verdict == L1ReviewVerdict.INSUFFICIENT_RETRY:
            # Retry tool execution without changing plan
            continue
        elif review.verdict == L1ReviewVerdict.INSUFFICIENT_REPLAN:
            # Re-plan: adapt L1 plan with feedback delta
            adapted = adapt_l1_plan_from_review(current_plan, review)
            current_plan = adapted
            plan_history.append(dict(adapted))
        elif review.verdict == L1ReviewVerdict.TERMINAL_FAIL:
            break

    # If loop exits without reaching SUFFICIENT, mark failure
    return L1L2LoopResult(
        success=False,
        cycles_completed=len(review_history),
        final_verdict=final_verdict,
        final_sealed_artifact=final_sealed,
        review_history=tuple(review_history),
        plan_history=tuple(plan_history),
    )


__all__ = [
    "MAX_LOOP_ITERATIONS_LIMIT",
    "L1L2LoopResult",
    "adapt_l1_plan_from_review",
    "execute_bounded_l1_l2_loop",
]
