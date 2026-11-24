#!/usr/bin/env python3
"""DIE-Parity QRELS Batch Grade Recorder, 70/30 Out-of-Sample Kappa Gate & Unclamped 4-Simplex Finalizer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps_eval.qrels.qrels_batch_widget import (  # noqa: E402
    build_batch_artifact_filename,
    compute_batch_fingerprint,
    render_blind_batch_widget_html,
)
from apps_eval.qrels.qrels_blind_grader import (  # noqa: E402
    compute_grader_source_sha256,
    grade_blind_core_statement,
    load_human_label_ledger,
    record_human_batch_grades,
    save_human_label_ledger,
)
from apps_eval.qrels.qrels_calibration_stats import (  # noqa: E402
    compute_bootstrap_kappa_ci95,
    compute_cohens_kappa,
    compute_kappa_receipt_hashes,
    compute_quadratic_weighted_kappa,
    compute_sparse_krippendorffs_alpha,
)
from apps_eval.qrels.weight_calibration import (  # noqa: E402
    CANONICAL_QRELS_RRF_WEIGHTS,
    run_holdout_isolated_weight_calibration,
)
from tools.audit_qrels_coverage import audit_qrels_coverage  # noqa: E402


_BATCH_FP_RE = re.compile(r"^batch\s*(\d+)\s*#\s*([0-9a-f]{8})$", re.IGNORECASE)


def parse_batch_reply_with_tags(
    raw_reply: str,
    queue: Sequence[Mapping[str, Any]],
    batch_index: int,
    *,
    require_fingerprint: bool = False,
) -> tuple[dict[str, dict[str, int | str]], dict[str, dict[str, str]]]:
    """Parse compact batch grades ('0'..'3' or 'Q') plus optional failure tags and fail-closed BATCH#fp check."""
    batch_items = [q for q in queue if int(q.get("batch_index", 0)) == int(batch_index)]
    expected_fp = compute_batch_fingerprint(batch_items, batch_index=batch_index)
    by_qrel = {str(q["qrel_id"]).lower(): str(q["qrel_id"]) for q in batch_items}
    by_qid = {str(q["query_id"]).lower(): str(q["qrel_id"]) for q in batch_items}
    by_local_q = {f"q{i}": str(q["qrel_id"]) for i, q in enumerate(batch_items, start=1)}
    by_global_q = {f"q{int(str(q['qrel_id']).split('-')[-1])}": str(q["qrel_id"]) for q in batch_items}

    parsed: dict[str, dict[str, int | str]] = {}
    parsed_tags: dict[str, dict[str, str]] = {}
    found_fp_header = False
    segments = [s.strip() for s in re.split(r"[|\n]+", str(raw_reply or "")) if s.strip()]
    for seg in segments:
        m_fp = _BATCH_FP_RE.match(seg)
        if m_fp:
            found_fp_header = True
            got_batch = int(m_fp.group(1))
            got_fp = m_fp.group(2).lower()
            if got_batch != int(batch_index) or got_fp != expected_fp:
                raise ValueError(
                    f"STALE_OR_MISMATCHED_BATCH_FINGERPRINT: expected BATCH{batch_index}#{expected_fp}, "
                    f"got BATCH{got_batch}#{got_fp}. Re-open the latest HTML batch artifact before grading."
                )
            continue
        if ":" not in seg:
            continue
        head_raw, rest = seg.split(":", 1)
        head = head_raw.strip().lower()
        qrel_id = by_qrel.get(head) or by_qid.get(head) or by_global_q.get(head) or by_local_q.get(head)
        if not qrel_id:
            continue
        tag_block = ""
        m_tags = re.search(r"\[([^\]]+)\]", rest)
        if m_tags:
            tag_block = m_tags.group(1)
            scores_raw = rest[: m_tags.start()]
        else:
            scores_raw = rest
        slot_map: dict[str, int | str] = {}
        for m in re.finditer(r"([ABCDabcd])\s*=\s*([0-3Qq])", scores_raw):
            val_raw = m.group(2).upper()
            slot_map[m.group(1).upper()] = "Q" if val_raw == "Q" else int(val_raw)
        if set(slot_map.keys()) == {"A", "B", "C", "D"}:
            parsed[qrel_id] = slot_map
            if tag_block:
                t_map: dict[str, str] = {}
                for part in tag_block.split(";"):
                    if ":" in part:
                        s_raw, t_lbl = part.split(":", 1)
                        slot_k = s_raw.strip().upper()
                        if slot_k in {"A", "B", "C", "D"} and t_lbl.strip():
                            t_map[slot_k] = t_lbl.strip()
                if t_map:
                    parsed_tags[qrel_id] = t_map
    if require_fingerprint and not found_fp_header:
        raise ValueError(
            f"MISSING_BATCH_FINGERPRINT: expected leading 'BATCH{batch_index}#{expected_fp}' header."
        )
    if len(parsed) != len(batch_items):
        missing = [str(q["qrel_id"]) for q in batch_items if str(q["qrel_id"]) not in parsed]
        raise ValueError(f"Incomplete batch {batch_index} grades; missing {len(missing)} items: {missing}")
    return parsed, parsed_tags


def parse_batch_reply(raw_reply: str, queue: Sequence[Mapping[str, Any]], batch_index: int) -> dict[str, dict[str, int | str]]:
    """Parse compact batch grades like 'Q1: A=3,B=1,C=0,D=0 | Q2: ...' (supports 'Q' quarantine)."""
    grades, _ = parse_batch_reply_with_tags(raw_reply, queue, batch_index)
    return grades


def cmd_record_batch(repo_root: Path, batch_index: int, reply_text: str) -> dict[str, Any]:
    qdir = repo_root / "data/qrels"
    queue_path = qdir / "hitl_qrels_queue.v1.json"
    ledger_path = qdir / "qrels_human_label_ledger.v1.json"
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    ledger = load_human_label_ledger(ledger_path)

    batch_grades, batch_tags = parse_batch_reply_with_tags(reply_text, queue, batch_index)
    added = record_human_batch_grades(queue, ledger, batch_grades, batch_tags=batch_tags)
    queue_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    save_human_label_ledger(ledger_path, ledger)

    human_vals: list[int] = []
    grader_vals: list[int] = []
    sparse_human: list[int | None] = []
    sparse_grader: list[int | None] = []
    quarantined_count = 0
    for entry in ledger.get("human_graded_queries") or []:
        if str(entry.get("qrel_id")) in batch_grades:
            for rid, hg in (entry.get("record_grades") or {}).items():
                cand = {"record_id": rid, "core_statement": (entry.get("passage_texts") or {}).get(rid, "")}
                bg = grade_blind_core_statement(entry, cand)
                human_vals.append(int(hg))
                grader_vals.append(bg)
                sparse_human.append(int(hg))
                sparse_grader.append(bg)
            for rid in (entry.get("quarantined_records") or {}):
                quarantined_count += 1
                cand = {"record_id": rid, "core_statement": (entry.get("passage_texts") or {}).get(rid, "")}
                sparse_human.append(None)
                sparse_grader.append(grade_blind_core_statement(entry, cand))
    batch_ck = compute_cohens_kappa(human_vals, grader_vals)
    batch_qwk = compute_quadratic_weighted_kappa(human_vals, grader_vals)
    batch_alpha = compute_sparse_krippendorffs_alpha([sparse_human, sparse_grader])
    return {
        "status": "PASS",
        "batch_index": batch_index,
        "queries_recorded": added,
        "quarantined_in_batch": quarantined_count,
        "total_human_queries": ledger["total_human_queries"],
        "total_human_passage_labels": ledger["total_human_passage_labels"],
        "remaining_passage_labels": ledger["remaining_passage_labels_to_collect"],
        "batch_interim_cohens_kappa": batch_ck,
        "batch_interim_qwk": batch_qwk,
        "batch_interim_krippendorff_alpha": batch_alpha,
    }


def finalize_wave2_and_wave3(repo_root: Path) -> dict[str, Any]:
    """Wave 2 + Wave 3: Verify 70/30 out-of-sample Kappa, seal ground truth, run unclamped 4-simplex sweep."""
    qdir = repo_root / "data/qrels"
    pool_path = qdir / "qrels_authentic_candidate_pool.v1.json"
    part_path = qdir / "qrels_partitions.v1.json"
    ledger_path = qdir / "qrels_human_label_ledger.v1.json"
    gt_path = qdir / "qrels_independent_ground_truth.v1.json"
    wt_path = qdir / "qrels_weight_calibration_results.v1.json"

    pool_data = json.loads(pool_path.read_text(encoding="utf-8"))
    part_data = json.loads(part_path.read_text(encoding="utf-8"))
    ledger = load_human_label_ledger(ledger_path)

    grader_sha = compute_grader_source_sha256()
    recorded_sha = str(ledger.get("frozen_blind_grader_sha256") or "")
    grader_immutability_ok = bool(recorded_sha and recorded_sha == grader_sha)

    cal_human: list[int] = []
    cal_grader: list[int] = []
    hold_human: list[int] = []
    hold_grader: list[int] = []
    hold_sparse_human: list[int | None] = []
    hold_sparse_grader: list[int | None] = []
    failure_taxonomy_counts: dict[str, int] = {}
    quarantined_total = 0
    human_grade_lookup: dict[tuple[str, str], int] = {}

    for entry in ledger.get("human_graded_queries") or []:
        qid = str(entry["query_id"])
        role = str(entry.get("split_role") or "grader_calibration_70pct")
        for tag_lbl in (entry.get("failure_tags") or {}).values():
            failure_taxonomy_counts[str(tag_lbl)] = failure_taxonomy_counts.get(str(tag_lbl), 0) + 1
        for rid, hg in (entry.get("record_grades") or {}).items():
            human_grade_lookup[(qid, str(rid))] = int(hg)
            cand = {"record_id": str(rid), "core_statement": (entry.get("passage_texts") or {}).get(str(rid), "")}
            bg = grade_blind_core_statement(entry, cand)
            if role == "human_holdout_30pct":
                hold_human.append(int(hg))
                hold_grader.append(int(bg))
                hold_sparse_human.append(int(hg))
                hold_sparse_grader.append(int(bg))
            else:
                cal_human.append(int(hg))
                cal_grader.append(int(bg))
        for rid in (entry.get("quarantined_records") or {}):
            quarantined_total += 1
            if role == "human_holdout_30pct":
                cand = {"record_id": str(rid), "core_statement": (entry.get("passage_texts") or {}).get(str(rid), "")}
                hold_sparse_human.append(None)
                hold_sparse_grader.append(grade_blind_core_statement(entry, cand))

    all_human = cal_human + hold_human
    all_grader = cal_grader + hold_grader
    hold_ck = compute_cohens_kappa(hold_human, hold_grader)
    hold_qwk = compute_quadratic_weighted_kappa(hold_human, hold_grader)
    hold_alpha = compute_sparse_krippendorffs_alpha([hold_sparse_human, hold_sparse_grader])
    hold_ci_low, hold_ci_high = compute_bootstrap_kappa_ci95(hold_human, hold_grader, n_boot=1000, seed=42)
    cal_ck = compute_cohens_kappa(cal_human, cal_grader)
    cal_qwk = compute_quadratic_weighted_kappa(cal_human, cal_grader)
    all_ck = compute_cohens_kappa(all_human, all_grader)
    all_qwk = compute_quadratic_weighted_kappa(all_human, all_grader)

    evaluated_queries: list[dict[str, Any]] = []
    for q in pool_data.get("queries") or []:
        qid = str(q["query_id"])
        judged_cands: list[dict[str, Any]] = []
        for cand in q.get("candidates") or []:
            rid = str(cand["record_id"])
            if (qid, rid) in human_grade_lookup:
                grade = human_grade_lookup[(qid, rid)]
                source = "human_gold_blind_panel"
            else:
                grade = grade_blind_core_statement(q, cand)
                source = "frozen_blind_core_grader"
            judged_cands.append(
                {
                    "record_id": rid,
                    "grade": grade,
                    "grade_source": source,
                    "fused_rank": cand["fused_rank"],
                    "fused_score": cand["fused_score"],
                    "dense_rank": cand["dense_rank"],
                    "sparse_rank": cand["sparse_rank"],
                    "colbert_rank": cand["colbert_rank"],
                    "bm25_rank": cand["bm25_rank"],
                    "is_verified_target": cand["is_verified_target"],
                }
            )
        evaluated_queries.append(
            {
                "query_id": qid,
                "query_text": q["query_text"],
                "topic_id": q["topic_id"],
                "surface": q["surface"],
                "partition": q["partition"],
                "answerable": q["answerable"],
                "target_record_id": q["target_record_id"],
                "judged_candidates": judged_cands,
            }
        )

    eq_sha, art_sha = compute_kappa_receipt_hashes(evaluated_queries, hold_human, hold_grader, hold_ck, hold_qwk)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gt_payload = {
        "schema_version": "3.0.0",
        "dataset_contract": "urn:agents:qrels:independent-judgments:3.0.0",
        "corpus_digest": pool_data["corpus_digest"],
        "kappa_calibration_receipt": {
            "calibration_protocol": "INV-QRELS-BLIND-ATOMIC-CORE-GRADING",
            "calibrated_at": now_utc,
            "external_api_cost_usd": 0.0,
            "grader_source_sha256": grader_sha,
            "grader_immutability_verified": grader_immutability_ok,
            "total_human_queries": len(ledger.get("human_graded_queries") or []),
            "total_human_passage_labels": len(all_human),
            "calibration_70pct_passages": len(cal_human),
            "calibration_70pct_cohens_kappa": cal_ck,
            "calibration_70pct_qwk": cal_qwk,
            "anchor_passages_evaluated": len(hold_human),
            "human_gold_grades": hold_human,
            "blind_grader_grades": hold_grader,
            "cohens_kappa": hold_ck,
            "quadratic_weighted_kappa": hold_qwk,
            "sparse_krippendorff_alpha": hold_alpha,
            "quarantined_passages_excluded": quarantined_total,
            "failure_taxonomy_counts": failure_taxonomy_counts,
            "kappa_ci95_low": hold_ci_low,
            "kappa_ci95_high": hold_ci_high,
            "all_200_cohens_kappa": all_ck,
            "all_200_qwk": all_qwk,
            "kappa_threshold": 0.80,
            "ci95_lower_threshold": 0.70,
            "evaluated_queries_sha256": eq_sha,
            "artifact_sha256": art_sha,
        },
        "evaluated_queries": evaluated_queries,
    }
    gt_path.write_text(json.dumps(gt_payload, indent=2) + "\n", encoding="utf-8")

    weight_report = run_holdout_isolated_weight_calibration(
        gt_payload,
        part_data,
        canonical_weights=CANONICAL_QRELS_RRF_WEIGHTS,
        output_path=wt_path,
    )
    cov_report = audit_qrels_coverage(
        part_path,
        gt_path,
        pool_path,
        receipt_output_path=repo_root / "reports/qrels_coverage_audit_receipt.json",
        min_total_human_labels=200,
        min_holdout_passages=60,
        ci95_lower_floor=0.70,
        expected_grader_sha256=grader_sha,
    )
    return {
        "status": cov_report["gate_status"],
        "grader_immutability_verified": grader_immutability_ok,
        "total_human_passage_labels": len(all_human),
        "holdout_30pct_passages": len(hold_human),
        "holdout_cohens_kappa": hold_ck,
        "holdout_qwk": hold_qwk,
        "holdout_ci95": [hold_ci_low, hold_ci_high],
        "calibration_70pct_kappa": cal_ck,
        "all_200_kappa": all_ck,
        "weight_verdict": weight_report["verdict"],
        "delta_ndcg_10": weight_report["delta_ndcg_10"],
        "canonical_weights": weight_report["canonical_weights"],
        "optimal_weights": weight_report["optimal_configuration"]["weights"],
        "holdout_eval": weight_report["final_holdout_evaluation"],
        "abstention": weight_report["abstention_calibration"],
        "coverage_failures": cov_report["failures"],
    }


def cmd_bind_studio(repo_root: Path, batch_index: int = 1) -> dict[str, Any]:
    """Bind the active repository QRELS queue and ledger to the centralized core-governance Human Labeling Studio."""
    qdir = repo_root / "data/qrels"
    queue_path = (qdir / "hitl_qrels_queue.v1.json").resolve()
    ledger_path = (qdir / "qrels_human_label_ledger.v1.json").resolve()
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    batch_items = [q for q in queue if int(q.get("batch_index", 0)) == int(batch_index)]
    fp = compute_batch_fingerprint(batch_items, batch_index=batch_index)

    cfg = {
        "mode": "qrels_4up",
        "repo_label": "agents",
        "queue_path": str(queue_path),
        "ledger_path": str(ledger_path),
        "batch_index": int(batch_index),
        "session_sha256": fp,
    }
    plugin_data_dirs = [
        Path.home() / ".gemini/config/plugins/core-governance/.local_data",
        Path.home() / ".gemini/antigravity/plugins/core-governance",
    ]
    written_paths: list[str] = []
    for d in plugin_data_dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
            target = d / "active_session.json"
            target.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
            written_paths.append(str(target))
        except OSError:
            pass
    return {
        "status": "PASS",
        "studio_resource_uri": "ui://labeling-studio/app.html",
        "batch_index": int(batch_index),
        "session_sha256": fp,
        "queue_path": str(queue_path),
        "ledger_path": str(ledger_path),
        "active_session_files": written_paths,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record QRELS human batch grades and run Wave 2-3 calibration")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_bind = sub.add_parser("bind-studio")
    p_bind.add_argument("--batch", type=int, default=1)
    p_rec = sub.add_parser("record-batch")
    p_rec.add_argument("--batch", type=int, required=True)
    p_rec.add_argument("--reply", required=True)
    sub.add_parser("finalize")
    args = parser.parse_args(argv)
    if args.cmd == "bind-studio":
        res = cmd_bind_studio(REPO_ROOT, args.batch)
        print(json.dumps(res, indent=2))
        return 0
    if args.cmd == "record-batch":
        res = cmd_record_batch(REPO_ROOT, args.batch, args.reply)
        print(json.dumps(res, indent=2))
        return 0
    if args.cmd == "finalize":
        res = finalize_wave2_and_wave3(REPO_ROOT)
        print(json.dumps(res, indent=2))
        return 0 if res["status"] == "PASS" else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
