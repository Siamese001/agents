"""Pytest fixtures for apps_lic_v2 tests."""

import pytest
from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)


@pytest.fixture
def sample_candidate() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="cand_test_01",
        full_name="Jordan Reed",
        target_title="Chief Technology Officer",
        executive_summary="Proven technology executive with expertise in scaling infrastructure and cloud transformations.",
        verified_facts=[
            CandidateFact(
                fact_id="fact_scale_01",
                category="scale",
                statement="scaled revenue from $50M to $250M ARR across 4 global regions",
                metric="$250M",
            ),
            CandidateFact(
                fact_id="fact_team_02",
                category="leadership",
                statement="recruited and retained an elite engineering organization of 180+ professionals",
                metric="180+",
            ),
        ],
        key_competencies=["Enterprise Architecture", "Cloud Migration", "P&L Management"],
    )


@pytest.fixture
def sample_opportunity() -> TargetOpportunity:
    return TargetOpportunity(
        opportunity_id="opp_test_01",
        company_name="Apex Financial Systems",
        role_title="Group CTO",
        industry="Fintech & WealthTech",
        recipient_name="Marcus Vance",
        recipient_title="Managing Partner",
        recipient_class=RecipientClass.EXECUTIVE_PEER,
        relationship_distance=RelationshipDistance.COLD,
        strategic_priorities=["global core banking rollout", "SOC2 Type II compliance"],
    )
