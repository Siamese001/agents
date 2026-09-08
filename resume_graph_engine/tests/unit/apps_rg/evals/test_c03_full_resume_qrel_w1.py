"""Tests for the W1 full-resume C0 retrieval preflight."""

from __future__ import annotations

from pathlib import Path

from apps_rg.evals.owner_solo.c03_full_resume_qrel_w1 import run_w1_preflight


ROOT = Path(__file__).resolve().parents[4]


def test_w1_fails_closed_when_scoped_sections_have_no_active_clusters() -> None:
    result = run_w1_preflight(ROOT)

    assert result["status"] == "W1_BLOCKED_PROJECTION_COVERAGE"
    assert result["missing_c0_sections"] == [
        "headline",
        "ibm_bullets",
        "ibm_narrative",
    ]
    assert result["query_section_case_count"] == 66
    assert result["candidate_judgment_count"] is None
    assert result["human_qrels_created"] is False
    assert result["metrics_computable"] is False
    assert result["runtime_graph_source_coverage"]["headline"] == {
        "source_present": True,
        "source_type": "headline_positioning_bundles",
        "bundle_count": 8,
        "graph_skill_node_count": 22,
        "linked_source_fact_count": 8,
    }
    assert result["runtime_graph_source_coverage"]["ibm_bullets"][
        "source_type"
    ] == "ibm_role_episode_bundles"


def test_w1_reports_existing_full_universe_without_calling_it_the_new_total() -> None:
    result = run_w1_preflight(ROOT)

    assert result["available_candidate_universe_by_section"] == {
        "competencies": 22,
        "executive_summary": 12,
        "unify_bullets": 19,
        "unify_narrative": 3,
        "ey_bullets": 2,
        "ey_narrative": 2,
        "insurtech_bullets": 8,
        "insurtech_narrative": 8,
    }
    assert result["available_candidate_judgment_count_before_missing_sections"] == 456
