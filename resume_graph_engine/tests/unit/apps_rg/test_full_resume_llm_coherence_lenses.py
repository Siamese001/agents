"""Unit tests for full-resume LLM coherence Rubric v3, multi-lens HR review, and lens analysis."""
from __future__ import annotations

import json
from pathlib import Path

from apps_rg.runtime.assembly.full_resume_llm_coherence import (
    aggregate_full_resume_coherence,
    emit_full_resume_llm_coherence_review,
    _build_prompt,
)
from apps_rg.runtime.assembly.full_resume_llm_coherence_rubric import (
    FULL_RESUME_COHERENCE_RUBRIC_VERSION,
    LENS_DEFINITIONS,
    _categorize_finding_by_lens,
    build_lens_analysis,
)
from apps_rg.runtime.judges.executive_summary_x1d import JudgeOutput


def _make_judge(*, key: str, pass_: bool, findings: list[str] | None = None, decisive: bool = False, score: float = 0.9) -> JudgeOutput:
    return JudgeOutput(
        judge_id=f"x1d_{key}_full_resume_coherence",
        provider_name=key,
        provider_key=key,
        evaluator_mode="LIVE",
        provider_status="OK",
        model_name="test-model",
        provider_available=True,
        provider_blocked=False,
        exact_provider_error=None,
        rubric_version=FULL_RESUME_COHERENCE_RUBRIC_VERSION,
        input_hash="abc",
        output_hash="def",
        score=score,
        score_scale="0_to_1",
        normalized_score=score,
        threshold=0.8,
        normalized_threshold=0.8,
        pass_=pass_,
        decisive_failure=decisive,
        findings=findings or [],
        cited_sentence_indexes=[],
        remediation_suggestions=[],
    )


def test_rubric_v3_prompt_contains_six_hr_lenses_and_briefing_context():
    assert FULL_RESUME_COHERENCE_RUBRIC_VERSION == "full_resume_llm_coherence_v3"
    assert len(LENS_DEFINITIONS) == 6
    assert "narrative_coherence" in LENS_DEFINITIONS
    assert "hr_recruiter_first_impression" in LENS_DEFINITIONS
    assert "ats_semantic_taxonomy" in LENS_DEFINITIONS
    assert "jd_briefing_resonance" in LENS_DEFINITIONS
    assert "knockout_and_risk_vectors" in LENS_DEFINITIONS
    assert "altitude_and_band_calibration" in LENS_DEFINITIONS

    prompt = _build_prompt(
        full_resume_text="SVP Engineering & AI Platforms executive resume text.",
        target_company="Anthropic",
        target_role="Manager of Applied AI Architecture, Partnerships",
        jd_context="Enterprise customer adoption, GTM alliance, AI safety frameworks.",
    )
    assert "EVALUATION LENSES & CORE DIMENSIONS:" in prompt
    assert "hr_recruiter_first_impression" in prompt
    assert "6-Second Initial Screen" in prompt
    assert "ats_semantic_taxonomy" in prompt
    assert "jd_briefing_resonance" in prompt
    assert "knockout_and_risk_vectors" in prompt
    assert "altitude_and_band_calibration" in prompt
    assert "TARGETING_CONTEXT (not proof)" in prompt


def test_categorize_finding_by_lens():
    assert _categorize_finding_by_lens("6-second recruiter screen passes cleanly") == "hr_recruiter_first_impression"
    assert _categorize_finding_by_lens("Visual rhythm and scannability are optimal") == "hr_recruiter_first_impression"
    assert _categorize_finding_by_lens("ATS taxonomy is cleanly clustered into domains") == "ats_semantic_taxonomy"
    assert _categorize_finding_by_lens("Strategic alignment with JD briefing priorities") == "jd_briefing_resonance"
    assert _categorize_finding_by_lens("Metric believability and attribution are verified") == "knockout_and_risk_vectors"
    assert _categorize_finding_by_lens("Executive altitude and band calibration match SVP bar") == "altitude_and_band_calibration"
    assert _categorize_finding_by_lens("Headline to summary narrative coherence holds") == "narrative_coherence"


def test_aggregate_full_resume_coherence_extracts_structured_lens_analysis():
    judges = [
        _make_judge(
            key="gemini_pro",
            pass_=True,
            score=0.92,
            findings=[
                "6-second recruiter skim immediately recognizes SVP platform leadership.",
                "ATS semantic taxonomy is cleanly organized in executive clusters.",
                "Briefing strategic resonance aligns with enterprise co-sell motion.",
                "Metric believability is strong with grounded $22M revenue attribution.",
            ],
        ),
        _make_judge(
            key="openai_chatgpt",
            pass_=True,
            score=0.88,
            findings=[
                "Seniority tone is properly calibrated to target executive band.",
                "End-to-end narrative coherence is sustained across all sections.",
            ],
        ),
    ]

    agg = aggregate_full_resume_coherence(judges, deterministic_blockers=[])
    assert agg["full_resume_coherence_pass"] is True
    assert agg["decisive_reason"] == "quorum_pass_no_blockers"
    assert "lens_analysis" in agg

    lens_analysis = agg["lens_analysis"]
    assert lens_analysis["rubric_version"] == "full_resume_llm_coherence_v3"
    assert set(lens_analysis["lenses_evaluated"]) == set(LENS_DEFINITIONS)

    assert lens_analysis["lens_status"]["hr_recruiter_first_impression"] == "OBSERVATION"
    assert lens_analysis["lens_status"]["ats_semantic_taxonomy"] == "OBSERVATION"
    assert lens_analysis["lens_status"]["jd_briefing_resonance"] == "OBSERVATION"
    assert lens_analysis["lens_status"]["knockout_and_risk_vectors"] == "OBSERVATION"
    assert lens_analysis["lens_status"]["altitude_and_band_calibration"] == "OBSERVATION"
    assert lens_analysis["lens_status"]["narrative_coherence"] == "OBSERVATION"

    assert lens_analysis["lens_findings_count"]["hr_recruiter_first_impression"] == 1
    assert lens_analysis["lens_findings_count"]["ats_semantic_taxonomy"] == 1
    assert lens_analysis["lens_findings_count"]["jd_briefing_resonance"] == 1
    assert lens_analysis["lens_findings_count"]["knockout_and_risk_vectors"] == 1
    assert lens_analysis["lens_findings_count"]["altitude_and_band_calibration"] == 1
    assert lens_analysis["lens_findings_count"]["narrative_coherence"] == 1


def test_aggregate_full_resume_coherence_flags_lens_blocker_when_decisive():
    judges = [
        _make_judge(key="gemini_pro", pass_=True),
        _make_judge(
            key="openai_chatgpt",
            pass_=False,
            decisive=True,
            score=0.4,
            findings=["JD language used as primary proof without candidate evidence."],
        ),
    ]
    agg = aggregate_full_resume_coherence(judges, deterministic_blockers=[])
    assert agg["full_resume_coherence_pass"] is False
    assert "unsupported_jd_proof:x1d_openai_chatgpt_full_resume_coherence" in agg["blockers"]
    assert agg["lens_analysis"]["lens_status"]["jd_briefing_resonance"] == "BLOCKER"


def test_emit_full_resume_llm_coherence_review_persists_lens_analysis(tmp_path: Path):
    final = {
        "final_resume_hash": "e1f2a3",
        "candidate_identity": {"candidate_name": "Test Exec", "header_contact": {}},
        "sections": [
            {
                "section_id": "headline",
                "assemble_order": 1,
                "l2_output_snapshot": {"headline_line": "SVP Engineering | AI Platform Systems"},
            },
            {
                "section_id": "executive_summary",
                "assemble_order": 2,
                "l2_output_snapshot": {
                    "resume_display_text": "Executive leader building governed agentic AI platforms."
                },
            },
        ],
    }

    review = emit_full_resume_llm_coherence_review(
        final_resume=final,
        final_resume_path=tmp_path / "final_resume.json",
        output_dir=tmp_path / "emit_lens_test",
        target_company="Anthropic",
        target_role="Applied AI Partnerships",
        mode="mocked",
    )

    review_file = tmp_path / "emit_lens_test" / "full_resume_llm_coherence_review.json"
    assert review_file.is_file()
    review_data = json.loads(review_file.read_text(encoding="utf-8"))
    assert "lens_analysis" in review_data
    assert review_data["lens_analysis"]["rubric_version"] == "full_resume_llm_coherence_v3"
    assert len(review_data["lens_analysis"]["lenses_evaluated"]) == 6

    x1d_file = tmp_path / "emit_lens_test" / "x1d_full_resume_judge_outputs.json"
    assert x1d_file.is_file()
    x1d_data = json.loads(x1d_file.read_text(encoding="utf-8"))
    assert "lens_analysis" in x1d_data["aggregation"]
