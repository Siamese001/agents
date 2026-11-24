"""Unit tests for Clean-Slate Judge v3 `executive_summary_x1d_dimension_verdicts`."""
from __future__ import annotations

import json

from apps_rg.runtime.judges.executive_summary_x1d import _make_model_backed_output
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import (
    EXEC_SUMMARY_RUBRIC_DIMENSION_IDS,
    build_x1d_dimension_matrix,
    ensure_dimension_verdicts,
    section_dimension_veto_passes,
    write_x1d_dimension_matrix_artifact,
)


def _all_pass_gates() -> dict[str, dict[str, object]]:
    return {
        "x2_exec_summary_sentence_band_3_to_4": {"pass": True, "detail": "ok"},
        "x2_exec_summary_evidence_utilization": {"pass": True, "detail": "ok"},
        "x2_exec_summary_no_credential_dump": {"pass": True, "detail": "ok"},
    }


def test_ensure_dimension_verdicts_validates_explicit_v3_block() -> None:
    body = {
        "score_scale": "0_to_1",
        "score": 1.0,
        "threshold": 0.80,
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
    assert set(out["dimension_verdicts"]) == set(EXEC_SUMMARY_RUBRIC_DIMENSION_IDS)


def test_make_model_backed_output_attaches_v3_dimension_verdicts() -> None:
    body = {
        "cold_read_takeaway": "Robotic template cadence detected.",
        "checks": {
            "verified_claim_entailment": {"verdict": "YES", "evidence_span": ""},
            "proof_boundary_integrity": {"verdict": "YES", "evidence_span": ""},
            "mandate_fit_without_clutter": {"verdict": "NO", "evidence_span": "off-domain legacy clutter"},
            "authentic_human_voice": {"verdict": "NO", "evidence_span": "abstract noun soup"},
            "distinct_mechanism_to_outcome": {"verdict": "YES", "evidence_span": ""},
        },
        "failure_tags": ["AI_FILLER_VOICE", "OMITTED_CONSTRAINT"],
    }
    out = _make_model_backed_output(
        "openai_chatgpt",
        "h",
        "m",
        dict(body),
        deterministic_gate_summary=_all_pass_gates(),
    )
    assert out.dimension_verdicts
    assert out.dimension_verdicts["authentic_human_voice"]["pass"] is False
    assert out.pass_ is False


def test_section_dimension_veto_blocks_allocated_metric_overlap() -> None:
    ok, reasons = section_dimension_veto_passes(
        {"distinct_mechanism_to_outcome": {"pass": True, "severity": "minor", "codes": ["MINOR_ALLOCATED_METRIC_OVERLAP"]}}
    )
    assert ok is False
    assert any("section_judge_veto_code:" in r for r in reasons)


def test_dimension_matrix_consensus_fail() -> None:
    judges = [
        {
            "evaluator_mode": "MODEL_BACKED",
            "provider_key": "gemini_pro",
            "provider_name": "Gemini",
            "pass": False,
            "dimension_verdicts": {
                "authentic_human_voice": {"pass": False, "severity": "major", "codes": ["AI_FILLER_VOICE"]},
                **{d: {"pass": True, "severity": "none", "codes": []} for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS if d != "authentic_human_voice"},
            },
        },
        {
            "evaluator_mode": "MODEL_BACKED",
            "provider_key": "openai_chatgpt",
            "provider_name": "OpenAI",
            "pass": False,
            "dimension_verdicts": {
                "authentic_human_voice": {"pass": False, "severity": "major", "codes": ["AI_FILLER_VOICE"]},
                **{d: {"pass": True, "severity": "none", "codes": []} for d in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS if d != "authentic_human_voice"},
            },
        },
    ]
    matrix = build_x1d_dimension_matrix(judges)
    assert matrix["by_dimension"]["authentic_human_voice"]["consensus_fail"] is True
    assert matrix["by_dimension"]["authentic_human_voice"]["fail_count"] == 2


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
    assert body["schema"] == "executive_summary_x1d_dimension_matrix_v3"
