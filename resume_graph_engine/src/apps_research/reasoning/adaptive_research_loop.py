"""Deterministic W4 coverage-gap revisions for apps_research retrieval.

The planner consumes only a completed first-pass retrieval observation and its
immutable query plan.  It proposes a small, bounded set of alternative
queries for JD-promoted source families.  The caller remains responsible for
governed retrieval and for recording the resulting evidence; this module never
retrieves, synthesizes, or treats target context as candidate proof.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

from apps_research.engines.query_decomposer import QueryPlan


ADAPTIVE_RESEARCH_REVISION_SCHEMA_VERSION: Final[str] = (
    "apps_research.adaptive_research_revision.v1"
)
MAX_ADAPTIVE_FOLLOW_UP_QUERIES: Final[int] = 3
_GROUNDED_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "PASS",
        "RECOVERED_FROM_SAME_RUN",
        "RECOVERED_BY_ADAPTIVE_FOLLOW_UP",
    }
)
_FAMILY_QUERY_TERMS: Final[dict[str, str]] = {
    "partner_ecosystem": "official partnerships alliances cloud ecosystem",
    "commercial_motion": "official enterprise commercial motion partner-led growth",
    "adoption_motion": "official customer deployment adoption enablement",
    "tech_stack_and_tools": "official technology platform architecture deployments",
    "recent_news_and_signals": "official news announcements launches",
    "competitive_landscape": "official market positioning alternatives",
    "leadership_and_org": "official leadership organization executives",
    "role_context": "official careers role hiring context",
}


class AdaptiveResearchRevisionError(ValueError):
    """Raised when a first-pass observation cannot drive a safe revision."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("revision_digest", None)
    return "sha256:" + hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _normalised_topic(value: str) -> str:
    topic = " ".join(str(value or "").split())
    if not topic:
        raise AdaptiveResearchRevisionError("topic is required")
    return topic


def _observation_by_family(
    observations: Sequence[Mapping[str, Any]],
    *,
    planned_families: set[str],
) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for observation in observations:
        if not isinstance(observation, Mapping):
            raise AdaptiveResearchRevisionError("family observation must be a mapping")
        family = str(observation.get("family") or "").strip()
        if not family or family not in planned_families or family in output:
            raise AdaptiveResearchRevisionError("family observation coverage is invalid")
        output[family] = observation
    if set(output) != planned_families:
        raise AdaptiveResearchRevisionError("family observations must cover the first-pass plan")
    return output


def _source_count(observation: Mapping[str, Any]) -> int:
    accepted_documents = observation.get("accepted_documents")
    if isinstance(accepted_documents, Sequence) and not isinstance(
        accepted_documents, (str, bytes)
    ):
        return len(accepted_documents)
    raw = observation.get("accepted_document_count")
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def _gap_reason(*, status: str, source_count: int, min_sources: int) -> str:
    if status not in _GROUNDED_STATUSES:
        return "NO_GROUNDED_FIRST_PASS_RESULT"
    if source_count < min_sources:
        return "MIN_SOURCE_COVERAGE_NOT_MET"
    return ""


def _follow_up_query(topic: str, family: str) -> str:
    terms = _FAMILY_QUERY_TERMS.get(family, family.replace("_", " "))
    return f"{topic} {terms} primary sources"


def _derive_adaptive_research_revision(
    *,
    topic: str,
    plans: Sequence[QueryPlan],
    family_observations: Sequence[Mapping[str, Any]],
    max_follow_up_queries: int = MAX_ADAPTIVE_FOLLOW_UP_QUERIES,
) -> dict[str, Any]:
    """Build an immutable, bounded research revision from first-pass gaps.

    Only JD-promoted query families can receive a follow-up.  Each action is
    derived from an explicit first-pass receipt and retains identity and
    candidate-proof restrictions for the governed retrieval owner.
    """

    normalised_topic = _normalised_topic(topic)
    if not 0 <= max_follow_up_queries <= MAX_ADAPTIVE_FOLLOW_UP_QUERIES:
        raise AdaptiveResearchRevisionError(
            "max_follow_up_queries must stay within the W4 bounded budget"
        )
    plan_by_family: dict[str, QueryPlan] = {}
    for plan in plans:
        family = str(plan.family or "").strip()
        if not family or family in plan_by_family:
            raise AdaptiveResearchRevisionError("planned query families must be unique")
        plan_by_family[family] = plan
    if not plan_by_family:
        raise AdaptiveResearchRevisionError("at least one first-pass query plan is required")
    observations = _observation_by_family(
        family_observations,
        planned_families=set(plan_by_family),
    )

    follow_ups: list[dict[str, Any]] = []
    observed_rows: list[dict[str, Any]] = []
    for family, plan in plan_by_family.items():
        observation = observations[family]
        status = str(observation.get("retrieval_attempt_status") or "").strip()
        source_count = _source_count(observation)
        reason = _gap_reason(
            status=status,
            source_count=source_count,
            min_sources=int(plan.min_sources),
        )
        row = {
            "family": family,
            "jd_promoted": bool(plan.jd_boosted),
            "first_pass_status": status,
            "first_pass_source_count": source_count,
            "required_min_sources": int(plan.min_sources),
            "gap_reason": reason,
        }
        observed_rows.append(row)
        if reason and plan.jd_boosted and len(follow_ups) < max_follow_up_queries:
            follow_ups.append(
                {
                    "family": family,
                    "query": _follow_up_query(normalised_topic, family),
                    "trigger": row,
                    "strategy": "COVERAGE_GAP_FOLLOW_UP",
                    "source_quality_policy": {
                        "primary_sources_preferred": True,
                        "company_identity_admissibility_required": True,
                        "candidate_claim_prohibited": True,
                    },
                }
            )

    revision: dict[str, Any] = {
        "schema_version": ADAPTIVE_RESEARCH_REVISION_SCHEMA_VERSION,
        "authority_class": "C0_RETRIEVAL_FOLLOW_UP_ONLY",
        "topic": normalised_topic,
        "first_pass_observations": observed_rows,
        "follow_up_queries": follow_ups,
        "revision_status": "FOLLOW_UP_PROPOSED" if follow_ups else "NO_FOLLOW_UP_REQUIRED",
        "budget": {
            "max_follow_up_queries": max_follow_up_queries,
            "follow_up_query_count": len(follow_ups),
        },
        "authority_assertions": {
            "does_not_create_candidate_evidence": True,
            "does_not_generate_candidate_claims": True,
            "does_not_change_l0_route": True,
            "requires_governed_retrieval_receipt": True,
        },
    }
    revision["revision_digest"] = _digest(revision)
    return revision


def build_adaptive_research_revision(
    *,
    topic: str,
    plans: Sequence[QueryPlan],
    family_observations: Sequence[Mapping[str, Any]],
    max_follow_up_queries: int = MAX_ADAPTIVE_FOLLOW_UP_QUERIES,
) -> dict[str, Any]:
    """Build and validate a deterministic research revision from first-pass gaps."""

    revision = _derive_adaptive_research_revision(
        topic=topic,
        plans=plans,
        family_observations=family_observations,
        max_follow_up_queries=max_follow_up_queries,
    )
    validate_adaptive_research_revision(
        revision,
        topic=topic,
        plans=plans,
        family_observations=family_observations,
    )
    return revision


def validate_adaptive_research_revision(
    revision: Mapping[str, Any],
    *,
    topic: str,
    plans: Sequence[QueryPlan],
    family_observations: Sequence[Mapping[str, Any]],
) -> None:
    """Fail closed unless a revision exactly follows the first-pass evidence."""

    if not isinstance(revision, Mapping):
        raise AdaptiveResearchRevisionError("adaptive research revision must be a mapping")
    if revision.get("schema_version") != ADAPTIVE_RESEARCH_REVISION_SCHEMA_VERSION:
        raise AdaptiveResearchRevisionError("unsupported adaptive research revision schema")
    if revision.get("authority_class") != "C0_RETRIEVAL_FOLLOW_UP_ONLY":
        raise AdaptiveResearchRevisionError("adaptive research revision authority is invalid")
    if revision.get("revision_digest") != _digest(revision):
        raise AdaptiveResearchRevisionError("adaptive research revision digest mismatch")
    assertions = revision.get("authority_assertions")
    if not isinstance(assertions, Mapping) or any(
        assertions.get(key) is not True
        for key in (
            "does_not_create_candidate_evidence",
            "does_not_generate_candidate_claims",
            "does_not_change_l0_route",
            "requires_governed_retrieval_receipt",
        )
    ):
        raise AdaptiveResearchRevisionError("adaptive research authority assertions are incomplete")

    budget = revision.get("budget")
    if not isinstance(budget, Mapping):
        raise AdaptiveResearchRevisionError("adaptive research revision budget is invalid")
    max_follow_up_queries = budget.get("max_follow_up_queries")
    if isinstance(max_follow_up_queries, bool):
        raise AdaptiveResearchRevisionError("adaptive research revision budget is invalid")
    try:
        bounded_max_follow_up_queries = int(max_follow_up_queries)
    except (TypeError, ValueError) as exc:
        raise AdaptiveResearchRevisionError(
            "adaptive research revision budget is invalid"
        ) from exc
    expected = _derive_adaptive_research_revision(
        topic=topic,
        plans=plans,
        family_observations=family_observations,
        max_follow_up_queries=bounded_max_follow_up_queries,
    )
    if dict(revision) != expected:
        raise AdaptiveResearchRevisionError(
            "adaptive research revision does not match first-pass observations"
        )


__all__ = [
    "ADAPTIVE_RESEARCH_REVISION_SCHEMA_VERSION",
    "AdaptiveResearchRevisionError",
    "MAX_ADAPTIVE_FOLLOW_UP_QUERIES",
    "build_adaptive_research_revision",
    "validate_adaptive_research_revision",
]
