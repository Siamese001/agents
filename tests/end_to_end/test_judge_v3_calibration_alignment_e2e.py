"""End-to-end calibration alignment and PR judge receipt verification tests for Clean-Slate Judge v3."""
from __future__ import annotations

import json
from pathlib import Path

from apps_eval.graders.judge.external_rubric_store import (
    DEFAULT_EXTERNAL_RUBRIC_V2_REL_PATH,
    ExternalRubricHumanStore,
    compute_payload_sha256,
    load_and_verify_external_rubric_v2,
)
from apps_eval.graders.judge.ide_judge_drift_evaluator import IDEJudgeDriftEvaluator
from apps_eval.graders.judge.v3_evaluator import build_v3_evaluation_bundle, parse_and_seal_v3_verdict
from apps_eval.graders.judge.v3_registry import JudgeRubricRegistryV3
from ops_scripts.run_ide_judge_drift import build_live_drift_score_schema, compute_v3_drift_unit_score_and_pass
from tools.pr_governance_core.judge_receipt_gate import JudgeGovernedSurface, verify_diff_judge_receipts

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_judge_v3_and_human_v2_1to1_calibration_drift_alignment_e2e(tmp_path: Path) -> None:
    """Verify 1:1 criterion parity between Judge v3 `human_calibration_studio` and `external_judge_rubric_v2`."""
    rubric_v2_path = REPO_ROOT / DEFAULT_EXTERNAL_RUBRIC_V2_REL_PATH
    rubric_v2 = load_and_verify_external_rubric_v2(rubric_v2_path)
    rubric_v2_sha = str(rubric_v2["rubric_sha256"])
    reg = JudgeRubricRegistryV3.load(REPO_ROOT / "config" / "governance" / "judge_rubrics_v3.json")

    v3_drift_schema = build_live_drift_score_schema(rubric_v2)
    assert v3_drift_schema["required"] == ["cold_read_takeaway", "checks"]

    store = ExternalRubricHumanStore(store_path=tmp_path / "human_v2_labels.json", rubric_path=rubric_v2_path)
    judge_verdicts_by_case: dict[str, dict[str, object]] = {}

    for idx in range(20):
        is_pass_case = idx < 10
        case_id = f"cal_v3_{idx:03d}"
        cand_text = (
            f"Directed enterprise cloud modernization Case-{idx} delivering {20 + idx}% latency reduction."
            if is_pass_case
            else f"Invented $999M unverified patent claim in Case-{idx} contradicting source records."
        )
        cand_file = tmp_path / f"cand_{idx:03d}.txt"
        cand_file.write_text(cand_text, encoding="utf-8")
        art_sha = compute_payload_sha256(cand_text)

        atomic_human = {
            "unsupported_claim_absent": is_pass_case,
            "source_contradiction_absent": is_pass_case,
            "core_question_fully_answered": is_pass_case,
            "scope_constraints_covered": is_pass_case,
            "cold_reader_jargon_free": True,
            "concrete_owner_and_next_step": is_pass_case,
        }
        rec = store.append_label(
            {
                "case_id": case_id,
                "judge_surface": "agent_trace_and_calibration:human_calibration_studio",
                "topic_family": f"topic_family_{idx:03d}",
                "partition": "calibration",
                "artifact_sha256": art_sha,
                "external_rubric_id": "external_judge_rubric_v2",
                "external_rubric_sha256": rubric_v2_sha,
                "atomic_checks": atomic_human,
                "failure_tags": [] if is_pass_case else ["HALLUCINATED_FACT", "OMITTED_CONSTRAINT"],
                "critique_rationale": "Clean grounded claim." if is_pass_case else "Invented $999M patent claim.",
                "human_verdict": "PASS" if is_pass_case else "FAIL",
                "annotator_id": "amit.ayer",
                "graded_at_utc": "2026-11-24T12:00:00Z",
            },
            candidate_text=cand_text,
            require_fail_critique=True,
        )
        assert rec.normalized_human_score() == (1.0 if is_pass_case else 0.15)

        bundle, profile, _ = build_v3_evaluation_bundle(
            profile_token="agent_trace_and_calibration:human_calibration_studio",
            artifact_id=case_id,
            raw_input={
                "candidate_text": cand_text,
                "target_context": "Target Role: SVP Cloud Modernization",
                "source_evidence": [f"Verified fact for Case-{idx}: {20 + idx}% latency reduction."],
            },
            author_model_family="anthropic",
            registry=reg,
            artifact_path=cand_file,
            repo_root=REPO_ROOT,
        )
        raw_llm = {
            "cold_read_takeaway": (
                "Grounded executive accomplishment aligned to cloud mandate."
                if is_pass_case
                else "Fabricates $999M patent claim absent from verified source facts."
            ),
            "checks": {
                cid: {
                    "verdict": "YES" if atomic_human[cid] else "NO",
                    "evidence_span": "" if atomic_human[cid] else "$999M unverified patent claim",
                }
                for cid in profile.check_ids
            },
            "failure_tags": [] if is_pass_case else ["HALLUCINATED_FACT", "OMITTED_CONSTRAINT"],
        }
        unit_s, j_pass, _ = compute_v3_drift_unit_score_and_pass(raw_llm, rubric_v2)
        assert unit_s == rec.normalized_human_score()
        assert j_pass is is_pass_case

        sealed = parse_and_seal_v3_verdict(
            raw_llm,
            bundle=bundle,
            profile=profile,
            rubric_sha256=reg.rubric_sha256,
            judge_model_id="gemini-4-argon-medium",
            judge_model_family="google",
            artifact_disk_path=cand_file,
        )
        assert sealed.normalized_unit_score == rec.normalized_human_score()
        assert sealed.passed is is_pass_case
        judge_verdicts_by_case[case_id] = sealed.to_dict()

    evaluator = IDEJudgeDriftEvaluator()
    drift_receipt = evaluator.evaluate(
        store.load_records(partition="calibration"),
        judge_verdicts_by_case,
        judge_surface="agent_trace_and_calibration:human_calibration_studio",
        partition="calibration",
    )
    assert drift_receipt.passed is True
    assert drift_receipt.drift_detected is False
    assert drift_receipt.cohens_kappa == 1.0
    assert drift_receipt.tpr == 1.0
    assert drift_receipt.tnr == 1.0
    assert drift_receipt.signed_leniency_bias == 0.0


def test_pr_judge_receipt_gate_enforces_v3_unit_scale_and_rejects_stub_or_legacy_float(tmp_path: Path) -> None:
    """Verify PR `judge_receipt_gate` accepts valid v3 unit receipts and blocks legacy >1.0 floats or stubs."""
    receipt_rel = "artifacts/eval_harness/judge_v3/test_exec_summary_receipt.json"
    artifact_rel = "artifacts/eval_harness/judge_v3/test_exec_summary_artifact.txt"
    receipt_file = tmp_path / receipt_rel
    artifact_file = tmp_path / artifact_rel
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    reg = JudgeRubricRegistryV3.load(REPO_ROOT / "config" / "governance" / "judge_rubrics_v3.json")

    cand_text = "Architected enterprise risk data platform cutting cycle time by 35% across global banking pods."
    artifact_file.write_text(cand_text, encoding="utf-8")
    bundle, profile, _ = build_v3_evaluation_bundle(
        profile_token="resume_sections:executive_summary",
        artifact_id="exec-summary-v3-gate",
        raw_input={
            "candidate_text": cand_text,
            "target_context": "Target: SVP Enterprise Data Architecture",
            "source_evidence": ["Led enterprise risk data platform (35% cycle time reduction)."],
        },
        author_model_family="anthropic",
        registry=reg,
        artifact_path=artifact_file,
        repo_root=REPO_ROOT,
    )
    sealed = parse_and_seal_v3_verdict(
        {
            "cold_read_takeaway": "Grounded SVP data platform summary.",
            "checks": {cid: {"verdict": "YES", "evidence_span": ""} for cid in profile.check_ids},
            "failure_tags": [],
        },
        bundle=bundle,
        profile=profile,
        rubric_sha256=reg.rubric_sha256,
        judge_model_id="gemini-4-argon-medium",
        judge_model_family="google",
        artifact_disk_path=artifact_file,
    )
    receipt_file.write_text(json.dumps(sealed.to_dict(), indent=2), encoding="utf-8")

    surface_cfg = (
        JudgeGovernedSurface(
            surface_id="resume_executive_summary",
            source_globs=("resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_*.py",),
            receipt_rel_path=receipt_rel,
            artifact_rel_path=artifact_rel,
            min_distinct_families=1,
        ),
    )
    res_ok = verify_diff_judge_receipts(
        ["resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_writer.py"],
        tmp_path,
        surfaces=surface_cfg,
    )
    assert res_ok["status"] == "PASS"

    # Corrupt normalized_unit_score to legacy >1.0 float -> must fail closed
    bad_payload = sealed.to_dict()
    bad_payload["normalized_unit_score"] = 4.85
    receipt_file.write_text(json.dumps(bad_payload, indent=2), encoding="utf-8")
    res_bad_scale = verify_diff_judge_receipts(
        ["resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_writer.py"],
        tmp_path,
        surfaces=surface_cfg,
    )
    assert res_bad_scale["status"] == "FAIL"
    assert any(
        "NON_UNIT_NORMALIZED_SCORE" in r
        for v in res_bad_scale["violations"]
        for r in v["reasons"]
    )

    # Stage A deterministic short-circuit (`llm_judge_executed: False`) -> cannot impersonate an LLM receipt
    skip_payload = sealed.to_dict()
    skip_payload["llm_judge_executed"] = False
    skip_payload["normalized_unit_score"] = None
    receipt_file.write_text(json.dumps(skip_payload, indent=2), encoding="utf-8")
    res_skip = verify_diff_judge_receipts(
        ["resume_graph_engine/src/apps_rg/runtime/sections/executive_summary_writer.py"],
        tmp_path,
        surfaces=surface_cfg,
    )
    assert res_skip["status"] == "FAIL"
    assert any(
        "STAGE_B_LLM_JUDGE_NOT_EXECUTED" in r
        for v in res_skip["violations"]
        for r in v["reasons"]
    )
