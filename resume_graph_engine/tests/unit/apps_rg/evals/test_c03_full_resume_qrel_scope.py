"""Tests for the separate W0 owner-solo full-resume QREL scope."""

from __future__ import annotations

import copy
from pathlib import Path

from apps_rg.evals.owner_solo.c03_full_resume_qrel_scope import (
    EXPECTED_SECTION_IDS,
    load_full_resume_scope,
    scope_status,
    validate_full_resume_scope,
)
from apps_rg.fact_inventory.c03_graph_node_semantic_hardening import canonical_sha256

ROOT = Path(__file__).resolve().parents[4]


def test_w0_scope_has_all_sections_but_is_invalidated_by_source_drift() -> None:
    scope = load_full_resume_scope(ROOT)

    assert [row["section_id"] for row in scope["resume_sections"]] == list(
        EXPECTED_SECTION_IDS
    )
    assert scope["planned_denominator"]["query_section_case_count"] == 66
    assert validate_full_resume_scope(scope, ROOT) == [
        "SECTION_PROFILE_DIGEST",
        "SOURCE_COMMIT",
        "TARGET_BRIEF_DIGEST",
        "TARGET_JD_DIGEST",
    ]


def test_w0_scope_detects_a_missing_ibm_section() -> None:
    scope = copy.deepcopy(load_full_resume_scope(ROOT))
    scope["resume_sections"] = [
        row for row in scope["resume_sections"] if row["section_id"] != "ibm_narrative"
    ]
    scope["scope_manifest_sha256"] = canonical_sha256(
        {key: value for key, value in scope.items() if key != "scope_manifest_sha256"}
    )

    assert "RESUME_SECTIONS" in validate_full_resume_scope(scope, ROOT)


def test_w0_scope_detects_a_changed_target_input() -> None:
    scope = copy.deepcopy(load_full_resume_scope(ROOT))
    scope["targets"][0]["jd_sha256"] = "0" * 64
    scope["scope_manifest_sha256"] = canonical_sha256(
        {key: value for key, value in scope.items() if key != "scope_manifest_sha256"}
    )

    assert "TARGET_JD_DIGEST" in validate_full_resume_scope(scope, ROOT)


def test_w0_status_is_blocked_and_not_human_or_release_ready() -> None:
    result = scope_status(ROOT)

    assert result["status"] == "W0_BLOCKED"
    assert result["issues"] == [
        "SECTION_PROFILE_DIGEST",
        "SOURCE_COMMIT",
        "TARGET_BRIEF_DIGEST",
        "TARGET_JD_DIGEST",
    ]
    assert result["human_qrels_created"] is False
    assert result["release_authorizing"] is False
