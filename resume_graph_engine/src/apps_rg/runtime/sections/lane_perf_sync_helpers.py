"""Companion helpers for Competencies, Headline, Role Episode, and Graph Selector lanes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "with",
    }
)
_INSURANCE_CONTEXT_TOKENS = frozenset(
    {"insurance", "brokerage", "underwriting", "claims", "guidewire", "actuarial", "carrier", "solvency"}
)
_AI_GOVERNANCE_CONTEXT_TOKENS = frozenset(
    {"agentic", "llm", "frontier", "safety", "anthropic", "guardrail", "sandbox", "route", "model"}
)


def mark_frozen_competencies_targeting(
    targeting_context: dict[str, Any],
    pp_meta: dict[str, Any],
) -> bool:
    graph_plan = pp_meta.get("selected_graph_evidence_plan")
    has_frozen = bool(isinstance(graph_plan, dict) and graph_plan.get("allocation_assignments"))
    if has_frozen:
        targeting_context["frozen_allocation_materialized"] = True
    return has_frozen


def extract_lane_targeting_kwargs(args: Any) -> dict[str, str]:
    return {
        "target_role": str(getattr(args, "target_title", "") or getattr(args, "target_role", "") or ""),
        "target_company": str(getattr(args, "target_company", "") or ""),
        "jd_text": str(getattr(args, "jd_text", "") or ""),
    }


def select_non_colliding_competency_synonym(
    worst: str,
    words: list[str],
    synonym_map: dict[str, str],
) -> str:
    sub = synonym_map.get(worst.lower(), "delivery")
    lower_words = [w.lower() for w in words]
    if sub.lower() in lower_words:
        return "platform" if "platform" not in lower_words else "operational"
    return sub


def score_domain_aware_target_alignment(
    target: str,
    candidate: str,
    target_terms: tuple[str, ...] | list[str],
) -> float:
    if not target or not candidate:
        return 0.0
    padded_target = f" {target} "
    padded_candidate = f" {candidate} "
    target_words = set(target.split())
    candidate_words = set(candidate.split())
    score = 0.0
    for term in target_terms:
        if term == "policy":
            if f" {term} " not in padded_target or f" {term} " not in padded_candidate:
                continue
            same_domain = bool(
                (target_words & _INSURANCE_CONTEXT_TOKENS and candidate_words & _INSURANCE_CONTEXT_TOKENS)
                or (target_words & _AI_GOVERNANCE_CONTEXT_TOKENS and candidate_words & _AI_GOVERNANCE_CONTEXT_TOKENS)
            )
            if not same_domain:
                continue
        elif term not in target or term not in candidate:
            continue
        score += 1.0
    overlap = len((target_words - _STOPWORDS) & (candidate_words - _STOPWORDS))
    score += min(overlap, 8) * 0.1
    return round(score, 6)


def format_headline_clarity_reason(clarity_pre: dict[str, Any]) -> str:
    reasons = list(clarity_pre.get("opaque_segments") or []) + list(
        clarity_pre.get("semantic_overlap_issues") or []
    )
    return "headline_pre_x1d_resume_native_clarity:" + "|".join(reasons)


def invoke_role_episode_gateway_with_usage_scope(
    *,
    artifact_dir: Path,
    run_id: str,
    sid: str,
    provider: str,
    gateway_fn: Any,
    compiled_obj: Any,
    max_output_tokens: int,
    temperature: float,
) -> Any:
    from apps_model_telemetry.external_model_usage import external_model_usage_scope

    with external_model_usage_scope(
        artifact_dir=artifact_dir,
        run_id=run_id,
        stage="L2.section_generation",
        section_id=sid,
        trace_id=run_id,
        app_id="apps_rg",
    ):
        return gateway_fn(sid, provider).generate(
            provider,
            compiled_obj,
            token_budget=max_output_tokens,
            temperature=temperature,
        )
