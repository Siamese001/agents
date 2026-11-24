"""Unit tests for Clean-Slate Judge v3 competencies binding (`competencies_x1d.py`)."""
from __future__ import annotations

from apps_rg.runtime.judges import competencies_x1d
from apps_rg.runtime.judges.executive_summary_x1d import _gemini_generation_config


def test_competencies_structured_output_schema_is_strict_and_section_specific() -> None:
    schema = competencies_x1d.COMPETENCIES_JUDGE_RESPONSE_SCHEMA
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"cold_read_takeaway", "checks", "failure_tags"}
    checks = schema["properties"]["checks"]
    assert checks["additionalProperties"] is False
    assert tuple(checks["required"]) == competencies_x1d.COMPETENCIES_RUBRIC_DIMENSION_IDS
    for verdict in checks["properties"].values():
        assert verdict["additionalProperties"] is False
        assert set(verdict["required"]) == {"verdict", "evidence_span"}


def test_gemini_schema_keeps_competencies_checks_clean() -> None:
    config = _gemini_generation_config(
        thinking_level="high",
        section_id="competencies",
        response_schema=competencies_x1d.COMPETENCIES_JUDGE_RESPONSE_SCHEMA,
    )
    schema = config["responseSchema"]
    assert tuple(schema["properties"]["checks"]["required"]) == (
        competencies_x1d.COMPETENCIES_RUBRIC_DIMENSION_IDS
    )


def test_competencies_rubric_v3_stays_under_300_words_and_checks_grounding() -> None:
    rubric = competencies_x1d.COMPETENCIES_RUBRIC.lower()
    assert len(competencies_x1d.COMPETENCIES_RUBRIC.split()) <= 300
    assert "competency_source_support" in rubric
    assert "no_unverified_domain_stretch" in rubric
    assert "target_role_relevance" in rubric
    assert "non_redundant_category_clarity" in rubric


def test_run_competencies_judges_mocked_provider_contract() -> None:
    outputs = competencies_x1d.run_competencies_judges(
        competency_categories=[{"label": "Cloud", "terms": ["AWS", "Kubernetes"]}],
        claim_ledger=[{"fact_id": "F1", "claim_text": "Scaled cloud controls."}],
        judge_keys=["openai_chatgpt"],
        mode="mocked",
    )
    assert len(outputs) == 1
    out = outputs[0]
    assert out.judge_id == "x1d_openai_chatgpt_competencies"
    assert out.provider_key == "openai_chatgpt"
    assert out.evaluator_mode == "MOCKED"
    assert out.provider_status == "MOCKED"
    assert out.rubric_version == competencies_x1d.JUDGE_RUBRIC_VERSION
    assert out.pass_ is True


def test_unknown_competencies_provider_blocks_with_section_specific_judge_id(monkeypatch) -> None:
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "external_api")
    outputs = competencies_x1d.run_competencies_judges(
        competency_categories=[],
        claim_ledger=[],
        judge_keys=["missing_provider"],
        mode="mocked",
    )
    assert len(outputs) == 2
    assert all(out.judge_id.endswith("_competencies") for out in outputs)
