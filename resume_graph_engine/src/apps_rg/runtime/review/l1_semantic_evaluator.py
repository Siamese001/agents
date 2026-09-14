"""L1 Post-L2 Semantic Sufficiency Reasoner.

This module evaluates whether a sealed L2 observation actually fulfills the
original L1 plan and intent, determines whether re-planning is required,
and synthesizes the authoritative L1PostToolReviewContract.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Final, Mapping

from apps_rg.runtime.contracts.l1_post_tool_review_contracts import (
    L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
    L1DeterministicCheckResult,
    L1PostToolReviewContract,
    L1ReviewVerdict,
    L1SemanticReviewResult,
    sha256_hex,
)
from apps_rg.runtime.review.l1_deterministic_checker import (
    _get_attr_or_key,
    l1_post_l2_deterministic_check,
)

STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
        "at", "by", "for", "with", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "to", "from",
        "up", "down", "in", "out", "on", "off", "over", "under", "again",
        "further", "then", "once", "here", "there", "all", "any", "both",
        "each", "few", "more", "most", "other", "some", "such", "no", "nor",
        "not", "only", "own", "same", "so", "than", "too", "very", "can",
        "will", "just", "should", "now", "is", "are", "was", "were", "be",
        "been", "being", "have", "has", "had", "having", "do", "does", "did",
        "doing", "section", "draft", "write", "generate", "create", "ensure",
    }
)


def _extract_keywords(text: str) -> set[str]:
    """Extract substantive keywords from text."""
    tokens = re.findall(r"[A-Za-z0-9_]{3,}", text.lower())
    return {t for t in tokens if t not in STOPWORDS}


def _evaluate_subgoal_coverage(subgoal: str, content: str) -> tuple[bool, float]:
    """Check if content substantially covers the key concepts in a planned subgoal."""
    keywords = _extract_keywords(subgoal)
    if not keywords:
        return True, 1.0

    content_lower = content.lower()
    matches = sum(1 for kw in keywords if kw in content_lower)
    ratio = matches / len(keywords)
    # Require at least 50% keyword presence for subgoal fulfillment
    return ratio >= 0.5, ratio


def l1_post_l2_semantic_evaluator(
    sealed_artifact: Any,
    l1_plan: Any | None = None,
    deterministic_result: L1DeterministicCheckResult | None = None,
    *,
    semantic_judge: Callable[[Any, Any], Mapping[str, Any]] | None = None,
) -> L1SemanticReviewResult:
    """Evaluate whether the sealed L2 observation semantically satisfies L1 intent.

    Args:
      sealed_artifact: SealedL2Artifact or dict containing execution output.
      l1_plan: L1PlanContract or dict containing original plan and goals.
      deterministic_result: Optional prior result of deterministic checks.
      semantic_judge: Optional custom callable (sealed, plan) -> Mapping.

    Returns:
      L1SemanticReviewResult with sufficiency status and strategic adaptation recommendations.
    """
    # 1. Check for deterministic failure short-circuit
    if deterministic_result is not None and deterministic_result.status == "FAIL":
        if not deterministic_result.tool_execution_success:
            return L1SemanticReviewResult(
                schema_version=L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
                status="SKIPPED",
                subgoal_accomplished=False,
                evidence_sufficient=False,
                plan_adaptation_required=False,
                critique=(
                    f"Deterministic tool execution failed ({list(deterministic_result.failure_reasons)}). "
                    "Semantic evaluation skipped; tool retry indicated."
                ),
                recommended_action="RETRY_TOOL_EXECUTION",
                suggested_strategy_delta={"deterministic_failures": list(deterministic_result.failure_reasons)},
            )
        else:
            return L1SemanticReviewResult(
                schema_version=L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
                status="INSUFFICIENT",
                subgoal_accomplished=False,
                evidence_sufficient=False,
                plan_adaptation_required=True,
                critique=(
                    f"Deterministic checks failed ({list(deterministic_result.failure_reasons)}). "
                    "Output is structurally incomplete and cannot satisfy L1 intent."
                ),
                recommended_action="REPLAN_STRATEGY",
                suggested_strategy_delta={
                    "missing_fields": list(deterministic_result.missing_fields),
                    "missing_evidence_ids": list(deterministic_result.missing_evidence_ids),
                },
            )

    # 2. Delegate to custom semantic judge if supplied
    if semantic_judge is not None:
        try:
            judge_res = semantic_judge(sealed_artifact, l1_plan)
            if isinstance(judge_res, Mapping):
                status_raw = str(judge_res.get("status", "PASS")).upper()
                status = "PASS" if status_raw == "PASS" else ("SKIPPED" if status_raw == "SKIPPED" else "INSUFFICIENT")
                return L1SemanticReviewResult(
                    schema_version=L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
                    status=status,
                    subgoal_accomplished=bool(judge_res.get("subgoal_accomplished", True)),
                    evidence_sufficient=bool(judge_res.get("evidence_sufficient", True)),
                    plan_adaptation_required=bool(judge_res.get("plan_adaptation_required", False)),
                    critique=str(judge_res.get("critique", "")),
                    recommended_action=str(judge_res.get("recommended_action", "PROCEED_TO_EXIT")),
                    suggested_strategy_delta=dict(judge_res.get("suggested_strategy_delta", {})),
                )
        except Exception as exc:
            return L1SemanticReviewResult(
                schema_version=L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
                status="INSUFFICIENT",
                subgoal_accomplished=False,
                evidence_sufficient=False,
                plan_adaptation_required=True,
                critique=f"Semantic judge raised exception: {exc}",
                recommended_action="REPLAN_STRATEGY",
            )

    # 3. Native semantic sufficiency reasoning
    generated_content = str(_get_attr_or_key(sealed_artifact, "generated_content", "") or "")
    raw_task_plan = _get_attr_or_key(l1_plan, "task_plan", ())
    task_plan: tuple[str, ...] = tuple(raw_task_plan) if isinstance(raw_task_plan, (list, tuple)) else ()
    grounding_required = bool(_get_attr_or_key(l1_plan, "grounding_required", False))

    unfulfilled_subgoals: list[str] = []
    for subgoal in task_plan:
        subgoal_str = str(subgoal).strip()
        if not subgoal_str:
            continue
        covered, _ = _evaluate_subgoal_coverage(subgoal_str, generated_content)
        if not covered:
            unfulfilled_subgoals.append(subgoal_str)

    # Grounding / evidence assessment
    has_citations = bool(re.search(r"\[(?:fact|cite|ref|id)[^\]]+\]", generated_content, re.IGNORECASE))
    evidence_sufficient = True
    if grounding_required and not has_citations:
        evidence_sufficient = False

    subgoal_accomplished = len(unfulfilled_subgoals) == 0

    if subgoal_accomplished and evidence_sufficient:
        return L1SemanticReviewResult(
            schema_version=L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
            status="PASS",
            subgoal_accomplished=True,
            evidence_sufficient=True,
            plan_adaptation_required=False,
            critique="Sealed observation satisfies original L1 objective and planned subgoals.",
            recommended_action="PROCEED_TO_EXIT",
            suggested_strategy_delta={},
        )

    critique_parts: list[str] = []
    if unfulfilled_subgoals:
        critique_parts.append(f"Unfulfilled subgoals: {unfulfilled_subgoals}")
    if not evidence_sufficient:
        critique_parts.append("Grounding is required but no evidence citations were detected in generated content.")

    return L1SemanticReviewResult(
        schema_version=L1_SEMANTIC_REVIEW_SCHEMA_VERSION,
        status="INSUFFICIENT",
        subgoal_accomplished=subgoal_accomplished,
        evidence_sufficient=evidence_sufficient,
        plan_adaptation_required=True,
        critique="; ".join(critique_parts),
        recommended_action="REPLAN_STRATEGY",
        suggested_strategy_delta={
            "unfulfilled_subgoals": unfulfilled_subgoals,
            "evidence_grounding_gap": not evidence_sufficient,
        },
    )


def evaluate_l1_post_l2_review(
    sealed_artifact: Any,
    execution_packet: Any | None = None,
    l1_plan: Any | None = None,
    *,
    review_cycle: int = 1,
    semantic_judge: Callable[[Any, Any], Mapping[str, Any]] | None = None,
    custom_assertions: Mapping[str, Any] | None = None,
    timestamp: str = "",
) -> L1PostToolReviewContract:
    """Execute complete L1 Post-L2 Review combining deterministic and semantic checks.

    Orchestrates:
      1. Deterministic checks (tool execution, schema, required sections/fields, evidence).
      2. Semantic reasoning (subgoal fulfillment, grounding sufficiency).
      3. Authoritative verdict synthesis (SUFFICIENT, INSUFFICIENT_RETRY, INSUFFICIENT_REPLAN, TERMINAL_FAIL).
      4. Assembly of immutable L1PostToolReviewContract.
    """
    # 1. Deterministic evaluation
    deterministic_checks = l1_post_l2_deterministic_check(
        sealed_artifact=sealed_artifact,
        execution_packet=execution_packet,
        l1_plan=l1_plan,
        custom_assertions=custom_assertions,
    )

    # 2. Semantic evaluation
    semantic_review = l1_post_l2_semantic_evaluator(
        sealed_artifact=sealed_artifact,
        l1_plan=l1_plan,
        deterministic_result=deterministic_checks,
        semantic_judge=semantic_judge,
    )

    # 3. Synthesize Authoritative Verdict
    if deterministic_checks.status == "FAIL":
        if not deterministic_checks.tool_execution_success:
            if review_cycle < 2:
                verdict = L1ReviewVerdict.INSUFFICIENT_RETRY
            else:
                verdict = L1ReviewVerdict.TERMINAL_FAIL
        else:
            verdict = L1ReviewVerdict.INSUFFICIENT_REPLAN
    else:
        if semantic_review.status == "PASS":
            verdict = L1ReviewVerdict.SUFFICIENT
        else:
            verdict = L1ReviewVerdict.INSUFFICIENT_REPLAN

    # 4. Resolve identification metadata
    request_id = str(
        _get_attr_or_key(sealed_artifact, "request_id", "")
        or _get_attr_or_key(execution_packet, "request_id", "")
        or _get_attr_or_key(l1_plan, "request_id", "")
        or "unknown_request"
    )
    run_id = str(
        _get_attr_or_key(sealed_artifact, "run_id", "")
        or _get_attr_or_key(execution_packet, "run_id", "")
        or _get_attr_or_key(l1_plan, "run_id", "")
        or "unknown_run"
    )
    trace_id = str(
        _get_attr_or_key(sealed_artifact, "trace_id", "")
        or _get_attr_or_key(execution_packet, "trace_id", "")
        or _get_attr_or_key(l1_plan, "trace_id", "")
        or "unknown_trace"
    )

    plan_ref = str(_get_attr_or_key(l1_plan, "signature", "") or "")
    if not plan_ref:
        plan_ref = f"plan:{sha256_hex(str(l1_plan))[:16]}"

    artifact_ref = str(_get_attr_or_key(sealed_artifact, "sovereign_execution_receipt", "") or "")
    if not artifact_ref:
        artifact_ref = f"sealed:{sha256_hex(str(sealed_artifact))[:16]}"

    review_ts = timestamp or datetime.now(timezone.utc).isoformat()

    return L1PostToolReviewContract(
        request_id=request_id,
        run_id=run_id,
        trace_id=trace_id,
        parent_l1_plan_ref=plan_ref,
        sealed_l2_artifact_ref=artifact_ref,
        verdict=verdict,
        deterministic_checks=deterministic_checks,
        semantic_review=semantic_review,
        review_cycle=review_cycle,
        review_timestamp=review_ts,
    )


__all__ = [
    "evaluate_l1_post_l2_review",
    "l1_post_l2_semantic_evaluator",
]
