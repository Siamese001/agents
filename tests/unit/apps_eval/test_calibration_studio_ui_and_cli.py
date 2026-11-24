"""Unit tests for centralized `core-governance` Pure-White 18px `judge_v3_6check` Studio binding and CLI."""
from __future__ import annotations

import json
from pathlib import Path

from apps_eval.graders.judge._core_governance_bridge import get_studio_session_contract
from apps_eval.graders.judge.studio_session_binder import (
    bind_centralized_judge_v3_studio,
    load_centralized_studio_html,
    sync_studio_store_to_human_provenance,
)
from ops_scripts.blind_human_grading_cli import (
    format_one_by_one_blind_chat_card,
    main as cli_main,
    parse_compact_human_grades,
)
from ops_scripts.curate_ide_judge_gold_corpus import (
    build_outreach_gold_candidates,
    build_resume_gold_candidates,
)
from ops_scripts.run_ide_judge_drift import (
    DEFAULT_RECEIPT_PATH,
    LIVE_DRIFT_SCORE_SCHEMA,
    build_live_drift_score_schema,
    compute_mechanical_drift_score_and_pass,
    score_candidate_cached,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_pure_white_centralized_studio_bundle_invariants() -> None:
    studio_html = load_centralized_studio_html()
    assert 'meta name="color-scheme" content="light only"' in studio_html
    assert "background: #ffffff !important" in studio_html
    assert "judge_v3_6check" in studio_html
    assert "INV-LABELING-STUDIO-UI-FROZEN" in studio_html
    assert not (REPO_ROOT / "apps_eval" / "graders" / "judge" / "calibration_studio_server.py").exists()
    assert not (REPO_ROOT / "apps_eval" / "graders" / "judge" / "calibration_studio_template.py").exists()

    rg_items = build_resume_gold_candidates()
    lic_items = build_outreach_gold_candidates()
    assert len(rg_items) == 24
    assert len(lic_items) == 24
    assert LIVE_DRIFT_SCORE_SCHEMA["type"] == "object"
    assert DEFAULT_RECEIPT_PATH.name == "ide_judge_drift_receipt.json"

    for r in rg_items:
        tcard = r.target_job_card()
        assert tcard["target_company"]
        assert tcard["target_role"]
        assert tcard["target_mandate"]
        assert tcard["section_label"]

    from apps_eval.graders.judge.gold_corpus import load_external_stakeholder_rubric

    rg_rubric, _ = load_external_stakeholder_rubric("resume_engine", repo_root=REPO_ROOT)
    bound_schema = build_live_drift_score_schema(rg_rubric)
    assert bound_schema["required"][0] == "rationale"

    mech_score, mech_pass, _, _ = compute_mechanical_drift_score_and_pass(
        {
            "rationale": "Stretched metric detected despite high holistic score.",
            "dimension_scores": {
                "role_mandate_fit": 5,
                "claim_credibility_and_grounding": 5,
                "executive_signal_density": 5,
                "authentic_human_voice": 5,
                "decision_usefulness": 5,
            },
            "hard_fail_flags": {
                "fabricated_or_stretched_metric": True,
                "jd_parrot_mimicry": False,
                "ai_slop_or_filler": False,
                "scope_or_employer_distortion": False,
            },
            "judge_score_1_5": 4.9,
            "judge_pass": True,
        },
        rg_rubric,
    )
    assert mech_score == 5.0
    assert mech_pass is False


def test_compact_human_grades_parser_and_chat_card() -> None:
    parsed = parse_compact_human_grades("F=5, C=4, R=4, A=4, Verdict=PASS")
    assert parsed == {
        "factual_faithfulness": 5,
        "completeness_and_relevance": 4,
        "cold_reader_clarity": 4,
        "actionability_and_proportion": 4,
    }
    pool_doc = json.loads(
        (REPO_ROOT / "artifacts" / "eval_harness" / "blind_packets" / "resume_blind_pool.v1.json").read_text(
            encoding="utf-8"
        )
    )
    rubric_doc = json.loads(
        (REPO_ROOT / "config" / "governance" / "external_judge_rubric_v1.json").read_text(encoding="utf-8")
    )
    card = format_one_by_one_blind_chat_card(pool_doc["items"][0], rubric_doc)
    assert "Blind Human Calibration Item" in card
    assert "Source Evidence Excerpts" in card

    rg_item = build_resume_gold_candidates()[0]
    from apps_eval.graders.judge.gold_corpus import canonical_sha256

    ck = canonical_sha256({"item_digest": rg_item.item_digest(), "rubric_sha256": "rsha", "model_slug": "neon"})
    cache = {ck: {"item_id": rg_item.item_id, "judge_score_1_5": 4.8, "judge_pass": True}}
    cached_res = score_candidate_cached(
        rg_item,
        model_slug="neon",
        rubric_doc=rubric_doc,
        rubric_sha256="rsha",
        cache=cache,
    )
    assert cached_res["judge_pass"] is True


def test_centralized_studio_session_binding_save_and_quarantine(tmp_path: Path) -> None:
    pool_path = REPO_ROOT / "artifacts" / "eval_harness" / "blind_packets" / "resume_blind_pool.v1.json"
    store_path = tmp_path / "studio_labels.json"
    data_dir = tmp_path / "plugin_data"

    bound = bind_centralized_judge_v3_studio(
        pool_path,
        store_path=store_path,
        annotator_id="human-exec-rater",
        seed=20260417,
        data_dir=data_dir,
    )
    assert bound["status"] == "PASS"
    assert bound["mode"] == "judge_v3_6check"
    state = bound["state"]
    assert len(state["cases"]) == 24
    first_item = state["cases"][0]
    second_item = state["cases"][1]

    sc = get_studio_session_contract()
    all_yes = {chk["id"]: True for chk in state["atomic_check_specs"]}
    state_after_1 = sc.persist_judge_v3_6check_label(
        pool_path,
        store_path,
        session_sha256=state["session_sha256"],
        case_id=first_item["case_id"],
        atomic_checks=all_yes,
        verdict="PASS",
        note="Strong grounded executive section.",
        annotator_id="human-exec-rater",
    )
    c1 = next(c for c in state_after_1["cases"] if c["case_id"] == first_item["case_id"])
    assert c1["verdict"] == "PASS"
    assert c1["normalized_human_score"] == 1.0

    state_after_2 = sc.persist_judge_v3_6check_label(
        pool_path,
        store_path,
        session_sha256=state_after_1["session_sha256"],
        case_id=second_item["case_id"],
        verdict="Q",
        quarantine_reason="ABSTAIN_INSUFFICIENT_EVIDENCE",
        note="Need extra contract context.",
        annotator_id="human-exec-rater",
    )
    c2 = next(c for c in state_after_2["cases"] if c["case_id"] == second_item["case_id"])
    assert c2["verdict"] == "Q"
    assert c2["quarantine_reason"] == "ABSTAIN_INSUFFICIENT_EVIDENCE"


def test_cli_judge_calibrate_ui_check_only_and_grade(tmp_path: Path) -> None:
    pool_path = REPO_ROOT / "artifacts" / "eval_harness" / "blind_packets" / "outreach_blind_pool.v1.json"
    store_path = tmp_path / "cli_labels.json"
    rc_ui = cli_main(
        [
            "judge-calibrate-ui",
            "--pool",
            str(pool_path),
            "--store-path",
            str(store_path),
            "--port",
            "0",
            "--annotator",
            "human-exec-rater",
            "--check-only",
        ]
    )
    assert rc_ui == 0

    pool_doc = json.loads(pool_path.read_text(encoding="utf-8"))
    item = pool_doc["items"][0]
    rc_grade = cli_main(
        [
            "judge-calibrate-grade",
            "--case-id",
            item["case_id"],
            "--surface",
            item["judge_surface"],
            "--partition",
            item["partition"],
            "--topic-family",
            item["topic_family"],
            "--artifact-sha256",
            item["artifact_sha256"],
            "--grades",
            "F=4,C=4,R=4,A=4",
            "--verdict",
            "PASS",
            "--annotator",
            "human-exec-rater",
            "--store-path",
            str(store_path),
        ]
    )
    assert rc_grade == 0
    saved = json.loads(store_path.read_text(encoding="utf-8"))
    assert len(saved["records"]) == 1


def test_studio_sync_to_human_provenance_and_real_multibullet_blocks(tmp_path: Path) -> None:
    rg_items = {r.item_id: r for r in build_resume_gold_candidates()}
    assert rg_items["rg_gold_015"].candidate_text.count("BCBS 239") == 2
    assert rg_items["rg_gold_015"].candidate_text.count("$10M") == 2
    assert "DevSecOps" in rg_items["rg_gold_019"].candidate_text
    assert rg_items["rg_gold_023"].candidate_text.count("20% joint revenue growth") == 2

    store_path = tmp_path / "studio_labels.json"
    pool_path = REPO_ROOT / "artifacts" / "eval_harness" / "blind_packets" / "resume_blind_pool.v1.json"
    pool_doc = json.loads(pool_path.read_text(encoding="utf-8"))
    first_item = pool_doc["items"][0]
    rc_grade = cli_main(
        [
            "judge-calibrate-grade",
            "--case-id",
            first_item["case_id"],
            "--surface",
            first_item["judge_surface"],
            "--partition",
            first_item["partition"],
            "--topic-family",
            first_item["topic_family"],
            "--artifact-sha256",
            first_item["artifact_sha256"],
            "--grades",
            "F=5,C=5,R=5,A=5",
            "--verdict",
            "PASS",
            "--annotator",
            "amit.ayer",
            "--store-path",
            str(store_path),
        ]
    )
    assert rc_grade == 0
    ledger_path = tmp_path / "resume_human_gold.v1.jsonl"
    adjudicated_path = tmp_path / "resume_human_adjudicated.v1.json"
    sync_res = sync_studio_store_to_human_provenance(
        store_path,
        engine="resume_engine",
        ledger_path=ledger_path,
        adjudicated_path=adjudicated_path,
        repo_root=REPO_ROOT,
    )
    assert sync_res["ok"] is True
    assert sync_res["adjudicated_count"] == 1
