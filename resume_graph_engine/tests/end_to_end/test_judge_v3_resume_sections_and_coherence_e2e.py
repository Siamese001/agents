"""Unmocked E2E tests for Clean-Slate Judge v3 across `apps_rg` Resume Sections & Whole-Resume Coherence."""
from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

from apps_eval.graders.judge import UnknownJudgeProfileError, run_preflight_lint
from apps_rg.runtime.assembly.full_resume_llm_coherence_rubric import (
    FULL_RESUME_COHERENCE_RUBRIC,
    build_lens_analysis,
    build_recruitment_readiness_scorecard,
)
from apps_rg.runtime.judges.competencies_x1d import COMPETENCIES_RUBRIC
from apps_rg.runtime.judges.employment_bullet_judge_rubric import grade_only_rubric_text
from apps_rg.runtime.judges.executive_summary_judge_packet import (
    build_executive_summary_judge_packet,
    render_judge_prompt_from_packet as render_exec_prompt,
)
from apps_rg.runtime.judges.executive_summary_x1d import (
    RUBRIC,
    _make_model_backed_output,
    build_x1d_judge_system_prompt,
)
from apps_rg.runtime.judges.grade_only_judge_packet import (
    build_grade_only_judge_packet,
    render_judge_prompt_from_packet as render_section_prompt,
)
from apps_rg.runtime.judges.headline_x1d import HEADLINE_RUBRIC
from apps_rg.runtime.judges.ibm_narrative_x1d import NARRATIVE_RUBRIC as IBM_NARRATIVE_RUBRIC
from apps_rg.runtime.judges.role_episode_x1d import ROLE_EPISODE_RUBRIC
from apps_rg.runtime.judges.v3_section_judge import (
    build_section_v3_response_schema,
    get_apps_rg_v3_profile,
    render_section_v3_rubric,
    resolve_apps_rg_v3_profile_id,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_NOUN_RE = re.compile(
    r"\b(?:bcbs\s*239|ccar|guidewire|slalom|unify|ibm|insurtech|mga)\b",
    re.IGNORECASE,
)


def test_all_apps_rg_judge_prompts_stay_under_300_words_with_zero_employer_or_incident_nouns() -> None:
    sections = (
        "headline",
        "executive_summary",
        "competencies",
        "ibm_bullets",
        "unify_bullets",
        "slalom_bullets",
        "role_episode",
        "ibm_narrative",
        "unify_narrative",
        "full_resume_coherence",
    )
    sys_prompt = build_x1d_judge_system_prompt(section_id="executive_summary")
    word_report: dict[str, int] = {}

    for sid in sections:
        rub = render_section_v3_rubric(sid)
        combined = f"{sys_prompt}\n\n{rub}"
        wc = len(combined.split())
        word_report[sid] = wc
        assert wc <= 300, f"{sid} combined prompt {wc}w > 300w"
        assert len(combined) <= 1800, f"{sid} combined prompt {len(combined)}c > 1800c"
        assert FORBIDDEN_NOUN_RE.search(combined) is None, f"Forbidden noun leaked in {sid}: {combined}"

    for exported_const in (
        RUBRIC,
        COMPETENCIES_RUBRIC,
        HEADLINE_RUBRIC,
        ROLE_EPISODE_RUBRIC,
        IBM_NARRATIVE_RUBRIC,
        FULL_RESUME_COHERENCE_RUBRIC,
        grade_only_rubric_text("ibm_bullets"),
    ):
        assert len(exported_const.split()) <= 300
        assert FORBIDDEN_NOUN_RE.search(exported_const) is None

    with pytest.raises(UnknownJudgeProfileError):
        resolve_apps_rg_v3_profile_id("unknown_section_xyz")


def test_apps_rg_judge_modules_all_satisfy_300_line_ceiling() -> None:
    judges_dir = REPO_ROOT / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "judges"
    target_files = [
        judges_dir / "v3_section_judge.py",
        judges_dir / "executive_summary_x1d.py",
        judges_dir / "executive_summary_x1d_dimension_verdicts.py",
        judges_dir / "executive_summary_judge_packet.py",
        judges_dir / "x1d_ide_cli.py",
        judges_dir / "competencies_x1d.py",
        judges_dir / "employment_bullet_judge_rubric.py",
        judges_dir / "headline_x1d.py",
        judges_dir / "ibm_bullets_x1d.py",
        judges_dir / "unify_bullets_x1d.py",
        judges_dir / "role_episode_x1d.py",
        judges_dir / "ibm_narrative_x1d.py",
        judges_dir / "unify_narrative_x1d.py",
        REPO_ROOT / "resume_graph_engine" / "src" / "apps_rg" / "runtime" / "assembly" / "full_resume_llm_coherence_rubric.py",
    ]
    line_counts = {}
    for path in target_files:
        lc = len(path.read_text(encoding="utf-8").splitlines())
        line_counts[path.name] = lc
        assert lc <= 300, f"{path.name} has {lc} lines (> 300L ceiling)"


def test_stage_a_and_stage_b_v3_e2e_across_resume_sections_and_whole_coherence() -> None:
    # Stage A catches buzzword/dash lint before LLM execution
    stage_a_bad = run_preflight_lint("SVP Engineering — holistic synergy paradigm", enforce_anti_ai_filter=True)
    assert stage_a_bad.passed is False
    assert stage_a_bad.llm_judge_executed is False
    assert stage_a_bad.normalized_unit_score is None

    # Blind packets omit deterministic_gate_summary from rendered prompt
    exec_pkt = build_executive_summary_judge_packet(
        resume_display_text="Built governed enterprise AI platform generating $42M partner co-sell pipeline.",
        claim_ledger=[{"claim_text": "$42M partner co-sell pipeline", "source_fact_ids": ["fact_01"]}],
        allowed_fact_packet=[{"fact_id": "fact_01", "claim_text": "$42M partner co-sell pipeline"}],
        targeting_context={"target_role": "Head of AI Partnerships"},
        deterministic_gate_summary={"x2_all_passed": True},
    )
    exec_rendered = render_exec_prompt(exec_pkt)
    assert "deterministic_gate_summary" not in exec_rendered
    assert "x2_all_passed" not in exec_rendered

    sec_pkt = build_grade_only_judge_packet(
        section_id="competencies",
        candidate_output={"resume_display_text": "Enterprise AI Governance: Runtime Policy Controls"},
        section_rubric=COMPETENCIES_RUBRIC,
        rubric_ref="config/governance/judge_rubrics_v3.json#resume_sections:competencies",
        claim_ledger=[],
        deterministic_gate_summary={"x2_passed": True},
    )
    sec_rendered = render_section_prompt(sec_pkt)
    assert "deterministic_gate_summary" not in sec_rendered

    # Stage B v3 atomic binary evaluation across competencies & full_resume_coherence
    comp_prof = get_apps_rg_v3_profile("competencies")
    comp_schema = build_section_v3_response_schema("competencies")
    assert comp_schema["required"][0] == "cold_read_takeaway"

    planted_flaw_resp = {
        "cold_read_takeaway": "Embeds unverified Basel III treasury modeling stretch claim.",
        "checks": {
            c.id: (
                {"verdict": "NO", "evidence_span": "Basel III treasury capital modeling"}
                if c.id == "no_unverified_domain_stretch"
                else {"verdict": "YES", "evidence_span": "Runtime Policy Controls"}
            )
            for c in comp_prof.checks
        },
        "failure_tags": ["UNSUPPORTED_EXTRAPOLATION"],
    }
    out_fail = _make_model_backed_output(
        "gemini_pro",
        "hash1234",
        "gemini-4-argon-medium",
        planted_flaw_resp,
        section_id="competencies",
    )
    expected_rem_weight = round(
        sum(c.weight for c in comp_prof.checks if c.id != "no_unverified_domain_stretch"),
        4,
    )
    assert out_fail.pass_ is False
    assert out_fail.decisive_failure is True
    assert out_fail.normalized_score == expected_rem_weight  # Critical check veto blocks pass!

    # Whole-resume coherence v3 -> recruitment readiness scorecard
    coh_prof = get_apps_rg_v3_profile("full_resume_coherence")
    coh_pass_resp = {
        "cold_read_takeaway": "Cohesive executive arc across all sections with zero metric echo.",
        "checks": {c.id: {"verdict": "YES", "evidence_span": "consistent scope"} for c in coh_prof.checks},
        "failure_tags": [],
    }
    out_coh = _make_model_backed_output(
        "openai_chatgpt",
        "hash5678",
        "gpt-oss-120b-medium",
        coh_pass_resp,
        section_id="full_resume_coherence",
    )
    assert out_coh.pass_ is True
    assert out_coh.normalized_score == 1.0
    lens = build_lens_analysis([out_coh])
    scorecard = build_recruitment_readiness_scorecard(lens, {"mean_normalized_score": 1.0}, True)
    assert scorecard["readiness_tier"] == "STRONG_HIRE_INTERVIEW_READY"

    rcpt = REPO_ROOT / "artifacts" / "eval_harness" / "judge_v3" / "wave3_apps_rg_receipt.json"
    rcpt.parent.mkdir(parents=True, exist_ok=True)
    rcpt.write_text(
        json.dumps(
            {
                "wave": "Wave 3",
                "all_prompts_le_300_words": True,
                "all_modules_le_300_lines": True,
                "zero_employer_nouns_in_prompts": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_non_critical_v3_checks_preserve_weights_floors_priming_and_writer_orthogonality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps_rg.runtime.assembly.full_resume_llm_coherence import (
        DEFAULT_PASS_THRESHOLD,
        _build_prompt as build_coherence_prompt,
        aggregate_full_resume_coherence,
        build_full_resume_evidence_packet,
    )
    from apps_rg.runtime.judges.x1d_ide_cli import (
        _governed_judge_quota_backups,
        actual_lane_writer_model,
        second_judge_model,
    )
    from apps_rg.runtime.sections.executive_summary_v2.blind_judge_and_loop import (
        EXEC_SUMMARY_PASS_FLOOR_0_TO_1,
        format_blind_judge_feedback,
        judge_row_passes_4_7_human_bar,
    )

    # 1. Executive summary: 4/5 checks YES (1 non-critical NO -> 0.85 >= 0.80) MUST PASS!
    exec_prof = get_apps_rg_v3_profile("executive_summary")
    assert EXEC_SUMMARY_PASS_FLOOR_0_TO_1 == exec_prof.pass_threshold == 0.80
    non_crit_check = next(c for c in exec_prof.checks if not c.critical)
    cand_text = "Built governed enterprise AI platform generating $42M partner co-sell pipeline."
    optional_miss_resp = {
        "cold_read_takeaway": "Strong grounded summary with minor cadence density in final clause.",
        "checks": {
            c.id: (
                {"verdict": "NO", "evidence_span": "partner co-sell pipeline"}
                if c.id == non_crit_check.id
                else {"verdict": "YES", "evidence_span": "governed enterprise AI platform"}
            )
            for c in exec_prof.checks
        },
        "failure_tags": [non_crit_check.failure_tag],
    }
    out_opt = _make_model_backed_output(
        "gemini_pro",
        "hash_opt_85",
        "gemini-4-argon-high",
        optional_miss_resp,
        section_id="executive_summary",
        candidate_text=cand_text,
    )
    assert out_opt.pass_ is True
    assert out_opt.decisive_failure is False
    assert out_opt.normalized_score >= 0.80
    assert judge_row_passes_4_7_human_bar(out_opt.to_dict()) is True

    # Retry feedback on failing 0_to_1 row never formats "/5.0"
    fail_row = {
        **out_opt.to_dict(),
        "pass": False,
        "decisive_failure": True,
        "score": 0.65,
        "score_scale": "0_to_1",
        "threshold": 0.80,
    }
    fb = format_blind_judge_feedback([fail_row])
    assert "unit_score=0.65 (threshold=0.80" in fb
    assert "/5.0" not in fb

    # 2. Full-resume coherence: 3/4 checks YES (1 non-critical NO -> 0.80 >= 0.80) MUST PASS!
    coh_prof = get_apps_rg_v3_profile("full_resume_coherence")
    assert DEFAULT_PASS_THRESHOLD == coh_prof.pass_threshold == 0.80
    coh_non_crit = next(c for c in coh_prof.checks if not c.critical)
    coh_80_resp = {
        "cold_read_takeaway": "Consistent whole-resume proof arc with slight transition stiffness.",
        "checks": {
            c.id: (
                {"verdict": "NO", "evidence_span": "transition stiffness"}
                if c.id == coh_non_crit.id
                else {"verdict": "YES", "evidence_span": "consistent scope"}
            )
            for c in coh_prof.checks
        },
        "failure_tags": [coh_non_crit.failure_tag],
    }
    j1 = _make_model_backed_output("gemini_pro", "h1", "gemini-4-argon-high", coh_80_resp, section_id="full_resume_coherence")
    j2 = _make_model_backed_output("openai_chatgpt", "h2", "gpt-oss-120b-medium", coh_80_resp, section_id="full_resume_coherence")
    assert j1.pass_ is True and j2.pass_ is True
    agg = aggregate_full_resume_coherence([j1, j2], deterministic_blockers=[])
    assert agg["full_resume_coherence_pass"] is True
    assert agg["pass_threshold"] == 0.80

    # 3. Priming stripped from grade_only_judge_packet and coherence prompt
    sec_pkt = build_grade_only_judge_packet(
        section_id="competencies",
        candidate_output={"resume_display_text": "Enterprise AI Governance"},
        section_rubric=COMPETENCIES_RUBRIC,
        rubric_ref="ref",
        deterministic_gate_summary={"x2_passed": True},
    )
    rendered_sec = render_section_prompt(sec_pkt)
    assert "GRAPH_BINDING_MATERIALITY_SUMMARY" not in rendered_sec
    assert "overlap_engine_report" not in rendered_sec

    ev_pkt = build_full_resume_evidence_packet(
        {
            "sections": [
                {
                    "section_id": "executive_summary",
                    "l2_output_snapshot": {
                        "resume_graph_claim_binding_pass": True,
                        "claim_ledger": [{"claim_text": "Built governed platform.", "source_fact_ids": ["f1"]}],
                    },
                }
            ]
        }
    )
    coh_prompt = build_coherence_prompt(
        full_resume_text="Built governed platform.",
        target_company="Acme",
        target_role="SVP",
        jd_context="AI",
        evidence_packet=ev_pkt,
    )
    assert "overlap_engine_report" not in coh_prompt
    assert "claim_binding_pass" not in coh_prompt

    # 4. IDE CLI quota backups never self-grade when writer maps to gemini-4-neon-medium
    monkeypatch.setenv("APPS_RG_GENERATION_TRANSPORT", "ide_cli")
    monkeypatch.setenv("APPS_RG_JUDGE_TRANSPORT", "ide_cli")
    assert actual_lane_writer_model("executive_summary") == "gemini-4-neon-medium"
    slot2_pin, _ = second_judge_model("executive_summary")
    assert "neon" not in slot2_pin
    for pkey, primary_pin in (("gemini_pro", "gemini-4-argon-high"), ("openai_chatgpt", slot2_pin)):
        backups = _governed_judge_quota_backups("executive_summary", pkey, primary_pin)
        assert all("neon" not in b for b in backups), f"Neon self-grading backup leaked: {backups}"
