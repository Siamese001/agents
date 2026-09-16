"""Unit tests for mtime-aware resolution caching, DAG manifest memoization, and scorecard."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from apps_rg.integrations.apps_research_bridge import (
    clear_canonical_targeting_brief_cache,
    _CANONICAL_TARGETING_BRIEF_CACHE,
    _resolve_canonical_targeting_brief,
)
from apps_rg.runtime.assembly.full_resume_llm_coherence import (
    aggregate_full_resume_coherence,
)
from apps_rg.runtime.assembly.full_resume_llm_coherence_rubric import (
    build_lens_analysis,
    build_recruitment_readiness_scorecard,
)
from apps_rg.runtime.briefing_resolution import (
    clear_briefing_cache,
    resolve_briefing_for_lanes,
    _RESOLVED_BRIEFING_CACHE,
)
from apps_rg.runtime.jd_resolution import (
    clear_jd_cache,
    resolve_jd_for_lanes,
    _RESOLVED_JD_CACHE,
)
from apps_rg.runtime.orchestration.section_lane_concurrency import (
    load_section_dag_manifest,
)
from apps_rg.runtime.resume_resolution import (
    clear_resume_cache,
    load_candidate_static_profile_json,
    resolve_resume_for_lanes,
    _RESOLVED_RESUME_CACHE,
    _STATIC_PROFILE_CACHE,
)


def test_briefing_resolution_caching_and_invalidation(tmp_path: Path) -> None:
    clear_briefing_cache()
    brief_file = tmp_path / "role_briefing.md"
    brief_file.write_text("# Test Brief\n\nInitial content.", encoding="utf-8")

    r1 = resolve_briefing_for_lanes(briefing_artifact_ref=str(brief_file))
    assert "Initial content" in r1.text
    assert len(_RESOLVED_BRIEFING_CACHE) >= 1

    # Second call should return cached result
    r2 = resolve_briefing_for_lanes(briefing_artifact_ref=str(brief_file))
    assert r2.briefing_digest == r1.briefing_digest
    assert r2.text == r1.text

    # Invalidate by updating mtime and content
    time.sleep(0.01)
    brief_file.write_text("# Test Brief\n\nUpdated content.", encoding="utf-8")
    os.utime(brief_file, (time.time() + 1, time.time() + 1))

    r3 = resolve_briefing_for_lanes(briefing_artifact_ref=str(brief_file))
    assert "Updated content" in r3.text
    assert r3.briefing_digest != r1.briefing_digest

    clear_briefing_cache()
    assert len(_RESOLVED_BRIEFING_CACHE) == 0


def test_jd_resolution_caching_and_invalidation(tmp_path: Path) -> None:
    clear_jd_cache()
    jd_file = tmp_path / "test_jd.md"
    jd_file.write_text("# Staff Engineer JD\n\nDistributed systems experience required.", encoding="utf-8")

    res1 = resolve_jd_for_lanes(job_description_ref=str(jd_file))
    assert res1.description
    assert len(_RESOLVED_JD_CACHE) >= 1

    # Second call with same mtime should return cached result
    res2 = resolve_jd_for_lanes(job_description_ref=str(jd_file))
    assert res2.jd_digest == res1.jd_digest
    assert res2.description == res1.description

    # Invalidate by modifying file
    time.sleep(0.01)
    jd_file.write_text("# Staff Engineer JD\n\nDistributed systems and AI experience.", encoding="utf-8")
    os.utime(jd_file, (time.time() + 1, time.time() + 1))

    res3 = resolve_jd_for_lanes(job_description_ref=str(jd_file))
    assert res3.jd_digest != res1.jd_digest

    clear_jd_cache()
    assert len(_RESOLVED_JD_CACHE) == 0


def test_resume_resolution_caching_and_invalidation(tmp_path: Path) -> None:
    clear_resume_cache()
    resume_file = tmp_path / "base_resume.json"
    resume_file.write_text('{"schema": "resume.v1", "sections": []}', encoding="utf-8")

    r1 = resolve_resume_for_lanes(source_resume_ref=str(resume_file), repo_root=tmp_path)
    assert len(_RESOLVED_RESUME_CACHE) >= 1

    r2 = resolve_resume_for_lanes(source_resume_ref=str(resume_file), repo_root=tmp_path)
    assert r2.resume_digest == r1.resume_digest

    time.sleep(0.01)
    resume_file.write_text('{"schema": "resume.v2", "sections": []}', encoding="utf-8")
    os.utime(resume_file, (time.time() + 1, time.time() + 1))

    r3 = resolve_resume_for_lanes(source_resume_ref=str(resume_file), repo_root=tmp_path)
    assert r3.resume_digest != r1.resume_digest

    clear_resume_cache()
    assert len(_RESOLVED_RESUME_CACHE) == 0


def test_static_profile_caching(tmp_path: Path) -> None:
    clear_resume_cache()
    profile_path = tmp_path / "candidate_static_profile.json"
    profile_path.write_text('{"schema": "profile.v1", "name": "Test Candidate"}', encoding="utf-8")

    doc1, path1, digest1 = load_candidate_static_profile_json(
        source_static_profile_ref=str(profile_path),
        repo_root=tmp_path,
    )
    assert doc1.get("name") == "Test Candidate"

    # Second call should hit cache
    doc2, path2, digest2 = load_candidate_static_profile_json(
        source_static_profile_ref=str(profile_path),
        repo_root=tmp_path,
    )
    assert (doc2, path2, digest2) == (doc1, path1, digest1)

    clear_resume_cache()
    assert len(_STATIC_PROFILE_CACHE) == 0


def test_canonical_targeting_brief_caching() -> None:
    clear_canonical_targeting_brief_cache()

    brief1, path1 = _resolve_canonical_targeting_brief(
        company_name="Anthropic",
        job_title="Applied AI",
    )
    if brief1:
        assert len(_CANONICAL_TARGETING_BRIEF_CACHE) >= 1

        # Second call should hit cache
        brief2, path2 = _resolve_canonical_targeting_brief(
            company_name="Anthropic",
            job_title="Applied AI",
        )
        assert (brief2, path2) == (brief1, path1)

    clear_canonical_targeting_brief_cache()
    assert len(_CANONICAL_TARGETING_BRIEF_CACHE) == 0


def test_section_dag_manifest_memoization() -> None:
    manifest1 = load_section_dag_manifest()
    manifest2 = load_section_dag_manifest()
    assert manifest1 is manifest2
    assert "lanes" in manifest1


def test_recruitment_readiness_scorecard_logic() -> None:
    # Test case 1: Clear pass
    lens_analysis_clear = {
        "lens_status": {
            "narrative_coherence": "CLEAR",
            "hr_recruiter_first_impression": "CLEAR",
            "ats_semantic_taxonomy": "CLEAR",
            "jd_briefing_resonance": "CLEAR",
            "knockout_and_risk_vectors": "CLEAR",
            "altitude_and_band_calibration": "CLEAR",
        },
        "lens_findings_count": {},
    }
    scorecard_clear = build_recruitment_readiness_scorecard(
        lens_analysis_clear,
        criteria_scores={"mean_normalized_score": 0.95},
        full_resume_coherence_pass=True,
    )
    assert scorecard_clear["readiness_tier"] == "STRONG_HIRE_INTERVIEW_READY"
    assert scorecard_clear["full_pass"] is True
    assert "Clear signal" in scorecard_clear["recruiter_verdict"]

    # Test case 2: Pass with non-fatal blocker/observations
    lens_analysis_risks = {
        "lens_status": {
            "narrative_coherence": "BLOCKER",
            "hr_recruiter_first_impression": "CLEAR",
        },
        "lens_findings_count": {"narrative_coherence": 1},
    }
    scorecard_risks = build_recruitment_readiness_scorecard(
        lens_analysis_risks,
        criteria_scores={"mean_normalized_score": 0.88},
        full_resume_coherence_pass=True,
    )
    assert scorecard_risks["readiness_tier"] == "QUALIFIED_WITH_FLAGGED_RISKS"

    # Test case 3: Failed pass
    scorecard_fail = build_recruitment_readiness_scorecard(
        lens_analysis_clear,
        criteria_scores={"mean_normalized_score": 0.40},
        full_resume_coherence_pass=False,
    )
    assert scorecard_fail["readiness_tier"] == "NEEDS_REMEDIATION"
