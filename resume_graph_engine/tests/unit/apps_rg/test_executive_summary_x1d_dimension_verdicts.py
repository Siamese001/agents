"""Unit tests for executive_summary X1D dimension_verdicts and operator matrix."""

from __future__ import annotations

import json

import pytest

from apps_rg.runtime.judges.executive_summary_x1d import _make_model_backed_output
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import (
    EXEC_SUMMARY_RUBRIC_DIMENSION_IDS,
    build_x1d_dimension_matrix,
    ensure_dimension_verdicts,
    infer_dimension_verdicts_from_judge_blob,
    write_x1d_dimension_matrix_artifact,
)
from apps_rg.runtime.sections.executive_summary_judge_remediation import (
    build_judge_remediation_user_message,
)


def _all_pass_gates() -> dict[str, dict[str, bool]]:
    return {
        "x2_exec_summary_sentence_band_3_to_4": {"pass": True, "detail": "ok"},
        "x2_exec_summary_evidence_utilization": {"pass": True, "detail": "ok"},
        "x2_exec_summary_no_credential_dump": {"pass": True, "detail": "ok"},
    }


def test_infer_dimension_verdicts_from_claude_style_blob() -> None:
    body = {
        "pass": False,
        "score": 3.0,
        "findings": ["bullet stack", "weak domain targeting for mandate"],
        "quality_flags": ["bullet_stack_prose", "weak_domain_targeting"],
        "fail_reasons": ["Generic interchangeable peer summary"],
    }
    verdicts = infer_dimension_verdicts_from_judge_blob(body, deterministic_gate_summary=_all_pass_gates())
    assert len(verdicts) == 6
    assert verdicts["six_second_scannability"]["pass"] is False
    assert verdicts["strategic_mandate_resonance"]["pass"] is False


def test_infer_dimension_verdicts_flags_ta_screen_and_ai_authenticity_language() -> None:
    body = {
        "pass": True,
        "score": 4.5,
        "findings": [
            "Ordinary peer summary, not an immediate call.",
            "The cadence feels machine-generated, with em dashes and buzzword soup.",
        ],
        "quality_flags": [],
        "fail_reasons": [],
    }
    verdicts = infer_dimension_verdicts_from_judge_blob(
        body,
        deterministic_gate_summary=_all_pass_gates(),
    )
    assert verdicts["immediate_call_conviction"]["pass"] is False
    assert verdicts["spoken_executive_authenticity"]["pass"] is False


def test_ensure_dimension_verdicts_validates_explicit_block() -> None:
    body = {
        "score_scale": "0_to_5",
        "score": 4.8,
        "threshold": 4.7,
        "pass": True,
        "decisive_failure": False,
        "findings": [],
        "cited_sentence_indexes": [],
        "remediation_suggestions": [],
        "dimension_verdicts": {
            dim: {"pass": True, "severity": "none", "codes": []}
            for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS
        },
    }
    out, inferred = ensure_dimension_verdicts(body, deterministic_gate_summary=_all_pass_gates())
    assert inferred is False
    assert len(out["dimension_verdicts"]) == 6


def test_make_model_backed_output_attaches_dimension_verdicts() -> None:
    body = {
        "score_scale": "0_to_5",
        "score": 3.0,
        "threshold": 4.7,
        "pass": False,
        "decisive_failure": False,
        "findings": ["robotic prose and bullet stack"],
        "cited_sentence_indexes": [1],
        "remediation_suggestions": [],
        "quality_flags": ["bullet_stack_prose"],
    }
    out = _make_model_backed_output(
        "openai_chatgpt",
        "h",
        "m",
        dict(body),
        deterministic_gate_summary=_all_pass_gates(),
    )
    assert out.dimension_verdicts
    assert "six_second_scannability" in out.dimension_verdicts
    assert "spoken_executive_authenticity" in out.dimension_verdicts


def test_dimension_matrix_consensus_fail() -> None:
    judges = [
        {
            "evaluator_mode": "MODEL_BACKED",
            "provider_key": "gemini_pro",
            "provider_name": "Gemini",
            "pass": False,
            "dimension_verdicts": {
                "spoken_executive_authenticity": {"pass": False, "severity": "major", "codes": ["ai_bridge_crutch"]},
                **{d: {"pass": True, "severity": "none", "codes": []} for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS if d != "spoken_executive_authenticity"},
            },
        },
        {
            "evaluator_mode": "MODEL_BACKED",
            "provider_key": "anthropic_claude",
            "provider_name": "Claude",
            "pass": False,
            "dimension_verdicts": {
                "spoken_executive_authenticity": {"pass": False, "severity": "major", "codes": ["ai_bridge_crutch"]},
                **{d: {"pass": True, "severity": "none", "codes": []} for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS if d != "spoken_executive_authenticity"},
            },
        },
        {
            "evaluator_mode": "MODEL_BACKED",
            "provider_key": "openai_chatgpt",
            "provider_name": "OpenAI",
            "pass": True,
            "dimension_verdicts": {d: {"pass": True, "severity": "none", "codes": []} for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS},
        },
    ]
    matrix = build_x1d_dimension_matrix(judges)
    assert matrix["by_dimension"]["spoken_executive_authenticity"]["consensus_fail"] is True
    assert matrix["by_dimension"]["spoken_executive_authenticity"]["fail_count"] == 2


def test_write_matrix_artifact(tmp_path) -> None:
    judges = [
        {
            "evaluator_mode": "MODEL_BACKED",
            "provider_key": "openai_chatgpt",
            "pass": True,
            "dimension_verdicts": {d: {"pass": True, "severity": "none", "codes": []} for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS},
        },
    ]
    path = write_x1d_dimension_matrix_artifact(tmp_path / "x1d_dimension_matrix.json", judges)
    body = json.loads(open(path, encoding="utf-8").read())
    assert body["schema"] == "executive_summary_x1d_dimension_matrix_v1"


def test_regen_message_includes_dimension_block() -> None:
    judges = [
        {
            "evaluator_mode": "MODEL_BACKED",
            "provider_key": "gemini_pro",
            "provider_name": "Gemini",
            "pass": False,
            "normalized_score": 0.6,
            "normalized_threshold": 0.94,
            "dimension_verdicts": {
                "spoken_executive_authenticity": {"pass": False, "severity": "major", "codes": ["ai_bridge_crutch"]},
                **{d: {"pass": True, "severity": "none", "codes": []} for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS if d != "spoken_executive_authenticity"},
            },
        },
    ]
    msg = build_judge_remediation_user_message(x1d_judges=judges, unused_fact_ids=[], allowed_fact_count=4)
    assert "REGEN_DELTA" in msg
    assert "spoken_executive_authenticity" in msg
