"""W4 contract tests for deterministic coverage-gap research revisions."""

from __future__ import annotations

import copy

import pytest

from apps_research.engines.query_decomposer import QueryPlan
from apps_research.reasoning.adaptive_research_loop import (
    AdaptiveResearchRevisionError,
    build_adaptive_research_revision,
    validate_adaptive_research_revision,
)


def _plans() -> list[QueryPlan]:
    return [
        QueryPlan(
            family="company_basics",
            query="Anthropic company overview",
            min_sources=2,
            jd_boosted=False,
        ),
        QueryPlan(
            family="partner_ecosystem",
            query="Anthropic partners",
            min_sources=1,
            jd_boosted=True,
        ),
        QueryPlan(
            family="tech_stack_and_tools",
            query="Anthropic technology",
            min_sources=2,
            jd_boosted=True,
        ),
    ]


def _observations() -> list[dict]:
    return [
        {
            "family": "company_basics",
            "retrieval_attempt_status": "PASS",
            "accepted_documents": [{"url": "https://example.com/company"}] * 2,
        },
        {
            "family": "partner_ecosystem",
            "retrieval_attempt_status": "ZERO_DOCUMENTS",
            "accepted_documents": [],
        },
        {
            "family": "tech_stack_and_tools",
            "retrieval_attempt_status": "PASS",
            "accepted_documents": [{"url": "https://example.com/tech"}],
        },
    ]


def test_w4_revises_only_jd_promoted_coverage_gaps() -> None:
    plans = _plans()
    observations = _observations()

    revision = build_adaptive_research_revision(
        topic="Anthropic",
        plans=plans,
        family_observations=observations,
    )

    assert revision["revision_status"] == "FOLLOW_UP_PROPOSED"
    assert [row["family"] for row in revision["follow_up_queries"]] == [
        "partner_ecosystem",
        "tech_stack_and_tools",
    ]
    assert revision["follow_up_queries"][0]["query"] == (
        "Anthropic official partnerships alliances cloud ecosystem primary sources"
    )
    assert revision["follow_up_queries"][0]["trigger"]["gap_reason"] == (
        "NO_GROUNDED_FIRST_PASS_RESULT"
    )
    assert revision["follow_up_queries"][1]["trigger"]["gap_reason"] == (
        "MIN_SOURCE_COVERAGE_NOT_MET"
    )
    assert revision["authority_assertions"] == {
        "does_not_create_candidate_evidence": True,
        "does_not_generate_candidate_claims": True,
        "does_not_change_l0_route": True,
        "requires_governed_retrieval_receipt": True,
    }


def test_w4_does_not_follow_up_when_jd_promoted_coverage_is_sufficient() -> None:
    plans = _plans()
    observations = _observations()
    observations[1]["retrieval_attempt_status"] = "PASS"
    observations[1]["accepted_documents"] = [{"url": "https://example.com/partner"}]
    observations[2]["accepted_documents"].append({"url": "https://example.com/tech-2"})

    revision = build_adaptive_research_revision(
        topic="Anthropic",
        plans=plans,
        family_observations=observations,
    )

    assert revision["revision_status"] == "NO_FOLLOW_UP_REQUIRED"
    assert revision["follow_up_queries"] == []


def test_w4_rejects_tampered_revision_even_if_caller_reuses_digest() -> None:
    plans = _plans()
    observations = _observations()
    revision = build_adaptive_research_revision(
        topic="Anthropic",
        plans=plans,
        family_observations=observations,
    )
    tampered = copy.deepcopy(revision)
    tampered["follow_up_queries"][0]["query"] = "Anthropic unrelated speculation"

    with pytest.raises(AdaptiveResearchRevisionError, match="digest mismatch"):
        validate_adaptive_research_revision(
            tampered,
            topic="Anthropic",
            plans=plans,
            family_observations=observations,
        )


def test_w4_rejects_incomplete_first_pass_observation_coverage() -> None:
    with pytest.raises(AdaptiveResearchRevisionError, match="must cover"):
        build_adaptive_research_revision(
            topic="Anthropic",
            plans=_plans(),
            family_observations=_observations()[:-1],
        )


def test_w4_rejects_an_unbounded_follow_up_budget() -> None:
    with pytest.raises(AdaptiveResearchRevisionError, match="bounded budget"):
        build_adaptive_research_revision(
            topic="Anthropic",
            plans=_plans(),
            family_observations=_observations(),
            max_follow_up_queries=4,
        )
