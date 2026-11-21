"""Adversarial tests for Executive Summary Hardening:
- Visual layout band (3-4 sentences, 420-680 chars, <= 210 chars/sentence, <= 110 words overflow cap, zero word min)
- Spoken human voice X2 checks (no AI bridge crutches, no abstract noun soup, rhythm & cadence variety)
- Prompt template & E0 cleanup (zero 6-sentence or AI bridge prescriptions)
- Frontier-lab grader separation (blind executive_summary LLM judge, zero score-inflation anchor, zero score coercion)
- 4.7/5.0 threshold + 6 pure human hiring-committee dimensions with zero-defect floor on conviction & authenticity
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps_rg.runtime.judges.executive_summary_judge_packet import (
    GRADE_ONLY_INSTRUCTION,
    GRAPH_ONLY_GRADE_ONLY_RUBRIC,
    SRFS_GRADE_ONLY_RUBRIC,
    build_executive_summary_judge_packet,
    reconcile_grade_only_judge_result,
    reconcile_judge_result_against_deterministic_gate_closures,
    render_judge_prompt_from_packet,
)
from apps_rg.runtime.judges.executive_summary_x1d import (
    _make_model_backed_output,
    build_judge_response_schema,
    build_x1d_judge_system_prompt,
)
from apps_rg.runtime.judges.executive_summary_x1d_dimension_verdicts import (
    EXEC_SUMMARY_RUBRIC_DIMENSION_IDS,
    EXEC_SUMMARY_STRICT_ZERO_DEFECT_DIMENSIONS,
    executive_summary_human_dimension_floor_passes,
)
from apps_rg.runtime.sections.executive_summary_x1d_judge_contract import (
    assert_executive_summary_x1d_judge_coherence,
)
from apps_rg.runtime.sections.section_product_shape_parity import assert_ssot_seam_parity
from apps_rg.runtime.validators.executive_summary_x2 import (
    EXEC_SUMMARY_MAX_CHARS,
    EXEC_SUMMARY_MAX_CHARS_PER_SENTENCE,
    EXEC_SUMMARY_MAX_SENTENCES,
    EXEC_SUMMARY_MAX_WORDS,
    EXEC_SUMMARY_MIN_CHARS,
    EXEC_SUMMARY_MIN_SENTENCES,
    check_exec_summary_no_abstract_noun_soup,
    check_exec_summary_no_ai_bridge_crutches,
    check_exec_summary_paragraph_max_words,
    check_exec_summary_rhythm_and_cadence_variety,
    check_exec_summary_sentence_band_3_to_4,
    check_exec_summary_visual_char_band,
)


_CLEAN_4_SENTENCE_SUMMARY = (
    "Engineering executive building governed AI platforms for regulated financial enterprises. "
    "Scaled an ML engineering organization from 8 to 28 specialists while generating $22M in IP-led platform revenue and lifting gross margins by 20%. "
    "Basel III and CCAR data lineage cut regulatory reporting errors by 40% across core banking risk workflows. "
    "Combines deep technical architecture with commercial discipline to move enterprise AI initiatives into production."
)


def _all_6_human_verdicts(*, override: dict[str, dict] | None = None) -> dict[str, dict]:
    verdicts = {
        dim: {"pass": True, "severity": "none", "codes": []}
        for dim in EXEC_SUMMARY_RUBRIC_DIMENSION_IDS
    }
    if override:
        verdicts.update(override)
    return verdicts


class TestWave1VisualBandAndSpokenVoiceX2:
    def test_ssot_constants_match_visual_layout_band(self) -> None:
        assert EXEC_SUMMARY_MIN_SENTENCES == 3
        assert EXEC_SUMMARY_MAX_SENTENCES == 4
        assert EXEC_SUMMARY_MIN_CHARS == 420
        assert EXEC_SUMMARY_MAX_CHARS == 680
        assert EXEC_SUMMARY_MAX_CHARS_PER_SENTENCE == 210
        assert EXEC_SUMMARY_MAX_WORDS == 110

    def test_clean_four_sentence_summary_passes_all_new_x2_gates(self) -> None:
        assert 420 <= len(_CLEAN_4_SENTENCE_SUMMARY) <= 680
        assert check_exec_summary_sentence_band_3_to_4(_CLEAN_4_SENTENCE_SUMMARY)[0] is True
        assert check_exec_summary_visual_char_band(_CLEAN_4_SENTENCE_SUMMARY)[0] is True
        assert check_exec_summary_paragraph_max_words(_CLEAN_4_SENTENCE_SUMMARY)[0] is True
        assert check_exec_summary_no_ai_bridge_crutches(_CLEAN_4_SENTENCE_SUMMARY)[0] is True
        assert check_exec_summary_no_abstract_noun_soup(_CLEAN_4_SENTENCE_SUMMARY)[0] is True
        assert check_exec_summary_rhythm_and_cadence_variety(_CLEAN_4_SENTENCE_SUMMARY)[0] is True

    def test_three_sentence_summary_passes_band_and_zero_word_min(self) -> None:
        three_sent = (
            "Engineering executive shipping production AI platforms for major regulated banks. "
            "Scaled engineering from 8 to 28 specialists, generated $22M in IP-led revenue, and lifted gross margins by 20% while replacing fragile manual release pipelines across enterprise accounts. "
            "Basel III and CCAR lineage controls cut regulatory reporting defects by 40% while shortening production risk stress-test cycles for senior leadership."
        )
        assert check_exec_summary_sentence_band_3_to_4(three_sent)[0] is True
        assert check_exec_summary_visual_char_band(three_sent)[0] is True
        assert check_exec_summary_paragraph_max_words(three_sent)[0] is True

    @pytest.mark.parametrize("n_sents", [2, 5, 6])
    def test_rejects_sentence_counts_outside_3_to_4(self, n_sents: int) -> None:
        text = " ".join(f"Sentence number {i} delivers measurable platform scale." for i in range(1, n_sents + 1))
        ok, reason = check_exec_summary_sentence_band_3_to_4(text)
        assert ok is False
        assert reason is not None

    def test_visual_char_band_rejects_too_short_too_long_and_overlong_sentence(self) -> None:
        too_short = "Engineering executive shipping AI. Scaled teams fast. Cut errors by 40%."
        assert check_exec_summary_visual_char_band(too_short)[0] is False

        overlong_sent = (
            "Engineering executive building governed AI platforms across regulated enterprise banks. "
            "Scaled an enterprise ML engineering organization from 8 to 28 specialists while generating $22M in IP-led platform revenue and lifting gross margins by 20% across multi-year regulated banking transformation accounts worldwide. "
            "Basel III lineage cut reporting defects by 40% across risk teams. "
            "Pairs actuarial depth with commercial accountability."
        )
        assert 420 <= len(overlong_sent) <= 680
        ok, reason = check_exec_summary_visual_char_band(overlong_sent)
        assert ok is False
        assert "exceeds max" in (reason or "")

        too_long_total = (
            "Engineering executive leading enterprise AI platform transformations across major regulated banks and global financial institutions with deep technical and operating command. "
            "Scaled an engineering organization from 8 to 28 specialists while generating $22M in IP-led platform revenue and lifting gross margins by 20% across multi-year client accounts. "
            "Basel III and CCAR data lineage frameworks cut regulatory reporting errors by 40% while shortening production stress-test cycles for senior risk leaders across core divisions. "
            "Combines hands-on cloud platform engineering with commercial accountability to embed enterprise AI across core business lines and operating units at sustained enterprise scale."
        )
        assert len(too_long_total) > 680
        assert check_exec_summary_visual_char_band(too_long_total)[0] is False

    @pytest.mark.parametrize(
        "crutch",
        [
            "In parallel, Basel III lineage cut reporting errors by 40%.",
            "Building on that architecture, engineering scaled from 8 to 28 specialists.",
            "Across enterprise programs, platform revenue reached $22M.",
            "The same platform discipline shortened stress-test cycles by 40%.",
            "That governed runtime enabled faster bank deployments.",
        ],
    )
    def test_rejects_ai_bridge_crutches(self, crutch: str) -> None:
        text = (
            "Engineering executive building governed AI platforms. "
            f"{crutch} "
            "Combines quantitative rigor with commercial execution."
        )
        ok, reason = check_exec_summary_no_ai_bridge_crutches(text)
        assert ok is False
        assert "ai_bridge_crutch" in (reason or "")

    @pytest.mark.parametrize(
        "soup",
        [
            "operating-model framing",
            "governed activation",
            "durable economics",
            "accountable operating cadence",
        ],
    )
    def test_rejects_abstract_noun_soup(self, soup: str) -> None:
        text = (
            f"Engineering executive delivering {soup} for regulated banks. "
            "Scaled ML teams from 8 to 28 specialists and generated $22M in IP-led revenue. "
            "Basel III lineage cut reporting defects by 40%."
        )
        ok, reason = check_exec_summary_no_abstract_noun_soup(text)
        assert ok is False
        assert "abstract_noun_soup" in (reason or "")

    def test_rhythm_gate_catches_flat_cadence_repeated_openers_and_trailing_gerunds(self) -> None:
        flat = (
            "Engineering executive leads enterprise AI platforms for major regulated banks today. "
            "Scaled enterprise engineering teams across multiple global financial client programs today. "
            "Basel lineage controls cut reporting defects across core banking risk teams today."
        )
        ok_flat, reason_flat = check_exec_summary_rhythm_and_cadence_variety(flat)
        assert ok_flat is False
        assert "monotonous_sentence_length_spread" in (reason_flat or "")

        repeated_openers = (
            "Scaled global AI platforms across regulated banks. "
            "Scaled engineering teams from 8 to 28 specialists while generating $22M in productized platform revenue and lifting margins by 20%. "
            "Basel III lineage cut reporting errors by 40%."
        )
        ok_rep, reason_rep = check_exec_summary_rhythm_and_cadence_variety(repeated_openers)
        assert ok_rep is False
        assert "duplicate_sentence_openers" in (reason_rep or "")

        trailing_gerunds = (
            "Engineering executive builds AI platforms, accelerating enterprise rollouts. "
            "Scaled engineering from 8 to 28 specialists and delivered $22M in IP-led platform revenue, lifting gross margins across accounts. "
            "Basel III lineage cut regulatory reporting errors by 40%."
        )
        ok_ger, reason_ger = check_exec_summary_rhythm_and_cadence_variety(trailing_gerunds)
        assert ok_ger is False
        assert "repetitive_trailing_gerund_clauses" in (reason_ger or "")


class TestWave2PromptTemplateAndE0Cleanup:
    def test_template_retires_six_sentence_and_ai_bridge_crutches(self) -> None:
        template_path = (
            Path(__file__).resolve().parents[3]
            / "src"
            / "apps_rg"
            / "prompt_assembly"
            / "templates"
            / "executive_summary.generate_scratch_v1.yaml"
        )
        text = template_path.read_text(encoding="utf-8")
        assert "<six_sentence_period_contract>" not in text
        assert "<approved_non_stock_openers>" not in text
        assert "exactly six" not in text.lower()
        assert "exactly 6" not in text.lower()
        assert "420 to 680" in text or "420-680" in text


class TestWave3BlindHumanJudgeAndThreshold47:
    def test_rubric_and_schema_have_6_human_dimensions_and_rationale_first(self) -> None:
        assert EXEC_SUMMARY_RUBRIC_DIMENSION_IDS == (
            "immediate_call_conviction",
            "spoken_executive_authenticity",
            "differentiated_edge",
            "six_second_scannability",
            "strategic_mandate_resonance",
            "factual_truth_and_non_exaggeration",
        )
        assert EXEC_SUMMARY_STRICT_ZERO_DEFECT_DIMENSIONS == frozenset(
            {"immediate_call_conviction", "spoken_executive_authenticity"}
        )
        schema = build_judge_response_schema()
        keys = list(schema["properties"].keys())
        assert keys[0] == "rationale"
        assert keys.index("rationale") < keys.index("score")
        dim_keys = tuple(schema["properties"]["dimension_verdicts"]["properties"].keys())
        assert dim_keys == EXEC_SUMMARY_RUBRIC_DIMENSION_IDS

    def test_blind_judge_prompt_and_system_prompt_omit_deterministic_gate_summary_and_inflation(self) -> None:
        packet = build_executive_summary_judge_packet(
            resume_display_text=_CLEAN_4_SENTENCE_SUMMARY,
            claim_ledger=[
                {"claim_text": "claim 1", "source_fact_ids": ["fact_1"]},
                {"claim_text": "claim 2", "source_fact_ids": ["fact_2"]},
                {"claim_text": "claim 3", "source_fact_ids": ["fact_3"]},
                {"claim_text": "claim 4", "source_fact_ids": ["fact_4"]},
            ],
            allowed_fact_packet=[
                {"fact_id": f"fact_{i}", "claim_text": f"fact {i}"} for i in range(1, 5)
            ],
            allowed_fact_ids={f"fact_{i}" for i in range(1, 5)},
            target_title="Head of Forward Deployed Engineering",
            target_company="Truist Financial Corporation",
            jd_text="Lead forward deployed AI engineering.",
            briefing_text="Targeting context only.",
            parsed_output={"resume_display_text": _CLEAN_4_SENTENCE_SUMMARY},
        )
        rendered = render_judge_prompt_from_packet(packet)
        assert "deterministic_gate_summary" not in rendered.lower()
        assert "4.5 and 4.9" not in rendered.lower()
        assert "4.5 and 4.9" not in GRADE_ONLY_INSTRUCTION.lower()
        assert "4.5 and 4.9" not in SRFS_GRADE_ONLY_RUBRIC.lower()
        assert "4.5 and 4.9" not in GRAPH_ONLY_GRADE_ONLY_RUBRIC.lower()

        sys_exec = build_x1d_judge_system_prompt(compact=True, section_id="executive_summary")
        assert "deterministic_gate_summary" not in sys_exec.lower()
        assert "4.7" in sys_exec

        sys_other = build_x1d_judge_system_prompt(compact=True, section_id="headline")
        assert "deterministic_gate_summary" in sys_other.lower()

    def test_threshold_47_and_zero_defect_floor_enforced(self) -> None:
        # 4.69 -> FAIL
        out_469 = _make_model_backed_output(
            "gemini_pro",
            "h1",
            "test-model",
            {
                "rationale": "Strong but just shy of immediate call.",
                "score_scale": "0_to_5",
                "score": 4.69,
                "threshold": 4.0,  # even if model emits 4.0, floor clamps to 4.7
                "pass": True,
                "decisive_failure": False,
                "findings": [],
                "cited_sentence_indexes": [],
                "remediation_suggestions": [],
                "dimension_verdicts": _all_6_human_verdicts(),
            },
            section_id="executive_summary",
        )
        assert out_469.threshold == pytest.approx(4.7)
        assert out_469.pass_ is False
        assert out_469.provider_status == "MODEL_BACKED_FAIL"

        # 4.70 clean -> PASS
        out_470 = _make_model_backed_output(
            "gemini_pro",
            "h2",
            "test-model",
            {
                "rationale": "Unmistakable high-caliber executive we must call today.",
                "score_scale": "0_to_5",
                "score": 4.70,
                "threshold": 4.7,
                "pass": True,
                "decisive_failure": False,
                "findings": [],
                "cited_sentence_indexes": [],
                "remediation_suggestions": [],
                "dimension_verdicts": _all_6_human_verdicts(),
            },
            section_id="executive_summary",
        )
        assert out_470.pass_ is True
        assert out_470.provider_status == "MODEL_BACKED_PASS"

        # 4.85 with minor ding on spoken_executive_authenticity -> FAIL
        out_minor_voice = _make_model_backed_output(
            "openai_chatgpt",
            "h3",
            "test-model",
            {
                "rationale": "Great scale, slight robotic phrasing in S3.",
                "score_scale": "0_to_5",
                "score": 4.85,
                "threshold": 4.7,
                "pass": True,
                "decisive_failure": False,
                "findings": [],
                "cited_sentence_indexes": [3],
                "remediation_suggestions": [],
                "dimension_verdicts": _all_6_human_verdicts(
                    override={
                        "spoken_executive_authenticity": {
                            "pass": True,
                            "severity": "minor",
                            "codes": ["stiff_essay_cadence"],
                        }
                    }
                ),
            },
            section_id="executive_summary",
        )
        assert out_minor_voice.pass_ is False
        assert out_minor_voice.provider_status == "MODEL_BACKED_FAIL"
        assert any("spoken_executive_authenticity=minor" in f for f in out_minor_voice.findings)

        # 4.85 with minor ding on immediate_call_conviction -> FAIL
        ok_conv, reasons_conv = executive_summary_human_dimension_floor_passes(
            _all_6_human_verdicts(
                override={
                    "immediate_call_conviction": {
                        "pass": True,
                        "severity": "minor",
                        "codes": ["not_immediate_call"],
                    }
                }
            )
        )
        assert ok_conv is False
        assert any("immediate_call_conviction=minor" in r for r in reasons_conv)

    def test_zero_score_upward_coercion_for_executive_summary(self) -> None:
        raw_fail = {
            "rationale": "Reads like template prose.",
            "score_scale": "0_to_5",
            "score": 4.2,
            "threshold": 4.7,
            "pass": False,
            "decisive_failure": False,
            "findings": ["credential dump in prose", "sentence count issue"],
            "cited_sentence_indexes": [2],
            "remediation_suggestions": [],
            "dimension_verdicts": _all_6_human_verdicts(
                override={
                    "spoken_executive_authenticity": {
                        "pass": False,
                        "severity": "major",
                        "codes": ["machine_generated_voice"],
                    }
                }
            ),
        }
        all_pass_gates = {
            "x2_exec_summary_no_credential_dump": {"pass": True, "detail": "ok"},
            "x2_exec_summary_sentence_band_3_to_4": {"pass": True, "detail": "ok"},
        }
        rec1 = reconcile_judge_result_against_deterministic_gate_closures(
            raw_fail, all_pass_gates, section_id="executive_summary"
        )
        assert rec1["score"] == pytest.approx(4.2)
        assert rec1["pass"] is False
        assert len(rec1["findings"]) == 2

        rec2 = reconcile_grade_only_judge_result(
            raw_fail, all_pass_gates, section_id="executive_summary"
        )
        assert rec2["score"] == pytest.approx(4.2)
        assert rec2["pass"] is False

        out = _make_model_backed_output(
            "gemini_pro",
            "h4",
            "test-model",
            raw_fail,
            deterministic_gate_summary=all_pass_gates,
            section_id="executive_summary",
        )
        assert out.score == pytest.approx(4.2)
        assert out.pass_ is False

    def test_non_exec_summary_section_keeps_4_0_threshold(self) -> None:
        out_bullets = _make_model_backed_output(
            "gemini_pro",
            "h5",
            "test-model",
            {
                "rationale": "Solid quantified bullets.",
                "score_scale": "0_to_5",
                "score": 4.2,
                "threshold": 4.0,
                "pass": True,
                "decisive_failure": False,
                "findings": [],
                "cited_sentence_indexes": [],
                "remediation_suggestions": [],
            },
            section_id="slalom_bullets",
        )
        assert out_bullets.threshold == pytest.approx(4.0)
        assert out_bullets.pass_ is True

    def test_contract_coherence_and_ssot_parity_pass(self) -> None:
        assert_ssot_seam_parity()
        assert_executive_summary_x1d_judge_coherence()

    def test_g5_v2_regen_sentence_count_invariant_accepts_3_to_4_and_rejects_6(self) -> None:
        from apps_rg.runtime.sections.executive_summary_v2.x2_invariants import (
            evaluate_executive_summary_v2_x2,
        )

        def _sentence_gate(text: str) -> dict:
            gates = evaluate_executive_summary_v2_x2(
                resume_display_text=text,
                claim_ledger=[],
                parsed_output={"resume_display_text": text},
                allowed_fact_ids=set(),
                verified_numbers=frozenset(),
                verified_corpus_lower="",
                target_company="Truist",
                jd_text="",
            )
            return next(g for g in gates if g["gate_id"] == "x2_v2_sentence_band_3_to_4")

        g4 = _sentence_gate(_CLEAN_4_SENTENCE_SUMMARY)
        assert g4["pass"] is True

        g3 = _sentence_gate("One. Two. Three.")
        assert g3["pass"] is True

        g6 = _sentence_gate("One. Two. Three. Four. Five. Six.")
        assert g6["pass"] is False
        assert "sentence_count=6" in str(g6["failure_reason"])

    def test_non_exec_summary_system_prompt_keeps_4_0_threshold_not_4_7(self) -> None:
        sys_comp = build_x1d_judge_system_prompt(compact=True, section_id="competencies")
        assert '"threshold":4.0' in sys_comp
        assert '"threshold":4.7' not in sys_comp
        sys_exec = build_x1d_judge_system_prompt(compact=True, section_id="executive_summary")
        assert '"threshold":4.7' in sys_exec
