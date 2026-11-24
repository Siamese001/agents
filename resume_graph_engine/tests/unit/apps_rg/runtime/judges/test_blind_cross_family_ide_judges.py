"""Wave 2 regression tests for Blind Hiring-Manager Judge Protocol & Cross-Family IDE Judges."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps_rg.runtime.judges.executive_summary_x1d import (
    _make_model_backed_output,
    build_judge_response_schema,
)
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import (
    EXEC_SUMMARY_RUBRIC_DIMENSION_IDS,
    ensure_dimension_verdicts,
    section_dimension_veto_passes,
    section_rubric_dimension_ids,
)
from apps_rg.runtime.judges.grade_only_judge_packet import (
    _SELECTED_FACT_PLAN_JUDGE_FIELDS,
    build_grade_only_judge_packet,
    compact_candidate_output_for_judge,
    render_judge_prompt_from_packet,
)
from apps_rg.runtime.judges.section_judge_profile import resolve_section_proof_judge_model
from apps_rg.runtime.judges.x1d_ide_cli import (
    _step_judge_pin_for_effort,
    actual_lane_writer_model,
    second_judge_model,
)


def test_blind_judge_packet_strips_allocation_and_slot_plumbing() -> None:
    """Judges must read sections cold like a hiring manager without allocation_assignments or selected_metrics."""
    forbidden_plumbing_keys = {
        "allocation_assignments",
        "allocation_plan_digest",
        "allocation_plan_id",
        "allocation_scope",
        "selected_metrics",
        "selected_skill_ids",
        "selected_skills",
        "selection_method",
        "selection_rationale",
    }
    assert forbidden_plumbing_keys.isdisjoint(_SELECTED_FACT_PLAN_JUDGE_FIELDS)

    candidate = {
        "bullets": ["Directed AWS Partner offering...", "Architected enterprise cloud-native..."],
        "selected_fact_plan": {
            "section_id": "ibm_bullets",
            "facts": [{"fact_id": "ibm_001"}],
            "allocation_assignments": [{"bullet_idx": 1, "metric_outcome_id": "bcbs_239"}],
            "selected_metrics": ["$10M", "99.9%", "BCBS 239"],
            "selection_rationale": "Allocated metric outcome per slot",
        },
    }
    compacted = compact_candidate_output_for_judge(candidate)
    projected_plan = compacted["selected_fact_plan"]
    for key in forbidden_plumbing_keys:
        assert key not in projected_plan
    assert "allocation_assignments" in projected_plan["judge_projection"]["omitted_non_authoritative_fields"]
    assert "selected_metrics" in projected_plan["judge_projection"]["omitted_non_authoritative_fields"]


def test_ide_cli_judge_never_downgrades_medium_or_high_to_low() -> None:
    """Judge 2 must never be silently rewritten from -medium to -low."""
    assert _step_judge_pin_for_effort("gpt-oss-120b-medium", "low")[0] == "gpt-oss-120b-medium"
    assert _step_judge_pin_for_effort("gemini-3.8-flash-medium", "low")[0] == "gemini-3.8-flash-medium"
    assert _step_judge_pin_for_effort("gemini-4-argon-high", "low")[0] == "gemini-4-argon-high"


def test_cross_family_ide_cli_second_judge_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anthropic-written lanes use Open-Weights 120B Medium as Judge 2; OpenAI narrative lanes use Gemini 4 Neon Medium."""
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "ide_cli")
    monkeypatch.setenv("APPS_RG_GENERATION_TRANSPORT", "ide_cli")

    for anthropic_lane in (
        "headline",
        "executive_summary",
        "competencies",
        "slalom_bullets",
        "unify_bullets",
        "ibm_bullets",
        "insurtech_bullets",
    ):
        actual_writer = actual_lane_writer_model(anthropic_lane)
        slot1 = resolve_section_proof_judge_model(anthropic_lane, "gemini_pro")
        slot2 = resolve_section_proof_judge_model(anthropic_lane, "openai_chatgpt")
        assert not slot1.blocked
        assert not slot2.blocked
        assert slot2.model_actual == "gpt-oss-120b-medium"
        assert slot2.reasoning_effort == "medium"
        assert slot1.model_actual != slot2.model_actual
        assert slot2.model_actual != actual_writer
        assert "flash-low" not in slot2.model_actual

    for narrative_lane in ("slalom_narrative", "unify_narrative", "ibm_narrative", "insurtech_narrative"):
        actual_writer = actual_lane_writer_model(narrative_lane)
        slot1 = resolve_section_proof_judge_model(narrative_lane, "gemini_pro")
        slot2 = resolve_section_proof_judge_model(narrative_lane, "openai_chatgpt")
        assert not slot2.blocked
        assert slot2.model_actual == "gemini-4-neon-medium"
        assert slot2.reasoning_effort == "medium"
        assert slot2.model_actual != slot1.model_actual
        assert slot2.model_actual != actual_writer


def test_real_anthropic_ibm_allocated_metric_overlap_receipt_fails_closed() -> None:
    """Replay the real Anthropic IBM judge output where MINOR_ALLOCATED_METRIC_OVERLAP previously passed at 4.7."""
    real_anthropic_ibm_judge_payload = {
        "rationale": (
            "All five IBM Partner bullets are directly grounded in the five authorized facts in "
            "allowed_fact_packet with zero metric inflation or unverified claims. Each bullet is "
            "single-line, opens with a strong past-tense leadership verb, and lands on a quantified "
            "commercial or operational outcome aligned with the Anthropic Head of Builder Partnerships "
            "target role."
        ),
        "score_scale": "0_to_5",
        "score": 4.7,
        "threshold": 4.0,
        "pass": True,
        "decisive_failure": False,
        "findings": [
            "Minor intra-section metric/framework overlap across bullets (BCBS 239 and 99.9% uptime appear in B1 and B4; $10M revenue/ARR appears in B2 and B3), though each matches its allocated metric_outcome_id."
        ],
        "cited_sentence_indexes": [1, 4],
        "remediation_suggestions": [
            "Optional polish: vary surface phrasing between B1 and B4 so BCBS 239 and 99.9% production uptime are not echoed verbatim across two bullets in the same section."
        ],
        "dimension_verdicts": {
            "immediate_call_conviction": {"pass": True, "severity": "none", "codes": []},
            "spoken_executive_authenticity": {"pass": True, "severity": "none", "codes": []},
            "differentiated_edge": {
                "pass": True,
                "severity": "minor",
                "codes": ["MINOR_ALLOCATED_METRIC_OVERLAP"],
            },
            "six_second_scannability": {"pass": True, "severity": "none", "codes": []},
            "strategic_mandate_resonance": {"pass": True, "severity": "none", "codes": []},
            "factual_truth_and_non_exaggeration": {"pass": True, "severity": "none", "codes": []},
        },
    }

    veto_ok, reasons = section_dimension_veto_passes(real_anthropic_ibm_judge_payload["dimension_verdicts"])
    assert veto_ok is False
    assert "section_judge_veto_code:differentiated_edge:MINOR_ALLOCATED_METRIC_OVERLAP" in reasons

    out = _make_model_backed_output(
        "gemini_pro",
        "28e6ca77d7001615",
        "gemini-4-argon-medium",
        real_anthropic_ibm_judge_payload,
        section_id="ibm_bullets",
    )
    assert out.pass_ is False
    assert out.decisive_failure is True
    assert out.provider_status == "MODEL_BACKED_FAIL"
    assert any("MINOR_ALLOCATED_METRIC_OVERLAP" in f for f in out.findings)

    receipt_path = Path(__file__).resolve().parents[6] / "reports" / "wave2_blind_cross_family_ide_judges_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            {
                "wave": "W2",
                "blind_judge_packet_plumbing_stripped": True,
                "second_judge_anthropic_writer": second_judge_model("ibm_bullets")[0],
                "second_judge_openai_writer": second_judge_model("ibm_narrative")[0],
                "anthropic_ibm_overlap_vetoed": not out.pass_,
                "anthropic_ibm_provider_status": out.provider_status,
                "veto_reasons": reasons,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_section_specific_dimension_verdicts_preserved_without_exec_summary_overwrite() -> None:
    """RC-2: Section-specific dimension_verdicts (ibm_bullets, competencies) must never be overwritten with exec-summary keys."""
    ibm_dims = section_rubric_dimension_ids("ibm_bullets")
    assert "cross_bullet_outcome_diversity" in ibm_dims
    assert "episode_fact_grounding" in ibm_dims
    assert "six_second_scannability" not in ibm_dims

    ibm_schema = build_judge_response_schema(ibm_dims)
    req_dims = tuple(ibm_schema["properties"]["dimension_verdicts"]["required"])
    assert req_dims == ibm_dims

    raw_ibm_verdicts = {
        dim: {"pass": True, "severity": "none", "codes": []}
        for dim in ibm_dims
    }
    raw_ibm_verdicts["cross_bullet_outcome_diversity"] = {
        "pass": False,
        "severity": "major",
        "codes": ["repeated_bcbs_239_and_10m"],
    }
    payload = {
        "rationale": "BCBS 239 and $10M repeated across two bullets.",
        "score_scale": "0_to_5",
        "score": 4.5,
        "threshold": 4.0,
        "pass": True,
        "decisive_failure": False,
        "findings": ["BCBS 239 repeated in B1 and B4"],
        "cited_sentence_indexes": [1, 4],
        "remediation_suggestions": [],
        "dimension_verdicts": raw_ibm_verdicts,
    }
    ensured, inferred = ensure_dimension_verdicts(payload, section_id="ibm_bullets")
    assert inferred is False
    assert tuple(ensured["dimension_verdicts"].keys()) == ibm_dims
    assert ensured["dimension_verdicts"]["cross_bullet_outcome_diversity"]["pass"] is False

    out = _make_model_backed_output(
        "gemini_pro",
        "h-ibm",
        "gemini-4-argon-medium",
        payload,
        section_id="ibm_bullets",
    )
    assert out.pass_ is False
    assert out.decisive_failure is True
    assert out.dimension_verdicts["cross_bullet_outcome_diversity"]["pass"] is False


def test_non_exec_summary_prompt_omits_deterministic_gate_summary_and_never_coerces_score_upward() -> None:
    """RC-1 & RC-3: All section prompts omit DETERMINISTIC_GATE_SUMMARY and reconcile never coerces failing scores upward."""
    from apps_rg.runtime.judges.executive_summary_judge_packet import reconcile_grade_only_judge_result

    pkt = build_grade_only_judge_packet(
        section_id="ibm_bullets",
        candidate_output={"bullets": ["B1", "B2"]},
        section_rubric="Rubric",
        rubric_ref="ref",
        deterministic_gate_summary={"x2_ibm_bullets_count": {"pass": True}},
    )
    rendered = render_judge_prompt_from_packet(pkt)
    assert "DETERMINISTIC_GATE_SUMMARY" not in rendered

    failed_judge = {
        "score_scale": "0_to_5",
        "score": 3.2,
        "threshold": 4.0,
        "pass": False,
        "decisive_failure": True,
        "findings": ["Missing mandatory S5 credibility sentence"],
    }
    reconciled = reconcile_grade_only_judge_result(
        failed_judge,
        {"x2_ibm_bullets_count": {"pass": True}},
        section_id="ibm_bullets",
    )
    assert reconciled["score"] == pytest.approx(3.2)
    assert reconciled["pass"] is False
