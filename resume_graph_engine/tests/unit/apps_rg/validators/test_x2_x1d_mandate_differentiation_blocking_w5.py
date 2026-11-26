"""Wave 5 unit tests: X2 validator harmonization & blocking X1D career-arc / mandate differentiation gates."""
from __future__ import annotations

import yaml
from pathlib import Path

from apps_eval.graders.judge.v3_registry import JudgeRubricRegistryV3
from apps_rg.runtime.assembly.final_resume_x2 import OPTIONAL_GENERATED_LANES
from apps_rg.runtime.judges.executive_summary_judge_packet import (
    build_executive_summary_judge_packet,
    render_judge_prompt_from_packet,
)
from apps_rg.runtime.judges.v3_section_judge import (
    BLOCKING_DIFFERENTIATION_CHECK_IDS,
    evaluate_v3_judge_response_to_dict,
)
from apps_rg.runtime.validators.exec_summary_x2.surface_checks import (
    check_cross_fact_display_conflation,
)


def _worktree_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_resume_x1d_quorum_alias_points_to_full_resume_coherence_without_breaking_outreach() -> None:
    reg = JudgeRubricRegistryV3.load()
    assert reg.get_profile("resume_x1d_quorum").profile_id == "resume_whole_coherence:full_resume"
    assert reg.get_profile("full_resume_coherence").profile_id == "resume_whole_coherence:full_resume"
    assert reg.get_profile("outreach_x1d_quorum").profile_id == "outreach_sequence:outreach_multi_touch_sequence"
    assert reg.get_profile("x1d_quorum").profile_id == "outreach_sequence:outreach_multi_touch_sequence"


def test_x1d_v2_exit_eval_rubric_exists_and_declares_blocking_differentiation_hard_gates() -> None:
    rg_root = _worktree_root() / "resume_graph_engine"
    versions = yaml.safe_load((rg_root / "config/exit_eval_rubrics/_versions.yaml").read_text(encoding="utf-8"))
    assert versions["versions"]["X1D"] == "v2"
    x1d_path = rg_root / "config/exit_eval_rubrics/x1d_v2.yaml"
    assert x1d_path.is_file()
    doc = yaml.safe_load(x1d_path.read_text(encoding="utf-8"))
    hard_gates = {d["name"] for d in doc["dimensions"] if d.get("is_hard_gate") is True}
    assert {"groundedness", "career_arc_three_era_differentiation", "target_mandate_differentiation"}.issubset(hard_gates)


def test_mandate_differentiation_failure_blocks_even_when_weighted_score_reaches_080() -> None:
    assert {
        "mandate_fit_without_clutter",
        "target_mandate_alignment",
        "target_role_relevance",
        "unified_mandate_arc",
    }.issubset(BLOCKING_DIFFERENTIATION_CHECK_IDS)

    candidate_text = (
        "Technology executive leading cloud modernization and agentic AI engineering across utility clients."
    )
    # All checks YES except unified_mandate_arc = NO (weight 0.2 -> raw score 0.80 >= 0.80 threshold).
    # Must STILL FAIL CLOSED due to blocking differentiation veto!
    raw_full_resume = {
        "cold_read_takeaway": "Omits FSA actuarial and insurance underwriting differentiation for insurer CTO role.",
        "checks": {
            "end_to_end_factual_consistency": {"verdict": "YES", "evidence_span": ""},
            "zero_cross_section_metric_echo": {"verdict": "YES", "evidence_span": ""},
            "unified_mandate_arc": {"verdict": "NO", "evidence_span": "across utility clients"},
            "consistent_executive_voice": {"verdict": "YES", "evidence_span": ""},
        },
        "failure_tags": ["OMITTED_CONSTRAINT"],
    }
    res = evaluate_v3_judge_response_to_dict(
        raw_full_resume,
        section_id="full_resume_coherence",
        candidate_text=candidate_text,
    )
    assert res["score"] == 0.8
    assert res["pass"] is False
    assert res["decisive_failure"] is True
    assert res["dimension_verdicts"]["unified_mandate_arc"]["critical"] is True

    raw_exec = {
        "cold_read_takeaway": "Generic summary drops actuarial and insurance proof for digital insurer CTO.",
        "checks": {
            "verified_claim_entailment": {"verdict": "YES", "evidence_span": ""},
            "proof_boundary_integrity": {"verdict": "YES", "evidence_span": ""},
            "mandate_fit_without_clutter": {"verdict": "NO", "evidence_span": "across utility clients"},
            "authentic_human_voice": {"verdict": "YES", "evidence_span": ""},
            "distinct_mechanism_to_outcome": {"verdict": "YES", "evidence_span": ""},
        },
        "failure_tags": ["OMITTED_CONSTRAINT"],
    }
    res_exec = evaluate_v3_judge_response_to_dict(
        raw_exec,
        section_id="executive_summary",
        candidate_text=candidate_text,
    )
    assert res_exec["score"] == 0.8
    assert res_exec["pass"] is False
    assert res_exec["decisive_failure"] is True


def test_blind_judge_packet_injects_candidate_mandate_differentiators_without_gate_priming() -> None:
    packet = build_executive_summary_judge_packet(
        resume_display_text="Executive summary text.",
        claim_ledger=[],
        allowed_fact_packet=[],
        targeting_context={
            "target_role": "Lead Engineer CTO",
            "jd_text": "Digital life insurer CTO leading underwriting, actuarial reserving, and agentic AI.",
        },
        deterministic_gate_summary={"all_passed": True},
    )
    diffs = packet["candidate_mandate_differentiators"]
    assert diffs["mandate_profile"] == "insurance_agentic_ai"
    assert "cert_fsa_001" in diffs["credential_elevation_ids"]
    rendered = render_judge_prompt_from_packet(packet)
    assert "candidate_mandate_differentiators" in rendered
    assert "deterministic_gate_summary" not in rendered


def test_surface_checks_permit_five_bridged_source_fact_ids_and_reject_six() -> None:
    ok_five, reason_five = check_cross_fact_display_conflation(
        "Integrated three-era executive platform summary.",
        [{"claim_text": "Integrated three-era executive platform summary.", "source_fact_ids": ["f1", "f2", "f3", "f4", "f5"]}],
    )
    assert ok_five is True and reason_five is None

    ok_six, reason_six = check_cross_fact_display_conflation(
        "Integrated three-era executive platform summary.",
        [{"claim_text": "Integrated three-era executive platform summary.", "source_fact_ids": ["f1", "f2", "f3", "f4", "f5", "f6"]}],
    )
    assert ok_six is False
    assert "too_many_source_fact_ids_in_one_sentence" in str(reason_six)
    assert {"ey_bullets", "ey_narrative", "early_career_bullets", "early_career_narrative"}.issubset(
        OPTIONAL_GENERATED_LANES
    )
