"""Unit tests for the pure-white (#ffffff) Calibration Studio UI server, endpoints, and CLI subcommands."""
from __future__ import annotations

import json
from pathlib import Path
import threading
import urllib.request

from apps_eval.graders.judge.calibration_studio_server import create_calibration_studio_server
from apps_eval.graders.judge.calibration_studio_template import STUDIO_HTML
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
    score_candidate_cached,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_pure_white_studio_template_invariants() -> None:
    assert 'meta name="color-scheme" content="light only"' in STUDIO_HTML
    assert "background: #ffffff !important" in STUDIO_HTML
    assert "Save as PASS &amp; Next" in STUDIO_HTML
    assert "Save as FAIL &amp; Next" in STUDIO_HTML
    assert "Abstain: Insufficient Evidence" in STUDIO_HTML
    assert "Flag: Defective Prompt" in STUDIO_HTML
    assert "Source Evidence Excerpts" in STUDIO_HTML
    rg_items = build_resume_gold_candidates()
    lic_items = build_outreach_gold_candidates()
    assert len(rg_items) == 24
    assert len(lic_items) == 24
    assert LIVE_DRIFT_SCORE_SCHEMA["type"] == "object"
    assert DEFAULT_RECEIPT_PATH.name == "ide_judge_drift_receipt.json"


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
    rubric_doc = json.loads((REPO_ROOT / "config" / "governance" / "external_judge_rubric_v1.json").read_text(encoding="utf-8"))
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


def test_studio_server_get_state_post_grade_and_post_quarantine(tmp_path: Path) -> None:
    pool_path = REPO_ROOT / "artifacts" / "eval_harness" / "blind_packets" / "resume_blind_pool.v1.json"
    store_path = tmp_path / "studio_labels.json"
    server = create_calibration_studio_server(
        pool_path,
        store_path=store_path,
        host="127.0.0.1",
        port=0,
        annotator_id="human-exec-rater",
        seed=20260417,
    )
    host, port = server.server_address[:2]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as resp:
            html = resp.read().decode("utf-8")
            assert resp.status == 200
            assert "#ffffff" in html

        with urllib.request.urlopen(f"http://{host}:{port}/api/state", timeout=5) as resp:
            state = json.loads(resp.read().decode("utf-8"))
            assert state["status"] == "PASS"
            assert len(state["items"]) == 24
            first_item = state["items"][0]
            second_item = state["items"][1]

        grade_payload = {
            "case_id": first_item["case_id"],
            "judge_surface": first_item["judge_surface"],
            "topic_family": first_item["topic_family"],
            "partition": first_item["partition"],
            "artifact_sha256": first_item["artifact_sha256"],
            "blinded_text": first_item["blinded_text"],
            "evidence_context_sha256": first_item["evidence_context_sha256"],
            "dimension_grades": {
                "factual_faithfulness": 5,
                "completeness_and_relevance": 4,
                "cold_reader_clarity": 4,
                "actionability_and_proportion": 4,
            },
            "atomic_checks": {
                "unsupported_claim_absent": True,
                "source_contradiction_absent": True,
            },
            "failure_tags": [],
            "critique_rationale": "Strong grounded executive section.",
            "notes": "Strong grounded executive section.",
            "human_verdict": "PASS",
        }
        req_grade = urllib.request.Request(
            f"http://{host}:{port}/api/grade",
            data=json.dumps(grade_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_grade, timeout=5) as resp:
            res_grade = json.loads(resp.read().decode("utf-8"))
            assert res_grade["status"] == "PASS"
            assert res_grade["record"]["case_id"] == first_item["case_id"]

        quar_payload = {
            "case_id": second_item["case_id"],
            "judge_surface": second_item["judge_surface"],
            "topic_family": second_item["topic_family"],
            "partition": second_item["partition"],
            "artifact_sha256": second_item["artifact_sha256"],
            "reason": "ABSTAIN_INSUFFICIENT_EVIDENCE",
            "notes": "Need extra contract context.",
        }
        req_quar = urllib.request.Request(
            f"http://{host}:{port}/api/quarantine",
            data=json.dumps(quar_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_quar, timeout=5) as resp:
            res_quar = json.loads(resp.read().decode("utf-8"))
            assert res_quar["status"] == "PASS"
            assert res_quar["quarantined"]["reason"] == "ABSTAIN_INSUFFICIENT_EVIDENCE"
    finally:
        server.shutdown()
        server.server_close()


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
