#!/usr/bin/env python3
"""Wave 3 unit & counterfactual suite for `agents` centralized flywheel unification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agents.observability.findings_consolidator import consolidate_all_findings
from agents.persistence.sqlite.findings_queue_store import SqliteFindingsQueueStore
from apps_eval.longitudinal import LongitudinalEvalEntry, LongitudinalEvaluationTracker
from tools.govern_eval_findings import main as govern_main


def test_agents_watermark_reopen_48h_stale_and_two_mode_closeout_cli(tmp_path: Path) -> None:
    q = SqliteFindingsQueueStore(tmp_path / "remediation_queue.sqlite")
    rec = q.upsert_finding(
        source_surface="online_eval",
        app_id="apps_rg",
        failed_gate_signature="groundedness",
        root_cause_bucket="apps_rg_groundedness_defect",
        owner_subsystem="resume_graph_engine",
        track="TRACK_2_CODE_FIX",
        priority="P1",
        title="Resume groundedness miss",
        summary="Failed groundedness",
        recommended_action="Fix citations",
        seen_at_utc="2026-11-20T10:00:00Z",
    )
    fid = rec.finding_id
    q.transition_status(fid, "APPROVED", actor="op", rationale="Approve", now_utc="2026-11-20T12:00:00Z")
    snap = q.export_snapshot(tmp_path / "remediation_queue_snapshot.json", now_utc="2026-11-23T15:00:00Z")
    assert snap["stale_approved_count"] == 1
    assert fid in snap["stale_approved_ids"]
    q.close()

    # Unverified closeout must exit 1 fail-closed
    assert govern_main(["--runtime-root", str(tmp_path), "verify", fid, "--rationale", "No proof yet"]) == 1

    # Mode B: post-approval passing trace in online_eval_ledger.jsonl seals closeout_proof and exits 0
    (tmp_path / "online_eval_ledger.jsonl").write_text(
        json.dumps({"trace_id": "tr-post-ok", "evaluated_at_utc": "2026-11-24T12:00:00Z", "passed": True}) + "\n",
        encoding="utf-8",
    )
    assert govern_main(["--runtime-root", str(tmp_path), "verify", fid, "--rationale", "Verified", "--proof-run-id", "tr-post-ok"]) == 0

    q2 = SqliteFindingsQueueStore(tmp_path / "remediation_queue.sqlite")
    verified_rec = q2.get_finding(fid)
    assert verified_rec is not None and verified_rec.status == "VERIFIED"
    assert verified_rec.metadata["closeout_proof"]["mode"] == "POST_FIX_SURFACE_RUN"

    # Pre-watermark failure stays VERIFIED; post-watermark failure reopens to OPEN
    pre = q2.upsert_finding(
        source_surface="online_eval",
        app_id="apps_rg",
        failed_gate_signature="groundedness",
        root_cause_bucket="apps_rg_groundedness_defect",
        owner_subsystem="resume_graph_engine",
        track="TRACK_2_CODE_FIX",
        priority="P1",
        title="Resume groundedness miss",
        summary="Old row",
        recommended_action="Fix citations",
        seen_at_utc="2026-11-20T11:00:00Z",
    )
    assert pre.status == "VERIFIED"

    post = q2.upsert_finding(
        source_surface="online_eval",
        app_id="apps_rg",
        failed_gate_signature="groundedness",
        root_cause_bucket="apps_rg_groundedness_defect",
        owner_subsystem="resume_graph_engine",
        track="TRACK_2_CODE_FIX",
        priority="P1",
        title="Resume groundedness miss",
        summary="Post-fix regression",
        recommended_action="Fix citations",
        seen_at_utc="2099-01-01T00:00:00Z",
    )
    assert post.status == "OPEN"
    assert any(ev["event_type"] == "REOPENED_POST_WATERMARK" for ev in q2.list_events(fid))
    q2.close()


def test_agents_dual_anchor_baseline_and_tampered_judge_receipt_consolidation(tmp_path: Path) -> None:
    tracker = LongitudinalEvaluationTracker(tmp_path / "longitudinal.json")
    for i, val in enumerate([96.0, 96.0, 95.0, 82.0, 94.0]):
        tracker.record_entry(
            LongitudinalEvalEntry(
                f"pre-{i}", f"2026-11-20T0{i}:00:00Z", "p1", "r1", "apps_rg_suite", "local", "low",
                {"composite": val}, {"g1": val >= 90.0},
            )
        )
    for i in range(5):
        tracker.record_entry(
            LongitudinalEvalEntry(
                f"post-{i}", f"2026-11-22T0{i}:00:00Z", "p2", "r1", "apps_rg_suite", "local", "low",
                {"composite": 95.6}, {"g1": True},
            )
        )
    res = tracker.detect_rolling_window_drift(
        benchmark_suite="apps_rg_suite",
        metric_name="composite",
        active_rubric_version="r1",
        verified_watermark_utc="2026-11-21T00:00:00Z",
    )
    assert res["status"] == "STABLE"
    assert res["baseline_advanced_post_fix"] is True

    # Tampered judge_receipt creates OPEN P0 finding during consolidate_all_findings
    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    rub = src / "external_judge_rubric_v2.json"
    rub.write_text('{"v": 2}', encoding="utf-8")
    (src / "ide_judge_drift_latest.json").write_text(
        json.dumps({
            "run_id": "bad-judge",
            "artifact_sha256": "a" * 64,
            "external_rubric_sha256": hashlib.sha256(rub.read_bytes()).hexdigest(),
            "judge_receipt": "0" * 64,
        }),
        encoding="utf-8",
    )
    summary = consolidate_all_findings(src, out)
    assert summary["ingested_by_surface"]["ide_judge_drift"] == 1
    assert summary["counts_by_status"].get("OPEN", 0) == 1
