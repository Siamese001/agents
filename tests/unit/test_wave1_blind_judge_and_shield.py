"""Wave 1 tests for Tier-1 pre-judge, Tier-2 zero-priming blind judge, panel escalation, calibration, PR gate, and shield."""

from __future__ import annotations

import json
from pathlib import Path

from apps_eval.contracts.digests import sha256_file
from apps_eval.graders.judge import (
    JudgeCalibrationRunner,
    LensSpec,
    LensVerdict,
    PositionSwapDebiaser,
    build_fail_closed_missing_verdict_receipt,
    build_sealed_blind_judge_bundle,
    evaluate_cross_family_judge_agreement,
    evaluate_multi_lens_panel,
    is_borderline_judge_result,
    run_tier1_deterministic_pre_judge,
    validate_blind_judge_verdict_provenance,
)
from tools.pr_governance_core.judge_receipt_gate import JudgeGovernedSurface, verify_diff_judge_receipts
from tools.run_diff_scoped_eval_shield import run_eval_shield

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_tier1_pre_judge_blocks_broken_and_ai_buzzword_candidates_with_zero_tokens() -> None:
    blocked = run_tier1_deterministic_pre_judge(
        "This holistic tapestry will delve into synergy.",
        enforce_anti_ai_filter=True,
    )
    assert not blocked.passed
    assert blocked.verdict == "TIER_1_BLOCKED"
    assert blocked.tokens_spent == 0
    assert blocked.evaluator_kind == "deterministic_gate"
    assert blocked.llm_judge_executed is False
    assert "anti_ai_buzzword_violation" in blocked.failed_gates

    passed = run_tier1_deterministic_pre_judge(
        {"summary": "Grounded output citing FACT-01.", "status": "ok"},
        required_keys=("summary", "status"),
        required_grounding_ids=("FACT-01",),
        enforce_anti_ai_filter=True,
    )
    assert passed.passed
    assert passed.verdict == "TIER_1_PASSED"


def test_blind_judge_zero_priming_cross_family_and_fail_closed_provenance(tmp_path: Path) -> None:
    artifact_file = tmp_path / "candidate_output.json"
    artifact_file.write_text('{"text": "Executive summary candidate."}', encoding="utf-8")

    bundle = build_sealed_blind_judge_bundle(
        artifact_id="art-exec-1",
        raw_input={
            "text": "Executive summary candidate.",
            "deterministic_gate_summary": {"passed": True, "score": 100},
            "x2_gate_outputs": {"all_passed": True},
        },
        author_model_family="anthropic",
        rubric_id="exec_summary.v1",
        artifact_path=artifact_file,
        repo_root=REPO_ROOT,
    )
    assert bundle.deterministic_priming_stripped is True
    assert "deterministic_gate_summary" in bundle.stripped_priming_keys
    assert "deterministic_gate_summary" not in bundle.payload
    assert bundle.required_judge_family != "anthropic"

    missing_rcpt = build_fail_closed_missing_verdict_receipt(bundle)
    assert missing_rcpt["status"] == "BLOCKED"
    assert missing_rcpt["gate_passed"] is False

    # Valid cross-family verdict passes.
    valid_verdict = {
        "evaluator_kind": "llm_judge",
        "judge_model_id": "gpt-5.6-luna",
        "author_model_family": "anthropic",
        "judge_model_family": "openai",
        "judge_model_families": ["openai"],
        "bundle_digest": bundle.bundle_digest,
        "artifact_sha256": sha256_file(artifact_file),
        "deterministic_priming_stripped": True,
        "judge_input_keys": bundle.judge_input_keys,
        "external_http_call_count": 0,
        "verdict": "PASS",
    }
    ok, errs = validate_blind_judge_verdict_provenance(
        valid_verdict,
        expected_bundle_digest=bundle.bundle_digest,
        artifact_disk_path=artifact_file,
    )
    assert ok, errs

    # Mutating artifact on disk invalidates receipt (defeats stale receipts).
    artifact_file.write_text('{"text": "Tampered after judge!"}', encoding="utf-8")
    stale_ok, stale_errs = validate_blind_judge_verdict_provenance(
        valid_verdict,
        expected_bundle_digest=bundle.bundle_digest,
        artifact_disk_path=artifact_file,
    )
    assert not stale_ok
    assert "STALE_ARTIFACT_RECEIPT_SHA256" in stale_errs

    # Rejects synthetic model IDs, non-LLM kinds, self-grading, and priming leaks.
    bad_verdict = dict(valid_verdict)
    bad_verdict["evaluator_kind"] = "deterministic_gate"
    bad_verdict["judge_model_id"] = "model_family_a"
    bad_verdict["judge_model_family"] = "anthropic"
    bad_verdict["judge_input_keys"] = ["text", "deterministic_gate_summary"]
    bad_ok, bad_errs = validate_blind_judge_verdict_provenance(bad_verdict)
    assert not bad_ok
    assert any(e.startswith("NON_LLM_EVALUATOR_KIND") for e in bad_errs)
    assert any(e.startswith("SYNTHETIC_MODEL_ID_REJECTED") for e in bad_errs)
    assert any(e.startswith("SELF_GRADING_FORBIDDEN") for e in bad_errs)
    assert any(e.startswith("DETERMINISTIC_PRIMING_LEAKED") for e in bad_errs)

    assert is_borderline_judge_result(8.9, {"clarity": 9.1})
    assert not is_borderline_judge_result(9.6, {"clarity": 9.5, "grounding": 9.4})


def test_multi_lens_panel_single_veto_deterministic_cap_and_spread_escalation() -> None:
    specs = [
        LensSpec("executive_buyer", weight=2.0, min_floor=8.5),
        LensSpec("factual_grounding", weight=2.0, min_floor=8.5),
        LensSpec("human_voice", weight=1.5, min_floor=8.0),
    ]
    # Deterministic voice cap pushes human_voice below floor -> single-lens veto FAIL.
    capped = evaluate_multi_lens_panel(
        specs,
        [
            LensVerdict("executive_buyer", 9.6, "openai"),
            LensVerdict("factual_grounding", 9.5, "google"),
            LensVerdict("human_voice", 9.4, "openai"),
        ],
        deterministic_score_caps={"human_voice": 6.8},
    )
    assert capped.verdict == "FAIL"
    assert capped.applied_deterministic_caps == {"human_voice": 6.8}
    assert any("SINGLE_LENS_FLOOR_VETO:human_voice" in r for r in capped.veto_reasons)

    # All lenses above floor and weighted >= 9.0, but spread 0.8 > 0.5 -> HITL_ESCALATE.
    spread = evaluate_multi_lens_panel(
        specs,
        [
            LensVerdict("executive_buyer", 9.8, "openai"),
            LensVerdict("factual_grounding", 9.0, "google"),
            LensVerdict("human_voice", 9.4, "openai"),
        ],
        pass_threshold=9.0,
        max_disagreement_spread=0.5,
    )
    assert spread.verdict == "HITL_ESCALATE"
    assert spread.persona_score_spread >= 0.8


def test_position_swap_and_calibration_single_class_collapse() -> None:
    debiaser = PositionSwapDebiaser(margin_threshold=0.20)
    # Consistent preference for candidate with higher score regardless of order.
    consistent = debiaser.evaluate_pair(
        pair_id="p1",
        candidate_a={"q": 10},
        candidate_b={"q": 2},
        judge_fn=lambda x, y: ("A" if x["q"] > y["q"] else "B", 0.90),
    )
    assert consistent.status == "CONSISTENT_WIN"
    assert consistent.winner == "A"

    # Always picking first slot ("A") is caught as order bias.
    biased = debiaser.evaluate_pair(
        pair_id="p2",
        candidate_a={"q": 10},
        candidate_b={"q": 2},
        judge_fn=lambda x, y: ("A", 0.85),
    )
    assert biased.status == "INCONCLUSIVE_ORDER_BIAS"

    runner = JudgeCalibrationRunner()
    collapse = runner.evaluate(
        ground_truth=[1, 1, 1, 1],
        predictions=[1, 1, 1, 1],
        probabilities=[0.95, 0.95, 0.95, 0.95],
    )
    assert not collapse.passed
    assert collapse.single_class_collapse

    good = runner.evaluate(
        ground_truth=[1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
        predictions=[1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
        probabilities=[0.95, 0.92, 0.96, 0.91, 0.94, 0.05, 0.08, 0.04, 0.07, 0.06],
    )
    assert good.passed
    assert good.cohens_kappa == 1.0

    cross = evaluate_cross_family_judge_agreement(
        [1, 1, 0, 0], [1, 1, 0, 0], [9.4, 9.2, 6.1, 5.9], [9.3, 9.1, 6.2, 6.0]
    )
    assert cross["passed"] is True


def test_pr_judge_receipt_gate_and_diff_scoped_eval_shield_fault_injection(tmp_path: Path) -> None:
    surface = JudgeGovernedSurface(
        surface_id="test_surface",
        source_globs=("apps_eval/target_*.py",),
        receipt_rel_path="receipt.json",
        artifact_rel_path="artifact.json",
    )
    # Missing receipt fails closed.
    missing = verify_diff_judge_receipts(["apps_eval/target_foo.py"], tmp_path, surfaces=[surface])
    assert missing["status"] == "FAIL"

    art = tmp_path / "artifact.json"
    art.write_text('{"ok": true}', encoding="utf-8")
    rcpt = {
        "verdict": "PASS",
        "evaluator_kind": "llm_judge",
        "judge_model_id": "gpt-5.6-luna",
        "author_model_family": "anthropic",
        "judge_model_family": "openai",
        "artifact_sha256": sha256_file(art),
        "deterministic_priming_stripped": True,
        "judge_input_keys": ["ok"],
        "external_http_call_count": 0,
    }
    (tmp_path / "receipt.json").write_text(json.dumps(rcpt), encoding="utf-8")
    ok_gate = verify_diff_judge_receipts(["apps_eval/target_foo.py"], tmp_path, surfaces=[surface])
    assert ok_gate["status"] == "PASS", ok_gate

    # Real repo shield passes all 5 domains and fails closed on counterfactual --inject-fault.
    all_pass = run_eval_shield(REPO_ROOT, run_all=True)
    assert all_pass["status"] == "PASS", all_pass
    assert len(all_pass["domains_run"]) == 5
    assert all_pass["slow_domains"] == []

    injected = run_eval_shield(REPO_ROOT, run_all=True, inject_fault="outreach_engine")
    assert injected["status"] == "FAIL"
