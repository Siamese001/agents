"""Unit & adversarial tests for frozen blind QRELS grader, 5-axis exclusivity, and out-of-sample Kappa gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps_eval.qrels.qrels_batch_widget import (
    DEFAULT_FONT_SIZE_PX,
    audit_rendered_batch_html,
    build_batch_artifact_filename,
    compute_batch_fingerprint,
    parse_structured_core_statement,
    render_blind_batch_widget_html,
)
from apps_eval.qrels.qrels_blind_grader import (
    compute_grader_source_sha256,
    grade_blind_core_statement,
    load_human_label_ledger,
    record_human_batch_grades,
    verify_qrels_mutual_exclusivity,
)
from apps_eval.qrels.qrels_calibration_stats import (
    compute_bootstrap_kappa_ci95,
    compute_cohens_kappa,
    compute_kappa_receipt_hashes,
    compute_quadratic_weighted_kappa,
    verify_kappa_calibration_receipt,
)
from ops_scripts.qrels_batch_runner import parse_batch_reply, parse_batch_reply_with_tags


def test_blind_grader_ignores_ranks_scores_and_target_flag() -> None:
    query = {
        "query_id": "q_1",
        "answerable": True,
        "query_text": "How did Slalom engineer a privacy-isolated live voice advisory assistant with sub-250ms latency?",
        "ground_truth_summary": "[Unit] engagement_episode · Slalom | [Claim] Built and deployed a production privacy-isolated local acoustic capture and sub-250ms live executive advisory copilot.",
    }
    cand_a = {
        "record_id": "r1",
        "core_statement": "[Unit] engagement_episode · Slalom | [Claim] Built and deployed a production privacy-isolated local acoustic capture and sub-250ms live executive advisory copilot.",
        "fused_rank": 1,
        "dense_rank": 1,
        "is_verified_target": True,
    }
    cand_b = {
        "record_id": "r1",
        "core_statement": cand_a["core_statement"],
        "fused_rank": 999,
        "dense_rank": 999,
        "is_verified_target": False,
    }
    assert grade_blind_core_statement(query, cand_a) == 3
    assert grade_blind_core_statement(query, cand_b) == 3
    assert grade_blind_core_statement({**query, "answerable": False}, cand_a) == 0


def test_five_axis_mutual_exclusivity_fails_closed() -> None:
    ledger = {"human_graded_queries": []}
    valid_queue = [
        {
            "qrel_id": "anchor-01",
            "query_id": "q_1",
            "query_text": "How did Slalom deploy bi-temporal knowledge graph search?",
            "target_record_id": "rec_a",
            "status": "PENDING_BLIND_GRADING",
            "candidates": [
                {"slot": "A", "record_id": "rec_a", "core_statement": "Slalom deployed bi-temporal knowledge graph hybrid search."},
                {"slot": "B", "record_id": "rec_b", "core_statement": "IBM migrated regulated banking workloads to AWS."},
                {"slot": "C", "record_id": "rec_c", "core_statement": "Unify built automated FinOps executive dashboards."},
                {"slot": "D", "record_id": "rec_d", "core_statement": "InsurTech decoupled PolicyCenter and ClaimCenter pipelines."},
            ],
        }
    ]
    rep = verify_qrels_mutual_exclusivity(valid_queue, ledger)
    assert rep["is_mutually_exclusive"] is True
    assert rep["unique_pending_record_ids"] == 4

    # Duplicate record_id collision fails closed
    dup_queue = [
        valid_queue[0],
        {
            **valid_queue[0],
            "qrel_id": "anchor-02",
            "query_id": "q_2",
            "query_text": "What NAIC cloud controls governed insurer migrations?",
            "target_record_id": "rec_e",
            "candidates": [
                {"slot": "A", "record_id": "rec_a", "core_statement": "Duplicate record id collision."},
                {"slot": "B", "record_id": "rec_f", "core_statement": "Unrelated distinct record text alpha."},
                {"slot": "C", "record_id": "rec_g", "core_statement": "Unrelated distinct record text beta."},
                {"slot": "D", "record_id": "rec_h", "core_statement": "Unrelated distinct record text gamma."},
            ],
        },
    ]
    with pytest.raises(ValueError, match="Record ID collision"):
        verify_qrels_mutual_exclusivity(dup_queue, ledger)


def test_out_of_sample_kappa_ci95_and_strict_200_fail_closed() -> None:
    human = [3, 2, 1, 0] * 15
    grader = list(human)
    grader[0] = 2
    grader[1] = 2
    ck = compute_cohens_kappa(human, grader)
    qwk = compute_quadratic_weighted_kappa(human, grader)
    lo, hi = compute_bootstrap_kappa_ci95(human, grader, n_boot=300, seed=42)
    assert 0.70 <= lo <= ck <= hi <= 1.0

    sha = compute_grader_source_sha256()
    eq_sha, art_sha = compute_kappa_receipt_hashes([], human, grader, ck, qwk)
    gt = {
        "evaluated_queries": [],
        "kappa_calibration_receipt": {
            "total_human_passage_labels": 200,
            "grader_source_sha256": sha,
            "human_gold_grades": human,
            "blind_grader_grades": grader,
            "cohens_kappa": ck,
            "quadratic_weighted_kappa": qwk,
            "evaluated_queries_sha256": eq_sha,
            "artifact_sha256": art_sha,
        },
    }
    ok = verify_kappa_calibration_receipt(
        gt,
        min_anchor_passages=60,
        min_total_human_labels=200,
        ci95_lower_floor=0.70,
        expected_grader_sha256=sha,
    )
    assert ok["is_valid"] is True

    # Sub-200 labels must fail closed
    gt_sub200 = {**gt, "kappa_calibration_receipt": {**gt["kappa_calibration_receipt"], "total_human_passage_labels": 180}}
    fail_sub = verify_kappa_calibration_receipt(gt_sub200, min_anchor_passages=60, min_total_human_labels=200)
    assert fail_sub["is_valid"] is False
    assert fail_sub["reason"] == "insufficient_or_mismatched_anchor_grades"

    # Tampered grader SHA-256 must fail closed
    fail_sha = verify_kappa_calibration_receipt(gt, expected_grader_sha256="deadbeef")
    assert fail_sha["is_valid"] is False
    assert fail_sha["reason"] == "grader_source_sha256_mismatch"


def test_parse_batch_reply_and_ledger_record(tmp_path: Path) -> None:
    queue = [
        {
            "qrel_id": "anchor-01",
            "batch_index": 1,
            "query_id": "q_su_01",
            "topic_id": "t1",
            "partition": "dev",
            "surface": "resume_graph_engine",
            "query_text": "Test query 1?",
            "target_record_id": "r1",
            "ground_truth_summary": "gt1",
            "status": "PENDING_BLIND_GRADING",
            "candidates": [
                {"slot": s, "record_id": f"r{i}", "core_statement": f"Core {i}", "relevance_label": None}
                for i, s in enumerate(("A", "B", "C", "D"), start=1)
            ],
        }
    ]
    parsed = parse_batch_reply("Q1: A=3, B=1, C=0, D=2", queue, batch_index=1)
    assert parsed == {"anchor-01": {"A": 3, "B": 1, "C": 0, "D": 2}}
    ledger = load_human_label_ledger(tmp_path / "ledger.json")
    added = record_human_batch_grades(queue, ledger, parsed)
    assert added == 1
    assert queue[0]["status"] == "COMPLETED_HUMAN_GRADED"
    assert ledger["human_graded_queries"][0]["record_grades"] == {"r1": 3, "r2": 1, "r3": 0, "r4": 2}


def test_structured_core_parser_and_large_font_blind_batch_widget() -> None:
    raw = (
        "[Claim] Graph evidence supports led 105 engineers across 33 programs. | "
        "[Outcomes] Graph evidence supports led 105 engineers across 33 programs; $25M+ SOW portfolio; zero red escalations | "
        "[Evidence] [Slalom] Directed 105 builders.; [IBM] Cut latency by 40%."
    )
    parsed = parse_structured_core_statement(raw)
    assert parsed["claim"] == "Led 105 engineers across 33 programs."
    # Verbatim duplicate of claim in outcomes is automatically collapsed
    assert parsed["outcomes"] == ["$25M+ SOW portfolio", "Zero red escalations"]
    assert len(parsed["evidence"]) == 2
    assert parsed["evidence"][0] == {"employer": "Slalom", "text": "Directed 105 builders."}

    batch = [
        {
            "qrel_id": "anchor-01",
            "query_id": "q_su_01",
            "query_text": "Scale of Slalom engineering leadership?",
            "surface": "outreach_engine",
            "tier": "tier4_near_domain_unanswerable",
            "answerable": False,
            "target_record_id": "secret_target_id_do_not_leak",
            "ground_truth_summary": "secret_gt_do_not_leak",
            "candidates": [
                {
                    "slot": s,
                    "record_id": f"rec_{s}",
                    "core_statement": raw,
                    "boilerplate_footer": "[Unit] engagement_episode · Slalom",
                    "dense_rank": 1,
                    "fused_rank": 1,
                }
                for s in ("A", "B", "C", "D")
            ],
        }
    ]
    fp = compute_batch_fingerprint(batch, batch_index=1)
    filename = build_batch_artifact_filename(batch, batch_index=1, total_batches=5, corpus_digest="7500b586abcd")
    assert filename.startswith(f"qrels_batch_1_of_5_{fp}_") and filename.endswith(".html")

    html = render_blind_batch_widget_html(batch, batch_index=1, total_batches=5, corpus_digest="7500b586abcd")
    audit_rendered_batch_html(html, batch_index=1, expected_fingerprint=fp)
    assert f"--fs: {DEFAULT_FONT_SIZE_PX}px" in html
    assert DEFAULT_FONT_SIZE_PX >= 17
    assert "position: sticky" in html and 'id="stickyHeader"' in html
    assert "q-grid-2x2" in html and "btnLayoutGrid" in html and "btnLayoutStack" in html
    assert "q-claim" in html and "q-outcome" in html
    assert "btnFontUp" in html and "btnFontDown" in html
    assert "Direct Hit" in html and "Partial Support" in html
    assert "Background Only" in html and "Off-Topic / Confounder" in html
    assert "0, 1, or multiple 3s" in html
    assert "Executive Outreach" in html
    assert "Wrong Employer" in html and "Keyword Trap" in html and "Missing Proof" in html
    assert "Why < 3:" in html and "cur < 3" in html
    assert f"agents_qrels_b1_{fp}" in html
    assert f"BATCH1#{fp}" in html
    assert f'data-batch-fingerprint="{fp}"' in html

    # Mutating a single query text on the same corpus_digest MUST change fingerprint, filename, and STORAGE_KEY
    mutated_batch = [{**batch[0], "query_text": "Different question on identical corpus digest?"}]
    fp_mutated = compute_batch_fingerprint(mutated_batch, batch_index=1)
    assert fp_mutated != fp
    assert build_batch_artifact_filename(mutated_batch, batch_index=1, corpus_digest="7500b586abcd") != filename

    # Strict blind-leakage audit: zero ranks, targets, ground truth, or answerable/tier metadata
    for forbidden in (
        "secret_target_id_do_not_leak",
        "secret_gt_do_not_leak",
        "dense_rank",
        "fused_rank",
        "tier4_near_domain_unanswerable",
        "\"answerable\"",
    ):
        assert forbidden not in html


def test_parse_batch_reply_supports_quarantine_and_failure_tags() -> None:
    queue = [
        {
            "qrel_id": "anchor-01",
            "batch_index": 1,
            "query_id": "q_neg_01",
            "query_text": "Out of scope probe?",
            "candidates": [{"slot": s, "record_id": f"r{i}", "core_statement": f"Core {i}"} for i, s in enumerate(("A", "B", "C", "D"), 1)],
        }
    ]
    fp = compute_batch_fingerprint(queue, batch_index=1)
    grades, tags = parse_batch_reply_with_tags(
        f"BATCH1#{fp} | Q1: A=0,B=Q,C=1,D=0 [A:Out-of-Scope Query;C:Wrong Employer]",
        queue,
        batch_index=1,
        require_fingerprint=True,
    )
    assert grades == {"anchor-01": {"A": 0, "B": "Q", "C": 1, "D": 0}}
    assert tags == {"anchor-01": {"A": "Out-of-Scope Query", "C": "Wrong Employer"}}

    # Stale or wrong-batch fingerprint MUST fail closed
    with pytest.raises(ValueError, match="STALE_OR_MISMATCHED_BATCH_FINGERPRINT"):
        parse_batch_reply_with_tags(
            "BATCH1#deadbeef | Q1: A=0,B=0,C=0,D=0",
            queue,
            batch_index=1,
            require_fingerprint=True,
        )
    with pytest.raises(ValueError, match="STALE_OR_MISMATCHED_BATCH_FINGERPRINT"):
        parse_batch_reply_with_tags(
            f"BATCH2#{fp} | Q1: A=0,B=0,C=0,D=0",
            queue,
            batch_index=1,
            require_fingerprint=True,
        )


def test_ensure_50_query_cohort_preserving_ledger_keeps_5x10_parity() -> None:
    import json
    from collections import Counter
    from ops_scripts.build_qrels_benchmark import ensure_50_query_cohort_preserving_ledger

    repo_root = Path(__file__).resolve().parents[3]
    qdir = repo_root / "data" / "qrels"
    queue = json.loads((qdir / "hitl_qrels_queue.v1.json").read_text(encoding="utf-8"))
    ledger = json.loads((qdir / "qrels_human_label_ledger.v1.json").read_text(encoding="utf-8"))
    pool = json.loads((qdir / "qrels_authentic_candidate_pool.v1.json").read_text(encoding="utf-8"))

    assert len(queue) == 50
    assert Counter(item["batch_index"] for item in queue) == {1: 10, 2: 10, 3: 10, 4: 10, 5: 10}
    assert all(len(item.get("candidates") or []) == 4 for item in queue)

    # Re-running cohort preservation on a truncated pending slice restores exact 50-query (5x10) cohort
    pending_only = [item for item in queue if item.get("status") != "COMPLETED_HUMAN_GRADED"]
    restored, me_report = ensure_50_query_cohort_preserving_ledger(pending_only, ledger, pool)
    assert len(restored) == 50
    assert Counter(item["batch_index"] for item in restored) == {1: 10, 2: 10, 3: 10, 4: 10, 5: 10}
    assert me_report["is_mutually_exclusive"] is True
    assert me_report["blind_negative_probes_interleaved"] == 5
    all_rids = [c["record_id"] for item in restored for c in item["candidates"]]
    assert len(set(all_rids)) == 200


