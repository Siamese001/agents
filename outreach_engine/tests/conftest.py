"""Pytest fixtures for apps_lic_v2 tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_PATHS = (
    _REPO_ROOT / "resume_graph_engine" / "src",
    _REPO_ROOT / "outreach_engine" / "src",
    _REPO_ROOT,
)
for _p in _REQUIRED_PATHS:
    _p_str = str(_p)
    if _p_str in sys.path:
        sys.path.remove(_p_str)
    sys.path.insert(0, _p_str)

_existing_pypath = os.environ.get("PYTHONPATH", "")
_pypath_parts = [str(_p) for _p in reversed(_REQUIRED_PATHS)]
if _existing_pypath:
    _pypath_parts.append(_existing_pypath)
os.environ["PYTHONPATH"] = os.pathsep.join(_pypath_parts)

from apps_lic.domain.models import (
    CandidateFact,
    CandidateProfile,
    RecipientClass,
    RelationshipDistance,
    TargetOpportunity,
)


@pytest.fixture(autouse=True)
def _isolate_outreach_test_env(tmp_path: Path, request: pytest.FixtureRequest) -> None:
    """Isolate per-test temporary cache/output paths and strip live keys unless marked live."""
    prev_cache = os.environ.get("APPS_LIC_CACHE_DIR")
    os.environ["APPS_LIC_CACHE_DIR"] = str(tmp_path / "lic_cache")
    try:
        yield
    finally:
        if prev_cache is None:
            os.environ.pop("APPS_LIC_CACHE_DIR", None)
        else:
            os.environ["APPS_LIC_CACHE_DIR"] = prev_cache


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
                source_reference="canonical_scale_dossier",
            ),
            CandidateFact(
                fact_id="fact_team_02",
                category="leadership",
                statement="recruited and retained an elite engineering organization of 180+ professionals",
                metric="180+",
                source_reference="canonical_leadership_dossier",
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
