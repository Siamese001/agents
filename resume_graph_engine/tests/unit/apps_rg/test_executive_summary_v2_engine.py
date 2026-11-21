"""Unit & adversarial negative-control suite for greenfield executive_summary_v2 engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from apps_rg.runtime.judges.executive_summary_judge_packet import (
    build_executive_summary_judge_packet,
    render_judge_prompt_from_packet,
)
from apps_rg.runtime.sections.executive_summary_v2 import (
    EXEC_SUMMARY_V2_CORE_GATE_IDS,
    GenerationTurnOutput,
    evaluate_executive_summary_v2_x2,
    judge_row_passes_4_7_human_bar,
    parse_strict_json_without_mutation,
    run_bounded_v2_generation_and_judge_loop,
    run_executive_summary_v2,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V2_DIR = REPO_ROOT / "resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_v2"
LANE_CONTRACT_PATH = REPO_ROOT / "apps_eval/registries/apps_rg_lane_contract.json"

# Exact v4 Truist robotic inanimate-subject output that slipped past legacy 100-file pipeline
PINNED_V4_ROBOTIC_DRAFT = (
    "Enterprise AI and platform engineering executive directing 105 software engineers and data leaders "
    "building governed multi-agent architectures across regulated financial and utility environments. "
    "Platform ownership covered a $22M IP-led AI accelerator expanding gross margins by 20% and 7 reusable "
    "cloud, Confluent Kafka, and AI accelerators driving 24% renewal lift. "
    "Fail-closed validation meshes, replayable execution traces, and GraphRAG retrieval enforced zero silent "
    "signal loss across regulated workflows. "
    "Field delivery scaled engineering teams from 8 to 28 specialists while cutting production cycle times "
    "from six months to three weeks."
)

POSITIVE_HUMAN_EXEC_SUMMARY = (
    "Enterprise AI and platform engineering executive directing 105 software engineers and data leaders "
    "across regulated financial and utility operations. "
    "Productized governed multi-agent orchestration, deterministic policy gates, and GraphRAG retrieval into "
    "reusable enterprise platforms, generating $22M in IP-led revenue and expanding gross margins by 20%. "
    "Scaled specialized AI platform engineering teams from 8 to 28 while compressing lab-to-production "
    "delivery from six months to three weeks at 99.9% production uptime."
)

VERIFIED_CORPUS = (
    "105 software engineers and data leaders $22m ip-led revenue 20% gross margin 8 to 28 "
    "six months to three weeks 99.9% production uptime slalom unify consulting ibm aws databricks graphrag"
)
VERIFIED_NUMBERS = frozenset({"105", "$22m", "22m", "20%", "8", "28", "99.9%"})
ALLOWED_IDS = {"reb_slalom_engineering_practice_leadership", "reb_unify_platform_commercialization_leadership", "reb_ibm_aws_modernization_architecture"}


def _valid_ledger() -> list[dict[str, Any]]:
    return [
        {"claim_text": "S1", "source_fact_ids": ["reb_slalom_engineering_practice_leadership"]},
        {"claim_text": "S2", "source_fact_ids": ["reb_unify_platform_commercialization_leadership"]},
        {"claim_text": "S3", "source_fact_ids": ["reb_ibm_aws_modernization_architecture"]},
    ]


def _gate_map(gates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {g["gate_id"]: g for g in gates}


def test_v2_package_stays_under_subtraction_first_loc_budget() -> None:
    total_loc = sum(
        len(p.read_text(encoding="utf-8").splitlines())
        for p in sorted(V2_DIR.glob("*.py"))
    )
    assert total_loc <= 1100, f"executive_summary_v2 exceeded 1,100 LOC ceiling: {total_loc}"


def test_positive_human_executive_summary_passes_all_14_v2_invariants() -> None:
    gates = evaluate_executive_summary_v2_x2(
        resume_display_text=POSITIVE_HUMAN_EXEC_SUMMARY,
        claim_ledger=_valid_ledger(),
        parsed_output={"resume_display_text": POSITIVE_HUMAN_EXEC_SUMMARY, "jd_alignment": {"jd_used_as_proof": False}},
        allowed_fact_ids=ALLOWED_IDS,
        verified_numbers=VERIFIED_NUMBERS,
        verified_corpus_lower=VERIFIED_CORPUS,
        target_company="Truist Financial Corporation",
        jd_text="Lead forward deployed engineering teams for commercial banking transformation.",
    )
    by_id = _gate_map(gates)
    for gid in EXEC_SUMMARY_V2_CORE_GATE_IDS:
        assert gid in by_id
        assert by_id[gid]["pass"] is True, f"{gid} failed unexpectedly: {by_id[gid]}"


def test_pinned_v4_robotic_inanimate_draft_fails_inanimate_opener_and_truth_gates() -> None:
    ledger_4 = _valid_ledger() + [{"claim_text": "S4", "source_fact_ids": ["reb_ibm_aws_modernization_architecture"]}]
    gates = evaluate_executive_summary_v2_x2(
        resume_display_text=PINNED_V4_ROBOTIC_DRAFT,
        claim_ledger=ledger_4,
        parsed_output={"resume_display_text": PINNED_V4_ROBOTIC_DRAFT},
        allowed_fact_ids=ALLOWED_IDS,
        verified_numbers=VERIFIED_NUMBERS,
        verified_corpus_lower=VERIFIED_CORPUS,
        target_company="Truist Financial Corporation",
        jd_text="Forward deployed engineering banking role.",
    )
    by_id = _gate_map(gates)
    assert by_id["x2_v2_no_inanimate_subject_openers"]["pass"] is False
    assert "inanimate_datasheet_opener" in str(by_id["x2_v2_no_inanimate_subject_openers"]["failure_reason"])
    assert by_id["x2_v2_zero_unverified_vendors_or_employers"]["pass"] is False
    assert "confluent" in str(by_id["x2_v2_zero_unverified_vendors_or_employers"]["failure_reason"])
    assert by_id["x2_v2_zero_unverified_numbers"]["pass"] is False
    assert "24%" in str(by_id["x2_v2_zero_unverified_numbers"]["failure_reason"])


@pytest.mark.parametrize(
    ("mutated_text", "expected_failed_gate"),
    [
        (POSITIVE_HUMAN_EXEC_SUMMARY.replace("Enterprise AI", "I am an enterprise AI"), "x2_v2_no_first_person_pronouns"),
        (POSITIVE_HUMAN_EXEC_SUMMARY.replace("operations. Productized", "operations — productized"), "x2_v2_no_em_dash_or_ai_punctuation"),
        (POSITIVE_HUMAN_EXEC_SUMMARY.replace("Scaled specialized", "In parallel, scaled specialized"), "x2_v2_no_ai_bridge_crutches"),
        (POSITIVE_HUMAN_EXEC_SUMMARY.replace("enterprise platforms", "execution substrates and durable economics"), "x2_v2_no_abstract_noun_soup"),
        (POSITIVE_HUMAN_EXEC_SUMMARY.replace("utility operations.", "utility operations and MGAs."), "x2_v2_no_undefined_mga_acronym"),
    ],
)
def test_individual_x2_v2_negative_controls_fail_deterministically(
    mutated_text: str, expected_failed_gate: str
) -> None:
    gates = evaluate_executive_summary_v2_x2(
        resume_display_text=mutated_text,
        claim_ledger=_valid_ledger(),
        parsed_output={"resume_display_text": mutated_text},
        allowed_fact_ids=ALLOWED_IDS,
        verified_numbers=VERIFIED_NUMBERS,
        verified_corpus_lower=VERIFIED_CORPUS,
        target_company="Truist Financial Corporation",
        jd_text="Forward deployed engineering banking role.",
    )
    by_id = _gate_map(gates)
    assert by_id[expected_failed_gate]["pass"] is False


def test_parse_strict_json_preserves_display_prose_byte_for_byte() -> None:
    raw = json.dumps({
        "resume_display_text": POSITIVE_HUMAN_EXEC_SUMMARY,
        "claim_ledger": _valid_ledger(),
    })
    parsed, disp, ledger, err = parse_strict_json_without_mutation(f"```json\n{raw}\n```")
    assert err == ""
    assert parsed is not None
    assert disp == POSITIVE_HUMAN_EXEC_SUMMARY
    assert len(ledger) == 3


def test_blind_judge_prompt_is_blind_to_x2_and_enforces_inanimate_datasheet_ban() -> None:
    packet = build_executive_summary_judge_packet(
        resume_display_text=PINNED_V4_ROBOTIC_DRAFT,
        claim_ledger=_valid_ledger(),
        allowed_fact_packet=[{"fact_id": fid, "claim_text": "Verified fact."} for fid in sorted(ALLOWED_IDS)],
        allowed_fact_ids=ALLOWED_IDS,
        target_title="Head of Forward Deployed Engineering",
        target_company="Truist Financial Corporation",
        jd_text="Banking FDE leadership.",
        briefing_text="",
        parsed_output={"resume_display_text": PINNED_V4_ROBOTIC_DRAFT},
        repo_root=REPO_ROOT / "resume_graph_engine/src",
    )
    prompt = render_judge_prompt_from_packet(packet)
    assert "DETERMINISTIC_GATE_SUMMARY" not in prompt
    assert "INANIMATE_SUBJECT_DATASHEET_BAN" in prompt
    assert "Platform ownership covered" in prompt
    assert "inanimate_subject_opener" in prompt


def test_bounded_loop_skips_judge_on_x2_fail_and_forwards_decisive_judge_feedback(tmp_path: Path) -> None:
    gen_calls: list[dict[str, Any]] = []
    judge_calls: list[int] = []

    def _fake_gen(**kwargs: Any) -> GenerationTurnOutput:
        gen_calls.append(kwargs)
        att = kwargs["attempt"]
        # Attempt 1 fails X2 (inanimate opener); Attempt 2 passes X2; Attempt 3 passes X2 + judges
        txt = PINNED_V4_ROBOTIC_DRAFT if att == 1 else POSITIVE_HUMAN_EXEC_SUMMARY
        led = (_valid_ledger() + [{"claim_text": "S4", "source_fact_ids": ["reb_ibm_aws_modernization_architecture"]}]) if att == 1 else _valid_ledger()
        return GenerationTurnOutput(
            attempt=att,
            messages=[{"role": "user", "content": "x"}],
            compiled_prompt="prompt",
            prompt_hash="h1",
            model_name="test-model",
            temperature=0.45,
            runtime_generation_status="REAL_LLM",
            raw_output=json.dumps({"resume_display_text": txt, "claim_ledger": led}),
            parsed_output={"resume_display_text": txt, "claim_ledger": led},
            resume_display_text=txt,
            claim_ledger=led,
            parse_error="",
            provider_request_data={},
            provider_result_data={"provider_available": True},
        )

    def _fake_judges(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        att = kwargs["attempt"]
        judge_calls.append(att)
        all_pass_dims = {
            d: {"pass": True, "severity": "none", "codes": []}
            for d in (
                "immediate_call_conviction",
                "spoken_executive_authenticity",
                "differentiated_edge",
                "six_second_scannability",
                "strategic_mandate_resonance",
                "factual_truth_and_non_exaggeration",
            )
        }
        if att == 2:
            bad_dims = dict(all_pass_dims)
            bad_dims["spoken_executive_authenticity"] = {"pass": False, "severity": "major", "codes": ["stiff_essay_cadence"]}
            return [
                {
                    "provider_key": "openai_chatgpt",
                    "provider_name": "Slot1",
                    "evaluator_mode": "MODEL_BACKED",
                    "provider_status": "MODEL_BACKED_FAIL",
                    "score_scale": "0_to_5",
                    "score": 4.2,
                    "threshold": 4.7,
                    "pass": False,
                    "decisive_failure": True,
                    "rationale": "Sentence 2 cadence feels stiff.",
                    "findings": ["Tighten S2 cadence"],
                    "remediation_suggestions": ["Make S2 punchier"],
                    "dimension_verdicts": bad_dims,
                },
                {
                    "provider_key": "gemini_pro",
                    "provider_name": "Slot2",
                    "evaluator_mode": "MODEL_BACKED",
                    "provider_status": "MODEL_BACKED_PASS",
                    "score_scale": "0_to_5",
                    "score": 4.8,
                    "threshold": 4.7,
                    "pass": True,
                    "decisive_failure": False,
                    "dimension_verdicts": all_pass_dims,
                },
            ], {}
        return [
            {
                "provider_key": k,
                "provider_name": k,
                "evaluator_mode": "MODEL_BACKED",
                "provider_status": "MODEL_BACKED_PASS",
                "score_scale": "0_to_5",
                "score": 4.85,
                "threshold": 4.7,
                "pass": True,
                "decisive_failure": False,
                "dimension_verdicts": all_pass_dims,
            }
            for k in ("openai_chatgpt", "gemini_pro")
        ], {}

    outcome = run_bounded_v2_generation_and_judge_loop(
        provider_name="external_claude",
        judge_mode="live",
        temperature=0.45,
        input_payload_hash="inhash",
        run_id="run_test",
        artifact_dir=tmp_path,
        target_company="Truist Financial Corporation",
        target_title="Head of Forward Deployed Engineering",
        jd_text="Banking FDE role.",
        briefing_text="",
        selected_fact_plan={"facts": []},
        allowed_fact_ids=ALLOWED_IDS,
        allowed_fact_ids_ordered=sorted(ALLOWED_IDS),
        compact_verified_facts=[],
        verified_numbers=VERIFIED_NUMBERS,
        verified_corpus_lower=VERIFIED_CORPUS,
        proof_pool_metadata={},
        generate_turn_fn=_fake_gen,
        evaluate_judges_fn=_fake_judges,
    )
    assert outcome.attempts_used == 3
    # Judge was SKIPPED on attempt 1 (X2 failed fast!) and only called on attempts 2 and 3
    assert judge_calls == [2, 3]
    # Decisive failure on attempt 2 was forwarded cleanly to attempt 3
    assert "x2_v2_no_inanimate_subject_openers" in gen_calls[1]["rejection_feedback"]
    assert "Tighten S2 cadence" in gen_calls[2]["rejection_feedback"]
    assert all(judge_row_passes_4_7_human_bar(r) for r in outcome.final_x1d_rows)


def test_contract_emitter_writes_all_15_required_lane_contract_artifacts(tmp_path: Path) -> None:
    contract = json.loads(LANE_CONTRACT_PATH.read_text(encoding="utf-8"))
    fmap = contract["artifact_role_filename_map"]
    required_files = [
        fmap[role]
        for roles in contract["required_lane_artifact_roles"].values()
        for role in roles
    ]
    assert len(required_files) == 15

    jd_text = (REPO_ROOT / "resume_graph_engine/src/apps_rg/config/targeting/truist_head_forward_deployed_engineering_jd.txt").read_text(encoding="utf-8")
    brief_text = (REPO_ROOT / "resume_graph_engine/src/apps_rg/config/targeting/truist_head_forward_deployed_engineering_briefing.md").read_text(encoding="utf-8")

    def _stub_product_turn(**kwargs: Any) -> GenerationTurnOutput:
        fids = list(kwargs["allowed_fact_ids_ordered"])[:3]
        led = [
            {"claim_text": "Enterprise AI and Cloud Architecture Leader with 20+ years scaling regulated transformations across Fortune 500 banking and financial platforms.", "source_fact_ids": [fids[0]]},
            {"claim_text": "Built and led Slalom's 100+ person Cloud and AI practice generating $45M+ in portfolio value across regulated data and agentic systems.", "source_fact_ids": [fids[1]]},
            {"claim_text": "Architected multi-agent RAG governance and AWS modernization blueprints for Tier-1 financial institutions, cutting cycle times by 40%.", "source_fact_ids": [fids[2]]},
        ]
        raw = json.dumps({"resume_display_text": POSITIVE_HUMAN_EXEC_SUMMARY, "claim_ledger": led})
        return GenerationTurnOutput(
            attempt=int(kwargs["attempt"]),
            messages=[{"role": "user", "content": "product_test"}],
            compiled_prompt="product_test",
            prompt_hash="phash_product_test",
            model_name="claude-opus-4-7",
            temperature=0.45,
            runtime_generation_status="REAL_LLM",
            raw_output=raw,
            parsed_output={"resume_display_text": POSITIVE_HUMAN_EXEC_SUMMARY, "claim_ledger": led},
            resume_display_text=POSITIVE_HUMAN_EXEC_SUMMARY,
            claim_ledger=led,
            parse_error="",
            provider_request_data={"provider": "external_claude", "model": "claude-opus-4-7"},
            provider_result_data={"provider_available": True, "usage": {"input_tokens": 900, "output_tokens": 220, "total_tokens": 1120}},
        )

    def _stub_product_judges(**kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        dims = {
            d: {"pass": True, "severity": "none", "codes": []}
            for d in (
                "immediate_call_conviction",
                "spoken_executive_authenticity",
                "differentiated_edge",
                "six_second_scannability",
                "strategic_mandate_resonance",
                "factual_truth_and_non_exaggeration",
            )
        }
        return [
            {
                "provider_key": k,
                "provider_name": k,
                "evaluator_mode": "MODEL_BACKED",
                "provider_status": "MODEL_BACKED_PASS",
                "score_scale": "0_to_5",
                "score": 4.85,
                "threshold": 4.7,
                "pass": True,
                "decisive_failure": False,
                "rationale": "Executive leader owns every sentence.",
                "findings": [],
                "remediation_suggestions": [],
                "dimension_verdicts": dims,
            }
            for k in ("openai_chatgpt", "gemini_pro")
        ], {"blind_to_deterministic_gates": True, "prompt_has_deterministic_gate_summary": False}

    args = argparse.Namespace(
        provider="external_claude",
        judge_mode="live",
        temperature=0.45,
        target_company="Truist Financial Corporation",
        target_role="Head of Forward Deployed Engineering",
        target_title="Head of Forward Deployed Engineering",
        jd=jd_text,
        jd_text=jd_text,
        briefing=brief_text,
        manual_brief=brief_text,
        best_effort_publish_allowed=False,
    )
    out_dir = tmp_path / "exec_v2_product_run"
    res = run_executive_summary_v2(
        args,
        artifact_dir_override=out_dir,
        generate_turn_fn=_stub_product_turn,
        evaluate_judges_fn=_stub_product_judges,
    )
    assert res["artifact_dir"] == out_dir
    for fname in required_files:
        assert (out_dir / fname).is_file(), f"Missing canonical lane contract artifact: {fname}"
    handoff = json.loads((out_dir / "l2_handoff_receipt.json").read_text(encoding="utf-8"))
    assert handoff["handoff_status"] == "PASS"
    assert (out_dir / "resume_display_text.txt").is_file()
    assert (out_dir / "claim_ledger.json").is_file()
    assert (out_dir / "fact_check_result.json").is_file()

    # Also verify non-product --provider mock works cleanly without authority rejection
    mock_dir = tmp_path / "exec_v2_mock_run"
    mock_args = argparse.Namespace(**{**vars(args), "provider": "mock", "judge_mode": "mocked"})
    mock_res = run_executive_summary_v2(mock_args, artifact_dir_override=mock_dir)
    assert (mock_dir / "l2_output.json").is_file()
    assert mock_res["runtime_generation_status"] == "OFFLINE_CONTRACT_STUB"


def test_real_provider_result_and_run_llm_judges_keyword_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from apps_rg.runtime.providers.provider_contract import ProviderResult
    from apps_rg.runtime.sections.executive_summary_v2 import prompt_and_generate as pg
    from apps_rg.runtime.sections.executive_summary_v2.blind_judge_and_loop import evaluate_blind_dual_judges

    raw = json.dumps({"resume_display_text": POSITIVE_HUMAN_EXEC_SUMMARY, "claim_ledger": _valid_ledger()})
    monkeypatch.setattr(
        pg,
        "generate_section",
        lambda *a, **kw: ProviderResult(
            provider_requested="external_claude",
            provider_attempted=True,
            provider_available=True,
            exact_provider_error=None,
            runtime_generation_status="REAL_LLM",
            model="claude-sonnet-5-5-medium",
            raw_model_output=raw,
            provider_response={"usage": {"input_tokens": 500, "output_tokens": 180, "total_tokens": 680}},
        ),
    )
    turn = pg.generate_executive_summary_v2_turn(
        attempt=1,
        provider_name="external_claude",
        temperature=0.45,
        input_payload_hash="inhash",
        run_id="r1",
        artifact_dir=tmp_path,
        target_company="Truist",
        target_title="Head of Forward Deployed Engineering",
        jd_text="banking fde",
        briefing_text="regulated banking",
        allowed_fact_ids=ALLOWED_IDS,
        allowed_fact_ids_ordered=sorted(ALLOWED_IDS),
        compact_verified_facts=[],
    )
    assert turn.runtime_generation_status == "REAL_LLM"
    assert turn.resume_display_text == POSITIVE_HUMAN_EXEC_SUMMARY

    rows, pkt = evaluate_blind_dual_judges(
        artifact_dir=tmp_path,
        attempt=1,
        turn=turn,
        selected_fact_plan={"facts": []},
        allowed_fact_ids=ALLOWED_IDS,
        proof_pool_metadata={},
        target_title="Head of Forward Deployed Engineering",
        target_company="Truist",
        jd_text="banking fde",
        briefing_text="regulated banking",
        judge_mode="mocked",
    )
    assert len(rows) >= 2
    assert "rubric" in pkt
